from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import numpy as np
from decouple import config
import os

from ..music_ai.loader import load_emotion_model, get_model
from ..music_ai.infer import predict_from_eeg
from ..music_ai.eeg_preprocess import MUSE_INPUT_FS, MODEL_EEG_FS, resample_eeg_channels, resample_eeg_batch

router = APIRouter()


class EEGPredictBody(BaseModel):
    # `samples` should be a 2D list (channels x time) or a shape your model expects
    samples: list


@router.on_event("startup")
async def startup_load_model():
    # Load valence and arousal model paths from environment or defaults
    valence_path = config('EMO_VALENCE_PATH', default=os.path.join(os.path.dirname(__file__), '..', '..', '..', 'valence.pth'))
    arousal_path = config('EMO_AROUSAL_PATH', default=os.path.join(os.path.dirname(__file__), '..', '..', '..', 'arousal.pth'))
    try:
        # register under name 'emotion'
        load_emotion_model('emotion', valence_path=valence_path, arousal_path=arousal_path)
    except Exception:
        # loader will raise if torch is missing or NotImplementedError
        pass


def _predict_from_samples(raw_samples: list) -> dict:
    """Validate, preprocess, and run EEGMamba prediction on raw EEG samples.

    `raw_samples` is a 2D (channels x seq) or 3D (batch x channels x seq)
    nested list/array of floats at the raw 256Hz Muse sample rate. Raises
    HTTPException (400) for client-caused errors (bad shape/values), or
    RuntimeError if the model itself isn't available. Shared by both the
    POST /predict endpoint and the /ws WebSocket endpoint.
    """
    arr = np.array(raw_samples, dtype=float)

    # If the model wasn't loaded at startup, try lazy-loading it now
    if get_model('emotion') is None:
        valence_path = config('EMO_VALENCE_PATH', default=os.path.join(os.path.dirname(__file__), '..', '..', '..', 'valence.pth'))
        arousal_path = config('EMO_AROUSAL_PATH', default=os.path.join(os.path.dirname(__file__), '..', '..', '..', 'arousal.pth'))
        try:
            load_emotion_model('emotion', valence_path=valence_path, arousal_path=arousal_path)
        except Exception as e:
            raise RuntimeError(f"Failed to load emotion model: {e}")

    # Validate input shape and values against model params
    model = get_model('emotion')
    if model is None:
        raise RuntimeError("Model 'emotion' not loaded")

    params = getattr(model, 'params', {}) or {}
    expected_channels = int(params.get('n_channels', 4))
    expected_seq = int(params.get('seq_len', 100))

    if arr.size == 0:
        raise HTTPException(status_code=400, detail="'samples' is empty")

    if not np.isfinite(arr).all():
        raise HTTPException(status_code=400, detail="'samples' contains non-finite values (NaN or Inf)")

    # Shared preprocessing with /experiment/feedback:
    # assume Muse2 stream is 256Hz and resample to model-side 200Hz before inference.
    # Compatibility fallback: if already aligned with expected_seq, keep original.
    arr_before = arr
    try:
        if arr.ndim == 2:
            arr = resample_eeg_channels(arr, src_fs=MUSE_INPUT_FS, dst_fs=MODEL_EEG_FS)
        elif arr.ndim == 3:
            arr = resample_eeg_batch(arr, src_fs=MUSE_INPUT_FS, dst_fs=MODEL_EEG_FS)
        else:
            raise HTTPException(status_code=400, detail="'samples' must be a 2D (channels x seq) or 3D (batch x channels x seq) numeric array")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"EEG resampling failed: {e}")

    if arr.ndim == 2:
        # (channels, seq_len)
        ch, seq = arr.shape
        if ch != expected_channels or seq != expected_seq:
            ch0, seq0 = arr_before.shape
            if ch0 == expected_channels and seq0 == expected_seq:
                arr = arr_before
            else:
                raise HTTPException(status_code=400, detail=f"Expected samples shape (channels={expected_channels}, seq_len={expected_seq}) for 2D input, got ({ch}, {seq})")
    elif arr.ndim == 3:
        # (batch, channels, seq_len)
        b, ch, seq = arr.shape
        if ch != expected_channels or seq != expected_seq:
            b0, ch0, seq0 = arr_before.shape
            if ch0 == expected_channels and seq0 == expected_seq:
                arr = arr_before
            else:
                raise HTTPException(status_code=400, detail=f"Expected samples shape (batch, channels={expected_channels}, seq_len={expected_seq}) for 3D input, got (batch={b}, channels={ch}, seq_len={seq})")
    else:
        raise HTTPException(status_code=400, detail="'samples' must be a 2D (channels x seq) or 3D (batch x channels x seq) numeric array")

    return predict_from_eeg('emotion', arr)


@router.post("/predict")
async def predict_emotion(body: EEGPredictBody):
    try:
        return _predict_from_samples(body.samples)
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def emotion_status():
    """Return load status and basic info about the registered emotion model."""
    try:
        model = get_model('emotion')
        if model is None:
            return {"loaded": False}

        valence_ok = getattr(model, 'model_v', None) is not None
        arousal_ok = getattr(model, 'model_a', None) is not None

        info = {
            "loaded": True,
            "valence_loaded": bool(valence_ok),
            "arousal_loaded": bool(arousal_ok),
            "params": getattr(model, 'params', None)
        }
        return info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/ws")
async def eeg_emotion_ws(websocket: WebSocket):
    """Continuous valence/arousal prediction over WebSocket.

    Client sends {"samples": <2D or 3D nested list>} messages (same shape
    POST /predict accepts) at whatever cadence it likes; each message gets
    one prediction back. No producer/consumer queue like some reference
    implementations use — the client already paces sends (500ms in the
    frontend) and inference is fast, so a plain sequential
    receive->infer->send loop is enough.
    """
    await websocket.accept()
    try:
        while True:
            try:
                data = await websocket.receive_json()
                result = _predict_from_samples(data.get("samples", []))
            except WebSocketDisconnect:
                raise
            except HTTPException as e:
                await websocket.send_json({"error": str(e.detail)})
                continue
            except Exception as e:
                await websocket.send_json({"error": str(e)})
                continue
            try:
                await websocket.send_json(result)
            except WebSocketDisconnect:
                raise
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
