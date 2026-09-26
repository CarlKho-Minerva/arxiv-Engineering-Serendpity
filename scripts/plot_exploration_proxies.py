#!/usr/bin/env python3
"""Figure 3 (exploratory): monthly exploration proxies from results/exploration_proxies_monthly.json.
Overlays per-source coverage so platform migration is not read as behaviour change."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "results" / "exploration_proxies_monthly.json"
FIG = ROOT / "paper" / "figures"
INK, BODY, MUTE, HAIR, ACC = "#171717", "#4d4d4d", "#888888", "#d9d9d9", "#0070f3"


def main():
    if not SRC.exists():
        sys.exit(f"missing {SRC}")
    d = json.loads(SRC.read_text())
    rows = []
    for key, c in d["series"].items():
        src, month = key.split("|")
        rows.append({"source": src, "month": pd.Timestamp(month + "-01"), **c})
    df = pd.DataFrame(rows).fillna(0)
    allm = df[df.source == "all"].set_index("month").sort_index().drop(columns=["source"])
    allm = allm[allm.index >= "2011-01-01"]
    # 3-month rolling to tame monthly noise
    r = allm.rolling(3, min_periods=1).mean()
    fig, axes = plt.subplots(4, 1, figsize=(11, 9), sharex=True, gridspec_kw={"hspace": 0.12})
    ax = axes[0]
    ax.plot(r.index, r["new_threads_inbound"], color=MUTE, label="new threads, other-initiated")
    ax.plot(r.index, r["new_threads_outbound"], color=ACC, label="new threads, self-initiated")
    ax.set_ylabel("new threads / month"); ax.legend(frameon=False, fontsize=8)
    ax = axes[1]
    num = allm["replied_new_inbound"].rolling(3, min_periods=1).sum()
    den = allm["new_threads_inbound"].rolling(3, min_periods=1).sum()
    rate = (num / den).where(den >= 15)   # mask windows with < 15 new inbound threads per 3 months
    ax.plot(rate.index, rate, color=INK); ax.set_ylim(0, 1); ax.set_ylabel("reply rate to\nnew inbound (7 d)")
    ax.text(0.01, 0.06, "masked where < 15 new inbound threads per 3-month window", transform=ax.transAxes, fontsize=7, color=MUTE)
    ax = axes[2]
    ax.plot(r.index, r["dormant_self_initiated"], color=ACC, label="self-initiated")
    ax.plot(r.index, r["dormant_reactivated"] - r["dormant_self_initiated"], color=MUTE, label="other-initiated")
    ax.set_ylabel("dormant ties\nreactivated / month"); ax.legend(frameon=False, fontsize=8)
    ax = axes[3]
    src = df[df.source != "all"].pivot_table(index="month", columns="source", values="msgs_out", aggfunc="sum").fillna(0)
    src = src[src.index >= "2011-01-01"]
    ax.stackplot(src.index, [src[c] for c in src.columns], labels=[c.replace("msg_", "") for c in src.columns],
                 colors=plt.cm.Greys([0.25 + 0.65 * i / max(1, len(src.columns) - 1) for i in range(len(src.columns))]))
    ax.set_ylabel("outbound msgs / month\n(by source: coverage)"); ax.legend(frameon=False, fontsize=7, ncol=3, loc="upper left")
    for a in axes:
        a.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Exploration-rate proxies from logged messaging, 2011–2026 (exploratory; 3-month rolling means; counts only)",
                 fontsize=10, color=BODY)
    FIG.mkdir(exist_ok=True, parents=True)
    for ext in ("svg", "pdf", "png"):
        fig.savefig(FIG / f"fig3_exploration_proxies.{ext}", dpi=300 if ext == "png" else None, bbox_inches="tight")
    print("wrote fig3_exploration_proxies.{svg,pdf,png}")


if __name__ == "__main__":
    main()
