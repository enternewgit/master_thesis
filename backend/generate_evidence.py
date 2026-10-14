#!/usr/bin/env python3
"""
generate_evidence.py

Create WAV files for paper evidence:
- Reproducibility: 5 trials for Happy (1.0,1.0) and Sad (0.0,0.0)
- Transition: 5 steps from 0.0 -> 1.0 (0.0,0.25,0.5,0.75,1.0)

Saves files into an output directory as out_<CV>_<CA>_<TV>_<TA>.wav
or out_<CV>_<CA>_<TV>_<TA>_trialN.wav for reproducibility trials.

Usage:
python generate_evidence.py --outdir generated_evidence
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime
from typing import Tuple

import pandas as pd
import requests

URL = "http://localhost:8000/experiment/feedback"
experiment_logs = []


def pct_int(x: float) -> int:
    try:
        return int(round(float(x) * 100))
    except Exception:
        return 0


def save_streamed_response(r: requests.Response, out_dir: str, trial_suffix: str | None = None) -> str:
    os.makedirs(out_dir, exist_ok=True)
    tmp_path = os.path.join(out_dir, "tmp_download.wav")
    with open(tmp_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    # prefer server-provided filename
    server_fname = r.headers.get("X-Output-Filename")
    if server_fname:
        final_name = server_fname
    else:
        cv = pct_int(float(r.headers.get("X-Current-Valence", 0.0)))
        ca = pct_int(float(r.headers.get("X-Current-Arousal", 0.0)))
        tv = pct_int(float(r.headers.get("X-Target-Valence", 0.0)))
        ta = pct_int(float(r.headers.get("X-Target-Arousal", 0.0)))
        final_name = f"out_{cv}_{ca}_{tv}_{ta}.wav"
    if trial_suffix:
        name, ext = os.path.splitext(final_name)
        final_name = f"{name}_trial{trial_suffix}{ext}"

    final_path = os.path.join(out_dir, final_name)
    try:
        os.replace(tmp_path, final_path)
    except Exception:
        # fallback: copy
        import shutil

        shutil.copyfile(tmp_path, final_path)
        os.remove(tmp_path)
    return final_path


def post_generate(current_v: float, current_a: float, target_v: float, target_a: float, duration: int, alpha: float, out_dir: str, trial: int | None = None, provider: str = "stable") -> str:
    payload = {
        "samples": [[0] * 1024 for _ in range(4)],
        "target_valence": float(target_v),
        "target_arousal": float(target_a),
        "alpha": float(alpha),
        "override_current": True,
        "override_current_valence": float(current_v),
        "override_current_arousal": float(current_a),
        "duration": int(duration),
        "provider": provider,
    }
    r = requests.post(URL, json=payload, stream=True, timeout=(10, 600))
    r.raise_for_status()
    trial_suffix = str(trial) if trial is not None else None
    saved = save_streamed_response(r, out_dir, trial_suffix)
    print("Saved ->", saved)
    return saved


def log_result(filename: str, target_val: float, target_aro: float, test_type: str):
    experiment_logs.append(
        {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "filename": filename,
            "target_valence": float(target_val),
            "target_arousal": float(target_aro),
            "test_type": test_type,
        }
    )


def save_csv():
    if not experiment_logs:
        return
    df = pd.DataFrame(experiment_logs)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name = f"experiment_log_{stamp}.csv"
    df.to_csv(out_name, index=False)
    print(f"Experiment log saved -> {out_name}")


def run_reproducibility_test(n_trials: int, out_dir: str, provider: str = "stable"):
    print("Running reproducibility tests:")
    # Happy
    for i in range(1, n_trials + 1):
        print(f"Happy trial {i}/{n_trials}")
        saved = post_generate(1.0, 1.0, 1.0, 1.0, duration=10, alpha=0.5, out_dir=out_dir, trial=i, provider=provider)
        log_result(saved, 1.0, 1.0, "repro_happy")
    # Sad
    for i in range(1, n_trials + 1):
        print(f"Sad trial {i}/{n_trials}")
        saved = post_generate(0.0, 0.0, 0.0, 0.0, duration=10, alpha=0.5, out_dir=out_dir, trial=i, provider=provider)
        log_result(saved, 0.0, 0.0, "repro_sad")


def run_transition_test(steps: int, out_dir: str, provider: str = "stable"):
    print("Running transition test (Sad->Happy):")
    # steps: number of states (e.g., 5 -> 0.0,0.25,0.5,0.75,1.0)
    for idx in range(steps):
        val = idx / float(steps - 1)
        print(f"Step {idx+1}/{steps}: current={val:.2f}")
        # use current=val, target=1.0 to show steering toward happy
        saved = post_generate(val, val, 1.0, 1.0, duration=10, alpha=0.5, out_dir=out_dir, trial=None, provider=provider)
        log_result(saved, 1.0, 1.0, "transition")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--outdir", default="generated_evidence", help="Output directory")
    p.add_argument("--repro_trials", type=int, default=5, help="Reproducibility trials per condition")
    p.add_argument("--transition_steps", type=int, default=5, help="Transition steps count")
    p.add_argument("--provider", default="stable", help="Music generation backend: 'stable' or 'mrt2'")
    args = p.parse_args()

    run_reproducibility_test(args.repro_trials, args.outdir, provider=args.provider)
    run_transition_test(args.transition_steps, args.outdir, provider=args.provider)


if __name__ == "__main__":
    main()
    save_csv()
