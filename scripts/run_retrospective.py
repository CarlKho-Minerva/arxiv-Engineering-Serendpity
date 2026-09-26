#!/usr/bin/env python3
"""Retrospective serendipity experiment runner.

Input: a per-day candidate table with leakage-safe features and outcome labels.
  --real data/derived/exposures_features.parquet   (built by src/ingest + features_at)
  default: demo/sample_data.json                   (SYNTHETIC; output is stamped)

Runs every policy in src.policies.scoring.DEFAULT_POLICIES plus the mandatory
random-with-diversity control, computes recall@k / MRR / NDCG / coverage /
novelty@k per day, cluster-bootstraps over days, and writes results/metrics.json
(and results/tables/retrospective.md). Split handling: if the table has a `split`
column, weights are tuned on `val` and reported on `test`; the synthetic fixture
has no split and is reported as-is with `"synthetic": true`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.evaluation.leakage import assert_no_future_fields  # noqa: E402
from src.evaluation.metrics import coverage_at_k, mrr, ndcg_at_k, recall_at_k, topk_novelty  # noqa: E402
from src.policies.scoring import DEFAULT_POLICIES, Weights, hybrid_policy, ranks_from_scores  # noqa: E402
from src.schema import FUTURE_ONLY_FIELDS  # noqa: E402

KS = (1, 3, 5, 10)
LABEL = "consequential"
FEATURES = ["relevance", "novelty", "uncertainty", "info_gain", "option_value", "cost", "popularity", "n_seen"]


def load_synthetic() -> pd.DataFrame:
    fx = json.loads((ROOT / "demo" / "sample_data.json").read_text())
    rows = []
    for d in fx["days"]:
        for c in d["candidates"]:
            rows.append({"day": d["date"], "category": c["kind"], LABEL: int(c["consequential_label"]),
                         "gain": 1.0 + len(c.get("downstream", [])),
                         **{f: c.get(f, 0.0) for f in FEATURES if f in c}})
    df = pd.DataFrame(rows)
    df["split"] = "test"
    return df


def random_with_diversity(df: pd.DataFrame, rng: np.random.Generator, k: int) -> np.ndarray:
    """Control: random order but forced to cover as many categories as the hybrid's top-k does."""
    scores = rng.random(len(df))
    cats = df["category"].to_numpy()
    order = np.argsort(-scores)
    seen, picked = set(), []
    for i in order:
        if cats[i] not in seen:
            picked.append(i); seen.add(cats[i])
        if len(picked) >= k:
            break
    scores[picked] += 10.0
    return scores


def evaluate_day(df: pd.DataFrame, policies: dict, rng: np.random.Generator) -> list[dict]:
    feats = df[[c for c in FEATURES if c in df.columns]]
    assert_no_future_fields(feats, where="features")
    pos = df[LABEL].to_numpy()
    out = []
    for name, fn in policies.items():
        scores = fn(feats, rng) if name != "random_diversity" else fn(df, rng)
        r = ranks_from_scores(scores)
        row = {"policy": name, "n_pos": int(pos.sum()), "n": len(df), "mrr": mrr(r, pos)}
        for k in KS:
            row[f"recall@{k}"] = recall_at_k(r, pos, k)
            row[f"ndcg@{k}"] = ndcg_at_k(r, df["gain"].to_numpy() * pos, k)
            row[f"coverage@{k}"] = coverage_at_k(r, df["category"].to_numpy(), k)
            row[f"novelty@{k}"] = topk_novelty(r, df["novelty"].to_numpy(), k)
        out.append(row)
    return out


def bootstrap(per_day: pd.DataFrame, metric: str, rng: np.random.Generator, n=2000) -> dict:
    piv = per_day.pivot_table(index="day", columns="policy", values=metric)
    piv = piv.dropna(how="all")
    means = piv.mean()
    boots = {p: [] for p in piv.columns}
    for _ in range(n):
        idx = rng.integers(0, len(piv), len(piv))
        m = piv.iloc[idx].mean()
        for p in piv.columns:
            boots[p].append(m[p])
    return {p: {"mean": float(means[p]), "ci95": [float(np.nanquantile(boots[p], .025)), float(np.nanquantile(boots[p], .975))]}
            for p in piv.columns}


