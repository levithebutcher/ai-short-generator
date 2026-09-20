"""CLI entry point.

Usage:
    python main.py "https://www.youtube.com/watch?v=..." \
        --num-clips 3 --aspect-ratio 9:16
"""
import argparse
import json
import sys

# Windows uses 'charmap' by default, which can't encode Unicode characters
# like →. Reconfigure stdout/stderr to UTF-8 so output works on all platforms.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from shorts_generator import generate_shorts


def main() -> int:
    parser = argparse.ArgumentParser(description="AI YouTube Shorts Generator")
    parser.add_argument("url", nargs="?", default=None, help="YouTube URL, file:// URL, or local file path")
    parser.add_argument("--web", action="store_true", help="Launch interactive web dashboard at http://localhost:8000")
    parser.add_argument("--port", type=int, default=8000, help="Web dashboard port (default: 8000)")
    parser.add_argument(
        "--mode",
        choices=["api", "local"],
        default="local",
        help="api (MuAPI) or local (default: faster-whisper + Gemini/OpenAI + ffmpeg).",
    )
    parser.add_argument("--num-clips", type=int, default=3, help="How many shorts to render (default: 3)")
    parser.add_argument("--aspect-ratio", default="9:16", help="Output aspect ratio (default: 9:16)")
    parser.add_argument("--format", default="720", help="Source download resolution: 360 / 480 / 720 / 1080 (default: 720)")
    parser.add_argument("--language", default=None, help="Force Whisper language code, e.g. 'en' (default: auto-detect)")
    parser.add_argument(
        "--caption-style",
        choices=["hormozi", "bounce", "beast", "karaoke", "box"],
        default="bounce",
        help="Subtitle style: bounce (active zoom), hormozi (yellow), beast (cyan), karaoke (progressive), box (pill) (default: bounce)",
    )
    parser.add_argument("--broll", action=argparse.BooleanOptionalAction, default=True, help="Enable contextual stock image popups (default: True)")
    parser.add_argument("--hook-header", action=argparse.BooleanOptionalAction, default=True, help="Pin viral hook title banner at top (default: True)")
    parser.add_argument("--turbo", action=argparse.BooleanOptionalAction, default=True, help="Turbo 10x single-pass render engine (default: True)")
    parser.add_argument("--output-json", default=None, help="Write the full result JSON to this path")
    args = parser.parse_args()

    if args.web:
        from app import start_server
        start_server(port=args.port, open_browser=True)
        return 0

    if not args.url:
        parser.error("URL is required when not using --web. Example: python main.py <url> or python main.py --web")

    try:
        result = generate_shorts(
            youtube_url=args.url,
            num_clips=args.num_clips,
            aspect_ratio=args.aspect_ratio,
            download_format=args.format,
            language=args.language,
            mode=args.mode,
            caption_style=args.caption_style,
            enable_broll=args.broll,
            enable_hook_header=args.hook_header,
            turbo_mode=args.turbo,
        )
    except Exception as e:
        print(f"\nFAILED: {e}", file=sys.stderr)
        return 1

    print("\n" + "=" * 72)
    print(f"Mode:          {result.get('mode', args.mode)}")
    print(f"Source video:  {result['source_video_url']}")
    print(f"Highlights:    {len(result['highlights'])} candidates → kept top {len(result['shorts'])}")
    print("=" * 72)
    for i, s in enumerate(result["shorts"], 1):
        print(f"\n#{i}  score={s.get('score')}  {s.get('start_time'):.1f}s → {s.get('end_time'):.1f}s")
        print(f"     title:  {s.get('title')}")
        print(f"     hook:   {s.get('hook_sentence')}")
        if s.get("clip_url"):
            print(f"     clip:   {s['clip_url']}")
        else:
            print(f"     clip:   FAILED ({s.get('error')})")

    if args.output_json:
        with open(args.output_json, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nFull JSON written to {args.output_json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
