#!/usr/bin/env python3
"""Independently recompute the prior carl-model (M2) result from raw per-case scores.

This does NOT trust ~/.local/state/lifeos/carl-model/runs/m2/results_test_M2_full.json.
It re-joins the prompt rows (gold_index, family, day) with the score rows
(logp_sum, null_logp_sum), recomputes PMI = logp_sum - null_logp_sum, ranks the
gold candidate with ties counting against it (same rule as carl-model
src/evaluate.py:rank_of_gold), and reports pooled top-1 (excluding the `said`
family, as the original pooled table did) plus per-family and per-day deltas.

Writes aggregates only to results/carl_model_verified.json. No prompt text,
candidate text, or case ids are written.

Run:  .venv/bin/python scripts/verify_carl_model.py
"""
from __future__ import annotations

import collections
import json
import os
import sys
from pathlib import Path

import numpy as np

STATE = Path(os.environ.get("CARL_MODEL_STATE", "~/.local/state/lifeos/carl-model")).expanduser()
M2 = STATE / "runs" / "m2"
EM = STATE / "runs" / "m2-all"
OUT = Path(__file__).resolve().parents[1] / "results" / "carl_model_verified.json"
POOL_EXCLUDE = {"said"}
N_BOOT = 10_000


def read_jsonl(p: Path, keep):
    with p.open() as f:
        for line in f:
            r = json.loads(line)
            yield {k: r[k] for k in keep if k in r}


def rank_of_gold(scores: np.ndarray, gold: int) -> int:
    others = np.delete(scores, gold)
    return int(1 + np.sum(others >= scores[gold]))


def load(prompts_path: Path, scores_path: Path):
    meta = {(p["case_id"], p["variant"]): p for p in
            read_jsonl(prompts_path, ("case_id", "variant", "family", "day", "cluster", "gold_index"))}
    table = collections.defaultdict(dict)  # variant -> case_id -> (top1, rr, family, day, cluster)
    for s in read_jsonl(scores_path, ("case_id", "variant", "logp_sum", "null_logp_sum")):
        m = meta.get((s["case_id"], s["variant"]))
        if m is None:
            # layer-ablation variants (E-<layer>) reuse the E prompt's case meta;
            # gold_index is per case_id (verified: identical across variants).
            m = meta.get((s["case_id"], "E"))
        if m is None:
            sys.exit(f"score row without prompt row: {s['case_id']} {s['variant']}")
        pmi = np.asarray(s["logp_sum"], float) - np.asarray(s["null_logp_sum"], float)
        if not np.all(np.isfinite(pmi)):
            sys.exit(f"non-finite PMI for {s['case_id']}")
        rk = rank_of_gold(pmi, int(m["gold_index"]))
        table[s["variant"]][s["case_id"]] = (float(rk == 1), 1.0 / rk, m["family"], m["day"], m["cluster"])
    return table


def pooled(table, variant, exclude):
    rows = [v for v in table[variant].values() if v[2] not in exclude]
    return {"n": len(rows), "top1": float(np.mean([r[0] for r in rows])), "mrr": float(np.mean([r[1] for r in rows]))}


def paired(table, a, b, exclude, rng):
    common = [c for c in table[a] if c in table[b] and table[a][c][2] not in exclude]
    da = np.array([table[b][c][0] - table[a][c][0] for c in common])
    clusters = collections.defaultdict(list)
    for c, d in zip(common, da):
        clusters[table[a][c][4]].append(d)
    cl = [np.array(v) for v in clusters.values()]
    # cluster bootstrap on the mean difference
    boots = np.empty(N_BOOT)
    for i in range(N_BOOT):
        idx = rng.integers(0, len(cl), len(cl))
        boots[i] = np.concatenate([cl[j] for j in idx]).mean()
    # per-day
    days = collections.defaultdict(list)
    for c, d in zip(common, da):
        days[table[a][c][3]].append(d)
    per_day = {d: float(np.mean(v)) for d, v in sorted(days.items())}
    return {"n": len(common), "d_top1": float(da.mean()),
            "ci95_cluster_boot": [float(np.quantile(boots, .025)), float(np.quantile(boots, .975))],
            "n_clusters": len(cl), "days": len(per_day),
            "days_with_gain": int(sum(v > 0 for v in per_day.values())), "per_day": per_day}


def per_family(table, a, b):
    fams = sorted({v[2] for v in table[a].values()})
    out = {}
    for f in fams:
        ca = {c: v for c, v in table[a].items() if v[2] == f}
        cb = {c: v for c, v in table[b].items() if v[2] == f and c in ca}
        if not cb:
            continue
        out[f] = {"n": len(cb), f"top1_{a}": float(np.mean([ca[c][0] for c in cb])),
                  f"top1_{b}": float(np.mean([cb[c][0] for c in cb])),
                  "d_top1": float(np.mean([cb[c][0] - ca[c][0] for c in cb]))}
    return out


def main():
    for p in (M2 / "prompts_test_M2_full.jsonl", M2 / "scores_test_M2_all.jsonl"):
        if not p.exists():
            sys.exit(f"MISSING: {p}. Cannot verify; refusing to write results.")
    rng = np.random.default_rng(0)
    t = load(M2 / "prompts_test_M2_full.jsonl", M2 / "scores_test_M2_all.jsonl")
    res = {"source": {"prompts": str(M2 / "prompts_test_M2_full.jsonl"), "scores": str(M2 / "scores_test_M2_all.jsonl"),
                      "mtime": os.path.getmtime(M2 / "scores_test_M2_all.jsonl")},
           "method": "pmi_sum (logp_sum - null_logp_sum), tie counts against gold",
           "pool_exclude": sorted(POOL_EXCLUDE), "n_candidates": 5, "chance": 0.20,
           "variants": {v: pooled(t, v, POOL_EXCLUDE) for v in sorted(t)},
           "vs_A": {v: paired(t, "A", v, POOL_EXCLUDE, rng) for v in sorted(t) if v != "A"},
           "per_family_L_vs_A": per_family(t, "A", "L"),
           "H2_C_vs_F": paired(t, "F", "C", POOL_EXCLUDE, rng)}
    # random gate: shuffle gold index
    res["random_gate_note"] = "gold_index shuffle gate reproduced in original evaluate.py; not re-run here"
    # event model (separate meta + scores files)
    emp, ems = EM / "em_meta_test.jsonl", EM / "em_scores_test.jsonl"
    if emp.exists() and ems.exists():
        te = load(emp, ems)
        res["event_model"] = {"meta": str(emp), "scores": str(ems),
                             "variants": {v: pooled(te, v, POOL_EXCLUDE) for v in sorted(te)}}
        if "EM-own" in te and "EM-all" in te:
            res["event_model"]["EM-all_vs_EM-own"] = paired(te, "EM-own", "EM-all", POOL_EXCLUDE, rng)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1, sort_keys=True))
    print(f"wrote {OUT}")
    for v, d in res["variants"].items():
        print(f"  {v:8s} n={d['n']} top1={d['top1']:.4f} mrr={d['mrr']:.4f}")
    for v, d in res["vs_A"].items():
        print(f"  {v:8s} vs A: d={d['d_top1']:+.4f} ci={d['ci95_cluster_boot']} days={d['days_with_gain']}/{d['days']}")
    if "event_model" in res:
        for v, d in res["event_model"]["variants"].items():
            if v in ("EM-own", "EM-all", "EM-none", "EM-shiftday"):
                print(f"  {v:12s} n={d['n']} top1={d['top1']:.4f}")


if __name__ == "__main__":
    main()
