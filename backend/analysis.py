#!/usr/bin/env python3
"""
analysis.py

簡易可視化ツール（論文用）
- 2つのオーディオファイルを比較してスペクトログラム・波形を出力
- スペクトル中心周波数 / 帯域幅 / RMS をCSVで保存

使い方の一例:
python analysis.py --file1 happy.wav --file2 sad.wav --label1 "Valence=1.0 (Happy)" --label2 "Valence=0.0 (Sad)" --outdir viz

依存: librosa, matplotlib, numpy
"""
from __future__ import annotations

import argparse
import csv
import os
from typing import Dict, Tuple

import librosa
import librosa.display
import matplotlib.pyplot as plt
import numpy as np


def load_audio(path: str, sr: int | None = None) -> Tuple[np.ndarray, int]:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Audio file not found: {path}. Use an absolute path or place the file in the current working directory."
        )
    try:
        y, sr = librosa.load(path, sr=sr, mono=True)
    except Exception as e:
        raise RuntimeError(f"Failed to load audio '{path}': {e}") from e
    return y, sr


def ensure_outdir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def compute_stats(y: np.ndarray, sr: int) -> Dict[str, float]:
    if y.size == 0:
        return {"centroid": 0.0, "bandwidth": 0.0, "rms": 0.0}
    # Pre-compute STFT once to avoid redundant computation in spectral features
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512))
    centroid = float(librosa.feature.spectral_centroid(S=S, sr=sr)[0].mean())
    bandwidth = float(librosa.feature.spectral_bandwidth(S=S, sr=sr)[0].mean())
    rms = float(librosa.feature.rms(y=y)[0].mean())
    return {"centroid": centroid, "bandwidth": bandwidth, "rms": rms}


def plot_spectrogram(ax, y: np.ndarray, sr: int, title: str):
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512))
    D = librosa.amplitude_to_db(S, ref=np.max)
    img = librosa.display.specshow(D, sr=sr, x_axis="time", y_axis="log", ax=ax, cmap="magma")
    ax.set_title(title)
    return img


def plot_waveform(ax, y: np.ndarray, sr: int, title: str):
    times = np.arange(len(y)) / sr if sr and len(y) > 0 else np.array([0.0])
    ax.plot(times, y, linewidth=0.5)
    ax.set_xlim(0, times[-1] if times.size > 0 else 1)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Amplitude")
    ax.set_title(title)


def save_stats_csv(stats1: Dict[str, float], stats2: Dict[str, float], label1: str, label2: str, outdir: str) -> str:
    keys = ["label", "centroid", "bandwidth", "rms"]
    csv_path = os.path.join(outdir, "stats_comparison.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        row1 = {"label": label1, "centroid": stats1["centroid"], "bandwidth": stats1["bandwidth"], "rms": stats1["rms"]}
        row2 = {"label": label2, "centroid": stats2["centroid"], "bandwidth": stats2["bandwidth"], "rms": stats2["rms"]}
        w.writerow(row1)
        w.writerow(row2)
    return csv_path


def compare_and_visualize(file1: str, file2: str, label1: str, label2: str, outdir: str) -> Dict[str, str]:
    outdir = ensure_outdir(outdir)

    y1, sr1 = load_audio(file1)
    y2, sr2 = load_audio(file2)

    if sr1 != sr2:
        y2 = librosa.resample(y2, orig_sr=sr2, target_sr=sr1)
        sr2 = sr1

    stats1 = compute_stats(y1, sr1)
    stats2 = compute_stats(y2, sr2)

    fig, axes = plt.subplots(4, 1, figsize=(12, 10), constrained_layout=True)

    img1 = plot_spectrogram(axes[0], y1, sr1, f"{label1} - Spectrogram")
    img2 = plot_spectrogram(axes[1], y2, sr2, f"{label2} - Spectrogram")

    plot_waveform(axes[2], y1, sr1, f"{label1} - Waveform")
    plot_waveform(axes[3], y2, sr2, f"{label2} - Waveform")

    cbar = fig.colorbar(img1, ax=axes[:2], orientation="vertical", fraction=0.02)
    cbar.set_label("dB")
    fig.suptitle(f"{label1} vs {label2}")

    out_png = os.path.join(outdir, "comparison_spectrogram_waveform.png")
    fig.savefig(out_png, dpi=300)
    plt.close(fig)

    csv_path = save_stats_csv(stats1, stats2, label1, label2, outdir)

    return {"image": out_png, "csv": csv_path}


def main():
    p = argparse.ArgumentParser(description="Compare two audio files and produce spectrogram/waveform and simple stats CSV")
    p.add_argument("--file1", required=True, help="Path to first audio file (e.g., Valence=1.0)")
    p.add_argument("--file2", required=True, help="Path to second audio file (e.g., Valence=0.0)")
    p.add_argument("--label1", default="File 1", help="Label for first file")
    p.add_argument("--label2", default="File 2", help="Label for second file")
    p.add_argument("--outdir", default="analysis_viz", help="Output directory")
    args = p.parse_args()

    res = compare_and_visualize(args.file1, args.file2, args.label1, args.label2, args.outdir)
    print("Saved image:", res["image"]) 
    print("Saved CSV:", res["csv"]) 


if __name__ == "__main__":
    main()
