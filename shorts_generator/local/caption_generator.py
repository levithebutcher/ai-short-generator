"""Advanced ASS caption generator inspired by nicolaigaina/ai-video-captions and jipraks/yt-short-clipper.

Supports 6 viral styles:
- hormozi: Bold uppercase, heavy black outline, active yellow highlight + green for numbers/money.
- mrbeast: Heavy punchy text, electric cyan/yellow pop colors, 2-word bursts.
- bounce: Kinetic scale pop (125% -> 100%) as each word is spoken.
- karaoke: CapCut/TikTok smooth word-by-word progressive highlight.
- minimal: Clean modern sans-serif with subtle shadow and natural capitalization.
- classic: Bounded opaque black box background with high legibility.

Features:
- Windows font fallback support (Nirmala UI for Hindi/Devanagari, Arial Black / Montserrat for bold).
- Word-level synchronization from faster-whisper.
- Safe vertical margins tuned for YouTube Shorts / Reels / TikTok UI overlays.
"""
import re
from typing import Any, Dict, List, Optional


# Style Definitions inspired by nicolaigaina/ai-video-captions
CAPTION_STYLES: Dict[str, Dict[str, Any]] = {
    "hormozi": {
        "name": "Hormozi",
        "description": "Alex Hormozi signature style: bold uppercase, heavy outline, active yellow highlight & green numbers",
        "font": "Arial Black",
        "font_size_9_16": 68,
        "primary_color": "&H00FFFFFF&",    # Pure White
        "highlight_color": "&H0000FFFF&",  # Bright Yellow (BGR)
        "number_color": "&H0000FF00&",     # Bright Green for money/numbers
        "outline_color": "&H00000000&",    # Black
        "back_color": "&H80000000&",
        "outline": 5,
        "shadow": 2,
        "border_style": 1,
        "chunk_size": 3,
        "uppercase": True,
        "bounce": False,
        "margin_v_9_16": 420,
    },
    "mrbeast": {
        "name": "MrBeast",
        "description": "High-energy pop style: punchy electric cyan active words, thick black border, rapid 2-word bursts",
        "font": "Arial Black",
        "font_size_9_16": 72,
        "primary_color": "&H00FFFFFF&",
        "highlight_color": "&H00FFFF00&",  # Electric Cyan/Blue (BGR)
        "number_color": "&H0000FFFF&",     # Bright Yellow
        "outline_color": "&H00000000&",
        "back_color": "&H00000000&",
        "outline": 6,
        "shadow": 0,
        "border_style": 1,
        "chunk_size": 2,
        "uppercase": True,
        "bounce": False,
        "margin_v_9_16": 420,
    },
    "bounce": {
        "name": "Bounce",
        "description": "Kinetic pop-in animation: active word pops up 125% and snaps back smoothly",
        "font": "Arial Black",
        "font_size_9_16": 66,
        "primary_color": "&H00FFFFFF&",
        "highlight_color": "&H0000FFFF&",  # Bright Yellow
        "number_color": "&H0000FF00&",     # Green
        "outline_color": "&H00000000&",
        "back_color": "&H80000000&",
        "outline": 5,
        "shadow": 2,
        "border_style": 1,
        "chunk_size": 3,
        "uppercase": True,
        "bounce": True,
        "margin_v_9_16": 420,
    },
    "karaoke": {
        "name": "Karaoke",
        "description": "CapCut classic karaoke: smooth progressive yellow word highlight in 4-word phrases",
        "font": "Arial",
        "font_size_9_16": 64,
        "primary_color": "&H00FFFFFF&",
        "highlight_color": "&H0000FFFF&",
        "number_color": "&H0000FFFF&",
        "outline_color": "&H00000000&",
        "back_color": "&H80000000&",
        "outline": 4,
        "shadow": 2,
        "border_style": 1,
        "chunk_size": 4,
        "uppercase": True,
        "bounce": False,
        "margin_v_9_16": 400,
    },
    "minimal": {
        "name": "Minimal",
        "description": "Clean, elegant modern subtitles with subtle drop shadow and natural casing",
        "font": "Segoe UI",
        "font_size_9_16": 54,
        "primary_color": "&H00FFFFFF&",
        "highlight_color": "&H0080FFFF&",  # Soft warm yellow
        "number_color": "&H0080FFFF&",
        "outline_color": "&H00000000&",
        "back_color": "&H60000000&",
        "outline": 2,
        "shadow": 2,
        "border_style": 1,
        "chunk_size": 4,
        "uppercase": False,
        "bounce": False,
        "margin_v_9_16": 380,
    },
    "classic": {
        "name": "Classic",
        "description": "Documentary-style bounded box with semi-transparent black background",
        "font": "Arial",
        "font_size_9_16": 56,
        "primary_color": "&H00FFFFFF&",
        "highlight_color": "&H0000FFFF&",
        "number_color": "&H0000FFFF&",
        "outline_color": "&H00000000&",
        "back_color": "&H90000000&",       # Opaque black box
        "outline": 2,
        "shadow": 0,
        "border_style": 3,                 # Opaque bounding box
        "chunk_size": 5,
        "uppercase": False,
        "bounce": False,
        "margin_v_9_16": 380,
    },
}


def list_caption_styles() -> List[Dict[str, Any]]:
    """Return list of available caption style presets with UI metadata."""
    styles = []
    for key, val in CAPTION_STYLES.items():
        styles.append({
            "id": key,
            "name": val["name"],
            "description": val["description"],
            "uppercase": val["uppercase"],
            "bounce": val["bounce"],
        })
    return styles


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


