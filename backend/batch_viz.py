#!/usr/bin/env python3
"""
Batch visualization: find matching pairs (e.g. out_happy*_ vs out_sad*),
and run `compare_and_visualize` on each pair producing images and CSVs.

使い方例:
python batch_viz.py --dir . --prefix1 out_happy --prefix2 out_sad --outdir viz_batch
"""
from __future__ import annotations

import argparse
import os
from importlib import util
from typing import List


def load_local_analysis_module():
    # Load analysis.py from the same directory as this script to avoid importing other modules named `analysis`.
    script_dir = os.path.dirname(__file__)
    analysis_path = os.path.join(script_dir, "analysis.py")
    spec = util.spec_from_file_location("local_analysis", analysis_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load local analysis module at {analysis_path}")
    mod = util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def find_files_with_prefix(directory: str, prefix: str) -> List[str]:
    files = []
    for fn in os.listdir(directory):
        if fn.startswith(prefix) and fn.lower().endswith((".wav", ".mp3", ".flac", ".ogg")):
            files.append(fn)
    return sorted(files)


def suffix_of(filename: str, prefix: str) -> str:
    return filename[len(prefix):]  # includes leading underscore or empty


def main():
    p = argparse.ArgumentParser(description="Batch visualize pairs of audio files by prefix")
    p.add_argument("--dir", default=".", help="Directory containing audio files")
    p.add_argument("--prefix1", default="out_happy", help="Prefix for first set (e.g. out_happy)")
    p.add_argument("--prefix2", default="out_sad", help="Prefix for second set (e.g. out_sad)")
    p.add_argument("--outdir", default="viz_batch", help="Base output directory")
    p.add_argument("--label1", default="Valence=1.0 (Happy)", help="Label for first set")
    p.add_argument("--label2", default="Valence=0.0 (Sad)", help="Label for second set")
    args = p.parse_args()

    mod = load_local_analysis_module()
    compare_and_visualize = getattr(mod, "compare_and_visualize")

    dirpath = os.path.abspath(args.dir)
    files1 = find_files_with_prefix(dirpath, args.prefix1)
    files2 = find_files_with_prefix(dirpath, args.prefix2)

    map1 = {suffix_of(fn, args.prefix1): fn for fn in files1}
    map2 = {suffix_of(fn, args.prefix2): fn for fn in files2}

    all_suffixes = sorted(set(list(map1.keys()) + list(map2.keys())))
    if not all_suffixes:
        print("No matching files found for prefixes", args.prefix1, args.prefix2)
        return

    os.makedirs(args.outdir, exist_ok=True)

    for suf in all_suffixes:
        f1 = map1.get(suf)
        f2 = map2.get(suf)
        if not f1 or not f2:
            # If exact suffix match not found, prefer base file (empty suffix)
            if not f1 and map1.get(""):
                f1 = map1.get("")
            if not f2 and map2.get(""):
                f2 = map2.get("")
        if not f1 or not f2:
            print(f"Skipping suffix '{suf}': missing pair (f1={f1}, f2={f2})")
            continue

        path1 = os.path.join(dirpath, f1)
        path2 = os.path.join(dirpath, f2)

        safe_suf = suf.lstrip("._") or "base"
        pair_outdir = os.path.join(args.outdir, safe_suf)
        print(f"Processing pair: {f1} vs {f2} -> {pair_outdir}")
        try:
            res = compare_and_visualize(path1, path2, args.label1 + " " + safe_suf, args.label2 + " " + safe_suf, pair_outdir)
            print("  -> image:", res.get("image"))
            print("  -> csv:", res.get("csv"))
        except Exception as e:
            print(f"  ERROR processing {f1} vs {f2}: {e}")


if __name__ == "__main__":
    main()
