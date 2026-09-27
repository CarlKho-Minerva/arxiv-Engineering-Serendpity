#!/usr/bin/env python3
"""Second rater: the same six AnyJev questions answered by a different model on
the Mac (Qwen3-8B, MLX, 8-bit) at level L0. Output data/derived/judgments_qwen8b.parquet.
Purpose: inter-model agreement on the judgment features; not used for ranking."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from anyjev import Decider

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.features.anyjev_mlx_backend import MLXBackend  # noqa: E402
from src.features.judgments_anyjev import QUESTIONS, TYPE_KEYS, load_texts  # noqa: E402
from src.features.judgments_local import situation  # noqa: E402

DER = ROOT / "data" / "derived"
MODEL = "mlx-community/Qwen3-8B-8bit"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--chunk", type=int, default=100)
    ap.add_argument("--out", default=str(DER / "judgments_qwen8b.parquet"))
    ap.add_argument("--shard", default="0/1", help="i/n: take every n-th exposure starting at i")
    ap.add_argument("--texts-json", default=None, help="standalone mode: read [{exposure_id, situation, message}] instead of the event stream")
    a = ap.parse_args()
    import json
    from types import SimpleNamespace
    outp = Path(a.out); rows, done = [], set()
    if outp.exists():
        prev = pd.read_parquet(outp); rows = prev.to_dict("records"); done = set(prev["exposure_id"])
    if a.texts_json:
        items = [SimpleNamespace(**x) for x in json.loads(Path(a.texts_json).read_text())]
        todo = [x for x in items if x.exposure_id not in done]
        texts = {x.exposure_id: x.message for x in todo}
        sit = {x.exposure_id: x.situation for x in todo}
        situation_of = lambda r: sit[r.exposure_id]  # noqa: E731
    else:
        exp = pd.read_parquet(DER / "exposures.parquet")
        exp["t"] = pd.to_datetime(exp["t"], utc=True)
        exp = exp[exp["is_new_thread"] | exp["is_dormant"]].reset_index(drop=True)
        i, n = (int(x) for x in a.shard.split("/"))
        exp = exp.iloc[i::n]
        if a.limit:
            exp = exp.head(a.limit)
        exp = exp[~exp["exposure_id"].isin(done)]
        texts = load_texts(exp)
        todo = [r for r in exp.itertuples() if r.exposure_id in texts]
        situation_of = situation
    print(f"to score: {len(todo)} on {MODEL} (MLX, L0)", file=sys.stderr)
    d = Decider(MLXBackend(MODEL), level="L0")
    t0 = time.time()
    for c0 in range(0, len(todo), a.chunk):
        chunk = todo[c0:c0 + a.chunk]
        states = [{"situation": situation_of(r), "message": texts[r.exposure_id]} for r in chunk]
        cols = {r.exposure_id: {"exposure_id": r.exposure_id, "model": MODEL} for r in chunk}
        for q in QUESTIONS:
            for r, dc in zip(chunk, d.decide_batch(states, q)):
                p = np.asarray(dc.probs, dtype=float); o = cols[r.exposure_id]; o["anyjev_level"] = dc.level
                if q.kind == "noul":
                    o[f"p_{q.name}"] = float(p[0])
                elif q.kind == "score":
                    o[f"ev_{q.name}"] = float((p * np.arange(len(p))).sum())
                    for i, v in enumerate(p):
                        o[f"p_{q.name}_{i}"] = float(v)
                else:
                    for k, v in zip(TYPE_KEYS, p):
                        o[f"p_{q.name}_{k}"] = float(v)
        rows.extend(cols.values()); pd.DataFrame(rows).to_parquet(outp, index=False)
        n = c0 + len(chunk); el = time.time() - t0
        print(f"{n}/{len(todo)} in {el:.0f}s ({el/n:.2f}s each), eta {(len(todo)-n)*el/n/60:.0f} min", file=sys.stderr)
    print(f"wrote {outp}: {len(rows)} rows", file=sys.stderr)


if __name__ == "__main__":
    main()
