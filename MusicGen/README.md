Lyria RealTime Proxy Demo

This folder contains a minimal WebSocket proxy to demo connecting a browser client to the Lyria RealTime API without exposing the API key to the client.

Files:
- `requirements.txt` - Python deps (`websockets`, `python-dotenv`)
- `.env.example` - Example environment variables. Copy to `.env` and fill `LYRIA_API_KEY`.
- `.env` - local env used for mock testing (created for dev convenience)
- `proxy.py` - Minimal asyncio WebSocket proxy.
- `mock_upstream.py` - Mock upstream server to test proxy locally without real Lyria access.
- `client_demo.html` - Simple browser demo that connects to the local proxy and exchanges messages.

Local test (mock upstream)

1. Create a virtual environment and install deps:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Ensure `.env` exists (copied from `.env.example`). The included `.env` points the proxy to the mock upstream by default.

3. Start the mock upstream server (this simulates Lyria):

```bash
python LyriaRealTime/mock_upstream.py
```

4. In a separate terminal, start the proxy:

```bash
python LyriaRealTime/proxy.py
```

5. Serve `client_demo.html` so the browser can open it (or open directly with `file://`, but serving is convenient):

```bash
# from repo root
python -m http.server 8000
# then open http://localhost:8000/LyriaRealTime/client_demo.html
```

6. Use the demo UI: Connect → Send a JSON message → observe the mock upstream response in the log.

Notes & Production
- This setup is for local development and learning. For production, add authentication, rate limiting, request validation, and TLS. Never commit secrets.

MusicGen prototype (Hugging Face)

This folder also contains a minimal MusicGen prototype using the Hugging Face Inference API.

Files added for MusicGen demo:
- `generate_music.py` - simple script that posts a prompt to a Hugging Face MusicGen model and saves returned audio.
- `.env.example` - (if present) copy to `.env` and set `HF_API_TOKEN` and `MUSICGEN_MODEL`.

Quick start (Hugging Face MusicGen)

1. Create virtualenv and install deps (this repository may already have a venv):

```bash
cd /home/sumi_masahiro312/graduation_research/MusicGen
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Create `.env` from `.env.example` and set `HF_API_TOKEN` and optionally `MUSICGEN_MODEL`:

```bash
cp .env.example .env
# edit .env and set HF_API_TOKEN
```

3. Run the generator (example):

```bash
./.venv/bin/python generate_music.py "A short upbeat piano loop" --out music.wav --duration 8
```

4. If the model returns audio, it will be written to the file you specified. If the request fails, the script prints the JSON/text error returned by the API.

Notes
- You need a valid Hugging Face token with Inference API access. Some models may require additional quota or permissions.
- Model ids: `facebook/musicgen-small`, `facebook/musicgen-medium`, etc. Check Hugging Face model hub for available MusicGen variants.

Stable Audio Open (代替案)

もし Stable Audio Open を使う場合、このリポジトリの `MusicGen/generate_stableaudio.py` を使えます。使い方:

1. `.env` へ以下を追加または設定:

```text
STABLE_AUDIO_API_URL=https://api.stableaudio.org/v1/generate  # 例 - 実エンドポイントはドキュメント参照
STABLE_AUDIO_API_KEY=your_stable_audio_key
OUTPUT_FILE=stable_out.wav
```

2. 仮想環境を有効にして依存をインストール（既にある場合は不要）:

```bash
cd MusicGen
source .venv/bin/activate
.venv/bin/python3 -m pip install requests python-dotenv
```

3. 生成を実行:

```bash
.venv/bin/python3 generate_stableaudio.py "A dreamy ambient pad with soft piano" --out stable.wav --duration 12
```

4. 応答が音声であれば `stable.wav` が生成されます。APIの入出力仕様はサービスによって異なるため、必要に応じて `generate_stableaudio.py` の `body` を調整してください。

注意: Stable Audio のエンドポイントやパラメータはサービス側のドキュメントに従ってください。API キーは決して公開しないでください。
Local (on-device) Stable Audio using `stable-audio-tools`

If you prefer to run Stable Audio models locally (no API key required), use the `stable-audio-tools` package.
This requires a compatible `torch` + `torchaudio` installation and sufficient resources (GPU strongly recommended).

Quick local setup (recommended `venv`):

```bash
cd MusicGen
# create venv if you don't have one
python3 -m venv .venv
source .venv/bin/activate

# Install torch first - choose CPU or CUDA wheel.
# CPU example:
.venv/bin/python3 -m pip install --upgrade pip
.venv/bin/python3 -m pip install torch --index-url https://download.pytorch.org/whl/cpu

# For CUDA, choose the appropriate wheel (example cu118):
# .venv/bin/python3 -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Then install stable-audio-tools and helpers
.venv/bin/python3 -m pip install stable-audio-tools einops
```

Run the provided local generator script:

```bash
.venv/bin/python3 generate_stableaudio_local.py \
	--model stabilityai/stable-audio-open-1.0 \
	--prompt "128 BPM tech house drum loop" \
	--seconds_total 47 \
	--steps 100 \
	--out demo_local.wav
```

Notes:
- Local generation can be resource intensive. For reasonable speeds, use a CUDA-capable GPU and install the matching CUDA torch wheel.
- If you cannot install torch or lack GPU, use the hosted API client (`generate_stableaudio.py`) with `STABLE_AUDIO_API_URL`/`STABLE_AUDIO_API_KEY`.
