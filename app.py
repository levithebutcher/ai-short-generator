"""FastAPI web dashboard server for AI YouTube Shorts Generator.

Provides:
- Interactive web dashboard (web/index.html)
- Real-time Server-Sent Events (SSE) progress streaming
- Video streaming & download API
- Background job processing
"""
import asyncio
import glob
import json
import os
import sys
import threading
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

# Ensure repository root is on sys.path
_repo_dir = str(Path(__file__).resolve().parent)
if _repo_dir not in sys.path:
    sys.path.insert(0, _repo_dir)

from shorts_generator.config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    LLM_PROVIDER,
    LOCAL_OUTPUT_DIR,
    LOCAL_WHISPER_DEVICE,
    LOCAL_WHISPER_MODEL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
)
from shorts_generator.pipeline import generate_shorts

app = FastAPI(title="AI YouTube Shorts Generator - Local Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for active jobs
jobs: Dict[str, Dict[str, Any]] = {}
job_event_queues: Dict[str, List[asyncio.Queue]] = {}


class GenerateRequest(BaseModel):
    url: str
    num_clips: int = 3
    aspect_ratio: str = "9:16"
    download_format: str = "720"
    language: Optional[str] = None


def _broadcast_event(job_id: str, event_data: Dict[str, Any]) -> None:
    """Broadcast progress event to all connected SSE clients for this job."""
    queues = job_event_queues.get(job_id, [])
    for q in queues:
        try:
            q.put_nowait(event_data)
        except Exception:
            pass


def _run_job_worker(job_id: str, req: GenerateRequest, loop: asyncio.AbstractEventLoop) -> None:
    job = jobs[job_id]
    job["status"] = "running"
    job["started_at"] = time.time()

    def _safe_broadcast(payload: Dict[str, Any]):
        if not loop.is_closed():
            try:
                loop.call_soon_threadsafe(_broadcast_event, job_id, payload)
            except RuntimeError:
                pass

    def progress_callback(step: str, percent: int, message: str, data: Optional[Dict] = None):
        job["step"] = step
        job["percent"] = percent
        job["message"] = message
        log_entry = f"[{time.strftime('%H:%M:%S')}] [{step.upper()}] {message}"
        job["logs"].append(log_entry)
        if data and "shorts" in data:
            job["result"] = data

        payload = {
            "type": "progress",
            "job_id": job_id,
            "step": step,
            "percent": percent,
            "message": message,
            "log": log_entry,
            "data": data,
        }
        _safe_broadcast(payload)

    try:
        progress_callback("start", 5, f"Starting generation for: {req.url}")
        result = generate_shorts(
            req.url,
            num_clips=req.num_clips,
            aspect_ratio=req.aspect_ratio,
            download_format=req.download_format,
            language=req.language,
            mode="local",
            progress_callback=progress_callback,
        )
        job["status"] = "completed"
        job["percent"] = 100
        job["result"] = result
        final_payload = {
            "type": "completed",
            "job_id": job_id,
            "percent": 100,
            "message": f"Successfully created {len(result.get('shorts', []))} shorts!",
            "result": result,
        }
        _safe_broadcast(final_payload)
    except Exception as e:
        err_msg = str(e)
        job["status"] = "failed"
        job["error"] = err_msg
        log_entry = f"[{time.strftime('%H:%M:%S')}] [ERROR] {err_msg}"
        job["logs"].append(log_entry)
        err_payload = {
            "type": "failed",
            "job_id": job_id,
            "error": err_msg,
            "log": log_entry,
        }
        _safe_broadcast(err_payload)


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = Path(_repo_dir) / "web" / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend web/index.html not found")
    return index_path.read_text(encoding="utf-8")


@app.get("/api/config")
async def get_config():
    """Return system configuration and capabilities."""
    return {
        "llm_provider": LLM_PROVIDER,
        "gemini_model": GEMINI_MODEL,
        "gemini_ready": bool(GEMINI_API_KEY),
        "openai_model": OPENAI_MODEL,
        "openai_ready": bool(OPENAI_API_KEY),
        "whisper_model": LOCAL_WHISPER_MODEL,
        "whisper_device": LOCAL_WHISPER_DEVICE,
        "output_dir": LOCAL_OUTPUT_DIR,
    }


@app.post("/api/generate")
async def start_generation(req: GenerateRequest):
    """Start a background generation job."""
    if not req.url or not req.url.strip():
        raise HTTPException(status_code=400, detail="Video URL or path is required.")

    job_id = f"job_{int(time.time() * 1000)}"
    jobs[job_id] = {
        "id": job_id,
        "url": req.url.strip(),
        "status": "queued",
        "step": "queued",
        "percent": 0,
        "message": "Queued in worker...",
        "logs": [f"[{time.strftime('%H:%M:%S')}] Job created: {req.url}"],
        "result": None,
        "error": None,
        "created_at": time.time(),
    }
    job_event_queues[job_id] = []

    loop = asyncio.get_running_loop()
    worker_thread = threading.Thread(
        target=_run_job_worker,
        args=(job_id, req, loop),
        daemon=True,
    )
    worker_thread.start()

    return {"job_id": job_id, "status": "started"}


@app.get("/api/progress/{job_id}")
async def stream_progress(job_id: str, request: Request):
    """SSE endpoint to stream real-time progress for a given job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    queue: asyncio.Queue = asyncio.Queue()
    if job_id not in job_event_queues:
        job_event_queues[job_id] = []
    job_event_queues[job_id].append(queue)

    async def event_generator():
        # Send initial snapshot
        initial_event = {
            "type": "snapshot",
            "job_id": job_id,
            "status": job["status"],
            "step": job["step"],
            "percent": job["percent"],
            "message": job["message"],
            "logs": job["logs"],
            "result": job.get("result"),
        }
        yield f"data: {json.dumps(initial_event)}\n\n"

        if job["status"] in ("completed", "failed"):
            return

        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event_data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(event_data)}\n\n"
                    if event_data.get("type") in ("completed", "failed"):
                        break
                except asyncio.TimeoutError:
                    # Keep-alive heartbeat
                    yield ": ping\n\n"
        finally:
            if job_id in job_event_queues and queue in job_event_queues[job_id]:
                job_event_queues[job_id].remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/shorts")
async def list_shorts():
    """List all available shorts in the output directory with metadata."""
    out_dir = Path(LOCAL_OUTPUT_DIR)
    if not out_dir.exists():
        return []

    shorts_files = sorted(out_dir.glob("short_*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    results = []

    # Attempt to load cached highlights for rich metadata
    highlights_map = {}
    for hf in out_dir.glob("*_highlights.json"):
        try:
            with open(hf, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for idx, h in enumerate(data, 1):
                        highlights_map[f"short_{idx:02d}.mp4"] = h
        except Exception:
            pass

    for f in shorts_files:
        st = f.stat()
        meta = highlights_map.get(f.name, {})
        results.append({
            "filename": f.name,
            "title": meta.get("title", f.stem.replace("_", " ").title()),
            "score": meta.get("score", 85),
            "hook": meta.get("hook_sentence", ""),
            "reason": meta.get("virality_reason", ""),
            "start_time": meta.get("start_time"),
            "end_time": meta.get("end_time"),
            "file_size": st.st_size,
            "file_size_human": f"{st.st_size / (1024 * 1024):.1f} MB",
            "mtime": st.st_mtime,
            "video_url": f"/api/video/{f.name}",
            "download_url": f"/api/video/{f.name}?download=1",
        })

    return results


@app.get("/api/video/{filename}")
async def get_video(filename: str, download: int = Query(0)):
    """Stream or download a generated short video."""
    video_path = Path(LOCAL_OUTPUT_DIR) / filename
    if not video_path.exists() or not video_path.is_file():
        raise HTTPException(status_code=404, detail="Video file not found")

    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'

    return FileResponse(
        str(video_path),
        media_type="video/mp4",
        headers=headers,
    )


def start_server(host: str = "127.0.0.1", port: int = 8000, open_browser: bool = True):
    """Launch the FastAPI server using Uvicorn."""
    import uvicorn
    import webbrowser

    url = f"http://{host}:{port}"
    print(f"\n=======================================================")
    print(f"  AI YouTube Shorts Generator - Web Dashboard")
    print(f"  Live at: {url}")
    print(f"=======================================================\n")

    if open_browser:
        def _open():
            time.sleep(1.2)
            webbrowser.open(url)
        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    start_server(open_browser=True)
