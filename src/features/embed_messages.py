#!/usr/bin/env python3
"""Local embedding pass over message text. Nothing leaves the machine.

Embeds (a) the first inbound message of every contact event in
data/derived/exposures.parquet and (b) every subject-sent message with
>= MIN_CHARS characters, with a multilingual sentence encoder run locally
(MPS if available). Writes float16 matrices to data/derived/ (git-ignored):

  emb_exposures.npz : exposure_id[str], emb[n,384]
  emb_self.npz      : t_ns[int64 sorted], thread[str], emb[n,384]

Text is held in memory only for the duration of the run and never written.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np
import orjson
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
STATE = Path(os.environ.get("CARL_MODEL_STATE", "~/.local/state/lifeos/carl-model")).expanduser()
EVENTS = STATE / "events"
DER = ROOT / "data" / "derived"
SOURCES = ["msg_messenger", "msg_instagram", "msg_twitter", "msg_telegram", "msg_discord", "msg_gmail",
           "msg_linkedin", "msg_gchat", "msg_gvoice"]
LOCK = pd.Timestamp("2026-09-17", tz="UTC")
MIN_CHARS = 20
MAX_CHARS = 1000
MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--limit", type=int, default=0, help="debug: cap self messages")
    a = ap.parse_args()
    exp = pd.read_parquet(DER / "exposures.parquet", columns=["exposure_id", "t", "thread"])
    exp["t"] = pd.to_datetime(exp["t"], utc=True)
    want = {(th, int(t.value)): eid for eid, t, th in zip(exp["exposure_id"], exp["t"], exp["thread"])}
    exp_text: dict[str, str] = {}
    self_rows: list[tuple[int, str, str]] = []
    t0 = time.time()
    for src in SOURCES:
        p = EVENTS / f"{src}.jsonl"
        if not p.exists():
            continue
        with p.open("rb") as fh:
            for line in fh:
                r = orjson.loads(line)
                meta = r.get("meta") or {}
                th = meta.get("thread_hash")
                c = r.get("content")
                if not th or not isinstance(c, str) or not c.strip():
                    continue
                t = pd.Timestamp(r["t_start"])
                t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
                if t >= LOCK:
                    continue
                key = (f"{src}:{th}", int(t.value))
                if key in want:
                    exp_text[want[key]] = c[:MAX_CHARS]
                if r.get("actor") == "carl" and len(c) >= MIN_CHARS:
                    self_rows.append((int(t.value), f"{src}:{th}", c[:MAX_CHARS]))
        print(f"{src}: scanned ({time.time()-t0:.0f}s), exposures matched {len(exp_text)}, self msgs {len(self_rows)}", file=sys.stderr)
    if a.limit:
        self_rows = self_rows[: a.limit]
    missing = len(exp) - len(exp_text)
    print(f"exposure texts: {len(exp_text)} / {len(exp)} (missing {missing}); self messages: {len(self_rows)}", file=sys.stderr)

    import torch
    from sentence_transformers import SentenceTransformer
    dev = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
    model = SentenceTransformer(a.model, device=dev)
    model.max_seq_length = 128
    print(f"model {a.model} on {dev}", file=sys.stderr)

    eids = list(exp_text)
    E = model.encode([exp_text[e] for e in eids], batch_size=a.batch, normalize_embeddings=True,
                     convert_to_numpy=True, show_progress_bar=False)
    np.savez(DER / "emb_exposures.npz", exposure_id=np.array(eids), emb=E.astype(np.float16))
    print(f"exposure embeddings done ({time.time()-t0:.0f}s)", file=sys.stderr)

    self_rows.sort()
    texts = [r[2] for r in self_rows]
    S = model.encode(texts, batch_size=a.batch, normalize_embeddings=True, convert_to_numpy=True,
                     show_progress_bar=False)
    np.savez(DER / "emb_self.npz", t_ns=np.array([r[0] for r in self_rows], dtype=np.int64),
             thread=np.array([r[1] for r in self_rows]), emb=S.astype(np.float16))
    del texts, self_rows, exp_text
    print(f"self embeddings done ({time.time()-t0:.0f}s): {S.shape}", file=sys.stderr)


if __name__ == "__main__":
    main()
