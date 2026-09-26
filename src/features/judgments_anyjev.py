#!/usr/bin/env python3
"""Typed-judgment pass with AnyJev (nokia-applied-research/AnyJev, Apache-2.0) at
level L0 (zero labels: position bias averaged over option rotations, label prior
divided out), served by the subject's own PC (vLLM, Gemma 4 31B AWQ) over the
tailnet. Nothing leaves the subject's machines.

Questions are the same six as judgments_local.py, expressed as AnyJev
Question.noul / .score(levels=…) / .choice. Output: data/derived/judgments.parquet
with one column per answer option plus the winning level, and `anyjev_level`.

Later (needs Carl's Tier B labels): Decider.fit_head(question, states, labels)
fits an L2 closed-form head on the served model's hidden state, i.e. the
"fine-tuned AnyJev" for the *consequential* judgment itself. That requires a
vLLM embed server (pooling) and is not run here.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import orjson
import pandas as pd
from anyjev import Decider, Question
from anyjev.backends.vllm import VLLMBackend

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.features.judgments_local import MAX_CHARS, SOURCES, STATE, situation  # noqa: E402

DER = ROOT / "data" / "derived"
URL, SERVED, TOKENIZER = "http://<tailnet-host>:8000", "gemma-4-31b-it", "QuantTrio/gemma-4-31B-it-AWQ"

QUESTIONS = [
    Question.noul("Does the message invite the recipient to an event, opportunity, project, job, collaboration, "
                  "meeting, or community, or ask them to apply, join, or participate?", name="invites_action"),
    Question.noul("Does the sender expect a reply from the recipient?", name="expects_reply"),
    Question.noul("Is the sender writing on behalf of, or introducing, an organization, group, community, or project, "
                  "rather than having purely personal chat?", name="org_or_group"),
    Question.noul("Is this an automated, system, bulk, or marketing message rather than a message written by a person "
                  "to this recipient?", name="automated"),
    Question.score("If the recipient engages with this message, how much could it open new people, communities, "
                   "skills, or projects for them?",
                   levels=["nothing new: routine, personal, or transactional", "slight",
                           "moderate: a new contact or activity",
                           "substantial: a new community, opportunity, role, or collaboration"], name="option_value"),
    Question.choice("What kind of message is this?",
                    ["invitation or opportunity", "request for help or a favor", "personal or social chat",
                     "transactional, notification, or logistics", "marketing or spam", "other"], name="exposure_type"),
]
TYPE_KEYS = ["invitation", "request", "social", "transactional", "marketing", "other"]


def load_texts(exp: pd.DataFrame) -> dict[str, str]:
    want = {(th, int(t.value)): eid for eid, t, th in zip(exp["exposure_id"], exp["t"], exp["thread"])}
    texts = {}
    for src in SOURCES:
        p = STATE / f"{src}.jsonl"
        if not p.exists():
            continue
        with p.open("rb") as fh:
            for line in fh:
                r = orjson.loads(line); m = r.get("meta") or {}; th = m.get("thread_hash")
                if not th:
                    continue
                t = pd.Timestamp(r["t_start"]); t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
                key = (f"{src}:{th}", int(t.value))
                if key in want and isinstance(r.get("content"), str) and r["content"].strip():
                    texts[want[key]] = r["content"][:MAX_CHARS]
    return texts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--chunk", type=int, default=200)
    ap.add_argument("--out", default=str(DER / "judgments.parquet"))
    a = ap.parse_args()
    exp = pd.read_parquet(DER / "exposures.parquet")
    exp["t"] = pd.to_datetime(exp["t"], utc=True)
    if not a.all:
        exp = exp[exp["is_new_thread"] | exp["is_dormant"]]
    if a.limit:
        exp = exp.head(a.limit)
    outp = Path(a.out)
    rows, done = [], set()
    if outp.exists():
        prev = pd.read_parquet(outp); rows = prev.to_dict("records"); done = set(prev["exposure_id"])
        print(f"resuming with {len(done)} done", file=sys.stderr)
    exp = exp[~exp["exposure_id"].isin(done)]
    texts = load_texts(exp)
    todo = [r for r in exp.itertuples() if r.exposure_id in texts]
    print(f"to score: {len(todo)} exposures × {len(QUESTIONS)} questions (AnyJev L0, {SERVED})", file=sys.stderr)
    be = VLLMBackend(URL, SERVED, tokenizer_name=TOKENIZER, workers=a.workers)
    d = Decider(be, level="L0")
    t0 = time.time()
    for c0 in range(0, len(todo), a.chunk):
        chunk = todo[c0:c0 + a.chunk]
        states = [{"situation": situation(r), "message": texts[r.exposure_id]} for r in chunk]
        cols = {r.exposure_id: {"exposure_id": r.exposure_id, "model": SERVED} for r in chunk}
        for q in QUESTIONS:
            decs = d.decide_batch(states, q)
            for r, dc in zip(chunk, decs):
                p = np.asarray(dc.probs, dtype=float); o = cols[r.exposure_id]
                o["anyjev_level"] = dc.level
                if q.kind == "noul":
                    o[f"p_{q.name}"] = float(p[0])
                elif q.kind == "score":
                    o[f"ev_{q.name}"] = float((p * np.arange(len(p))).sum())
                    for i, v in enumerate(p):
                        o[f"p_{q.name}_{i}"] = float(v)
                else:
                    for k, v in zip(TYPE_KEYS, p):
                        o[f"p_{q.name}_{k}"] = float(v)
        rows.extend(cols.values())
        pd.DataFrame(rows).to_parquet(outp, index=False)
        n = c0 + len(chunk); el = time.time() - t0
        print(f"{n}/{len(todo)} in {el:.0f}s ({el/n:.2f}s each), eta {(len(todo)-n)*el/n/60:.0f} min", file=sys.stderr)
    print(f"wrote {outp}: {len(rows)} rows", file=sys.stderr)


if __name__ == "__main__":
    main()
