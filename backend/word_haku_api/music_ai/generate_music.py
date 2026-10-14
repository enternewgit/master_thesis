"""
Hugging Face MusicGen API helper moved into backend `music_ai`.

Reads `HF_API_TOKEN` and `MUSICGEN_MODEL` from environment (or `.env`).
Provides `generate` that returns output file path when run standalone, and
can be imported for programmatic use.
"""
import os
import argparse
import requests
from dotenv import load_dotenv

load_dotenv()
HF_API_TOKEN = os.environ.get("HF_API_TOKEN")
MUSICGEN_MODEL = os.environ.get("MUSICGEN_MODEL", "facebook/musicgen-small")
DEFAULT_OUT = os.environ.get("OUTPUT_FILE", "out.wav")

if not HF_API_TOKEN:
    raise RuntimeError("HF_API_TOKEN is not set. Put your Hugging Face token into .env or environment.")

API_URL = f"https://api-inference.huggingface.co/models/{MUSICGEN_MODEL}"


def generate(prompt: str, out_path: str = DEFAULT_OUT, params: dict | None = None):
    headers = {
        "Authorization": f"Bearer {HF_API_TOKEN}",
    }
    payload = {"inputs": prompt}
    if params:
        payload["parameters"] = params

    resp = requests.post(API_URL, headers=headers, json=payload, stream=True, timeout=300)
    content_type = resp.headers.get("content-type", "")
    if resp.status_code == 200 and content_type.startswith("audio"):
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return out_path
    else:
        try:
            data = resp.json()
        except Exception:
            data = resp.text
        raise RuntimeError(f"Provider error: {data}")


if __name__ == '__main__':
    p = argparse.ArgumentParser(description="Generate music via Hugging Face MusicGen model")
    p.add_argument("prompt", help="Text prompt for music generation")
    p.add_argument("--out", default=DEFAULT_OUT, help="Output filename (wav)")
    p.add_argument("--duration", type=int, default=8, help="Target duration (seconds), if supported by model")
    args = p.parse_args()

    params = {"duration": args.duration} if args.duration else None
    try:
        out = generate(args.prompt, args.out, params)
        print("Saved", out)
    except Exception as e:
        print("Error during generation:", e)
