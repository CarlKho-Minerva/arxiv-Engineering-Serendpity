#!/usr/bin/env python3
"""E2: leakage-safe features for the exposure table + fixed chronological split.

Input : data/derived/exposures.parquet (E1)
Output: data/derived/exposures_features.parquet  (columns required by
        scripts/run_retrospective.py: day, category, consequential, gain, split,
        + relevance, novelty, uncertainty, info_gain, option_value, cost,
        popularity, n_seen), and results/split.json.

Every history feature in the E1 table is computed from messages with t <= t0
by construction. This module additionally (a) drops every label column before
fitting anything (assert_no_future_fields), (b) fits the relevance ensemble on
the train period only, (c) applies the same transform to val/test.

Relevance   = mean over a 5-member bootstrap logistic ensemble of P(replied_7d | x)
Uncertainty = std across the ensemble (epistemic proxy)
Info gain   = BALD: H(mean p) - mean_i H(p_i)
Novelty     = 1 for a new thread, else 1/(1+prior_contact_events)
Popularity  = share of prior contact events from this source
Option value= 0.5*is_new_thread + 0.5*min(1, log1p(n_participants)/log1p(50))   [PROXY]
Cost        = log1p(chars_first_msg) scaled to [0,1] by the train 99th percentile  [PROXY]
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.evaluation.leakage import LeakageError, assert_no_future_fields  # noqa: E402
from src.evaluation.splits import ChronoSplit, assert_split_is_chronological  # noqa: E402

IN = ROOT / "data" / "derived" / "exposures.parquet"
OUT = ROOT / "data" / "derived" / "exposures_features.parquet"
UTC = dt.timezone.utc
LABEL_COLS_PREFIX = ("bursts_", "self_msgs_", "tie_persisted_", "label_complete_", "consequential_auto_")


def design(df: pd.DataFrame) -> pd.DataFrame:
    x = pd.DataFrame(index=df.index)
    x["new"] = df["is_new_thread"].astype(float)
    x["dormant"] = df["is_dormant"].astype(float)
    x["group"] = df["is_group"].astype(float)
    x["l_npart"] = np.log1p(df["npart"])
    for c in ("prior_msgs_in", "prior_msgs_out", "prior_contact_events", "thread_age_days",
              "global_30d_msgs_out", "global_30d_active_threads", "chars_first_msg"):
        x["l_" + c] = np.log1p(df[c].fillna(0).clip(lower=0))
    x["prr"] = df["prior_reply_rate"].fillna(0.5); x["prr_missing"] = df["prior_reply_rate"].isna().astype(float)
    for c in ("days_since_last_self", "days_since_last_any"):
        x["l_" + c] = np.log1p(df[c].fillna(3650).clip(lower=0)); x[c + "_missing"] = df[c].isna().astype(float)
    x["src_share"] = df["source_prior_share"].fillna(0)
    x["h_sin"] = np.sin(2 * np.pi * df["hour_utc"] / 24); x["h_cos"] = np.cos(2 * np.pi * df["hour_utc"] / 24)
    x["dow"] = df["dow"].astype(float)
    for s in sorted(df["source"].unique()):
        x["src_" + s] = (df["source"] == s).astype(float)
    return x


def entropy(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return -(p * np.log(p) + (1 - p) * np.log(1 - p))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=365)
    ap.add_argument("--candidates", choices=["weak", "all"], default="weak")
    ap.add_argument("--members", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    H = a.horizon
    df = pd.read_parquet(IN)
    df["t"] = pd.to_datetime(df["t"], utc=True)
    stream_end = df["t"].max()
    if a.candidates == "weak":
        df = df[df["is_new_thread"] | df["is_dormant"]].copy()
    df = df[df[f"label_complete_{H}"]].copy()

    # ---- fixed chronological split (set before any evaluation; recorded) ----
    split = ChronoSplit(train_end=dt.datetime(2019, 12, 31, 23, 59, 59, tzinfo=UTC),
                        val_start=dt.datetime(2021, 1, 1, tzinfo=UTC),
                        val_end=dt.datetime(2022, 12, 31, 23, 59, 59, tzinfo=UTC),
                        test_start=dt.datetime(2024, 1, 1, tzinfo=UTC), embargo_days=366)
    assert_split_is_chronological(split, horizon_days=H)
    df["split"] = split.assign(df["t"]).to_numpy()
    df = df[df["split"] != "embargo"].copy()

    # ---- features: strip labels first, loudly ----
    labels = [c for c in df.columns if c.startswith(LABEL_COLS_PREFIX)]
    feat_src = df.drop(columns=labels + ["replied_7d"])
    assert_no_future_fields(feat_src, where="exposure features")
    X = design(feat_src)
    y = df["replied_7d"].astype(int).to_numpy()
    tr = (df["split"] == "train").to_numpy()
    rng = np.random.default_rng(a.seed)
    probs = []
    for m in range(a.members):
        idx = rng.integers(0, tr.sum(), tr.sum())
        clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=0.5))
        clf.fit(X[tr].iloc[idx], y[tr][idx])
        probs.append(clf.predict_proba(X)[:, 1])
    P = np.vstack(probs)
    out = pd.DataFrame(index=df.index)
    out["exposure_id"] = df["exposure_id"]
    out["t"] = df["t"]
    out["day"] = (df["t"] - pd.to_timedelta(df["t"].dt.dayofweek, unit="D")).dt.strftime("%Y-%m-%d")  # ISO week key
    out["category"] = df["source"]
    out["split"] = df["split"]
    out["relevance"] = P.mean(0)
    out["uncertainty"] = P.std(0)
    out["info_gain"] = entropy(P.mean(0)) - entropy(P).mean(0)
    out["novelty"] = np.where(df["is_new_thread"], 1.0, 1.0 / (1.0 + df["prior_contact_events"]))
    out["popularity"] = df["source_prior_share"].fillna(0)
    out["option_value"] = 0.5 * df["is_new_thread"].astype(float) + 0.5 * np.minimum(1.0, np.log1p(df["npart"]) / np.log1p(50))
    p99 = np.log1p(df.loc[tr, "chars_first_msg"]).quantile(0.99)
    out["cost"] = np.clip(np.log1p(df["chars_first_msg"]) / max(p99, 1e-9), 0, 1)
    out["n_seen"] = df["prior_contact_events"] + 1
    out["replied_7d"] = df["replied_7d"].astype(int)
    out["consequential"] = df[f"consequential_auto_{H}"].astype(int)
    out["gain"] = np.log1p(df[f"bursts_{H}"])
    out["is_new_thread"] = df["is_new_thread"]; out["is_dormant"] = df["is_dormant"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.reset_index(drop=True).to_parquet(OUT, index=False)
    # relevance-model sanity on val (AUC) — the clone-of-engagement half of the table
    from sklearn.metrics import roc_auc_score
    va = (df["split"] == "val").to_numpy(); te = (df["split"] == "test").to_numpy()
    info = {"generated": dt.datetime.now(UTC).isoformat(timespec="seconds"), "horizon_days": H, "candidates": a.candidates,
            "split": {k: (v.isoformat() if isinstance(v, dt.datetime) else v) for k, v in dataclasses.asdict(split).items()},
            "stream_end": str(stream_end), "n": {s: int((df["split"] == s).sum()) for s in ("train", "val", "test")},
            "positives": {s: int(df.loc[df["split"] == s, f"consequential_auto_{H}"].sum()) for s in ("train", "val", "test")},
            "weeks_with_positives": {s: int(out.loc[(out["split"] == s) & (out["consequential"] == 1), "day"].nunique()) for s in ("train", "val", "test")},
            "relevance_auc_val": float(roc_auc_score(y[va], P.mean(0)[va])) if va.sum() and len(set(y[va])) > 1 else None,
            "relevance_auc_test_NOT_TO_BE_READ_BEFORE_FREEZE": None,
            "features": list(X.columns), "ensemble_members": a.members}
    (ROOT / "results" / "split.json").write_text(json.dumps(info, indent=1))
    print(json.dumps({k: v for k, v in info.items() if k != "features"}, indent=1))


if __name__ == "__main__":
    main()
