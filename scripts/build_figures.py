#!/usr/bin/env python3
"""Build publication figures into paper/figures/.

Figure 1 (architecture) needs no data.
Figure 2 (counterfactual timeline) is built from results/retrospective/*.parquet
if present; otherwise from demo/sample_data.json with a SYNTHETIC watermark.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.visualization.architecture import draw as draw_arch  # noqa: E402
from src.visualization.counterfactual_timeline import draw as draw_cf  # noqa: E402
from src.visualization.forest import draw as draw_forest  # noqa: E402

FIG = ROOT / "paper" / "figures"


def main() -> None:
    for p in draw_arch(FIG):
        print("wrote", p.relative_to(ROOT))
    if (ROOT / "results" / "metrics_test_primary.json").exists():
        for p in draw_forest(ROOT / "results", FIG):
            print("wrote", p.relative_to(ROOT))
    real = ROOT / "results" / "retrospective" / "exposures_ranked_test_primary.parquet"
    if real.exists():
        df = pd.read_parquet(real)
        for p in draw_cf(df, FIG, synthetic=False, k=1, log_ranks=False,
                         exploit_label="relevance-only rank (clone proxy)",
                         explore_label="new-thread-first rank (mean over 20 tie-breaks)",
                         hybrid_label="hybrid exploration-score rank",
                         stream_label="held-out test period: weak-tie inbound exposures stacked by week  (gray = ordinary · ring = became a lasting tie within 365 d)",
                         stack_stream=True, rank_unit="week"):
            print("wrote", p.relative_to(ROOT))
    else:
        fx = json.loads((ROOT / "demo" / "sample_data.json").read_text())
        rows = []
        for day in fx["days"]:
            for c in day["candidates"]:
                rows.append({"t": day["date"], "consequential": int(c["consequential_label"]),
                             "rank_exploit": c["rank"]["exploit"], "rank_explore": c["rank"]["serendipity"],
                             "downstream": c.get("downstream", [])})
        for p in draw_cf(pd.DataFrame(rows), FIG, synthetic=True):
            print("wrote", p.relative_to(ROOT), "(SYNTHETIC)")


if __name__ == "__main__":
    main()