def _is_numeric_or_currency(word: str) -> bool:
    """Detect if a word contains numbers, currency, or percentage symbols."""
    clean = re.sub(r"[^\w$%]", "", word)
    return any(c.isdigit() or c in ("$", "%", "€", "₹") for c in clean)


def create_ass_subtitles(
    segments: List[Dict[str, Any]],
    clip_start: float,
    clip_end: float,
    out_ass_path: str,
    aspect_ratio: str = "9:16",
    caption_style: str = "hormozi",
    chunk_size: Optional[int] = None,
    hook_title: Optional[str] = None,
) -> bool:
    """Extract words for a subclip and create a stylized ASS animated subtitle file.

    Args:
        segments: List of segment dicts (with 'start', 'end', 'text', and optionally 'words').
        clip_start: Start timestamp (in seconds) in the source video.
        clip_end: End timestamp (in seconds) in the source video.
        out_ass_path: File path to write the .ass subtitle.
        aspect_ratio: Video aspect ratio ('9:16', '1:1', etc.).
        caption_style: One of 'hormozi', 'mrbeast', 'bounce', 'karaoke', 'minimal', 'classic'.
        chunk_size: Optional override for number of words displayed per subtitle line.
        hook_title: Optional headline banner to display at the top of the video.

    Returns:
        True if subtitles were generated and written, False if no words found.
    """
    clip_dur = clip_end - clip_start
    if clip_dur <= 0:
        return False

    # Normalize style selection
    style_key = (caption_style or "hormozi").lower().strip()
    style_cfg = CAPTION_STYLES.get(style_key, CAPTION_STYLES["hormozi"])

    effective_chunk_size = chunk_size if (chunk_size and chunk_size > 0) else style_cfg["chunk_size"]

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
        font_size = style_cfg["font_size_9_16"]
        margin_v = style_cfg["margin_v_9_16"]
    elif aspect_ratio == "1:1":
        play_res_x = 1080
        play_res_y = 1080
        font_size = int(style_cfg["font_size_9_16"] * 0.75)
        margin_v = 180
    else:
        # Default landscape
        play_res_x = 1920
        play_res_y = 1080
        font_size = int(style_cfg["font_size_9_16"] * 0.8)
        margin_v = 140

    font_name = style_cfg["font"]
    # Script-aware font fallback: use Nirmala UI for Hindi/Devanagari scripts
    has_indic = any(any('\u0900' <= c <= '\u0D7F' for c in w.get("word", "")) for w in clip_words)
    if has_indic:
        font_name = "Nirmala UI"

    primary_color = style_cfg["primary_color"]
    highlight_color = style_cfg["highlight_color"]
    number_color = style_cfg.get("number_color", highlight_color)
    outline_color = style_cfg["outline_color"]
    back_color = style_cfg["back_color"]
    outline = style_cfg["outline"]
    shadow = style_cfg["shadow"]
    border_style = style_cfg["border_style"]
    is_uppercase = style_cfg["uppercase"]
    is_bounce = style_cfg["bounce"]

    hook_style_block = ""
    if hook_title and hook_title.strip():
        hook_font_size = 46 if aspect_ratio == "9:16" else 36
        hook_margin_v = 90 if aspect_ratio == "9:16" else 45
        hook_style_block = f"Style: HookHeader,{font_name},{hook_font_size},&H0000FFFF,&H000000FF,&H00000000,&HB0000000,-1,0,0,0,100,100,0,0,3,4,0,8,40,40,{hook_margin_v},1\n"

    ass_content = f"""[Script Info]
Title: AI Shorts Animated Captions ({style_cfg['name']})
ScriptType: v4.00+
WrapStyle: 0
PlayResX: {play_res_x}
PlayResY: {play_res_y}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary_color},&H000000FF,{outline_color},{back_color},-1,0,0,0,100,100,0,0,{border_style},{outline},{shadow},2,50,50,{margin_v},1
{hook_style_block}
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    if hook_title and hook_title.strip():
        clean_hook = hook_title.strip().upper().replace("{", "").replace("}", "")
        hook_end_s = min(clip_dur, 8.0)
        ass_content += f"Dialogue: 1,0:00:00.00,{_format_ass_time(hook_end_s)},HookHeader,,0,0,0,,{clean_hook}\n"

    events: List[Dict[str, str]] = []

    # Chunk words into groups
    for i in range(0, len(clip_words), effective_chunk_size):
        chunk = clip_words[i:i + effective_chunk_size]
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
                raw_token = w["word"].strip().replace("{", "").replace("}", "")
                word_text = raw_token.upper() if is_uppercase else raw_token

                if k == j:
                    # Active word styling
                    active_col = number_color if _is_numeric_or_currency(raw_token) else highlight_color

                    if is_bounce:
                        # Kinetic pop-in: scale up to 125% in 70ms, then settle back to 100% in next 70ms
                        anim_tags = (
                            f"{{\\c{active_col}"
                            f"\\t(0,70,\\fscx125\\fscy125)"
                            f"\\t(70,140,\\fscx100\\fscy100)}}"
                        )
                        reset_tags = f"{{\\c{primary_color}\\fscx100\\fscy100}}"
                        text_parts.append(f"{anim_tags}{word_text}{reset_tags}")
                    else:
                        text_parts.append(f"{{\\c{active_col}}}{word_text}{{\\c{primary_color}}}")
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
