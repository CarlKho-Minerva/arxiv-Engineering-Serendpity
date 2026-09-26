#!/usr/bin/env python3
"""Local "System One"-style judgment pass (the Jev pattern, run on-device).

For each exposure's first inbound message, ask a fixed set of typed questions and
read the answer *probabilities* from next-token logits of a local model
(Qwen3-8B, MLX, 8-bit). No text is generated, no data leaves the machine.

Primitives (mirroring TypeSafe's Choice / Noul / Score, see docs.typesafe.ai):
  noul  -> P(yes) from logits over {yes, no}
  score -> expected level from logits over ordered levels {0..3}
  choice-> distribution over option letters {A..F}

Output: data/derived/judgments.parquet (exposure_id + one column per answer).
State given to the model: platform, thread situation (new / dormant / ongoing,
group or 1:1), year, and the message text (truncated). The recipient is never
named. Questions are message-level; they cannot see the subject's history, so
"new community" is judged from the message alone (documented limitation).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import mlx.core as mx
import numpy as np
import pandas as pd
import orjson
from mlx_lm import load

ROOT = Path(__file__).resolve().parents[2]
DER = ROOT / "data" / "derived"
STATE = Path("~/.local/state/lifeos/carl-model/events").expanduser()
SOURCES = ["msg_messenger", "msg_instagram", "msg_twitter", "msg_telegram", "msg_discord", "msg_gmail",
           "msg_linkedin", "msg_gchat", "msg_gvoice"]
MODEL = "mlx-community/Qwen3-8B-8bit"
MAX_CHARS = 700

QUESTIONS = {
    "invites_action": ("noul", "Does the message invite the recipient to an event, opportunity, project, job, "
                       "collaboration, meeting, or community, or ask them to apply, join, or participate?"),
    "expects_reply": ("noul", "Does the sender expect a reply from the recipient?"),
    "org_or_group": ("noul", "Is the sender writing on behalf of, or introducing, an organization, group, community, "
                     "or project, rather than having purely personal chat?"),
    "automated": ("noul", "Is this an automated, system, bulk, or marketing message rather than a message written "
                  "by a person to this recipient?"),
    "option_value": ("score", "If the recipient engages with this message, how much could it open new people, "
                     "communities, skills, or projects for them? Answer with one word: "
                     "none = nothing new (routine, personal, or transactional); slight = a little; "
                     "moderate = a new contact or activity; substantial = a new community, "
                     "opportunity, role, or collaboration."),
    "exposure_type": ("choice", "What kind of message is this? Answer with one letter: "
                      "A = invitation or opportunity; B = request for help or a favor; C = personal or social chat; "
                      "D = transactional, notification, or logistics; E = marketing or spam; F = other."),
}
ANSWER_TOKENS = {"noul": ["yes", "no"], "score": ["none", "slight", "moderate", "substantial"], "choice": ["A", "B", "C", "D", "E", "F"]}


def situation(row) -> str:
    kind = "first message ever in this thread" if row.is_new_thread else (
        "thread was silent for over 180 days" if row.is_dormant else "ongoing thread")
    return (f"platform: {row.source.replace('msg_', '')}; thread: {kind}; "
            f"{'group chat with ' + str(int(row.npart)) + ' participants' if row.is_group else 'one-to-one'}; "
            f"year: {row.t.year}")


def build_prompt(tok, state: str, text: str, q: str, kind: str) -> str:
    fmt = {"noul": "Answer with exactly one word: yes or no.", "score": "Answer with exactly one word: none, slight, moderate, or substantial.",
           "choice": "Answer with exactly one letter: A, B, C, D, E, or F."}[kind]
    msgs = [{"role": "system", "content": "You judge one inbound message received by a person. Use only the message "
             "and the situation. Be literal and calibrated. " + fmt},
            {"role": "user", "content": f"Situation: {state}\n\nMessage from the sender:\n\"\"\"\n{text}\n\"\"\"\n\n"
             f"Question: {q}\n{fmt}"}]
    p = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    return p + "Answer: "


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only-candidates", action="store_true", default=True)
    ap.add_argument("--all", dest="only_candidates", action="store_false")
    ap.add_argument("--out", default=str(DER / "judgments.parquet"))
    a = ap.parse_args()
    exp = pd.read_parquet(DER / "exposures.parquet")
    exp["t"] = pd.to_datetime(exp["t"], utc=True)
    if a.only_candidates:
        exp = exp[exp["is_new_thread"] | exp["is_dormant"]]
    if a.limit:
        exp = exp.head(a.limit)
    want = {(th, int(t.value)): eid for eid, t, th in zip(exp["exposure_id"], exp["t"], exp["thread"])}
    texts = {}
    for src in SOURCES:
        p = STATE / f"{src}.jsonl"
        if not p.exists():
            continue
        with p.open("rb") as fh:
            for line in fh:
                r = orjson.loads(line)
                m = r.get("meta") or {}
                th = m.get("thread_hash")
                if not th:
                    continue
                t = pd.Timestamp(r["t_start"]); t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
                key = (f"{src}:{th}", int(t.value))
                if key in want and isinstance(r.get("content"), str):
                    texts[want[key]] = r["content"][:MAX_CHARS]
    print(f"texts: {len(texts)} / {len(exp)}", file=sys.stderr)
    model, tok = load(a.model)
    # answer token ids: use the first token of " yes"/" no" etc. after "Answer:" (leading space variant + bare)
    def ids(word):
        out = set()
        for v in (" " + word, word):
            enc = tok.encode(v, add_special_tokens=False)
            if len(enc) == 1:
                out.add(enc[0])
        return out
    tokid = {}
    for k, ws in ANSWER_TOKENS.items():
        raw = {w: ids(w) for w in ws}
        shared = {i for w in ws for i in raw[w] if sum(i in raw[x] for x in ws) > 1}
        tokid[k] = {w: sorted(raw[w] - shared) for w in ws}
        if any(not v for v in tokid[k].values()):
            sys.exit(f"no unique single token for some answer in {k}: {tokid[k]}")
    print("answer token ids:", tokid, file=sys.stderr)
    rows, t0, n = [], time.time(), 0
    for row in exp.itertuples():
        text = texts.get(row.exposure_id)
        if not text or not text.strip():
            continue
        out = {"exposure_id": row.exposure_id}
        st = situation(row)
        for name, (kind, q) in QUESTIONS.items():
            prompt = build_prompt(tok, st, text, q, kind)
            toks = mx.array(tok.encode(prompt))[None]
            logits = model(toks)[0, -1].astype(mx.float32)
            lp = logits - mx.logsumexp(logits)
            lp = np.array(lp)
            # log-sum over token-id variants per answer, then renormalize over the answer set
            vals = np.array([np.logaddexp.reduce(lp[tokid[kind][w]]) for w in ANSWER_TOKENS[kind]])
            pr = np.exp(vals - np.logaddexp.reduce(vals))
            out[f"{name}_mass"] = float(np.exp(np.logaddexp.reduce(vals)))  # how much prob sat on legal answers
            if kind == "noul":
                out[f"p_{name}"] = float(pr[0])
            elif kind == "score":
                out[f"ev_{name}"] = float((pr * np.arange(len(pr))).sum())
                for i, p_ in enumerate(pr):
                    out[f"p_{name}_{i}"] = float(p_)
            else:
                for w, p_ in zip(ANSWER_TOKENS[kind], pr):
                    out[f"p_{name}_{w}"] = float(p_)
        rows.append(out); n += 1
        if n % 100 == 0:
            el = time.time() - t0
            print(f"{n} exposures, {el:.0f}s, {el/n:.2f}s each, eta {(len(texts)-n)*el/n/60:.0f} min", file=sys.stderr)
            pd.DataFrame(rows).to_parquet(a.out, index=False)   # checkpoint
    pd.DataFrame(rows).to_parquet(a.out, index=False)
    print(f"wrote {a.out}: {len(rows)} rows in {time.time()-t0:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
