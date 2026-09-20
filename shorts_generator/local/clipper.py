"""Local clipping: ffmpeg subclip + OpenCV face-aware vertical crop.

Two stages per highlight:
  1. Cut the source video to [start, end] with ffmpeg (re-encoded, audio kept).
  2. Reframe the cut to the target aspect ratio. For 9:16 we slide a vertical
     window horizontally across the frame to keep faces centred (Haar
     cascade — same approach as the original repo, no external models).
"""
import gc
import os
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..config import LOCAL_OUTPUT_DIR
from .caption_generator import create_ass_subtitles


def _safe_remove(path: str, retries: int = 5, delay: float = 0.5) -> None:
    """Safely remove a file, retrying if Windows still holds a lock on it."""
    for _ in range(retries):
        try:
            if os.path.exists(path):
                os.remove(path)
            return
        except PermissionError:
            gc.collect()
            time.sleep(delay)
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _format_srt_time(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _build_clip_srt(
    segments: List[Dict],
    clip_start: float,
    clip_end: float,
    out_srt_path: str,
    max_words_per_line: int = 5,
) -> bool:
    """Extract and shift transcript segments for a clip, writing a formatted SRT file."""
    lines = []
    idx = 1
    for s in segments:
        s_start = float(s.get("start", 0.0))
        s_end = float(s.get("end", 0.0))
        text = str(s.get("text", "")).strip()
        if not text or s_end <= clip_start or s_start >= clip_end:
            continue

        rel_start = max(0.0, s_start - clip_start)
        rel_end = min(clip_end - clip_start, s_end - clip_start)
        if rel_end <= rel_start:
            continue

        words = text.split()
        if len(words) <= max_words_per_line:
            sub_chunks = [(rel_start, rel_end, text)]
        else:
            sub_chunks = []
            dur_per_word = (rel_end - rel_start) / max(1, len(words))
            cur_words = []
            cur_start = rel_start
            for w_idx, w in enumerate(words):
                cur_words.append(w)
                if len(cur_words) >= max_words_per_line or w_idx == len(words) - 1:
                    cur_end = rel_start + (w_idx + 1) * dur_per_word
                    sub_chunks.append((cur_start, cur_end, " ".join(cur_words)))
                    cur_start = cur_end
                    cur_words = []

        for c_start, c_end, c_text in sub_chunks:
            if c_end <= c_start:
                continue
            lines.append(str(idx))
            lines.append(f"{_format_srt_time(c_start)} --> {_format_srt_time(c_end)}")
            lines.append(c_text)
            lines.append("")
            idx += 1

    if not lines:
        return False

    with open(out_srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return True


def _ratio(aspect_ratio: str) -> float:
    """Parse '9:16' → 9/16, '1:1' → 1.0."""
    try:
        w, h = aspect_ratio.split(":")
        return float(w) / float(h)
    except (ValueError, ZeroDivisionError):
        return 9.0 / 16.0


def _cut_subclip(source_path: str, start: float, end: float, out_path: str) -> str:
    """ffmpeg -ss start -to end → re-encoded mp4 with audio."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", source_path,
        "-ss", f"{start:.3f}",
        "-to", f"{end:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        out_path,
    ]
    subprocess.run(cmd, check=True)
    return out_path


def _reframe_vertical(
    in_path: str,
    out_path: str,
    aspect_ratio: str,
    subtitle_ass_path: Optional[str] = None,
    broll_overlays: Optional[List[Dict[str, Any]]] = None,
    turbo_mode: bool = True,
) -> str:
    """Crop video with 10x adaptive face tracking and single-pass FFmpeg rawvideo pipe."""
    try:
        import cv2  # type: ignore
        import imageio_ffmpeg
        ff = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as e:
        raise RuntimeError(
            "opencv-python and imageio-ffmpeg are required for local clipping."
        ) from e

    target_ratio = _ratio(aspect_ratio)
    cap = cv2.VideoCapture(in_path)
    if not cap.isOpened():
        raise RuntimeError(f"could not open {in_path}")

    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    # Compute target crop dimensions
    if target_ratio < src_w / src_h:
        crop_h = src_h
        crop_w = int(crop_h * target_ratio)
    else:
        crop_w = src_w
        crop_h = int(crop_w / target_ratio)
    crop_w = max(2, crop_w - (crop_w % 2))
    crop_h = max(2, crop_h - (crop_h % 2))

    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

    # Assemble single-pass FFmpeg command
    cmd = [
        ff, "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "bgr24",
        "-s", f"{crop_w}x{crop_h}",
        "-r", str(fps),
        "-i", "-",        # Input 0: piped frames from OpenCV
        "-i", in_path,    # Input 1: source audio
    ]

    # Prepare B-Roll overlays
    from .broll_engine import build_ffmpeg_broll_filters
    broll_inputs, broll_filter_str = build_ffmpeg_broll_filters(
        broll_overlays or [],
        canvas_w=crop_w,
        canvas_h=crop_h,
    )
    cmd.extend(broll_inputs)

    filter_chains = []
    current_v = "0:v"

    if broll_filter_str:
        filter_chains.append(broll_filter_str)
        current_v = f"v_broll{len(broll_overlays or [])}"

    if subtitle_ass_path and os.path.exists(subtitle_ass_path):
        escaped_ass = subtitle_ass_path.replace("\\", "/").replace(":", "\\:")
        filter_chains.append(f"[{current_v}]ass='{escaped_ass}'[v_out]")
        current_v = "v_out"

    if filter_chains:
        cmd.extend(["-filter_complex", ";".join(filter_chains), "-map", f"[{current_v}]"])
    else:
        cmd.extend(["-map", "0:v"])

    # Output encoding with mobile loudness normalization
    cmd.extend([
        "-map", "1:a:0?",
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        out_path,
    ])

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    # Adaptive face detection sampling (every 10 frames in turbo mode)
    sample_interval = 10 if turbo_mode else 5
    frame_idx = 0
    last_center: Optional[Tuple[int, int]] = None
    smoothing = 0.15

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % sample_interval == 0:
                try:
                    # 50% downsample for 4x faster face detection
                    small_gray = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (0, 0), fx=0.5, fy=0.5)
                    faces = face_cascade.detectMultiScale(small_gray, scaleFactor=1.15, minNeighbors=4, minSize=(25, 25))
                    if len(faces) > 0:
                        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                        cx = int((x + w // 2) * 2)
                        cy = int((y + h // 2) * 2)
                        if last_center is None:
                            last_center = (cx, cy)
                        else:
                            lx, ly = last_center
                            last_center = (
                                int(lx + (cx - lx) * smoothing),
                                int(ly + (cy - ly) * smoothing),
                            )
                except Exception:
                    pass

            if last_center is None:
                last_center = (src_w // 2, src_h // 2)

            cx, cy = last_center
            x0 = max(0, min(src_w - crop_w, cx - crop_w // 2))
            y0 = max(0, min(src_h - crop_h, cy - crop_h // 2))
            x0 = x0 - (x0 % 2)
            y0 = y0 - (y0 % 2)
            cropped = np.ascontiguousarray(frame[y0:y0 + crop_h, x0:x0 + crop_w])

            try:
                proc.stdin.write(cropped.tobytes())
            except (BrokenPipeError, OSError):
                break

            frame_idx += 1
    finally:
        cap.release()
        try:
            if proc.stdin:
                proc.stdin.close()
            proc.wait()
        except Exception:
            pass

    return out_path


def crop_clip_local(
    source_path: str,
    start_time: float,
    end_time: float,
    aspect_ratio: str,
    out_path: str,
    transcript: Optional[Dict] = None,
    caption_style: str = "hormozi",
    enable_broll: bool = True,
    enable_hook_header: bool = True,
    hook_title: Optional[str] = None,
    turbo_mode: bool = True,
) -> str:
    """Cut + reframe one highlight with burned captions & B-roll overlays in a single fast pass."""
    cut_path = out_path + ".cut.mp4"
    sub_path = out_path + ".sub.ass"
    has_sub = False

    if transcript and "segments" in transcript:
        has_sub = create_ass_subtitles(
            transcript["segments"],
            start_time,
            end_time,
            sub_path,
            aspect_ratio=aspect_ratio,
            caption_style=caption_style,
            hook_title=hook_title if enable_hook_header else None,
        )

    broll_overlays: List[Dict[str, Any]] = []
    if enable_broll and transcript and "segments" in transcript:
        try:
            from .broll_engine import extract_visual_keywords, get_or_fetch_stock_image
            keywords_data = extract_visual_keywords(transcript["segments"], start_time, end_time, max_items=2)
            for kw_item in keywords_data:
                badge_path = get_or_fetch_stock_image(kw_item["keyword"])
                if badge_path and os.path.exists(badge_path):
                    broll_overlays.append({
                        "image_path": badge_path,
                        "start": kw_item["start"],
                        "end": kw_item["end"],
                    })
        except Exception as e:
            print(f"[clip/local] b-roll fetch error: {e}", flush=True)

    try:
        _cut_subclip(source_path, start_time, end_time, cut_path)
        _reframe_vertical(
            cut_path,
            out_path,
            aspect_ratio,
            subtitle_ass_path=sub_path if has_sub else None,
            broll_overlays=broll_overlays,
            turbo_mode=turbo_mode,
        )
    finally:
        _safe_remove(cut_path)
        if has_sub:
            _safe_remove(sub_path)
    return out_path


def crop_highlights_local(
    source_path: str,
    highlights: List[Dict],
    aspect_ratio: str = "9:16",
    out_dir: Optional[str] = None,
    transcript: Optional[Dict] = None,
    on_progress: Optional[Any] = None,
    caption_style: str = "hormozi",
    enable_broll: bool = True,
    enable_hook_header: bool = True,
    turbo_mode: bool = True,
) -> List[Dict]:
    out_dir = out_dir or LOCAL_OUTPUT_DIR
    os.makedirs(out_dir, exist_ok=True)

    if transcript is None:
        try:
            from .transcriber import _load_srt_cache, _transcript_cache_path
            cache_file = _transcript_cache_path(source_path)
            if cache_file.exists():
                transcript = _load_srt_cache(cache_file)
        except Exception:
            pass

    results: List[Dict] = []
    for i, h in enumerate(highlights, 1):
        out_path = os.path.join(out_dir, f"short_{i:02d}.mp4")
        title = h.get('title', f'Clip {i}')
        print(f"[clip/local] {i}/{len(highlights)}: {title}", flush=True)
        if on_progress:
            try:
                on_progress(i, len(highlights), title)
            except Exception:
                pass
        try:
            crop_clip_local(
                source_path,
                float(h["start_time"]),
                float(h["end_time"]),
                aspect_ratio,
                out_path,
                transcript=transcript,
                caption_style=caption_style,
                enable_broll=enable_broll,
                enable_hook_header=enable_hook_header,
                hook_title=title,
                turbo_mode=turbo_mode,
            )
            results.append({**h, "clip_url": out_path})
        except Exception as e:
            print(f"[clip/local] {i} failed: {e}", flush=True)
            results.append({**h, "clip_url": None, "error": str(e)})
    return results
