"""Inference helpers for music_ai.

Functions here should be small wrappers that accept numpy arrays or lists
and return JSON-serializable dicts. They should call models loaded via
`loader.get_model(name)` and perform preprocessing and postprocessing.
"""
from typing import Any, Dict
import numpy as np

from .loader import get_model


def predict_from_eeg(model_name: str, eeg_samples: np.ndarray) -> Dict:
    """Run EEG-based prediction using a loaded model.

    - `eeg_samples` should be a numpy array shaped appropriately for your model.
    - Returns a JSON-serializable dict.
    """
    model = get_model(model_name)
    if model is None:
        raise RuntimeError(f"Model '{model_name}' not loaded")

    # Expect model to be an EmotionModel-like object exposing `predict` method
    try:
        valence, arousal = model.predict(eeg_samples)
        return {"valence": float(valence), "arousal": float(arousal)}
    except Exception as e:
        raise RuntimeError(f"Inference failed: {e}")


def predict_batch_from_eeg(model_name: str, eeg_batch: np.ndarray) -> list:
    """Run batch EEG prediction for multiple windows at once.

    - `eeg_batch`: numpy array shaped (batch, channels, seq_len).
    - Returns a list of dicts [{"valence": float, "arousal": float}, ...].
    """
    model = get_model(model_name)
    if model is None:
        raise RuntimeError(f"Model '{model_name}' not loaded")

    try:
        results = model.predict_batch(eeg_batch)
        return [{"valence": float(v), "arousal": float(a)} for v, a in results]
    except Exception as e:
        raise RuntimeError(f"Batch inference failed: {e}")


def predict_from_audio(model_name: str, audio_array: np.ndarray, sr: int) -> Dict:
    """Run model on raw audio (numpy array) and return results.

    TODO: implement audio preprocessing (mel spectrograms, normalization).
    """
    model = get_model(model_name)
    if model is None:
        raise RuntimeError(f"Model '{model_name}' not loaded")

    raise NotImplementedError("Implement predict_from_audio for audio models")
