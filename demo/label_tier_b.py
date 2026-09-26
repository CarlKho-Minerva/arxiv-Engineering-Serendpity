"""Tier B labelling page.  .venv/bin/streamlit run demo/label_tier_b.py --server.port 8512

Walks annotations/private/tier_b_sample_v1.csv, shows the exposure with its
before/after thread context, saves one row per label to
annotations/private/tier_b_labels_v1.csv immediately, and resumes. Shows no
policy ranking and no Tier A label. Everything stays local.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
PRIV = ROOT / "annotations" / "private"
SAMPLE, CTX, LABELS = PRIV / "tier_b_sample_v1.csv", PRIV / "tier_b_context_v1.json", PRIV / "tier_b_labels_v1.csv"
OUTCOMES = ["repeat interactions", "resulting project", "resulting application", "money or prize", "publication",
            "new collaborator", "sustained topic shift", "repeated behavior (e.g. attended ≥2 more events)", "none"]

st.set_page_config(page_title="Tier B labels", layout="wide")
st.markdown("""<style>
.block-container{padding-top:1rem;max-width:1100px}
.msg{border-left:2px solid #262626;padding:.25rem .6rem;margin:.2rem 0;color:#a1a1a1;font-size:14px}
.msg.you{border-left-color:#52a8ff;color:#ededed}
.exp{background:#111;border:1px solid #262626;border-radius:8px;padding:.8rem 1rem;font-size:16px;white-space:pre-wrap}
.mono{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:#7a7a7a;text-transform:uppercase;letter-spacing:.04em}
</style>""", unsafe_allow_html=True)


@st.cache_data
def load():
    s = pd.read_csv(SAMPLE, dtype={"exposure_id": str}).fillna("")
    c = json.loads(CTX.read_text()) if CTX.exists() else {}
    return s, c


def labels() -> pd.DataFrame:
    if LABELS.exists():
        return pd.read_csv(LABELS, dtype={"exposure_id": str})
    return pd.DataFrame(columns=["sample_id", "exposure_id", "consequential", "outcome_type", "evidence",
                                 "confidence", "rationale", "labelled_at"])


def save(row: dict):
    df = labels()
    df = df[df["exposure_id"] != row["exposure_id"]]
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df.to_csv(LABELS, index=False)


samp, ctx = load()
done = labels()
done_ids = set(done["exposure_id"])
todo = [i for i, e in enumerate(samp["exposure_id"]) if e not in done_ids]
if "i" not in st.session_state:
    st.session_state.i = todo[0] if todo else 0

top = st.columns([3, 1, 1, 1])
top[0].markdown(f"<span class='mono'>Tier B · {len(done_ids)} / {len(samp)} labelled · blind to rankings and Tier A</span>", unsafe_allow_html=True)
if top[1].button("← prev", use_container_width=True):
    st.session_state.i = max(0, st.session_state.i - 1)
if top[2].button("next →", use_container_width=True):
    st.session_state.i = min(len(samp) - 1, st.session_state.i + 1)
if top[3].button("next unlabelled", use_container_width=True, type="primary"):
    nxt = [i for i in todo if i > st.session_state.i] or todo
    st.session_state.i = nxt[0] if nxt else st.session_state.i
if not todo:
    st.success("All 300 labelled. Freeze the protocol next.")

i = st.session_state.i
r = samp.iloc[i]
c = ctx.get(r["exposure_id"], {})
prev = done[done["exposure_id"] == r["exposure_id"]]
left, right = st.columns([1.15, 1])

with left:
    st.markdown(f"<span class='mono'>{r['sample_id']} · {r['date']} · {r['source']} · {r['situation']}</span>", unsafe_allow_html=True)
    if c.get("before"):
        st.markdown("<span class='mono'>before, same thread</span>", unsafe_allow_html=True)
        for m in c["before"]:
            st.markdown(f"<div class='msg {m['who']}'>{m['t']} · {m['who']}: {m['text']}</div>", unsafe_allow_html=True)
    st.markdown("<span class='mono'>the exposure (inbound)</span>", unsafe_allow_html=True)
    st.markdown(f"<div class='exp'>{r['message_text']}</div>", unsafe_allow_html=True)
    st.markdown(f"<span class='mono'>after, within 365 d · {c.get('n_after_total', 0)} messages, {c.get('n_after_you', 0)} yours · last {c.get('last_after') or '—'}</span>", unsafe_allow_html=True)
    for m in c.get("after", []):
        st.markdown(f"<div class='msg {m['who']}'>{m['t']} · {m['who']}: {m['text']}</div>", unsafe_allow_html=True)
    if c.get("n_after_total", 0) > 30:
        st.caption(f"… {c['n_after_total'] - 30} more not shown")

with right:
    st.markdown("<span class='mono'>your label</span>", unsafe_allow_html=True)
    with st.form(key=f"f{i}", clear_on_submit=False):
        cons = st.radio("Did this exposure turn out to be consequential within a year? (a logged downstream artifact: sustained tie, project, application, money, publication, collaborator, topic shift, repeated behavior)",
                        ["no", "yes"], index=int(prev["consequential"].iloc[0]) if len(prev) else 0, horizontal=True)
        outs = st.multiselect("Outcome type(s)", OUTCOMES, default=(prev["outcome_type"].iloc[0].split("|") if len(prev) and prev["outcome_type"].iloc[0] else []))
        ev = st.radio("Evidence", ["direct (a logged artifact in the thread/horizon links exposure → outcome)", "inferred (you remember/believe it, no artifact here)"],
                      index=0 if not len(prev) or str(prev["evidence"].iloc[0]).startswith("direct") else 1)
        conf = st.slider("Confidence", 0.0, 1.0, float(prev["confidence"].iloc[0]) if len(prev) else 0.7, 0.05)
        rat = st.text_area("Rationale (one line)", value=prev["rationale"].iloc[0] if len(prev) else "", height=80)
        submitted = st.form_submit_button("Save and go to next unlabelled", type="primary", use_container_width=True)
    if submitted:
        save({"sample_id": r["sample_id"], "exposure_id": r["exposure_id"], "consequential": int(cons == "yes"),
              "outcome_type": "|".join(outs), "evidence": ev.split(" ")[0], "confidence": conf, "rationale": rat,
              "labelled_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")})
        done_ids.add(r["exposure_id"])
        nxt = [j for j, e in enumerate(samp["exposure_id"]) if e not in done_ids and j > i] or \
              [j for j, e in enumerate(samp["exposure_id"]) if e not in done_ids]
        st.session_state.i = nxt[0] if nxt else i
        st.rerun()
    st.caption("Rules: outcome must be after the exposure and within 365 days. Feeling it mattered without an artifact = inferred. "
               "Skip nothing; 'no' with confidence is a valid label.")
