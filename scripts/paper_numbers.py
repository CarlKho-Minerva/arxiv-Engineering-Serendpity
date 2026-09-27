#!/usr/bin/env python3
"""Collect every number cited in paper/main.tex into results/paper_numbers.json (aggregates only)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "results"; D = ROOT / "data" / "derived"
out = {}
out["clone"] = json.loads((R / "carl_model_verified.json").read_text())
ex = json.loads((R / "exposures_summary.json").read_text())
out["exposures"] = ex
e = pd.read_parquet(D / "exposures.parquet"); e["t"] = pd.to_datetime(e["t"], utc=True)
j = pd.read_parquet(D / "judgments.parquet")
weak = e[(e.is_new_thread | e.is_dormant) & e.label_complete_365].merge(j[["exposure_id", "p_automated"]], on="exposure_id")
def split(t):
    if t <= pd.Timestamp("2019-12-31 23:59:59", tz="UTC"): return "train"
    if pd.Timestamp("2021-01-01", tz="UTC") <= t <= pd.Timestamp("2022-12-31 23:59:59", tz="UTC"): return "val"
    if t >= pd.Timestamp("2024-01-01", tz="UTC"): return "test"
    return "embargo"
weak["split"] = weak.t.map(split)
for pool, df in (("primary", weak[weak.p_automated <= 0.5]), ("secondary", weak)):
    out[f"pool_{pool}"] = {s: {"candidates": int((df.split == s).sum()), "positives": int(df.loc[df.split == s, "consequential_auto_365"].sum()),
                               "first": str(df.loc[df.split == s, "t"].min())[:10], "last": str(df.loc[df.split == s, "t"].max())[:10]}
                           for s in ("train", "val", "test")}
out["weak_complete_total"] = int(len(weak)); out["weak_complete_positive_rate"] = float(weak.consequential_auto_365.mean())
out["automated_share_weak"] = float((weak.p_automated > 0.5).mean())
for f in ["metrics_val_primary", "metrics_test_primary", "metrics_test_primary_permuted", "metrics_val_secondary_fullpool", "metrics_test_secondary_fullpool"]:
    m = json.loads((R / f"{f}.json").read_text())
    out[f] = {"weeks": m["n_test_days_with_positives"], "candidates": m["n_candidates_eval"], "positives": m["n_positives_eval"],
              "set_size": m["candidate_set_size"], "hybrid_weights": m["hybrid_weights"], "hybrid_tuned_on": m["hybrid_tuned_on"],
              "policies": {p: {k: round(m["metrics"][k][p]["mean"], 3) for k in ("mrr", "recall@1", "recall@3", "recall@5")}
                           | {"mrr_ci": [round(x, 3) for x in m["metrics"]["mrr"][p]["ci95"]]} for p in m["metrics"]["mrr"]},
              "paired": {k: {mm: {"diff": round(v[mm]["diff"], 3), "ci": [round(x, 3) for x in v[mm]["ci95"]], "p_le0": round(v[mm]["p_le0"], 3)}
                             for mm in v} for k, v in m["paired"].items()}}
out["auc"] = {"primary": {"metadata": [0.606, 0.618], "metadata+content": [0.644, 0.626], "metadata+judgments": [0.670, 0.668]},
              "note": "val, test; from exposure_features.py --post-freeze runs 2026-09-27 (ablation, exploratory)"}
for t in ("primary", "secondary"):
    s = json.loads((R / f"split_test_{t}.json").read_text())
    out["auc"].setdefault(t, {})["all"] = [round(s["relevance_auc_val"], 3), round(s["relevance_auc_test"], 3)]
# judgments vs label (Gemma, all complete weak-tie; Qwen on same)
q = pd.read_parquet(D / "judgments_qwen8b.parquet")
cols = ["p_invites_action", "p_org_or_group", "p_automated", "p_exposure_type_social", "p_exposure_type_invitation", "ev_option_value"]
from sklearn.metrics import roc_auc_score
jl = {}
for name, jj in (("gemma", j), ("qwen", q)):
    d = e[(e.is_new_thread | e.is_dormant) & e.label_complete_365][["exposure_id", "consequential_auto_365"]].merge(jj, on="exposure_id")
    jl[name] = {"n": int(len(d)), "positives": int(d.consequential_auto_365.sum()),
                **{c: {"ordinary": round(float(d.loc[~d.consequential_auto_365, c].mean()), 3),
                       "consequential": round(float(d.loc[d.consequential_auto_365, c].mean()), 3),
                       "auc": round(float(roc_auc_score(d.consequential_auto_365, d[c])), 3)} for c in cols}}
out["judgments_vs_label"] = jl
m = q.merge(j, on="exposure_id", suffixes=("_q", "_g")); ag = {}
for c in ["p_invites_action", "p_expects_reply", "p_org_or_group", "p_automated", "p_exposure_type_social", "p_exposure_type_invitation", "p_exposure_type_marketing"]:
    x, y = m[c + "_q"] > 0.5, m[c + "_g"] > 0.5; a = float((x == y).mean()); pe = float(x.mean() * y.mean() + (~x).mean() * (~y).mean())
    ag[c] = {"agreement": round(a, 3), "kappa": round((a - pe) / (1 - pe), 3)}
out["inter_judge"] = {"n": int(len(m)), **ag}
out["rq6_yearly_file"] = "results/tables/exploration_proxies_yearly.md"
(R / "paper_numbers.json").write_text(json.dumps(out, indent=1, default=str))
print(json.dumps({k: out[k] for k in ("pool_primary", "pool_secondary", "weak_complete_total", "weak_complete_positive_rate", "automated_share_weak", "auc", "inter_judge")}, indent=1))
for f in ("metrics_val_primary", "metrics_test_primary", "metrics_test_secondary_fullpool"):
    print(f, out[f]["weeks"], out[f]["candidates"], out[f]["positives"], out[f]["hybrid_weights"])
    print({p: v["mrr"] for p, v in out[f]["policies"].items()})
print(json.dumps(jl, indent=0)[:1500])
