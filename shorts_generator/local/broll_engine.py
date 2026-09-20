"""Contextual AI Stock Image / B-Roll Overlay Engine.

Inspired by opensource-clipping, MoneyPrinterTurbo, and AI-B-roll:
- Extracts high-impact visual keywords (objects, animals, products, food) from speech with exact timestamps.
- Fetches royalty-free stock imagery (Pexels API or zero-key Wikimedia/Web search fallback).
- Automatically converts photos into viral floating sticker badges (rounded corners, white stroke, drop-shadow).
- Injects smooth fade-in/fade-out overlays into FFmpeg at the exact timestamps spoken in audio.
"""
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageOps


BROLL_CACHE_DIR = os.path.join("output", "broll_cache")


def _sanitize_slug(text: str) -> str:
    return re.sub(r"[^\w\-]", "_", text.lower().strip())[:30]


def extract_visual_keywords(
    transcript_segments: List[Dict[str, Any]],
    clip_start: float,
    clip_end: float,
    max_items: int = 3,
) -> List[Dict[str, Any]]:
    """Analyze spoken words in clip window and extract concrete visual keywords with timestamps."""
    clip_dur = clip_end - clip_start
    if clip_dur <= 0:
        return []

    # Gather words within clip window
    clip_words = []
    full_text_parts = []
    for seg in transcript_segments:
        s_start = float(seg.get("start", 0.0))
        s_end = float(seg.get("end", 0.0))
        if s_end <= clip_start or s_start >= clip_end:
            continue

        words = seg.get("words")
        if words:
            for w in words:
                w_start = float(w.get("start", s_start))
                w_end = float(w.get("end", s_end))
                w_text = str(w.get("word", "")).strip()
                if w_text and w_end > clip_start and w_start < clip_end:
                    clip_words.append({
                        "word": w_text,
                        "start": max(0.0, w_start - clip_start),
                        "end": min(clip_dur, w_end - clip_start),
                    })
        else:
            t = str(seg.get("text", "")).strip()
            if t:
                full_text_parts.append(t)

    full_clip_text = " ".join([w["word"] for w in clip_words]) if clip_words else " ".join(full_text_parts)
    if not full_clip_text or len(full_clip_text.split()) < 3:
        return []

    # Prompt Gemini / LLM to extract concrete visual nouns
    prompt = f"""You are a viral YouTube Shorts video editor.
Analyze this short video speech excerpt:
"{full_clip_text}"

Identify up to {max_items} concrete, physical objects, animals, food items, tools, products, or vehicles explicitly mentioned that would look great as a visual pop-up graphic/stock image (e.g. "crow", "chicken", "soup", "money", "car", "phone", "coffee").

For each object:
- "keyword": A 1-2 word search query for a clean stock photo (e.g. "crow bird", "fried chicken", "hot soup bowl").
- "start_word": The exact word in the text where this object is first spoken.

Return ONLY a valid JSON array of objects, example:
[
  {{"keyword": "crow bird", "start_word": "crow"}},
  {{"keyword": "hot soup", "start_word": "soup"}}
]
If there are no tangible physical objects mentioned, return: []"""

    try:
        from .llm import call_local_llm
        raw_resp = call_local_llm(prompt)
        # Parse JSON
        m = re.search(r"\[\s*\{.*\}\s*\]", raw_resp, re.DOTALL)
        if m:
            candidates = json.loads(m.group(0))
        else:
            candidates = []
    except Exception as e:
        print(f"[broll] LLM keyword extraction failed: {e}", flush=True)
        candidates = []

    results = []
    for item in candidates[:max_items]:
        kw = str(item.get("keyword", "")).strip()
        start_word = str(item.get("start_word", "")).lower().strip()
        if not kw:
            continue

        # Find approximate start timestamp from word list
        matched_start = None
        for w in clip_words:
            clean_w = re.sub(r"[^\w]", "", w["word"].lower())
            if start_word and (start_word in clean_w or clean_w in start_word):
                matched_start = w["start"]
                break

        if matched_start is None:
            matched_start = 1.5  # fallback reasonable offset

        start_time = max(0.5, matched_start)
        # Display each sticker for 2.0 seconds
        end_time = min(clip_dur - 0.2, start_time + 2.0)
        if end_time > start_time + 0.8:
            results.append({
                "keyword": kw,
                "start": round(start_time, 2),
                "end": round(end_time, 2),
            })

    print(f"[broll] extracted {len(results)} visual overlay moments: {results}", flush=True)
    return results


