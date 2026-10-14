"""EEG emotion prediction helper.

Place model-loading and inference logic here. This file is intentionally
lightweight and contains TODO comments showing where to implement the
PyTorch model architecture, loading, preprocessing, and postprocessing.
"""
from typing import Any, Dict
import numpy as np

# Optionally import torch if available in your environment
try:
    import torch
except Exception:
    torch = None

# Global handle for the loaded model
_MODEL = None

def load_model(path: str):
    """
    Load the trained model from `path` (a .pth file).

    TODO: replace the pseudo-code below with the actual model class and
    loading procedure used during training. Keep this function synchronous
    so it can be called at FastAPI startup.
    """
    global _MODEL
    if torch is None:
        raise RuntimeError("PyTorch is not available in the environment")

    # === TODO: Implement model architecture ===
    # Example pattern:
    # from .your_model_file import YourModelClass
    # model = YourModelClass(*args)
    # state = torch.load(path, map_location=torch.device('cpu'))
    # model.load_state_dict(state)
    # model.eval()
    # _MODEL = model

    raise NotImplementedError("Implement model creation and loading here")


def predict(eeg_array: np.ndarray) -> Dict[str, Any]:
    """
    Run inference on a numpy array of EEG data and return a dictionary of
    predictions (for example: arousal / valence scores or class probabilities).

    Inputs:
    - eeg_array: numpy array shape should match what the model expects

    Returns:
    - dict with prediction results, e.g. {"arousal": 0.12, "valence": -0.3}
    """
    global _MODEL
    if _MODEL is None:
        raise RuntimeError("Model not loaded. Call load_model(path) at startup.")

    # === TODO: implement preprocessing ===
    # Example:
    # tensor = torch.from_numpy(eeg_array).float().unsqueeze(0)  # add batch
    # with torch.no_grad():
    #     out = _MODEL(tensor)
    # # postprocess to return friendly json
    # return {"arousal": float(out[0,0]), "valence": float(out[0,1])}

    raise NotImplementedError("Implement inference/preprocessing/postprocessing here")
