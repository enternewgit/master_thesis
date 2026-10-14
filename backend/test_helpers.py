"""Shared test helpers for feedback endpoint tests."""
import os
import requests


def do_test(name: str, payload: dict, out_fname: str, url: str = "http://localhost:8000/experiment/feedback", timeout=(10, 300)):
    """Send a feedback request, print diagnostics, and save the response to a file.

    If the server returns an X-Output-Filename header, the file is renamed accordingly.
    """
    print("==", name)
    r = requests.post(url, json=payload, stream=True, timeout=timeout)
    print("status:", r.status_code)
    print("headers:")
    for k, v in r.headers.items():
        if k.startswith("X-"):
            print(" ", k, v)

    # Save to temp file first
    tmp_path = out_fname + ".tmp"
    with open(tmp_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    # Determine final filename from server header or valence/arousal headers
    server_fname = r.headers.get("X-Output-Filename")
    if server_fname:
        new_fname = server_fname
    else:
        def _pct_from_header(key: str, default: float = 0.0) -> int:
            try:
                val = float(r.headers.get(key, None))
                return int(round(val * 100))
            except Exception:
                return int(round(default * 100))

        cv_pct = _pct_from_header("X-Current-Valence", 0.0)
        ca_pct = _pct_from_header("X-Current-Arousal", 0.0)
        tv_pct = _pct_from_header("X-Target-Valence", 0.0)
        ta_pct = _pct_from_header("X-Target-Arousal", 0.0)
        new_fname = f"out_{cv_pct}_{ca_pct}_{tv_pct}_{ta_pct}.wav"

    out_dir = os.path.dirname(os.path.abspath(out_fname)) or os.getcwd()
    final_path = os.path.join(out_dir, new_fname)
    try:
        os.replace(tmp_path, final_path)
        print("saved:", final_path)
    except Exception:
        print("saved (tmp):", tmp_path)
    print("Server console should contain the generated prompt line: [experiment] prompt: ...")
    print()
