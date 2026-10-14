#!/usr/bin/env python3
"""stats_tests.py

Compute statistical tests comparing RMS between Happy and Sad groups.

Outputs results to stdout and saves a small text summary under --outdir.
"""
from __future__ import annotations

import argparse
import os
import numpy as np
import pandas as pd

def cohen_d(x, y):
    nx = len(x)
    ny = len(y)
    dof = nx + ny - 2
    sx2 = x.var(ddof=1)
    sy2 = y.var(ddof=1)
    pooled = np.sqrt(((nx - 1) * sx2 + (ny - 1) * sy2) / dof)
    return (x.mean() - y.mean()) / pooled


def permutation_test(x, y, n_perm=10000, seed=0):
    rng = np.random.default_rng(seed)
    obs = x.mean() - y.mean()
    combined = np.concatenate([x, y])
    n = len(x)
    count = 0
    for _ in range(n_perm):
        perm = rng.permutation(combined)
        if abs(perm[:n].mean() - perm[n:].mean()) >= abs(obs):
            count += 1
    p = (count + 1) / (n_perm + 1)
    return obs, p


def bootstrap_ci_effect(x, y, n_boot=10000, seed=0):
    rng = np.random.default_rng(seed)
    boot = []
    nx = len(x)
    ny = len(y)
    for _ in range(n_boot):
        bx = rng.choice(x, size=nx, replace=True)
        by = rng.choice(y, size=ny, replace=True)
        try:
            d = cohen_d(bx, by)
        except Exception:
            d = np.nan
        boot.append(d)
    arr = np.array(boot)
    lo = np.nanpercentile(arr, 2.5)
    hi = np.nanpercentile(arr, 97.5)
    return lo, hi


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--happy", default="viz_by_label/happy/stats_happy.csv")
    p.add_argument("--sad", default="viz_by_label/sad/stats_sad.csv")
    p.add_argument("--outdir", default="viz_stats")
    args = p.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    dfh = pd.read_csv(args.happy)
    dfs = pd.read_csv(args.sad)

    # ensure column 'rms' exists
    if 'rms' not in dfh.columns or 'rms' not in dfs.columns:
        raise RuntimeError('rms column not found in one of the CSVs')

    x = dfh['rms'].to_numpy(dtype=float)
    y = dfs['rms'].to_numpy(dtype=float)

    # Welch t-test
    try:
        from scipy import stats

        t_res = stats.ttest_ind(x, y, equal_var=False)
        mw_res = stats.mannwhitneyu(x, y, alternative='two-sided')
    except Exception:
        t_res = None
        mw_res = None

    obs_perm, p_perm = permutation_test(x, y, n_perm=10000, seed=1)

    # Cohen's d and bootstrap CI
    d = cohen_d(x, y)
    lo_d, hi_d = bootstrap_ci_effect(x, y, n_boot=10000, seed=2)

    out_txt = os.path.join(args.outdir, 'rms_stat_tests.txt')
    with open(out_txt, 'w') as f:
        f.write('RMS statistical comparison\n')
        f.write('--------------------------\n')
        f.write(f'Happy (n={len(x)}): mean={x.mean():.6f}, std={x.std(ddof=1):.6f}\n')
        f.write(f'Sad   (n={len(y)}): mean={y.mean():.6f}, std={y.std(ddof=1):.6f}\n')
        f.write('\n')
        if t_res is not None:
            f.write(f'Welch t-test: t={t_res.statistic:.4f}, p={t_res.pvalue:.6f}\n')
            f.write(f'Mann-Whitney U: U={mw_res.statistic:.4f}, p={mw_res.pvalue:.6f}\n')
        else:
            f.write('scipy not available: skipping Welch and Mann-Whitney tests\n')
        f.write(f'Permutation test (mean difference): obs_diff={obs_perm:.6f}, p={p_perm:.6f}\n')
        f.write('\n')
        f.write(f"Cohen's d: {d:.4f}\n")
        f.write(f"Cohen's d 95% CI (bootstrap): [{lo_d:.4f}, {hi_d:.4f}]\n")

    # also print to stdout
    with open(out_txt, 'r') as f:
        print(f.read())


if __name__ == '__main__':
    main()
