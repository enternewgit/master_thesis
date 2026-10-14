#!/usr/bin/env python3
"""per_file_viz.py

Generate per-file spectrogram+waveform images and CSV stats grouped by target label
(happy/sad) using the experiment log to determine targets.

Usage:
python per_file_viz.py --indir generated_evidence --log experiment_log_20260212_003847.csv --outdir viz_by_label
"""
from __future__ import annotations

import argparse
import csv
import os
from typing import Dict, List

import matplotlib.pyplot as plt

from analysis import load_audio, compute_stats, plot_spectrogram, plot_waveform, ensure_outdir


def find_log_file(log_path: str | None) -> str | None:
    if log_path:
        return log_path if os.path.exists(log_path) else None
    # find newest experiment_log_*.csv
    files = sorted([f for f in os.listdir(".") if f.startswith("experiment_log_") and f.endswith(".csv")])
    return files[-1] if files else None


def read_experiment_log(log_file: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with open(log_file, "r", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(row)
    return rows


def classify_target(target_valence: str) -> str:
    try:
        v = float(target_valence)
    except Exception:
        v = 0.0
    return "happy" if v >= 0.5 else "sad"


def process_files(rows: List[Dict[str, str]], indir: str, outdir: str):
    groups: Dict[str, List[Dict[str, str]]] = {"happy": [], "sad": []}
    for r in rows:
        fname = r.get("filename") or r.get("file") or r.get("filename")
        if not fname:
            continue
        # ensure path refers to file under indir if relative
        if not os.path.exists(fname):
            candidate = os.path.join(indir, os.path.basename(fname))
            if os.path.exists(candidate):
                fname = candidate
        label = classify_target(r.get("target_valence", "0.0"))
        groups[label].append({"path": fname, "row": r})

    for label, items in groups.items():
        if not items:
            print(f"No files for label {label}")
            continue
        label_out = ensure_outdir(os.path.join(outdir, label))
        stats_csv = os.path.join(label_out, f"stats_{label}.csv")
        with open(stats_csv, "w", newline="") as outf:
            w = csv.writer(outf)
            w.writerow(["filename", "centroid", "bandwidth", "rms"])
            for it in items:
                path = it["path"]
                base = os.path.basename(path)
                try:
                    y, sr = load_audio(path)
                except Exception as e:
                    print(f"Failed to load {path}: {e}")
                    continue

                stats = compute_stats(y, sr)

                # save image (spec + waveform)
                fig, axes = plt.subplots(2, 1, figsize=(10, 6), constrained_layout=True)
                img = plot_spectrogram(axes[0], y, sr, f"{base} - Spectrogram")
                plot_waveform(axes[1], y, sr, f"{base} - Waveform")
                cbar = fig.colorbar(img, ax=axes[0], orientation="vertical", fraction=0.02)
                cbar.set_label("dB")
                out_png = os.path.join(label_out, f"{os.path.splitext(base)[0]}_spec_wave.png")
                fig.savefig(out_png, dpi=200)
                plt.close(fig)

                w.writerow([base, stats.get("centroid", 0.0), stats.get("bandwidth", 0.0), stats.get("rms", 0.0)])
                print(f"Wrote {out_png} and appended stats for {base}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--indir", default="generated_evidence", help="Input directory for generated audio")
    p.add_argument("--log", default=None, help="Experiment log CSV (optional). If omitted, picks latest experiment_log_*.csv")
    p.add_argument("--outdir", default="viz_by_label", help="Output base directory")
    args = p.parse_args()

    log_file = find_log_file(args.log)
    if not log_file:
        print("No experiment log found. Please pass --log experiment_log_*.csv")
        return

    rows = read_experiment_log(log_file)
    # rows should contain 'filename' and 'target_valence' columns per generate_evidence.py
    process_files(rows, args.indir, args.outdir)


if __name__ == "__main__":
    main()
