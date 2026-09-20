"""Local LLM backend — OpenAI or Gemini, selected by LLM_PROVIDER."""
from ..config import (
    GEMINI_MODEL,
    LLM_PROVIDER,
    OPENAI_MODEL,
    require_gemini_key,
    require_openai_key,
)


def call_openai_llm(prompt: str) -> str:
    """OpenAI Chat Completions backend used by --mode local."""
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "openai is required for --mode local. Install it with:\n"
            "    pip install -r requirements-local.txt"
        ) from e

    client = OpenAI(api_key=require_openai_key())
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0.7,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or ""


def call_gemini_llm(prompt: str) -> str:
    """Gemini backend used by --mode local when LLM_PROVIDER=gemini."""
    try:
        from google import genai  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "google-genai is required for LLM_PROVIDER=gemini. Install it with:\n"
            "    pip install -r requirements-local.txt"
        ) from e

    import re
    import time

    client = genai.Client(api_key=require_gemini_key())
    models_to_try = []
    for m in [GEMINI_MODEL, "gemini-3.5-flash-lite", "gemini-3.6-flash"]:
        if m and m not in models_to_try:
            models_to_try.append(m)

    last_err = None
    for model_name in models_to_try:
        for attempt in range(1, 4):
            try:
                print(f"[llm/gemini] calling {model_name} (attempt {attempt})...", flush=True)
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={
                        "temperature": 0.2,
                        "response_mime_type": "application/json",
                        "max_output_tokens": 8192,
                    },
                )
                return response.text or ""
            except Exception as e:
                last_err = e
                err_str = str(e)
                # If 404 (model deprecated/unavailable), immediately try next model
                if "404" in err_str:
                    print(f"[llm/gemini] {model_name} not available, switching model...", flush=True)
                    break
                # If 429 or 503, try next fallback model first, else back off
                print(f"[llm/gemini] {model_name} attempt {attempt} failed: {err_str[:120]}...", flush=True)
                if attempt < 3:
                    # Parse server retry delay if provided
                    match = re.search(r"retry in (\d+(?:\.\d+)?)s", err_str)
                    wait_time = float(match.group(1)) + 1.0 if match else (attempt * 4)
                    wait_time = min(wait_time, 30.0)
                    print(f"[llm/gemini] waiting {wait_time:.1f}s before retry...", flush=True)
                    time.sleep(wait_time)
                else:
                    print(f"[llm/gemini] {model_name} exhausted attempts, trying next model...", flush=True)
                    break

    raise RuntimeError(f"All Gemini models failed. Last error: {last_err}")


def call_local_llm(prompt: str) -> str:
    """Dispatch to the configured local LLM provider."""
    provider = (LLM_PROVIDER or "openai").strip().lower()
    if provider == "openai":
        return call_openai_llm(prompt)
    if provider == "gemini":
        return call_gemini_llm(prompt)
    raise RuntimeError(
        f"Unknown LLM_PROVIDER={provider!r}. Use 'openai' or 'gemini'."
    )
