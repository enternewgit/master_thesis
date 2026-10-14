"""Local Magenta RealTime 2 (MRT2) generation helper.

MRT2 runs on a JAX backend in its own venv (see mrt2_poc/), separate from the
torch-based venv this API runs in. Running JAX in-process here would compete
with torch for GPU memory and mix incompatible bundled CUDA/cuDNN libraries
(this crashed with a cuDNN sublibrary version mismatch during PoC testing).

Generation is delegated to a persistent HTTP server (mrt2_poc/server.py)
running inside that venv, rather than spawning a fresh `mrt jax generate`
subprocess per request: spawning fresh meant paying JAX's ~15-20s JIT compile
cost on every single call, regardless of audio duration. The persistent
server compiles once at startup and reuses the compiled function afterwards.

Start it with:
    cd mrt2_poc
    env -u LD_LIBRARY_PATH XLA_PYTHON_CLIENT_PREALLOCATE=false \\
      XLA_FLAGS="--xla_gpu_autotune_level=0" \\
      .venv/bin/python server.py --model mrt2_small --port 8799
"""
import os
import threading
from typing import Optional, Union

import requests

_GENERATION_LOCK = threading.Lock()

_DEFAULT_SERVER_URL = "http://127.0.0.1:8799"


def _server_url() -> str:
    return os.environ.get("MRT2_SERVER_URL", _DEFAULT_SERVER_URL).rstrip("/")


def _auth_headers() -> dict:
    key = os.environ.get("MRT2_SERVER_KEY")
    return {"X-Internal-Key": key} if key else {}


def generate_local(prompt: str, out_path: Optional[str] = "mrt2_local_out.wav", seconds_total: float = 8.0,
                    model: str = "mrt2_small", reset: bool = False) -> Union[str, bytes]:
    """Generate audio with MRT2 via the persistent server and return out_path.

    When out_path is None, returns the WAV bytes directly instead of a path.

    By default this continues the server's streaming state from the previous
    call, so consecutive calls (e.g. successive feedback-loop steps with a
    changing prompt) transition smoothly instead of cutting hard between
    clips. Pass reset=True to start a fresh sequence (e.g. the first
    generation of a new session) -- equivalent to calling reset_session()
    first.
    """
    url = f"{_server_url()}/generate"

    with _GENERATION_LOCK:
        try:
            resp = requests.post(
                url,
                json={"prompt": prompt, "duration": seconds_total, "model": model, "reset": reset},
                headers=_auth_headers(), timeout=300,
            )
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(
                f"Could not reach the MRT2 server at {url}. Start it first: "
                "cd mrt2_poc && .venv/bin/python server.py --model mrt2_small --port 8799 "
                f"(original error: {e})"
            )

        if resp.status_code != 200:
            raise RuntimeError(f"mrt2 generation failed ({resp.status_code}): {resp.text[:2000]}")

        data = resp.content

        if out_path is None:
            return data

        with open(out_path, "wb") as f:
            f.write(data)

    return out_path


def reset_session() -> None:
    """Clear the MRT2 server's streaming state so the next generate_local()
    call starts a fresh sequence instead of continuing the previous one.

    Call this at the start of a new feedback session (e.g. from
    /experiment/stop or wherever a session boundary is tracked), otherwise
    the first generation of a new session would continue musically from
    whatever session generated last.
    """
    url = f"{_server_url()}/reset"
    with _GENERATION_LOCK:
        try:
            resp = requests.post(url, json={}, headers=_auth_headers(), timeout=30)
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(
                f"Could not reach the MRT2 server at {url}. Start it first: "
                "cd mrt2_poc && .venv/bin/python server.py --model mrt2_small --port 8799 "
                f"(original error: {e})"
            )
        if resp.status_code != 200:
            raise RuntimeError(f"mrt2 reset failed ({resp.status_code}): {resp.text[:2000]}")
