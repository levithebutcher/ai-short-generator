# AI YouTube Shorts Generator

**The open-source alternative to Opus Clip, Vidyo.ai, Klap, SubMagic, 2short.ai, and other AI clipping tools.** Drop in any long-form YouTube video and get back ranked, viral-ready 9:16 shorts — for free, with no per-clip credits, no watermarks, and full control over the highlight algorithm.

Built for creators, agencies, and developers who don't want to pay $20–$300/month or be capped on minutes processed. Uses LLM highlight detection (OpenAI or Google Gemini) and Whisper transcription to extract the most viral-worthy moments and auto-crop them vertically with CapCut-style karaoke captions for TikTok, Reels, and Shorts.

![longshorts](https://github.com/user-attachments/assets/3f5d1abf-bf3b-475f-8abf-5e253003453a)

## Why Use This Instead of Opus Clip / Vidyo.ai / Klap?

| | This repo | Opus Clip / Vidyo.ai / Klap / SubMagic |
|---|---|---|
| **Price** | Free + open source | $20–$300/month subscriptions |
| **Per-clip credits** | None — process unlimited videos | Monthly minute caps, overage fees |
| **Watermarks** | Never | On free tiers |
| **Highlight algorithm** | Fully editable virality framework | Black box |
| **Output format** | Any aspect ratio, any resolution | Locked presets |
| **Batch processing** | `xargs` an entire URL list | Manual upload one-by-one |
| **JSON / API output** | Built-in (`--output-json`) | Limited or paid tier only |
| **Self-hostable** | Yes — runs on your machine or server | SaaS only, your videos sit on their servers |
| **White-label / embeddable** | Yes — MIT licensed, import as Python lib | No |

## Features

- **🎬 YouTube In, Vertical Out**: Hand it any YouTube URL — get back N viral-ready 9:16 mp4s
- **✨ CapCut-Style Karaoke Subtitles**: Word-by-word active yellow karaoke highlighting, bold typography, safe vertical positioning for YouTube Shorts & TikTok
- **🔀 Two Modes — API (fast) or Local (offline)**: Default `--mode api` uses cloud APIs for download/transcription/cropping; `--mode local` runs entirely on your machine with `yt-dlp`, `faster-whisper`, and `ffmpeg`/`opencv`, with OpenAI or Gemini for highlight ranking
- **🤖 Virality-Aware Highlight Selection**: Clips ranked on hooks, emotional peaks, opinion bombs, revelation moments, conflict, quotable lines, story peaks, and practical value — not just generic "interesting"
- **📈 Score + Hook + Reason for Every Clip**: Each highlight comes with a viral score, an opening hook line, and a one-sentence explanation of why it works
- **🎤 Whisper Transcription**: Cloud or local (`faster-whisper`, CPU or CUDA with word-level timestamps) — same downstream output shape
- **🧩 Long-Video Aware**: Videos over 30 minutes are auto-chunked with overlap so nothing gets missed
- **♻️ Smart Dedupe**: Overlapping highlights are collapsed by score so you never get two near-duplicate clips
- **🎯 Smart Vertical Crop**: Local mode runs OpenCV face tracking with motion smoothing
- **📱 Any Aspect Ratio**: 9:16 for TikTok/Reels/Shorts, 1:1 for square, anything else by flag
- **🧰 CLI + Python Library**: Use it from the shell or import `generate_shorts(...)` into your own pipeline
- **📦 JSON Output**: `--output-json` dumps the full result (transcript + every candidate highlight + final clip URLs/paths) for downstream automation

---

## Installation

### Prerequisites

- Python 3.10+
- `ffmpeg` on your PATH (automatically handled if installed in virtual environment)
- An LLM API key: `GEMINI_API_KEY` (Free tier supported!) or `OPENAI_API_KEY`

### Steps

1. **Clone the repository:**
   ```bash
   git clone https://github.com/levithebutcher/ai-short-generator.git
   cd ai-short-generator
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```

3. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   # For local offline mode (Whisper, OpenCV face tracking, Gemini):
   pip install -r requirements-local.txt
   ```

4. **Set up environment variables:**

   Create a `.env` file in the project root:
   ```bash
   # Local mode (--mode local)
   LLM_PROVIDER=gemini               # gemini or openai
   GEMINI_API_KEY=your_gemini_key_here
   GEMINI_MODEL=gemini-2.5-flash    # optional, default gemini-2.5-flash

   # Optional OpenAI configuration
   OPENAI_API_KEY=your_openai_key_here
   OPENAI_MODEL=gpt-4o-mini

   # Whisper transcription settings
   LOCAL_WHISPER_MODEL=base          # tiny / base / small / medium / large-v3
   LOCAL_WHISPER_DEVICE=auto         # auto / cpu / cuda
   LOCAL_OUTPUT_DIR=output           # where local mp4s land
   ```

## Usage

### Single video (Local mode — runs offline with Gemini & Whisper)

```bash
python main.py "https://www.youtube.com/watch?v=VIDEO_ID" --mode local
```

Local mode writes the rendered shorts with burned CapCut-style karaoke captions to `./output/short_01.mp4`, `short_02.mp4`, …

### With options

```bash
python main.py "https://www.youtube.com/watch?v=VIDEO_ID" \
    --mode local \
    --num-clips 3 \
    --aspect-ratio 9:16 \
    --output-json result.json
```

### Local file or path

In `--mode local`, you can pass a local video file path directly and skip YouTube downloading:

```bash
python main.py "input_video.mp4" --mode local
```

The Python API works the same way:

```python
from shorts_generator import generate_shorts

result = generate_shorts(
    "input_video.mp4",
    num_clips=3,
    aspect_ratio="9:16",
    mode="local",
)
for short in result["shorts"]:
    print(short["score"], short["title"], short["clip_url"])
```

### Automatic Caching

- **Transcription caching**: Transcriptions are cached as `.srt` files in `LOCAL_OUTPUT_DIR`. If the cache already exists, Whisper runs are skipped.
- **Highlights caching**: Highlight detections from Gemini/OpenAI are saved to `LOCAL_OUTPUT_DIR` to save API quota.
- **Source download caching**: Source videos are cached in `LOCAL_OUTPUT_DIR` as `source_<youtube_id>.mp4`.

### Batch processing

Create a `urls.txt` file with one URL per line, then:

```bash
xargs -a urls.txt -I{} python main.py "{}" --mode local
```

### CLI flags

| Flag | Default | Notes |
|------|---------|-------|
| `--mode` | `local` | `local` (faster-whisper + Gemini/OpenAI + OpenCV + CapCut subtitles) or `api` |
| `--num-clips` | `3` | How many shorts to render |
| `--aspect-ratio` | `9:16` | Any ratio; `9:16` for TikTok/Reels, `1:1` for square |
| `--format` | `720` | Source download resolution: `360` / `480` / `720` / `1080` |
| `--language` | auto | Force Whisper language code (e.g. `en`) |
| `--output-json` | — | Dump the full result (transcript + all candidates) to a file |

## How It Works

1. **Download**: Fetches the source video from YouTube (or reads local video)
2. **Transcribe**: `faster-whisper` produces a word-level timestamped transcript
3. **Detect content type**: An LLM classifies the video (podcast, interview, tutorial, vlog, etc.) and density
4. **Long-video chunking**: Videos > 30 min are split into 20-min overlapping chunks
5. **Highlight ranking**: Gemini/OpenAI scans the transcript through a virality framework — hook moments, emotional peaks, opinion bombs, revelations, conflict, quotables, story peaks, practical value — and emits ranked candidates with scores 0–100
6. **Dedupe**: Overlapping candidates are collapsed by score (>50% overlap → keep the higher score)
7. **Top-N selection**: The top `--num-clips` candidates are selected
8. **Auto-crop & Subtitle Burn**: Each highlight is reframed vertically with face tracking and burned with word-by-word active yellow karaoke ASS subtitles

## Project Structure

```
ai-short-generator/
├── main.py                       CLI entry point
├── requirements.txt              core dependencies
├── requirements-local.txt        local mode dependencies (faster-whisper, opencv, torch)
├── .env.example
└── shorts_generator/
    ├── config.py                 env / settings (Gemini, OpenAI, Whisper, FFmpeg)
    ├── highlights.py             LLM virality ranking framework
    ├── pipeline.py               orchestrator with caching
    └── local/                    local offline backends
        ├── downloader.py         yt-dlp download
        ├── transcriber.py        faster-whisper transcription with word timestamps
        ├── llm.py                Gemini & OpenAI client selector
        ├── caption_generator.py  CapCut-style ASS karaoke subtitle generator
        └── clipper.py            ffmpeg cut + OpenCV face tracking + ASS subtitle burn
```

## Contributing

Contributions are welcome! Please fork the repository and submit a pull request.

## License

This project is licensed under the MIT License.
