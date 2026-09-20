"""End-to-end orchestrator.

Two modes:
  * mode="api"   (default) — MuAPI does download / transcribe / LLM / autocrop.
                              Fast, no local deps, pay-per-call.
  * mode="local"            — yt-dlp + faster-whisper + OpenAI or Gemini + ffmpeg/opencv.
                              Self-hosted, LLM_PROVIDER selects OpenAI or Gemini.
"""
from typing import Any, Dict, List, Optional

from .clipper import crop_highlights
from .downloader import download_youtube
from .highlights import call_muapi_llm, get_highlights
from .transcriber import transcribe


def _run_local(
    youtube_url: str,
    num_clips: int,
    aspect_ratio: str,
    download_format: str,
    language: Optional[str],
    progress_callback: Optional[Any] = None,
    caption_style: str = "hormozi",
    enable_broll: bool = True,
    enable_hook_header: bool = True,
    turbo_mode: bool = True,
) -> Dict:
    from .local.clipper import crop_highlights_local
    from .local.downloader import download_youtube_local
    from .local.llm import call_local_llm
    from .local.transcriber import transcribe_local

    def _report(step: str, percent: int, msg: str, data: Optional[Dict] = None):
        if progress_callback:
            try:
                progress_callback(step, percent, msg, data)
            except Exception:
                pass

    _report("download", 10, "Fetching source video...")
    source_path = download_youtube_local(youtube_url, fmt=download_format)
    import os
    _report("download", 25, f"Source video ready: {os.path.basename(source_path)}")

    _report("transcribe", 30, "Transcribing audio with faster-whisper (turbo mode)...")
    transcript = transcribe_local(source_path, language=language)
    if not transcript["segments"]:
        raise RuntimeError(
            "Whisper produced no segments. The video may have no detectable speech."
        )
    _report("transcribe", 50, f"Transcription complete ({len(transcript['segments'])} segments)")

    _report("analyze", 55, "Analyzing virality & selecting highlights with AI...")
    import json
    from pathlib import Path
    from .config import LOCAL_OUTPUT_DIR

    highlights_cache = os.path.join(LOCAL_OUTPUT_DIR, Path(source_path).stem + "_highlights.json")
    if os.path.exists(highlights_cache):
        print(f"[highlights/local] reusing cached highlights: {highlights_cache}", flush=True)
        with open(highlights_cache, "r", encoding="utf-8") as f:
            all_highlights = json.load(f)
    else:
        highlights_result = get_highlights(transcript, num_clips=num_clips, llm_fn=call_local_llm)
        all_highlights: List[Dict] = highlights_result.get("highlights", [])
        if not all_highlights:
            raise RuntimeError("Highlight generator returned zero clips.")
        try:
            with open(highlights_cache, "w", encoding="utf-8") as f:
                json.dump(all_highlights, f, indent=2)
        except Exception:
            pass

    top = sorted(all_highlights, key=lambda h: int(h.get("score", 0)), reverse=True)[:num_clips]
    _report("analyze", 65, f"Selected top {len(top)} viral highlights")
    print(f"[pipeline/local] cropping {len(top)} candidates (style: {caption_style}, broll: {enable_broll}, turbo: {turbo_mode})", flush=True)

    def _on_render_clip(current: int, total: int, title: str):
        pct = 65 + int(((current - 1) / max(1, total)) * 30)
        _report("render", pct, f"Rendering Short {current}/{total}: {title}")

    shorts = crop_highlights_local(
        source_path,
        top,
        aspect_ratio=aspect_ratio,
        transcript=transcript,
        on_progress=_on_render_clip,
        caption_style=caption_style,
        enable_broll=enable_broll,
        enable_hook_header=enable_hook_header,
        turbo_mode=turbo_mode,
    )

    result = {
        "mode": "local",
        "source_video_url": source_path,
        "transcript": transcript,
        "highlights": all_highlights,
        "shorts": shorts,
    }
    _report("completed", 100, f"Generated {len(shorts)} shorts successfully!", result)
    return result


def _run_api(
    youtube_url: str,
    num_clips: int,
    aspect_ratio: str,
    download_format: str,
    language: Optional[str],
) -> Dict:
    source_url = download_youtube(youtube_url, fmt=download_format)

    transcript = transcribe(source_url, language=language)
    if not transcript["segments"]:
        raise RuntimeError(
            "Whisper produced no segments. The video may have no detectable speech."
        )

    highlights_result = get_highlights(transcript, num_clips=num_clips, llm_fn=call_muapi_llm)
    all_highlights: List[Dict] = highlights_result.get("highlights", [])
    if not all_highlights:
        raise RuntimeError("Highlight generator returned zero clips.")

    top = sorted(all_highlights, key=lambda h: int(h.get("score", 0)), reverse=True)[:num_clips]
    print(f"[pipeline] cropping {len(top)} of {len(all_highlights)} candidates", flush=True)

    shorts = crop_highlights(source_url, top, aspect_ratio=aspect_ratio)

    return {
        "mode": "api",
        "source_video_url": source_url,
        "transcript": transcript,
        "highlights": all_highlights,
        "shorts": shorts,
    }


def generate_shorts(
    youtube_url: str,
    num_clips: int = 3,
    aspect_ratio: str = "9:16",
    download_format: str = "720",
    language: Optional[str] = None,
    mode: str = "api",
    progress_callback: Optional[Any] = None,
    caption_style: str = "hormozi",
    enable_broll: bool = True,
    enable_hook_header: bool = True,
    turbo_mode: bool = True,
) -> Dict:
    """Run the full pipeline and return a structured result.

    Args:
        youtube_url: source URL.
        num_clips: how many shorts to render.
        aspect_ratio: e.g. "9:16", "1:1".
        download_format: source resolution ("360" / "480" / "720" / "1080").
        language: ISO-639-1 to force Whisper language detection.
        mode: "api" (default, MuAPI) or "local" (yt-dlp + faster-whisper +
            OpenAI or Gemini + ffmpeg).
        progress_callback: Optional callback fn(step, percent, message, data).
        caption_style: One of 'hormozi', 'mrbeast', 'bounce', 'karaoke', 'minimal', 'classic'.
        enable_broll: Auto-insert contextual stock images/stickers for spoken objects/products.
        enable_hook_header: Display attention-grabbing hook headline bar at the top.
        turbo_mode: 10x faster frame-sampled face tracking & fast encoding.

    Returns:
        {
          "mode": "api" | "local",
          "source_video_url": str,   # hosted URL (api) or local path (local)
          "transcript": {...},
          "highlights": [...],       # all candidates ranked
          "shorts": [...],           # top `num_clips` with clip_url / local path
        }
    """
    mode = (mode or "api").lower()
    if mode == "local":
        return _run_local(
            youtube_url,
            num_clips,
            aspect_ratio,
            download_format,
            language,
            progress_callback=progress_callback,
            caption_style=caption_style,
            enable_broll=enable_broll,
            enable_hook_header=enable_hook_header,
            turbo_mode=turbo_mode,
        )
    if mode == "api":
        return _run_api(youtube_url, num_clips, aspect_ratio, download_format, language)
    raise ValueError(f"Unknown mode: {mode!r}. Use 'api' or 'local'.")
