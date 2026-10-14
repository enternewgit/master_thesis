#!/usr/bin/env python3
"""generate_slide_figs.py

Create high-resolution centroid/RMS bar plots and a short slide caption
using combined stats and RMS test results produced earlier.

Usage:
python generate_slide_figs.py --in /path/to/viz_stats_n10 --out /path/to/viz_stats_n10
"""
from __future__ import annotations

import argparse
import os

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np


def read_rms_pvals(txtpath: str) -> dict:
    res = {}
    if not os.path.exists(txtpath):
        return res
    with open(txtpath, 'r') as f:
        txt = f.read()
    # try to extract p-values and Cohen's d
    for line in txt.splitlines():
        if 'Welch t-test' in line and 'p=' in line:
            try:
                p = float(line.split('p=')[-1])
                res['welch_p'] = p
            except Exception:
                pass
        if 'Permutation test' in line and 'p=' in line:
            try:
                p = float(line.split('p=')[-1])
                res['perm_p'] = p
            except Exception:
                pass
        if "Cohen's d" in line and ':' in line:
            try:
                d = float(line.split(':')[-1])
                res['cohen_d'] = d
            except Exception:
                pass
    return res


def make_barplot(df: pd.DataFrame, value_col: str, title: str, ylabel: str, out_png: str, dpi: int = 600):
    stats = df.groupby('label')[value_col].agg(['mean', 'std'])
    means = stats['mean']
    stds = stats['std']
    fig, ax = plt.subplots(figsize=(6, 4))
    x = np.arange(len(means))
    ax.bar(x, means.values, yerr=stds.values, capsize=8, color=['#4CAF50', '#2196F3'])
    ax.set_xticks(x)
    ax.set_xticklabels(means.index)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    for i, v in enumerate(means.values):
        ax.text(i, v + max(stds.values) * 0.05, f"{v:.1f}" if 'centroid' in value_col else f"{v:.3f}", ha='center')
    fig.savefig(out_png, dpi=dpi, bbox_inches='tight')
    plt.close(fig)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--in', dest='indir', default='viz_stats_n10')
    p.add_argument('--out', dest='outdir', default='viz_stats_n10')
    args = p.parse_args()

    indir = args.indir
    outdir = args.outdir
    os.makedirs(outdir, exist_ok=True)

    combined_csv = os.path.join(indir, 'combined_stats.csv')
    rms_txt = os.path.join(indir, 'rms_stat_tests.txt')

    if not os.path.exists(combined_csv):
        raise FileNotFoundError(f'combined CSV not found: {combined_csv}')

    df = pd.read_csv(combined_csv)
    # ensure label exists
    if 'label' not in df.columns:
        raise RuntimeError('combined_stats.csv missing label column')

    # High-res centroid plot
    centroid_png = os.path.join(outdir, 'centroid_bar_hd.png')
    make_barplot(df, 'centroid', 'Spectral Centroid (Happy vs Sad)', 'Spectral Centroid (Hz)', centroid_png, dpi=600)

    # High-res RMS plot
    rms_png = os.path.join(outdir, 'rms_bar_hd.png')
    make_barplot(df, 'rms', 'RMS (Happy vs Sad)', 'RMS (linear)', rms_png, dpi=600)

    # caption using summary and p-values
    stats = df.groupby('label').agg({'centroid': ['mean','std'], 'rms': ['mean','std']})
    stats = stats.round(4)
    pvals = read_rms_pvals(rms_txt)

    caption = []
    caption.append('Spectral Centroid (mean ± std):')
    for lbl in stats.index:
        caption.append(f"- {lbl}: {stats.loc[lbl,('centroid','mean')]:.1f} Hz ± {stats.loc[lbl,('centroid','std')]:.1f} Hz")
    caption.append('')
    caption.append('RMS (mean ± std):')
    for lbl in stats.index:
        caption.append(f"- {lbl}: {stats.loc[lbl,('rms','mean')]:.3f} ± {stats.loc[lbl,('rms','std')]:.3f}")
    caption.append('')
    if pvals:
        caption.append('Statistical tests (RMS):')
        if 'welch_p' in pvals:
            caption.append(f"- Welch t-test p = {pvals['welch_p']:.3f}")
        if 'perm_p' in pvals:
            caption.append(f"- Permutation test p = {pvals['perm_p']:.3f}")
        if 'cohen_d' in pvals:
            caption.append(f"- Cohen's d = {pvals['cohen_d']:.2f}")

    caption_txt = os.path.join(outdir, 'slide_caption.txt')
    with open(caption_txt, 'w') as f:
        f.write('\n'.join(caption))

    print('Wrote high-res plots and caption to', outdir)


if __name__ == '__main__':
    main()