def tune_hybrid(val: pd.DataFrame, rng: np.random.Generator) -> Weights:
    grid = [0.0, 0.25, 0.5, 1.0]
    best, best_w = -1.0, Weights()
    for u in grid:
        for n in grid:
            for i in grid:
                for o in grid:
                    w = Weights(relevance=1.0, uncertainty=u, novelty=n, info_gain=i, option_value=o, cost=0.25)
                    hits = []
                    for _, d in val.groupby("day"):
                        if d[LABEL].sum() == 0:
                            continue
                        r = ranks_from_scores(hybrid_policy(w)(d, rng))
                        hits.append(recall_at_k(r, d[LABEL].to_numpy(), 5))
                    s = float(np.nanmean(hits)) if hits else -1
                    if s > best:
                        best, best_w = s, w
    return best_w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", type=Path, default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--split-eval", choices=["val", "test"], default="test",
                    help="evaluate on val while the annotation protocol is unfrozen; test only after the freeze")
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    if a.real:
        df = pd.read_parquet(a.real)
        synthetic = False
        if not {"day", "category", LABEL, "gain", "split"} <= set(df.columns):
            sys.exit("real table must have day, category, consequential, gain, split")
        for c in FUTURE_ONLY_FIELDS - {LABEL}:
            if c in df.columns:
                df = df.drop(columns=c)
    else:
        df = load_synthetic(); synthetic = True

    policies = dict(DEFAULT_POLICIES)
    tune_split = "train" if a.split_eval == "val" else "val"   # never tune on the split you report
    if (df["split"] == tune_split).any():
        w = tune_hybrid(df[df["split"] == tune_split], rng)
        policies["hybrid"] = hybrid_policy(w)
        tuned = w.as_dict()
    else:
        tuned = Weights(relevance=1.0, uncertainty=0.5, novelty=0.5, info_gain=0.5, option_value=0.5, cost=0.25).as_dict()
        policies["hybrid"] = hybrid_policy(Weights(**tuned))
    test = df[df["split"] == a.split_eval]
    rows = []
    for day, d in test.groupby("day"):
        if d[LABEL].sum() == 0:
            continue
        pols = dict(policies)
        pols["random_diversity"] = lambda frame, r, k=5: random_with_diversity(frame, r, k)
        for row in evaluate_day(d.reset_index(drop=True), pols, rng):
            row["day"] = day; rows.append(row)
    per_day = pd.DataFrame(rows)
    set_sizes = test.groupby("day").size()
    metrics = {m: bootstrap(per_day, m, rng) for m in ["mrr"] + [f"{s}@{k}" for s in ("recall", "ndcg", "coverage", "novelty") for k in KS]}
    out = {"synthetic": synthetic,
           "eval_split": a.split_eval,
           "note": "SYNTHETIC FIXTURE: numbers illustrate the pipeline only. Not a result." if synthetic
                   else f"Real retrospective evaluation on the chronological {a.split_eval} split (weak-tie exposures, Tier A labels).",
           "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "n_test_days_with_positives": int(per_day["day"].nunique()),
           "candidate_set_size": {"mean": float(set_sizes.mean()), "median": float(set_sizes.median()),
                                  "p90": float(set_sizes.quantile(.9)), "max": int(set_sizes.max())},
           "hybrid_weights": tuned, "hybrid_tuned_on": tune_split if not synthetic else None, "ks": list(KS), "metrics": metrics}
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / ("metrics.json" if synthetic else f"metrics_{a.split_eval}.json")).write_text(json.dumps(out, indent=1))
    # markdown table
    lines = [f"# Retrospective serendipity — {'SYNTHETIC FIXTURE (not a result)' if synthetic else a.split_eval + ' split (real, Tier A labels)'}", "",
             f"generated {out['generated']}; weeks with positives: {out['n_test_days_with_positives']}; candidate set size mean {out['candidate_set_size']['mean']:.1f} / median {out['candidate_set_size']['median']:.0f} / p90 {out['candidate_set_size']['p90']:.0f}; hybrid weights {tuned} (tuned on {out.get('hybrid_tuned_on')})", "",
             "| policy | " + " | ".join(f"recall@{k}" for k in KS) + " | MRR | coverage@5 | novelty@5 |", "|---|" + "---|" * (len(KS) + 3)]
    for p in per_day["policy"].unique():
        cells = [f"{metrics[f'recall@{k}'][p]['mean']:.3f} [{metrics[f'recall@{k}'][p]['ci95'][0]:.2f},{metrics[f'recall@{k}'][p]['ci95'][1]:.2f}]" for k in KS]
        lines.append(f"| {p} | " + " | ".join(cells) + f" | {metrics['mrr'][p]['mean']:.3f} | {metrics['coverage@5'][p]['mean']:.2f} | {metrics['novelty@5'][p]['mean']:.2f} |")
    (ROOT / "results" / "tables").mkdir(exist_ok=True, parents=True)
    (ROOT / "results" / "tables" / ("retrospective_synthetic.md" if synthetic else f"retrospective_{a.split_eval}.md")).write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
