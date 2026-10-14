"""Model loader utilities for music/EEG models.

Put code here to construct your PyTorch model class and load weights from a
.pth file. Keep load functions synchronous so they can be called in FastAPI
startup events.
"""
from typing import Any, Dict, Optional
try:
    import torch
except Exception:
    torch = None

_MODEL_REGISTRY: Dict[str, Any] = {}


def load_model(name: str, path: str) -> Any:
    """Generic loader placeholder. Kept for backward-compat but not implemented.

    Use `load_emotion_model` for the EEG valence/arousal pair.
    """
    raise NotImplementedError("Use load_emotion_model for emotion models or implement custom loader")


def load_emotion_model(name: str, valence_path: str, arousal_path: str, params: Optional[Dict] = None) -> Any:
    """Load valence + arousal models as an EmotionModel and register it.

    Returns the created EmotionModel instance.
    """
    if torch is None:
        raise RuntimeError("torch not available; install PyTorch to load models")

    from .emotion_model import EmotionModel

    # Prefer adaptive loading: detect checkpoint dims and instantiate accordingly
    try:
        model = EmotionModel.load_from_checkpoints(valence_path=valence_path, arousal_path=arousal_path, params=params)
        _MODEL_REGISTRY[name] = model
        return model
    except Exception as e:
        # fallback to legacy constructor
        try:
            model = EmotionModel(valence_path=valence_path, arousal_path=arousal_path, params=params)
            _MODEL_REGISTRY[name] = model
            return model
        except Exception as e2:
            raise RuntimeError(f"Failed to load emotion model adaptively or via legacy path: {e}; {e2}")


def get_model(name: str):
    return _MODEL_REGISTRY.get(name)
