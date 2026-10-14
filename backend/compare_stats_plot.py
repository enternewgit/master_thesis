#!/usr/bin/env python3
"""compare_stats_plot.py

Read happy/sad stats CSVs, combine into one CSV, compute mean/std for Centroid and RMS,
and save a centroid bar plot with error bars (Happy vs Sad).

Usage:
poetry run python compare_stats_plot.py --happy viz_by_label/happy/stats_happy.csv --sad viz_by_label/sad/stats_sad.csv --outdir viz_stats
"""
from __future__ import annotations

import argparse
import os

import matplotlib.pyplot as plt
import pandas as pd


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--happy", default="viz_by_label/happy/stats_happy.csv")
    p.add_argument("--sad", default="viz_by_label/sad/stats_sad.csv")
    p.add_argument("--outdir", default="viz_stats")
    args = p.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    df_h = pd.read_csv(args.happy)
    df_h = df_h.copy()
    df_h["label"] = "Happy"

    df_s = pd.read_csv(args.sad)
    df_s = df_s.copy()
    df_s["label"] = "Sad"

    df = pd.concat([df_h, df_s], ignore_index=True)
    combined_csv = os.path.join(args.outdir, "combined_stats.csv")
    df.to_csv(combined_csv, index=False)

    # compute mean/std for centroid and rms
    stats = df.groupby("label")[ ["centroid", "rms"] ].agg(["mean", "std"]).round(6)
    stats_csv = os.path.join(args.outdir, "summary_stats.csv")
    stats.to_csv(stats_csv)

    # centroid bar plot
    means = stats["centroid"]["mean"]
    stds = stats["centroid"]["std"]

    fig, ax = plt.subplots(figsize=(6, 4))
    x = range(len(means))
    ax.bar(x, means.values, yerr=stds.values, capsize=8, color=["#4CAF50", "#2196F3"])
    ax.set_xticks(x)
    ax.set_xticklabels(means.index)
    ax.set_ylabel("Spectral Centroid (Hz)")
    ax.set_title("Spectral Centroid: Happy vs Sad (mean ± std)")
    out_png = os.path.join(args.outdir, "centroid_bar.png")
    fig.savefig(out_png, dpi=200)
    plt.close(fig)

    # also create RMS bar plot
    means_r = stats["rms"]["mean"]
    stds_r = stats["rms"]["std"]
    fig2, ax2 = plt.subplots(figsize=(6, 4))
    ax2.bar(x, means_r.values, yerr=stds_r.values, capsize=8, color=["#FF9800", "#9C27B0"])
    ax2.set_xticks(x)
    ax2.set_xticklabels(means_r.index)
    ax2.set_ylabel("RMS (linear)")
    ax2.set_title("RMS: Happy vs Sad (mean ± std)")
    out_png2 = os.path.join(args.outdir, "rms_bar.png")
    fig2.savefig(out_png2, dpi=200)
    plt.close(fig2)

    print("Wrote:")
    print(" - combined CSV:", combined_csv)
    print(" - summary stats:", stats_csv)
    print(" - centroid plot:", out_png)
    print(" - rms plot:", out_png2)


if __name__ == "__main__":
    main()
