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
weak["week"] = (weak.t - pd.to_timedelta(weak.t.dt.dayofweek, unit="D")).dt.strftime("%Y-%m-%d")
sw = {}
for pool, df in (("primary", weak[weak.p_automated <= 0.5]), ("secondary", weak)):
    sw[pool] = {}
    for sp in ("train", "val", "test"):
        dd = df[df.split == sp]; g = dd.groupby("week")
        scored = g.filter(lambda x: x.consequential_auto_365.sum() > 0)
        sizes = scored.groupby("week").size()
        sw[pool][sp] = {"weeks_total": int(g.ngroups), "weeks_scored": int(scored.week.nunique()), "exposures_scored": int(len(scored)),
                        "positives": int(scored.consequential_auto_365.sum()), "median_set_scored": float(sizes.median()) if len(sizes) else None,
                        "positive_rate": float(dd.consequential_auto_365.mean())}
out["scored_weeks"] = sw
out["weak_complete_total"] = int(len(weak)); out["weak_complete_positive_rate"] = float(weak.consequential_auto_365.mean())
out["automated_share_weak"] = float((weak.p_automated > 0.5).mean())
for f in ["metrics_val_primary", "metrics_test_primary", "metrics_test_primary_permuted", "metrics_val_secondary_fullpool", "metrics_test_secondary_fullpool"]:
    m = json.loads((R / f"{f}.json").read_text())
    out[f] = {"weeks": m["n_test_days_with_positives"], "candidates": m["n_candidates_eval"], "positives": m["n_positives_eval"],
              "set_size": m["candidate_set_size"], "hybrid_weights": m["hybrid_weights"], "hybrid_tuned_on": m["hybrid_tuned_on"],
              "policies": {p: {k: m["metrics"][k][p]["mean"] for k in ("mrr", "recall@1", "recall@3", "recall@5")}
                           | {"mrr_ci": m["metrics"]["mrr"][p]["ci95"]} for p in m["metrics"]["mrr"]},
              "paired": {k: {mm: {"diff": v[mm]["diff"], "ci": v[mm]["ci95"], "p_le0": v[mm]["p_le0"]}
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
                **{c: {"ordinary": float(d.loc[~d.consequential_auto_365, c].mean()),
                       "consequential": float(d.loc[d.consequential_auto_365, c].mean()),
                       "auc": float(roc_auc_score(d.consequential_auto_365, d[c]))} for c in cols}}
out["judgments_vs_label"] = jl
jp = {}
for per, sel in (("dev", lambda t: t < pd.Timestamp("2024-01-01", tz="UTC")), ("test", lambda t: t >= pd.Timestamp("2024-01-01", tz="UTC"))):
    jp[per] = {}
    for name, jj in (("gemma", j), ("qwen", q)):
        d = e[(e.is_new_thread | e.is_dormant) & e.label_complete_365 & sel(e.t)][["exposure_id", "consequential_auto_365"]].merge(jj, on="exposure_id")
        jp[per][name] = {"n": int(len(d)), "positives": int(d.consequential_auto_365.sum()),
                         **{c: {"ordinary": float(d.loc[~d.consequential_auto_365, c].mean()),
                                "consequential": float(d.loc[d.consequential_auto_365, c].mean()),
                                "auc": float(roc_auc_score(d.consequential_auto_365, d[c]))} for c in cols}}
out["judgments_by_period"] = jp
dq = e[(e.is_new_thread | e.is_dormant) & e.label_complete_365][["exposure_id"]].merge(q, on="exposure_id")
out["qwen_automated_share_weak"] = float((dq.p_automated > 0.5).mean())
m = q.merge(j, on="exposure_id", suffixes=("_q", "_g")); ag = {}
for c in ["p_invites_action", "p_expects_reply", "p_org_or_group", "p_automated", "p_exposure_type_social", "p_exposure_type_invitation", "p_exposure_type_marketing"]:
    x, y = m[c + "_q"] > 0.5, m[c + "_g"] > 0.5; a = float((x == y).mean()); pe = float(x.mean() * y.mean() + (~x).mean() * (~y).mean())
    ag[c] = {"agreement": a, "kappa": (a - pe) / (1 - pe)}
out["inter_judge"] = {"n": int(len(m)), **ag}
out["rq6_yearly_file"] = "results/tables/exploration_proxies_yearly.md"
import collections, orjson, os
EV = Path(os.path.expanduser("~/.local/state/lifeos/carl-model/events"))
LOCK = pd.Timestamp("2026-09-17", tz="UTC"); src_counts = {}; first_year = {}
for src in ["msg_messenger", "msg_telegram", "msg_instagram", "msg_discord", "msg_gmail", "msg_linkedin", "msg_twitter", "msg_gvoice", "msg_gchat"]:
    n = 0; fy = 9999
    with open(EV / f"{src}.jsonl", "rb") as fh:
        for line in fh:
            r = orjson.loads(line); m = r.get("meta") or {}
            if not m.get("thread_hash"): continue
            ts = r["t_start"]
            if ts >= "2026-09-17": continue
            n += 1; fy = min(fy, int(ts[:4]))
    src_counts[src] = n; first_year[src] = fy
out["sources"] = {"messages": src_counts, "first_year": first_year, "total": sum(src_counts.values())}
pc = collections.defaultdict(set); fam = collections.Counter()
for line in open(os.path.expanduser("~/.local/state/lifeos/carl-model/runs/m2/prompts_test_M2_full.jsonl")):
    r = json.loads(line)
    if r["variant"] != "A": continue
    fam[r["family"]] += 1
    if r["family"] != "said": pc[r["day"]].add(r["family"])
out["clone_extra"] = {"family_counts": dict(fam), "test_days": len(pc), "days_only_reply_sent": sum(1 for f in pc.values() if f <= {"reply", "sent"})}
out["freeze"] = {"commit_original": "8862642", "commit_after_history_rewrite": "20c6ceb", "github_push_event_utc": "2026-09-27T19:16:34Z", "test_opened_utc": "2026-09-27T19:16:42Z"}
(R / "paper_numbers.json").write_text(json.dumps(out, indent=1, default=str))
print(json.dumps({k: out[k] for k in ("pool_primary", "pool_secondary", "weak_complete_total", "weak_complete_positive_rate", "automated_share_weak", "auc", "inter_judge")}, indent=1))
for f in ("metrics_val_primary", "metrics_test_primary", "metrics_test_secondary_fullpool"):
    print(f, out[f]["weeks"], out[f]["candidates"], out[f]["positives"], out[f]["hybrid_weights"])
    print({p: v["mrr"] for p, v in out[f]["policies"].items()})
print(json.dumps(jl, indent=0)[:1500])
