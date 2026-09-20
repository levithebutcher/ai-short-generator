"""Smart Silence Removal & Jump-Cut Module.

Inspired by misbakhul29/clipper and auto-editor:
- Detects audio silence and dead pauses (> 0.6s below -35dB).
- Tightens video pacing by micro-trimming awkward pauses.
- Applies EBU R128 audio loudness normalization (loudnorm) so speech is loud and clear on mobile devices.
"""
import subprocess
from pathlib import Path
from typing import Optional


def get_audio_loudnorm_filter() -> str:
    """Return standard EBU R128 broadcast loudness normalization filter."""
    return "loudnorm=I=-16:TP=-1.5:LRA=11"


def remove_silence(
    in_video_path: str,
    out_video_path: str,
    min_silence_sec: float = 0.6,
    silence_thresh_db: int = -35,
    normalize_audio: bool = True,
) -> bool:
    """Apply FFmpeg silenceremove filter to eliminate awkward silent gaps.

    Args:
        in_video_path: Source input video.
        out_video_path: Destination trimmed video.
        min_silence_sec: Minimum duration in seconds to consider silence.
        silence_thresh_db: Audio dB threshold for silence (default -35dB).
        normalize_audio: Whether to chain EBU R128 loudnorm filter.

    Returns:
        True if processed successfully, False otherwise.
    """
    af_filters = [
        f"silenceremove=stop_periods=-1:stop_duration={min_silence_sec}:stop_threshold={silence_thresh_db}dB:leave_silence=0.08"
    ]
    if normalize_audio:
        af_filters.append(get_audio_loudnorm_filter())

    af_chain = ",".join(af_filters)

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", in_video_path,
        "-af", af_chain,
        "-c:v", "copy",
        out_video_path,
    ]

    try:
        subprocess.run(cmd, check=True)
        return Path(out_video_path).exists()
    except Exception as e:
        print(f"[silence_remover] warning: {e}", flush=True)
        return False
