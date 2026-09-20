# AI YouTube Shorts Generator ⚡ (Turbo 10x Edition)

**The open-source alternative to Opus Clip, Vidyo.ai, Klap, SubMagic, and 2short.ai.** Drop in any long-form YouTube video or local MP4 and get back ranked, viral-ready 9:16 vertical shorts — for free, with no per-clip credits, no watermarks, full control over the virality algorithm, and an interactive web dashboard.

Built for creators, agencies, and developers who don't want to pay $20–$300/month or be capped on minutes processed. Uses Gemini / OpenAI for highlight detection, Whisper for transcription, OpenCV adaptive face tracking, and FFmpeg for single-pass 10x vertical rendering with viral CapCut/SubMagic captions and contextual B-roll stock overlays.

![longshorts](https://github.com/user-attachments/assets/3f5d1abf-bf3b-475f-8abf-5e253003453a)

---

## ⚡ Why Use This Instead of Opus Clip / Vidyo.ai / Klap?

| | This repo | Opus Clip / Vidyo.ai / Klap / SubMagic |
|---|---|---|
| **Price** | **100% Free + Open Source** | $20–$300/month subscriptions |
| **Per-clip credits** | **None** — process unlimited videos | Monthly minute caps, overage fees |
| **Watermarks** | **Never** | On free tiers |
| **Highlight algorithm** | **Customizable Virality Framework** | Black box |
| **Render Speed** | **Turbo 10x Single-Pass Pipe** (under 10s per short) | Multi-minute cloud queues |
| **Contextual B-Roll** | **Automated Stock Image Badges (Zero-Key)** | Premium add-on |
| **Subtitle Styles** | **5 Viral Styles** (Bounce, Hormozi, Beast, Box, Karaoke) | Locked presets |
| **Web Dashboard** | **Interactive Dark UI + Realtime Progress** | Proprietary SaaS |
| **Self-Hostable** | **Yes** — runs locally on your laptop or server | SaaS only |
| **License** | **MIT** (commercial & personal use) | Proprietary |

---

## 🚀 Key Features

- **⚡ Turbo 10x Single-Pass Engine**: Completely eliminates slow software double-encoding! Streams raw frames directly from OpenCV into FFmpeg `stdin` (`-f rawvideo -pix_fmt bgr24`) with 10-frame adaptive face detection on downsampled grayscale and EMA smoothing.
- **🖼️ Contextual AI Stock Image / B-Roll Overlays**: Detects spoken physical objects (e.g. *"crow"*, *"soup"*, *"chicken"*, *"money"*, *"car"*, *"coffee"*), fetches royalty-free stock photos (via Wikimedia Commons zero-key fallback or Pexels API), styles them into viral rounded sticker badges (white border + drop shadow), and displays them with smooth alpha fade at the exact spoken moment.
- **📌 Viral Hook Header Banner**: Pins a high-retention hook headline at the top center with yellow typography and a dark bounding box to maximize watch time.
- **✨ 5 Viral Subtitle Caption Styles (SubMagic / CapCut inspired)**:
  - `bounce`: Word-by-word active zoom pop-in with radiant yellow highlight.
  - `hormozi`: Bold uppercase yellow word-by-word highlight.
  - `beast`: Cyan MrBeast-style punchy text with black contrast outline.
  - `box`: High-contrast black pill highlight box behind the active word.
  - `karaoke`: Smooth progressive line karaoke highlighting.
- **🌐 Interactive Web Dashboard**: Launch `python main.py --web` for a modern dark-themed web studio with live stage progress, video preview player, and one-click MP4 downloads.
- **🔊 Mobile Loudness Normalization & Silence Removal**: Standardizes audio to **EBU R128** (`loudnorm=I=-16:TP=-1.5:LRA=11`) for maximum punch on mobile speakers.
- **🎯 Intelligent Face-Centered Crop**: Automatically reframes 16:9 widescreen video into 9:16 vertical video while keeping the speaker's face centered.
- **🤖 Multi-LLM Virality Scoring**: Evaluates transcripts across hook strength, emotional spikes, revelations, controversy, and practical value using **Google Gemini** (Free tier supported!) or **OpenAI**.

---

## 🛠️ Installation

### Prerequisites
- **Python 3.10+**
- **FFmpeg** (installed automatically via `imageio-ffmpeg` or system PATH)
- **API Key**: `GEMINI_API_KEY` (Free tier recommended!) or `OPENAI_API_KEY`

### Setup

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

3. **Install dependencies:**
   ```bash
   pip install -r requirements-local.txt
   ```

4. **Configure environment variables:**
   Create a `.env` file in the root folder:
   ```env
   # LLM Provider (gemini or openai)
   LLM_PROVIDER=gemini
   GEMINI_API_KEY=your_gemini_api_key_here
   GEMINI_MODEL=gemini-2.5-flash

   # Optional OpenAI settings
   OPENAI_API_KEY=your_openai_key_here
   OPENAI_MODEL=gpt-4o-mini

   # Optional Pexels API Key for HD stock images (defaults to Wikimedia Commons if omitted)
   PEXELS_API_KEY=your_pexels_key_optional

   # Whisper transcription settings
   LOCAL_WHISPER_MODEL=base          # tiny / base / small / medium / large-v3
   LOCAL_WHISPER_DEVICE=auto         # auto / cpu / cuda
   LOCAL_OUTPUT_DIR=output           # output directory for rendered shorts
   ```

---

## 🖥️ Usage

### 1. Interactive Web Dashboard (Recommended)

Launch the web studio in your browser:
```bash
python main.py --web
```
Or directly:
```bash
python app.py
```
Open **http://127.0.0.1:8000** to paste YouTube URLs, toggle Turbo 10x, enable B-roll popups, choose subtitle styles, and watch live progress.

---

### 2. Command-Line Interface (CLI)

#### Basic generation:
```bash
python main.py "https://www.youtube.com/watch?v=VIDEO_ID" --num-clips 3
```

#### Full customization (Subtitles, B-Roll, Hook Banner):
```bash
python main.py "https://www.youtube.com/watch?v=VIDEO_ID" \
    --num-clips 3 \
    --caption-style bounce \
    --broll \
    --hook-header \
    --turbo \
    --aspect-ratio 9:16 \
    --output-json results.json
```

#### Process a local video file directly:
```bash
python main.py "my_podcast.mp4" --num-clips 5 --caption-style hormozi
```

---

### 3. Python API Integration

Embed the pipeline directly into your applications:

```python
from shorts_generator import generate_shorts

result = generate_shorts(
    youtube_url="https://www.youtube.com/watch?v=VIDEO_ID",
    num_clips=3,
    aspect_ratio="9:16",
    mode="local",
    caption_style="bounce",     # bounce / hormozi / beast / karaoke / box
    enable_broll=True,          # contextual stock image overlays
    enable_hook_header=True,    # pinned viral hook banner
    turbo_mode=True,            # single-pass high-speed pipe
)

for short in result["shorts"]:
    print(f"Title: {short['title']} (Score: {short['score']})")
    print(f"File: {short['clip_url']}")
```

---

## ⚙️ CLI Options Reference

| Flag | Default | Description |
|---|---|---|
| `url` | *None* | YouTube URL, local video file path, or `file://` URI |
| `--web` | `False` | Launch interactive web UI at `http://127.0.0.1:8000` |
| `--port` | `8000` | Web server port |
| `--mode` | `local` | `local` (offline Whisper + Gemini + OpenCV + FFmpeg) or `api` |
| `--num-clips` | `3` | Number of top viral shorts to generate |
| `--caption-style` | `bounce` | Subtitle style: `bounce`, `hormozi`, `beast`, `karaoke`, `box` |
| `--broll` / `--no-broll` | `True` | Enable/disable contextual stock image badge overlays |
| `--hook-header` / `--no-hook-header` | `True` | Enable/disable top-center pinned hook title banner |
| `--turbo` / `--no-turbo` | `True` | Enable/disable Turbo 10x single-pass fast render engine |
| `--aspect-ratio` | `9:16` | Aspect ratio: `9:16` (vertical), `1:1` (square), `16:9` |
| `--format` | `720` | Video download resolution: `360`, `480`, `720`, `1080` |
| `--language` | *auto* | Force Whisper language code (e.g. `en`, `hi`, `es`, `fr`) |
| `--output-json` | *None* | Path to export full JSON metadata |

---

## 📁 Project Architecture

```
ai-short-generator/
├── app.py                         FastAPI web server & background job runner
├── main.py                        CLI entry point with full argument controls
├── requirements.txt               Core dependencies
├── requirements-local.txt         Local offline dependencies (FastAPI, OpenCV, Whisper, Pillow)
├── web/
│   └── index.html                 Single-page dark modern web dashboard
├── shorts_generator/
│   ├── config.py                  Environment settings & defaults
│   ├── highlights.py              LLM virality ranking framework
│   ├── pipeline.py                End-to-end pipeline orchestrator & cache manager
│   └── local/
│       ├── broll_engine.py        AI noun extraction, stock image fetcher, sticker badge formatter
│       ├── caption_generator.py   5 viral ASS subtitle styles + hook header banner
│       ├── clipper.py             Turbo 10x single-pass OpenCV rawvideo pipe + face tracking
│       ├── downloader.py          yt-dlp multi-fragment concurrent video downloader
│       ├── llm.py                 Gemini and OpenAI multi-provider client
│       ├── silence_remover.py     Audio silence trimming & EBU R128 loudness normalizer
│       └── transcriber.py         faster-whisper word-level timestamp transcriber
```

---

## 🤝 Contributing

Pull requests and feature suggestions are very welcome! If you have ideas for new caption animations, B-roll integrations, or transitions, feel free to open an issue or PR.

## 📄 License

This project is licensed under the [MIT License](LICENSE).
