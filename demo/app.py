"""Algorithmic Mirrors demo.

    .venv/bin/streamlit run demo/app.py

Loads demo/real_fixture.json if present (written by scripts/export_demo_fixture.py
from actual experiment output), otherwise demo/sample_data.json, which is a
SYNTHETIC fixture. The banner at the top says which one you are looking at.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.policies.scoring import (Weights, clone_policy, hybrid_policy, random_policy,  # noqa: E402
                                  ranks_from_scores, relevance_policy, ucb_policy)

st.set_page_config(page_title="Algorithmic Mirrors", layout="wide")


@st.cache_data
def load_fixture() -> dict:
    real = ROOT / "demo" / "real_fixture.json"
    p = real if real.exists() else ROOT / "demo" / "sample_data.json"
    fx = json.loads(p.read_text())
    fx["_path"] = str(p.relative_to(ROOT))
    return fx


fx = load_fixture()
if fx.get("synthetic", True):
    st.error(f"SYNTHETIC DEMO FIXTURE ({fx['_path']}). Every number on this page is seeded noise that "
             "illustrates the mechanics. Nothing here is an experimental result.", icon="⚠️")
else:
    st.success(f"Real experiment output: {fx['_path']} (generated {fx.get('generated', '?')}).")

st.title("Algorithmic Mirrors: prediction vs. augmentation")
st.caption("Left: what the model knows at time t. Middle: exposures available at t and how each policy scores "
           "them. Right: which policy would have surfaced the exposures that later turned out to matter.")

days = fx["days"]
dates = [d["date"] for d in days]
cons_days = [i for i, d in enumerate(days) if any(c["consequential_label"] for c in d["candidates"])]

# ---------------- sidebar: sliders ----------------
with st.sidebar:
    st.header("Serendipity weights")
    w0 = fx.get("weights_default", {})
    w = Weights(
        relevance=st.slider("λ relevance", 0.0, 2.0, float(w0.get("relevance", 1.0)), 0.05),
        uncertainty=st.slider("λ uncertainty", 0.0, 2.0, float(w0.get("uncertainty", 0.5)), 0.05),
        novelty=st.slider("λ novelty", 0.0, 2.0, float(w0.get("novelty", 0.5)), 0.05),
        info_gain=st.slider("λ information gain", 0.0, 2.0, float(w0.get("info_gain", 0.5)), 0.05),
        option_value=st.slider("λ option value", 0.0, 2.0, float(w0.get("option_value", 0.5)), 0.05),
        cost=st.slider("λ cost", 0.0, 2.0, float(w0.get("cost", 0.25)), 0.05),
    )
    k = st.select_slider("exposure budget k", options=[1, 3, 5, 10], value=5)
    seed = st.number_input("seed (random / ε-greedy)", 0, 10_000, 0)
    st.markdown("---")
    jump = st.checkbox("only show days with a later-consequential exposure", value=True)

idx_options = cons_days if (jump and cons_days) else list(range(len(days)))
sel = st.select_slider("time t", options=idx_options, value=idx_options[0], format_func=lambda i: dates[i])
day = days[sel]
cands = pd.DataFrame(day["candidates"])
rng = np.random.default_rng(int(seed))

POLICIES = {
    "Clone / Exploit": lambda df: clone_policy(df, rng) if "clone_loglik" in df else relevance_policy(df, rng),
    "Curious": lambda df: ucb_policy(1.0)(df, rng),
    "Serendipity": lambda df: hybrid_policy(w)(df, rng),
    "Random": lambda df: random_policy(df, np.random.default_rng(int(seed))),
}
ranks = {name: ranks_from_scores(fn(cands)) for name, fn in POLICIES.items()}
cands["score_serendipity"] = hybrid_policy(w)(cands, rng)
for name, r in ranks.items():
    cands[f"rank: {name}"] = r

left, mid, right = st.columns([1.0, 1.6, 1.2])

# ---------------- LEFT: state at t ----------------
with left:
    st.subheader(f"State at {day['date']}")
    s = day["state"]
    st.metric("belief uncertainty H(b_t) (proxy)", f"{s['belief_uncertainty']:.2f}")
    st.markdown("**Recent activities**")
    for a in s["recent_activities"]:
        st.markdown(f"- {a}")
    st.markdown("**Modeled interests**")
    st.bar_chart(pd.Series(s["modeled_interests"]).sort_values(ascending=False), height=160)
    st.markdown("**Active people / projects**")
    for a in s["active_people_projects"]:
        st.markdown(f"- {a}")

# ---------------- MIDDLE: candidates ----------------
with mid:
    st.subheader(f"Candidate exposures at t  (n={len(cands)})")
    order = st.radio("order by", ["Serendipity", "Clone / Exploit", "Curious", "Random"], horizontal=True)
    show = cands.sort_values(f"rank: {order}")
    cols = ["kind", "topic", "relevance", "novelty", "uncertainty", "info_gain", "option_value", "cost",
            "score_serendipity", f"rank: {order}", "consequential_label", "actually_encountered"]
    st.dataframe(
        show[cols].rename(columns={"score_serendipity": "final score", "consequential_label": "later consequential",
                                    "actually_encountered": "encountered"}),
        height=520, hide_index=True,
        column_config={c: st.column_config.ProgressColumn(c, min_value=0.0, max_value=1.0, format="%.2f")
                       for c in ["relevance", "novelty", "uncertainty", "info_gain", "option_value", "cost"]},
    )

# ---------------- RIGHT: counterfactual comparison ----------------
with right:
    st.subheader("Counterfactual: who would have surfaced it?")
    tabs = st.tabs(["Clone / Exploit", "Curious", "Serendipity", "Random", "Actual history"])
    cons = cands[cands["consequential_label"]]
    for tab, name in zip(tabs[:4], ["Clone / Exploit", "Curious", "Serendipity", "Random"]):
        with tab:
            topk = cands.sort_values(f"rank: {name}").head(k)
            st.markdown(f"**Top-{k} under {name}**")
            st.table(topk[["kind", "topic", f"rank: {name}"]].reset_index(drop=True))
            if len(cons):
                hit = int((cons[f"rank: {name}"] <= k).sum())
                st.metric(f"later-consequential exposures in top-{k}", f"{hit} / {len(cons)}")
    with tabs[4]:
        enc = cands[cands["actually_encountered"]]
        st.markdown(f"**Actually encountered that day: {len(enc)}**")
        st.table(enc[["kind", "topic", "consequential_label"]].head(k).reset_index(drop=True))

    if len(cons):
        st.markdown("---")
        st.markdown("**Historically consequential exposure(s) on this day**")
        for _, c in cons.iterrows():
            st.markdown(f"*{c['summary_redacted']}*")
            a, b, cc = st.columns(3)
            a.metric("Relevance-only rank", int(c["rank: Clone / Exploit"]))
            b.metric("Serendipity-policy rank", int(c["rank: Serendipity"]))
            cc.metric("Actually encountered", "yes" if c["actually_encountered"] else "no")
    else:
        st.info("No later-consequential exposure on this day.")

# ---------------- bottom: whole-history summary under current weights ----------------
st.markdown("---")
st.subheader(f"Across all {len(days)} time points: recall@{k} of later-consequential exposures")
rows = []
for d in days:
    df = pd.DataFrame(d["candidates"])
    if not df["consequential_label"].any():
        continue
    r_local = np.random.default_rng(int(seed))
    for name, fn in {"Clone / Exploit": relevance_policy, "Curious": ucb_policy(1.0),
                     "Serendipity": hybrid_policy(w), "Random": random_policy}.items():
        rk = ranks_from_scores(fn(df, r_local))
        pos = df["consequential_label"].to_numpy()
        rows.append({"policy": name, "hit": float((rk[pos] <= k).mean())})
summary = pd.DataFrame(rows).groupby("policy")["hit"].mean().reindex(
    ["Clone / Exploit", "Curious", "Serendipity", "Random"])
st.bar_chart(summary, height=200)
st.caption("Bars are the fraction of later-consequential exposures ranked within the budget. "
           + ("SYNTHETIC: the fixture plants consequential exposures with low relevance and high novelty, "
              "so this pattern is built in, not discovered." if fx.get("synthetic", True) else
              "Computed from real experiment output under the current slider weights."))
