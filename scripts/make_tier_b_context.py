#!/usr/bin/env python3
"""Evidence context for Tier B labelling: for each sampled exposure, the last 3
messages in the thread before it and up to 30 messages in the 365 days after
(both directions, truncated), plus counts. Written to annotations/private/
(git-ignored). This is the evidence the annotator judges outcomes from; it is
not a ranking and not the Tier A label."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import orjson
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.features.judgments_local import SOURCES, STATE  # noqa: E402

H_NS = 365 * 86400 * 10**9
PRIV = ROOT / "annotations" / "private"


def main():
    samp = pd.read_csv(PRIV / "tier_b_sample_v1.csv", dtype={"exposure_id": str})
    exp = pd.read_parquet(ROOT / "data" / "derived" / "exposures.parquet", columns=["exposure_id", "t", "thread"])
    exp["t"] = pd.to_datetime(exp["t"], utc=True)
    exp = exp[exp["exposure_id"].isin(samp["exposure_id"])]
    threads = set(exp["thread"])
    msgs = {th: [] for th in threads}
    for src in SOURCES:
        p = STATE / f"{src}.jsonl"
        if not p.exists():
            continue
        with p.open("rb") as fh:
            for line in fh:
                r = orjson.loads(line); m = r.get("meta") or {}; th = m.get("thread_hash")
                if not th:
                    continue
                key = f"{src}:{th}"
                if key in threads:
                    c = r.get("content"); c = c if isinstance(c, str) else ""
                    msgs[key].append((r["t_start"], "you" if r.get("actor") == "carl" else "them", c[:300]))
    for th in msgs:
        msgs[th].sort()
    out = {}
    for row in exp.itertuples():
        tn = int(row.t.value)
        allm = [(int(pd.Timestamp(t).tz_localize("UTC").value) if pd.Timestamp(t).tzinfo is None else int(pd.Timestamp(t).tz_convert("UTC").value), who, txt)
                for t, who, txt in msgs[row.thread]]
        before = [m for m in allm if m[0] < tn][-3:]
        after = [m for m in allm if tn < m[0] <= tn + H_NS]
        out[row.exposure_id] = {
            "before": [{"t": pd.Timestamp(t, tz="UTC").strftime("%Y-%m-%d"), "who": w, "text": x} for t, w, x in before],
            "after": [{"t": pd.Timestamp(t, tz="UTC").strftime("%Y-%m-%d"), "who": w, "text": x} for t, w, x in after[:30]],
            "n_after_total": len(after), "n_after_you": sum(1 for m in after if m[1] == "you"),
            "last_after": pd.Timestamp(after[-1][0], tz="UTC").strftime("%Y-%m-%d") if after else None,
        }
    (PRIV / "tier_b_context_v1.json").write_text(json.dumps(out))
    print(f"wrote context for {len(out)} exposures")


if __name__ == "__main__":
    main()
