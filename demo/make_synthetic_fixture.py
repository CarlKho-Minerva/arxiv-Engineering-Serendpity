#!/usr/bin/env python3
"""Generate demo/sample_data.json: a SYNTHETIC fixture for the Streamlit demo.

Nothing here is measured. Every number is drawn from a seeded generator so the
demo can show the *mechanics* (ranking under sliders, counterfactual ranks)
before real experiment output exists. The fixture is stamped
`"synthetic": true` and the app renders a red banner whenever it is loaded.

When results/retrospective/exposures_ranked.parquet exists, scripts/export_demo_fixture.py
will write demo/real_fixture.json (git-ignored) with the same shape and
`"synthetic": false`.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np

rng = np.random.default_rng(2026)
TOPICS = ["web dev", "hackathon", "neuroscience", "design", "startup", "music", "philosophy",
          "robotics", "photography", "policy", "linguistics", "climbing"]
KINDS = ["post", "event", "person", "community", "opportunity", "article", "video"]


def candidate(i, day_idx, interests):
    topic = TOPICS[rng.integers(len(TOPICS))]
    kind = KINDS[rng.integers(len(KINDS))]
    rel = float(np.clip(0.75 * interests[topic] + rng.normal(0, 0.12), 0, 1))
    nov = float(np.clip(1 - interests[topic] + rng.normal(0, 0.1), 0, 1))
    unc = float(np.clip(0.35 * nov + rng.normal(0.05, 0.06), 0.01, 0.6))
    ig = float(np.clip(0.6 * unc / 0.6 + 0.2 * nov + rng.normal(0, 0.08), 0, 1))
    ov = float(np.clip(0.5 * (kind in ("person", "community", "opportunity", "event")) + 0.3 * nov
                       + rng.normal(0, 0.1), 0, 1))
    cost = float(np.clip(0.2 + 0.5 * (kind in ("event", "opportunity")) + rng.normal(0, 0.08), 0, 1))
    return {"id": f"d{day_idx}c{i}", "kind": kind, "topic": topic,
            "summary_redacted": f"[synthetic {kind} about {topic}]",
            "relevance": round(rel, 3), "novelty": round(nov, 3), "uncertainty": round(unc, 3),
            "info_gain": round(ig, 3), "option_value": round(ov, 3), "cost": round(cost, 3),
            "consequential_label": False, "actually_encountered": bool(rng.random() < 0.35),
            "downstream": []}


def main():
    start = dt.date(2019, 9, 1)
    interests = {t: float(rng.beta(2, 5)) for t in TOPICS}
    interests["web dev"] = 0.9; interests["design"] = 0.7
    days = []
    for d in range(60):
        date = start + dt.timedelta(days=7 * d)
        # slow drift of interests
        for t in interests:
            interests[t] = float(np.clip(interests[t] + rng.normal(0, 0.03), 0.02, 0.98))
        cands = [candidate(i, d, interests) for i in range(60)]
        # plant a consequential exposure on ~1 in 6 weeks: low relevance, high novelty/option value
        if d % 6 == 2:
            c = cands[rng.integers(len(cands))]
            c.update({"consequential_label": True, "actually_encountered": True,
                      "relevance": round(float(rng.uniform(0.05, 0.3)), 3),
                      "novelty": round(float(rng.uniform(0.7, 0.95)), 3),
                      "uncertainty": round(float(rng.uniform(0.3, 0.55)), 3),
                      "option_value": round(float(rng.uniform(0.6, 0.95)), 3),
                      "info_gain": round(float(rng.uniform(0.5, 0.9)), 3),
                      "downstream": [[(date + dt.timedelta(days=int(h))).isoformat(), lab] for h, lab in
                                     zip(rng.integers(20, 200, 2), ["[synthetic] new project", "[synthetic] new collaborator"])]})
        top = sorted(interests, key=interests.get, reverse=True)[:4]
        state = {"date": date.isoformat(),
                 "recent_activities": [f"[synthetic] {t} session" for t in rng.choice(TOPICS, 3, replace=False)],
                 "modeled_interests": {t: round(interests[t], 2) for t in top},
                 "active_people_projects": [f"[synthetic person {rng.integers(100)}]", f"[synthetic project {rng.integers(20)}]"],
                 "belief_uncertainty": round(float(np.clip(0.25 + rng.normal(0, 0.08), 0.05, 0.8)), 2)}
        days.append({"date": date.isoformat(), "state": state, "candidates": cands})
    # precompute reference ranks for the figure builder (exploit = relevance only; serendipity = default hybrid)
    for day in days:
        cs = day["candidates"]
        ex = np.argsort(-np.array([c["relevance"] for c in cs]), kind="stable")
        hy = np.argsort(-np.array([c["relevance"] + 0.5 * c["uncertainty"] + 0.5 * c["novelty"]
                                   + 0.5 * c["info_gain"] + 0.5 * c["option_value"] - 0.25 * c["cost"] for c in cs]), kind="stable")
        rank_ex = np.empty(len(cs), int); rank_ex[ex] = np.arange(1, len(cs) + 1)
        rank_hy = np.empty(len(cs), int); rank_hy[hy] = np.arange(1, len(cs) + 1)
        for i, c in enumerate(cs):
            c["rank"] = {"exploit": int(rank_ex[i]), "serendipity": int(rank_hy[i])}
    out = {"synthetic": True,
           "note": "SYNTHETIC DEMO FIXTURE. Seeded random numbers. Not experiment output. Do not cite.",
           "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "weights_default": {"relevance": 1.0, "uncertainty": 0.5, "novelty": 0.5, "info_gain": 0.5,
                               "option_value": 0.5, "cost": 0.25},
           "days": days}
    Path(__file__).with_name("sample_data.json").write_text(json.dumps(out, indent=0))
    print("wrote demo/sample_data.json:", len(days), "days,", sum(len(d["candidates"]) for d in days), "candidates,",
          sum(c["consequential_label"] for d in days for c in d["candidates"]), "planted consequential")


if __name__ == "__main__":
    main()
