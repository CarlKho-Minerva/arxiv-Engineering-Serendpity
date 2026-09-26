#!/usr/bin/env python3
"""Sanity baselines on whatever table run_retrospective.py would use: prints, for each
policy, the mean rank of consequential exposures and the mean rank of ordinary
engaged exposures (RQ3's premise check). Same synthetic/real switch."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_retrospective import FEATURES, LABEL, load_synthetic  # noqa: E402
from src.policies.scoring import DEFAULT_POLICIES, ranks_from_scores  # noqa: E402


def main():
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--split-eval", default="val"); a = ap.parse_args()
    real = ROOT / "data" / "derived" / "exposures_features.parquet"
    if real.exists():
        df = pd.read_parquet(real); df = df[df["split"] == a.split_eval]; tag = f"REAL {a.split_eval} split (Tier A labels)"
    else:
        df = load_synthetic(); tag = "SYNTHETIC (not a result)"
    rng = np.random.default_rng(0)
    print(f"# RQ3 premise check on {tag}: mean rank of consequential vs ordinary exposures")
    print("| policy | mean rank consequential | mean rank ordinary | n days |"); print("|---|---|---|---|")
    for name, fn in DEFAULT_POLICIES.items():
        rc, ro, nd = [], [], 0
        for _, d in df.groupby("day"):
            if d[LABEL].sum() == 0:
                continue
            r = ranks_from_scores(fn(d[[c for c in FEATURES if c in d.columns]], rng))
            pos = d[LABEL].to_numpy().astype(bool)
            rc.append(r[pos].mean()); ro.append(r[~pos].mean()); nd += 1
        print(f"| {name} | {np.mean(rc):.1f} | {np.mean(ro):.1f} | {nd} |")


if __name__ == "__main__":
    main()
