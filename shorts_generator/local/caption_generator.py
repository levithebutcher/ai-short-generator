"""CapCut-style ASS caption generator for local shorts generator.

Ported and adapted from jipraks/yt-short-clipper:
- CapCut/TikTok karaoke word-by-word active yellow highlighting (BGR: &H00FFFF&)
- Clean Arial Bold uppercase text with thick black outline (&H00000000, Outline=4, Shadow=2)
- Chunking words into 4-word groups to maximize readability
- Safe vertical positioning (MarginV=400) above YouTube Shorts UI elements
"""
from typing import Any, Dict, List, Optional


def _format_ass_time(seconds: float) -> str:
    """Convert seconds to ASS time format H:MM:SS.cc"""
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centisecs = int(round((seconds % 1) * 100))
    if centisecs >= 100:
        centisecs = 99
    return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"


def create_ass_subtitles(
    segments: List[Dict[str, Any]],
    clip_start: float,
    clip_end: float,
    out_ass_path: str,
    aspect_ratio: str = "9:16",
    chunk_size: int = 4,
) -> bool:
    """Extract words for a subclip and create a CapCut-style ASS karaoke subtitle file.

    Args:
        segments: List of segment dicts (with 'start', 'end', 'text', and optionally 'words').
        clip_start: Start timestamp (in seconds) in the source video.
        clip_end: End timestamp (in seconds) in the source video.
        out_ass_path: File path to write the .ass subtitle.
        aspect_ratio: Video aspect ratio ('9:16', '1:1', etc.) to tune font size & safe margins.
        chunk_size: Number of words displayed per subtitle line.

    Returns:
        True if subtitles were generated and written, False if no words found.
    """
    clip_dur = clip_end - clip_start
    if clip_dur <= 0:
        return False

    clip_words: List[Dict[str, Any]] = []

    for seg in segments:
        s_start = float(seg.get("start", 0.0))
        s_end = float(seg.get("end", 0.0))
        if s_end <= clip_start or s_start >= clip_end:
            continue

        words_data = seg.get("words")
        if words_data:
            for w in words_data:
                w_text = str(w.get("word", "")).strip()
                w_start = float(w.get("start", s_start))
                w_end = float(w.get("end", s_end))
                if not w_text or w_end <= clip_start or w_start >= clip_end:
                    continue
                clip_words.append({
                    "word": w_text,
                    "start": max(0.0, w_start - clip_start),
                    "end": min(clip_dur, w_end - clip_start),
                })
        else:
            text = str(seg.get("text", "")).strip()
            if not text:
                continue
            tokens = text.split()
            if not tokens:
                continue
            seg_dur = max(0.1, s_end - s_start)
            word_dur = seg_dur / len(tokens)
            for idx, token in enumerate(tokens):
                w_start = s_start + idx * word_dur
                w_end = s_start + (idx + 1) * word_dur
                if w_end <= clip_start or w_start >= clip_end:
                    continue
                clip_words.append({
                    "word": token,
                    "start": max(0.0, w_start - clip_start),
                    "end": min(clip_dur, w_end - clip_start),
                })

    if not clip_words:
        return False

    clip_words.sort(key=lambda x: x["start"])

    # Ensure valid monotonically increasing non-zero word intervals
    for i in range(len(clip_words)):
        if clip_words[i]["end"] <= clip_words[i]["start"]:
            clip_words[i]["end"] = clip_words[i]["start"] + 0.1

    # Configure canvas resolution & margins based on aspect ratio
    if aspect_ratio == "9:16":
        play_res_x = 1080
        play_res_y = 1920
        font_size = 65
        margin_v = 400
    elif aspect_ratio == "1:1":
        play_res_x = 1080
        play_res_y = 1080
        font_size = 48
        margin_v = 160
    else:
        # Default horizontal / landscape
        play_res_x = 1920
        play_res_y = 1080
        font_size = 52
        margin_v = 120

    ass_content = f"""[Script Info]
Title: Auto-generated captions
ScriptType: v4.00+
WrapStyle: 0
PlayResX: {play_res_x}
PlayResY: {play_res_y}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,50,50,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events: List[Dict[str, str]] = []

    # Chunk words into groups of `chunk_size`
    for i in range(0, len(clip_words), chunk_size):
        chunk = clip_words[i:i + chunk_size]
        if not chunk:
            continue

        for j, cur in enumerate(chunk):
            word_start = cur["start"]
            # Smooth end boundary to prevent flicker between words in the same phrase
            if j < len(chunk) - 1:
                next_start = chunk[j + 1]["start"]
                word_end = max(cur["end"], next_start)
            else:
                word_end = cur["end"]

            if word_end <= word_start:
                word_end = word_start + 0.1

            text_parts = []
            for k, w in enumerate(chunk):
                word_text = w["word"].strip().upper().replace("{", "").replace("}", "")
                if k == j:
                    # Yellow highlight for current active word (BGR: &H00FFFF&)
                    text_parts.append(f"{{\\c&H00FFFF&}}{word_text}{{\\c&HFFFFFF&}}")
                else:
                    text_parts.append(word_text)

            line_text = " ".join(text_parts)
            events.append({
                "start": _format_ass_time(word_start),
                "end": _format_ass_time(word_end),
                "text": line_text,
            })

    if not events:
        return False

    for ev in events:
        ass_content += f"Dialogue: 0,{ev['start']},{ev['end']},Default,,0,0,0,,{ev['text']}\n"

    with open(out_ass_path, "w", encoding="utf-8") as f:
        f.write(ass_content)

    return True
