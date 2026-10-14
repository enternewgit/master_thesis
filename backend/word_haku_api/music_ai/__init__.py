"""music_ai package: place music / EEG related model helpers here.

This package is intended to group modules for audio / music / EEG AI
functionality (model loaders, inference helpers, preprocessing utilities).

Files to implement:
- loader.py: load .pth / weights
- infer.py: inference wrappers that return JSON-serializable results

Fill functions with your model specifics (architecture, preprocessing).
"""

from .loader import load_model  # type: ignore
from .infer import predict_from_eeg, predict_from_audio  # type: ignore
