"""Persistent MRT2 generation server.

Loads MagentaRT2Jax once at startup (paying the JAX JIT compile cost a
single time) and serves generation requests over a minimal local HTTP API.
This replaces the old subprocess-per-request approach (`mrt jax generate`),
which recompiled on every call and added a fixed ~15-20s overhead to every
single generation regardless of duration.

Usage:
    env -u LD_LIBRARY_PATH \\
      XLA_PYTHON_CLIENT_PREALLOCATE=false \\
      XLA_FLAGS="--xla_gpu_autotune_level=0" \\
      .venv/bin/python server.py --model mrt2_small --port 8799
"""
import argparse
import io
import json
import logging
import os
import random
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("mrt2_server")

_GENERATION_LOCK = threading.Lock()
_mrt = None
_model_name = None
_device_info = None

# Streaming state from the most recent /generate call, carried forward so the
# next call continues the same autoregressive sequence instead of starting
# over (see MagentaRT2Jax.generate()'s `state` argument). style/prompt can
# still change from call to call -- only the underlying sequence state is
# threaded through, which is what makes a smooth musical transition between
# successive prompts possible instead of a hard cut. Reset to None to start a
# fresh sequence (new feedback session): either via POST /reset, or by
# passing {"reset": true} on a /generate call.
_state = None

FRAMES_PER_SECOND = 25
MAX_DURATION_SECONDS = 120.0

# magenta_rt's JAX system bakes a fixed PRNGKey into its JIT-compiled
# sampling step at model-load time (see MagentaRT2Jax._compile()). Together
# with a fresh state (state=None), that means calling /generate twice from
# a reset sequence with the same prompt returns byte-identical audio -- there
# is no seed argument exposed to change this. temperature/top_k *are* plain
# per-call values (not baked into the JIT trace), so jittering temperature
# around the model's default is the workaround: it changes which token wins
# at each sampling step without needing to touch magenta_rt internals. See
# analysis_results/mrt2_viz_stats_n10/point_comparison.txt for how this was
# discovered. (Continued-state calls carry their own entropy forward from
# prior steps and don't need this to differ from call to call.)
TEMPERATURE_JITTER_FRACTION = 0.15

# Optional shared-secret auth: set MRT2_SERVER_KEY to require a matching
# X-Internal-Key header on /generate. Left unset, the server stays open
# (fine for 127.0.0.1-only local use) -- but this MUST be set once the
# server is reachable over a network (e.g. exposed via Tailscale for a
# remote demo), since /generate has no other access control.
_SERVER_KEY = os.environ.get("MRT2_SERVER_KEY")


def _wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
    """Encode (N, channels) float samples in [-1, 1] as 16-bit PCM WAV bytes."""
    audio = np.clip(samples, -1.0, 1.0)
    frames = (audio * 32767).astype("<i2")  # already (N, channels)
    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(frames.shape[1])
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(frames.tobytes())
    return bio.getvalue()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        log.info("%s - %s", self.address_string(), fmt % args)

    def do_GET(self):
        if self.path == "/health":
            self._respond_json(200, {
                "status": "ok",
                "model": _model_name,
                "device_platform": _device_info["platform"],
                "device_kind": _device_info["kind"],
                "gpu_ready": _device_info["platform"] == "gpu",
            })
        else:
            self._respond_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/reset":
            self._handle_reset()
            return
        if self.path != "/generate":
            self._respond_json(404, {"error": "not found"})
            return
        if _SERVER_KEY and self.headers.get("X-Internal-Key") != _SERVER_KEY:
            self._respond_json(401, {"error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            prompt = body.get("prompt", "")
            duration = float(body.get("duration", 4.0))
            requested_model = body.get("model")
            temperature = body.get("temperature")
            top_k = body.get("top_k")
            reset = bool(body.get("reset", False))
        except Exception as e:
            self._respond_json(400, {"error": f"bad request: {e}"})
            return

        if duration <= 0 or duration > MAX_DURATION_SECONDS:
            self._respond_json(400, {
                "error": f"duration must be in (0, {MAX_DURATION_SECONDS}] seconds, got {duration}"
            })
            return

        if requested_model and requested_model != _model_name:
            self._respond_json(400, {
                "error": f"server has model={_model_name!r} loaded, cannot serve model={requested_model!r}. "
                         f"Restart the server with --model {requested_model} instead."
            })
            return

        global _state
        try:
            with _GENERATION_LOCK:
                t0 = time.time()
                embedding = _mrt.embed_style(prompt, use_mapper=True)
                frames = max(1, int(duration * FRAMES_PER_SECOND))
                if temperature is None:
                    lo = _mrt.temperature * (1.0 - TEMPERATURE_JITTER_FRACTION)
                    hi = _mrt.temperature * (1.0 + TEMPERATURE_JITTER_FRACTION)
                    temperature = random.uniform(lo, hi)
                incoming_state = None if reset else _state
                continued = incoming_state is not None
                wav, new_state = _mrt.generate(
                    style=embedding, frames=frames,
                    temperature=float(temperature),
                    top_k=int(top_k) if top_k is not None else None,
                    state=incoming_state,
                )
                _state = new_state
                data = _wav_bytes(np.array(wav.samples), wav.sample_rate)
                log.info("generated %.1fs of audio in %.2fs (prompt=%r, temperature=%.4f, continued=%s)",
                          duration, time.time() - t0, prompt[:80], temperature, continued)
        except Exception as e:
            log.exception("generation failed")
            self._respond_json(500, {"error": str(e)})
            return

        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Temperature-Used", f"{temperature:.6f}")
        self.send_header("X-State-Continued", "true" if continued else "false")
        self.end_headers()
        self.wfile.write(data)

    def _handle_reset(self):
        global _state
        if _SERVER_KEY and self.headers.get("X-Internal-Key") != _SERVER_KEY:
            self._respond_json(401, {"error": "unauthorized"})
            return
        with _GENERATION_LOCK:
            _state = None
        log.info("session state reset")
        self._respond_json(200, {"status": "reset"})

    def _respond_json(self, status, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    global _mrt, _model_name, _device_info
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="mrt2_small")
    parser.add_argument("--port", type=int, default=8799)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    import jax
    from magenta_rt import MagentaRT2Jax

    log.info("Loading MRT2 model %s (this triggers the JAX JIT compile, ~15-20s)...", args.model)
    _mrt = MagentaRT2Jax(size=args.model)
    _model_name = args.model
    # Warm up the JIT compile immediately so the first real request is fast.
    _mrt.generate(style=_mrt.embed_style("warmup", use_mapper=True), frames=1)
    log.info("MRT2 model ready and warmed up.")

    # JAX silently falls back to CPU when the GPU CUDA libs are broken (see
    # mrt2_poc/README.txt section 4(2)) -- no exception is raised, generation
    # just gets much slower. Surface the actual backend on /health so this is
    # checkable with a single curl instead of discovered live during a demo.
    device = jax.devices()[0]
    _device_info = {"platform": device.platform, "kind": device.device_kind}
    log.info("JAX backend device: platform=%s kind=%s", device.platform, device.device_kind)
    if device.platform != "gpu":
        log.warning("MRT2 is running on %s, not GPU -- generation will be far slower than expected.",
                    device.platform)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    log.info("MRT2 server listening on http://%s:%d", args.host, args.port)
    server.serve_forever()


if __name__ == "__main__":
    main()
