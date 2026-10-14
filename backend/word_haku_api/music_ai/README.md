music_ai
========

This package groups helper utilities for audio / music / EEG models used by
the `word_haku_api` service.

Developer notes
- Implement model classes (or import them) and fill `loader.load_model`.
- Implement preprocessing + inference in `infer.py` functions.
- Call `loader.load_model("my_model", "/path/to/file.pth")` during FastAPI
  startup (e.g. in a router `@on_event("startup")`).

Environment variables
- `EEG_MODEL_PATH` or other names can be used to point to .pth files.
