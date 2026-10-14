"""
Simple MusicGen prototype using Hugging Face Inference API.
- Requires `HF_API_TOKEN` and `MUSICGEN_MODEL` in `.env` or environment.
- Sends a prompt and saves returned audio (if content-type is audio/*) to a file.

Note: This is a minimal demo. Check Hugging Face docs for model-specific params.
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
        # Accept not strictly required; we inspect content-type
    }
    payload = {
        "inputs": prompt,
    }
    if params:
        payload["parameters"] = params

    print(f"Requesting model {MUSICGEN_MODEL} -> {API_URL}")
    r = requests.post(API_URL, headers=headers, json=payload, stream=True, timeout=300)

    content_type = r.headers.get("content-type", "")
    if r.status_code == 200 and content_type.startswith("audio"):
        print(f"Saving audio to {out_path} (content-type: {content_type})")
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        print("Saved.")
        return out_path
    else:
        # Try to show json error or fallback text
        try:
            data = r.json()
            print("Response (json):", data)
        except Exception:
            print("Response (text):", r.text)
        r.raise_for_status()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description="Generate music via Hugging Face MusicGen model")
    p.add_argument("prompt", help="Text prompt for music generation")
    p.add_argument("--out", default=DEFAULT_OUT, help="Output filename (wav)")
    p.add_argument("--duration", type=int, default=8, help="Target duration (seconds), if supported by model")
    args = p.parse_args()

    params = {"duration": args.duration} if args.duration else None
    try:
        generate(args.prompt, args.out, params)
    except Exception as e:
        print("Error during generation:", e)
