#!/usr/bin/env python3
"""Draw the Tier B manual-annotation sample (annotations/PROTOCOL.md), blind to
every policy ranking and to Tier A.

Sampling rule (protocol): from the weak-tie candidate pool in the val and test
periods, all exposures with >= 1 later burst within the horizon, plus an equal
number of exposures with none, shuffled with a fixed seed, capped at --n.
The CSV includes the inbound message text so the annotator can judge it; it is
written to annotations/private/ (git-ignored) and must never be committed.
Columns to fill: consequential (0/1), outcome_type, evidence (direct|inferred),
confidence (0-1), rationale.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.features.judgments_anyjev import load_texts  # noqa: E402
from src.features.judgments_local import situation  # noqa: E402

H = 365


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", default=str(ROOT / "annotations" / "private" / "tier_b_sample_v1.csv"))
    a = ap.parse_args()
    exp = pd.read_parquet(ROOT / "data" / "derived" / "exposures.parquet")
    exp["t"] = pd.to_datetime(exp["t"], utc=True)
    feats = pd.read_parquet(ROOT / "data" / "derived" / "exposures_features.parquet", columns=["exposure_id", "split"])
    pool = exp.merge(feats, on="exposure_id")
    pool = pool[pool["split"].isin(["val", "test"]) & pool[f"label_complete_{H}"]]
    rng = np.random.default_rng(a.seed)
    pos = pool[pool[f"bursts_{H}"] >= 1]; neg = pool[pool[f"bursts_{H}"] == 0]
    k = min(a.n // 2, len(pos), len(neg))
    samp = pd.concat([pos.sample(k, random_state=a.seed), neg.sample(k, random_state=a.seed + 1)])
    samp = samp.sample(frac=1, random_state=a.seed + 2).reset_index(drop=True)
    texts = load_texts(samp)
    out = pd.DataFrame({
        "sample_id": [f"B{i:04d}" for i in range(len(samp))],
        "exposure_id": samp["exposure_id"],
        "date": samp["t"].dt.strftime("%Y-%m-%d"),
        "source": samp["source"].str.replace("msg_", ""),
        "situation": [situation(r) for r in samp.itertuples()],
        "message_text": [texts.get(e, "") for e in samp["exposure_id"]],
        "consequential": "", "outcome_type": "", "evidence": "", "confidence": "", "rationale": "",
    })
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(a.out, index=False)
    print(f"wrote {a.out}: {len(out)} rows ({k} with a later burst, {k} without; val/test mix "
          f"{samp['split'].value_counts().to_dict()}). Blind: no rankings or Tier A labels included.")
    # record the draw (ids only) so the freeze can reference it
    (ROOT / "annotations" / "tier_b_sample_v1.ids.txt").write_text("\n".join(out["exposure_id"]) + "\n")


if __name__ == "__main__":
    main()
