"""
Minimal Stable Audio Open client (prototype).

Environment variables expected in `.env` or environment:
- STABLE_AUDIO_API_URL: Full endpoint URL to call (e.g. https://api.stableaudio.org/v1/generate)
- STABLE_AUDIO_API_KEY: Your Stable Audio Open API key
- OUTPUT_FILE: default output filename

This script posts a JSON payload with a `prompt` and optional `duration` and writes returned audio bytes to file when the response is audio/*.
Adjust payload structure to match the provider's API if necessary.
"""
import os
import argparse
import requests
from dotenv import load_dotenv

load_dotenv()
STABLE_API_URL = os.environ.get("STABLE_AUDIO_API_URL")
STABLE_API_KEY = os.environ.get("STABLE_AUDIO_API_KEY")
DEFAULT_OUT = os.environ.get("OUTPUT_FILE", "stable_out.wav")

if not STABLE_API_URL:
    raise RuntimeError("STABLE_AUDIO_API_URL not set. Set it in .env or environment.")
if not STABLE_API_KEY:
    print("Warning: STABLE_AUDIO_API_KEY not set. Requests may be rejected.")


def generate(prompt: str, out_path: str = DEFAULT_OUT, duration: int | None = None, params: dict | None = None):
    headers = {
        "Authorization": f"Bearer {STABLE_API_KEY}" if STABLE_API_KEY else None,
        "Accept": "audio/wav, audio/mpeg, application/json",
    }
    # Build body - many Stable Audio APIs accept prompt + duration; adapt if your provider differs
    body = {"prompt": prompt}
    if duration:
        body["duration"] = duration
    if params:
        body["parameters"] = params

    # Remove None headers
    headers = {k: v for k, v in headers.items() if v is not None}

    print(f"Requesting Stable Audio at {STABLE_API_URL}")
    resp = requests.post(STABLE_API_URL, headers=headers, json=body, stream=True, timeout=300)

    content_type = resp.headers.get("content-type", "")
    # If audio returned, either write to disk (out_path specified) or return bytes (out_path is None)
    if resp.status_code == 200 and content_type.startswith("audio"):
        # If caller passed out_path explicitly as None, return bytes to avoid disk I/O
        if out_path is None:
            print(f"Receiving audio as bytes (content-type: {content_type})")
            data = bytearray()
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    data.extend(chunk)
            print("Received audio bytes.")
            return bytes(data), content_type
        else:
            print(f"Saving audio to {out_path} (content-type: {content_type})")
            with open(out_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            print("Saved.")
            return out_path
    else:
        try:
            data = resp.json()
            print("Response (json):", data)
        except Exception:
            print("Response (text):", resp.text)
        resp.raise_for_status()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description="Generate audio via Stable Audio Open API")
    p.add_argument("prompt", help="Text prompt for audio generation")
    p.add_argument("--out", default=DEFAULT_OUT, help="Output filename (wav)")
    p.add_argument("--duration", type=int, default=None, help="Target duration (seconds), if supported")
    args = p.parse_args()

    try:
        generate(args.prompt, args.out, args.duration)
    except Exception as e:
        print("Error during generation:", e)
