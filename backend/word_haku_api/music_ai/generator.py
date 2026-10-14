"""Music generation helpers for the API.

Generates audio via the local Magenta RealTime 2 (MRT2) server. Returns a
streaming iterator and the response content-type so the FastAPI route can
stream audio to clients.

Environment variables used:
- MRT2_SERVER_URL, MRT2_SERVER_KEY (see generate_mrt2_local.py)
- MRT2_LOCAL_MODEL

The functions raise RuntimeError on provider errors.
"""
from typing import Iterator, Optional, Dict, Any
import asyncio
import os
import tempfile
import pathlib

from .generate_mrt2_local import generate_local as generate_mrt2_local


def _file_iterator(path: str, chunk_size: int = 8192) -> Iterator[bytes]:
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk
    finally:
        # remove temp file after streaming
        try:
            pathlib.Path(path).unlink()
        except Exception:
            pass


def _require_mrt2(provider: Optional[str]) -> None:
    provider = (provider or "mrt2").lower()
    if provider != "mrt2":
        raise RuntimeError(f"Unsupported provider: {provider!r} (only 'mrt2' is supported)")


def generate(prompt: str, *, provider: str = "mrt2", duration: Optional[int] = None, params: Optional[Dict[str, Any]] = None):
    """Generate audio via MRT2 and return {"iterable": ..., "content_type": ...}."""
    _require_mrt2(provider)
    try:
        tmp = tempfile.NamedTemporaryFile(prefix="mrt2_local_", suffix=".wav", delete=False)
        tmp.close()
        out_path = tmp.name
        generate_mrt2_local(prompt, out_path=out_path, seconds_total=(duration or 8),
                             model=os.environ.get("MRT2_LOCAL_MODEL", "mrt2_small"))
        return {"iterable": _file_iterator(out_path), "content_type": "audio/wav"}
    except Exception as e:
        raise RuntimeError(f"Local MRT2 generation failed: {e}")


async def generate_async(prompt: str, *, provider: str = "mrt2", duration: Optional[int] = None, params: Optional[Dict[str, Any]] = None):
    """Async version of generate() using a background thread for the (blocking) MRT2 call."""
    _require_mrt2(provider)
    try:
        tmp = tempfile.NamedTemporaryFile(prefix="mrt2_local_", suffix=".wav", delete=False)
        tmp.close()
        out_path = tmp.name
        await asyncio.to_thread(
            generate_mrt2_local,
            prompt,
            out_path=out_path,
            seconds_total=(duration or 8),
            model=os.environ.get("MRT2_LOCAL_MODEL", "mrt2_small"),
        )
        return {"iterable": _file_iterator(out_path), "content_type": "audio/wav"}
    except Exception as e:
        raise RuntimeError(f"Local MRT2 generation failed: {e}")