def _download_image_url(url: str, out_path: str) -> bool:
    """Download an image from a URL to out_path."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            if len(data) > 1000:
                with open(out_path, "wb") as f:
                    f.write(data)
                return True
    except Exception:
        pass
    return False


def _fetch_from_wikimedia(keyword: str) -> Optional[str]:
    """Search Wikimedia Commons for high-quality royalty-free image."""
    try:
        clean_kw = re.sub(r"[^\w\s]", "", keyword).strip()
        params = urllib.parse.urlencode({
            "action": "query",
            "generator": "search",
            "gsrsearch": f"{clean_kw} filetype:bitmap",
            "gsrnamespace": "6",
            "gsrlimit": "3",
            "prop": "imageinfo",
            "iiprop": "url",
            "iiurlwidth": "720",
            "format": "json",
        })
        url = f"https://commons.wikimedia.org/w/api.php?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            pages = data.get("query", {}).get("pages", {})
            for p in pages.values():
                info = p.get("imageinfo", [])
                if info and ("thumburl" in info[0] or "url" in info[0]):
                    return info[0].get("thumburl", info[0].get("url"))
    except Exception as e:
        print(f"[broll] wikimedia error for '{keyword}': {e}", flush=True)
    return None


def _fetch_from_pexels(keyword: str) -> Optional[str]:
    """Search Pexels API if PEXELS_API_KEY is available."""
    api_key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        url = f"https://api.pexels.com/v1/search?query={urllib.parse.quote(keyword)}&per_page=1"
        req = urllib.request.Request(url, headers={"Authorization": api_key, "User-Agent": "AIShortGen/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            photos = data.get("photos", [])
            if photos and "src" in photos[0]:
                return photos[0]["src"].get("medium") or photos[0]["src"].get("large")
    except Exception:
        pass
    return None


def create_sticker_badge(image_path: str, out_badge_path: str, size: int = 360) -> bool:
    """Format raw image into a viral short sticker badge (rounded corners, white stroke, shadow)."""
    try:
        with Image.open(image_path) as raw_img:
            img = raw_img.convert("RGBA")

            # Square crop
            w, h = img.size
            min_dim = min(w, h)
            left = (w - min_dim) // 2
            top = (h - min_dim) // 2
            img = img.crop((left, top, left + min_dim, top + min_dim))
            img = img.resize((size, size), Image.Resampling.LANCZOS)

            # Create rounded rectangle mask
            radius = 36
            mask = Image.new("L", (size, size), 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.rounded_rectangle([(0, 0), (size, size)], radius=radius, fill=255)

            # Apply rounded mask
            rounded_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            rounded_img.paste(img, (0, 0), mask=mask)

            # Canvas with border and drop shadow
            border_width = 8
            shadow_offset = 12
            shadow_blur = 16
            canvas_w = size + (border_width * 2) + shadow_blur * 2
            canvas_h = size + (border_width * 2) + shadow_blur * 2 + shadow_offset

            canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

            # Draw Shadow
            shadow_box = [
                (shadow_blur, shadow_blur + shadow_offset),
                (shadow_blur + size + border_width * 2, shadow_blur + size + border_width * 2 + shadow_offset)
            ]
            shadow_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
            draw_shadow = ImageDraw.Draw(shadow_layer)
            draw_shadow.rounded_rectangle(shadow_box, radius=radius + border_width, fill=(0, 0, 0, 160))
            shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(shadow_blur // 2))
            canvas.paste(shadow_layer, (0, 0), shadow_layer)

            # Draw White Border
            border_box = [
                (shadow_blur, shadow_blur),
                (shadow_blur + size + border_width * 2, shadow_blur + size + border_width * 2)
            ]
            draw_border = ImageDraw.Draw(canvas)
            draw_border.rounded_rectangle(border_box, radius=radius + border_width, fill=(255, 255, 255, 255))

            # Paste inner image
            canvas.paste(rounded_img, (shadow_blur + border_width, shadow_blur + border_width), rounded_img)

            canvas.save(out_badge_path, "PNG")
            return True
    except Exception as e:
        print(f"[broll] failed to create sticker badge: {e}", flush=True)
        return False


def get_or_fetch_stock_image(keyword: str, cache_dir: Optional[str] = None) -> Optional[str]:
    """Fetch and return path to a styled PNG sticker for the given keyword."""
    cache_dir = cache_dir or BROLL_CACHE_DIR
    os.makedirs(cache_dir, exist_ok=True)

    slug = _sanitize_slug(keyword)
    final_badge_path = os.path.join(cache_dir, f"{slug}_badge.png")
    if os.path.exists(final_badge_path) and os.path.getsize(final_badge_path) > 1000:
        return final_badge_path

    # Fuzzy check cached badges if any keyword token matches (e.g. 'soup' matches 'soup bowl')
    tokens = [t for t in slug.split('_') if len(t) > 2]
    try:
        for f in os.listdir(cache_dir):
            if f.endswith("_badge.png"):
                for t in tokens:
                    if t in f:
                        candidate = os.path.join(cache_dir, f)
                        if os.path.getsize(candidate) > 1000:
                            print(f"[broll] fuzzy cache hit: {f} for keyword '{keyword}'", flush=True)
                            return candidate
    except Exception:
        pass

    raw_img_path = os.path.join(cache_dir, f"{slug}_raw.jpg")
    img_url = _fetch_from_pexels(keyword) or _fetch_from_wikimedia(keyword)

    # If multi-word keyword failed, try individual noun tokens
    if not img_url and len(tokens) > 1:
        for t in reversed(tokens):
            img_url = _fetch_from_pexels(t) or _fetch_from_wikimedia(t)
            if img_url:
                break

    if not img_url:
        print(f"[broll] no image found for: {keyword}", flush=True)
        return None

    if not _download_image_url(img_url, raw_img_path):
        return None

    ok = create_sticker_badge(raw_img_path, final_badge_path)
    if ok:
        print(f"[broll] created viral sticker badge: {final_badge_path}", flush=True)
        return final_badge_path
    return None


def build_ffmpeg_broll_filters(
    overlays: List[Dict[str, Any]],
    canvas_w: int = 1080,
    canvas_h: int = 1920,
    start_input_idx: int = 2,
) -> Tuple[List[str], str]:
    """Compile FFmpeg command inputs and filter_complex string for overlaying B-roll badges."""
    inputs: List[str] = []
    filter_chains: List[str] = []

    valid_overlays = []
    for item in overlays:
        img_path = item.get("image_path")
        if img_path and os.path.exists(img_path):
            valid_overlays.append(item)

    if not valid_overlays:
        return [], ""

    # Each valid overlay gets added as an input file with -loop 1
    for item in valid_overlays:
        inputs.extend(["-loop", "1", "-i", item["image_path"]])

    # Top/middle positioning: centered horizontally, upper quadrant
    badge_w = max(120, int(canvas_w * 0.42))
    badge_y = max(40, int(canvas_h * 0.16))

    last_v = "0:v"
    for idx, item in enumerate(valid_overlays):
        input_idx = start_input_idx + idx
        start = float(item["start"])
        end = float(item["end"])
        fade_dur = 0.25

        # Format with scale and smooth alpha fade in & out
        stk_label = f"stk{idx+1}"
        next_v = f"v_broll{idx+1}"

        fade_filter = (
            f"[{input_idx}:v]scale={badge_w}:-1,format=rgba,"
            f"fade=t=in:st={start:.2f}:d={fade_dur}:alpha=1,"
            f"fade=t=out:st={end - fade_dur:.2f}:d={fade_dur}:alpha=1[{stk_label}]"
        )
        filter_chains.append(fade_filter)

        overlay_filter = (
            f"[{last_v}][{stk_label}]overlay="
            f"x=(W-w)/2:y={badge_y}:enable='between(t,{start:.2f},{end:.2f})':eof_action=pass[{next_v}]"
        )
        filter_chains.append(overlay_filter)
        last_v = next_v

    full_filter = ";".join(filter_chains)
    return inputs, full_filter
