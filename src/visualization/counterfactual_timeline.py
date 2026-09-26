"""Figure 2: the serendipity counterfactual timeline.

Input is a *results* frame (one row per exposure) with columns:
  t (datetime), consequential (0/1), rank_exploit, rank_explore, label (optional),
  downstream (optional list of (t, label)) for fan-out.
The figure is only built from real experiment output or from the clearly
labelled synthetic fixture; the caller passes `synthetic=True` to watermark it.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

INK, BODY, MUTE, HAIR = "#171717", "#4d4d4d", "#888888", "#d9d9d9"
EXPLOIT, EXPLORE = "#888888", "#0070f3"


def draw(df: pd.DataFrame, out_dir: Path, *, k: int = 5, stem: str = "fig2_counterfactual",
         synthetic: bool = False) -> list[Path]:
    df = df.sort_values("t").reset_index(drop=True)
    t = pd.to_datetime(df["t"], utc=True)
    fig, (ax0, ax1) = plt.subplots(2, 1, figsize=(11, 5.6), sharex=True,
                                   gridspec_kw={"height_ratios": [1.0, 2.2], "hspace": 0.08})
    # top strip: exposure stream
    ordinary = df["consequential"] == 0
    ax0.scatter(t[ordinary], np.zeros(ordinary.sum()), s=8, color=HAIR, zorder=1)
    ax0.scatter(t[~ordinary], np.zeros((~ordinary).sum()), s=60, facecolor="white", edgecolor=INK,
                lw=1.4, zorder=3)
    if "downstream" in df.columns:
        n_down = int(sum(len(r or []) for r in df.loc[~ordinary, "downstream"]))
        for _, row in df[~ordinary].iterrows():
            for (dt_, lab) in (row["downstream"] or []):
                dt_ = pd.Timestamp(dt_, tz="UTC")
                ax0.plot([pd.Timestamp(row["t"], tz="UTC"), dt_], [0, 0.55], color=BODY, lw=0.8, alpha=0.6)
                ax0.scatter([dt_], [0.55], s=14, color=BODY, zorder=2)
                if n_down <= 8:
                    ax0.text(dt_, 0.62, lab, fontsize=6.5, rotation=30, ha="left", va="bottom", color=BODY)
    ax0.set_ylim(-0.25, 1.4); ax0.set_yticks([]); ax0.spines[:].set_visible(False)
    ax0.text(0.0, 1.0, "exposure stream  (gray = ordinary · ring = later consequential · fan-out = downstream events)",
             transform=ax0.transAxes, fontsize=8, color=BODY, va="top")

    # bottom: ranks for consequential exposures under both policies
    cons = df[~ordinary]
    tc = pd.to_datetime(cons["t"], utc=True)
    for x, r0, r1 in zip(tc, cons["rank_exploit"], cons["rank_explore"]):
        ax1.plot([x, x], [r0, r1], color=HAIR, lw=1.0, zorder=1)
    ax1.scatter(tc, cons["rank_exploit"], s=40, color=EXPLOIT, label="relevance-only (exploit) rank", zorder=2)
    ax1.scatter(tc, cons["rank_explore"], s=40, color=EXPLORE, label="serendipity policy rank", zorder=3)
    ax1.axhspan(0.5, k + 0.5, color=EXPLORE, alpha=0.06, lw=0)
    ax1.axhline(k + 0.5, color=EXPLORE, lw=0.8, ls="--")
    ax1.text(0.005, k + 0.9, f"exposure budget k={k}", transform=ax1.get_yaxis_transform(), fontsize=8,
             color=EXPLORE, va="bottom")
    ax1.set_yscale("log"); ax1.invert_yaxis()
    from matplotlib.ticker import FixedLocator, NullFormatter, ScalarFormatter
    ax1.yaxis.set_major_locator(FixedLocator([1, 2, 5, 10, 20, 50, 100]))
    ax1.yaxis.set_major_formatter(ScalarFormatter()); ax1.yaxis.set_minor_formatter(NullFormatter())
    ax1.set_ylabel("rank among that day's candidates (1 = top)")
    ax1.spines[["top", "right"]].set_visible(False)
    ax1.legend(frameon=False, fontsize=8, loc="lower left")
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    for lab in ax1.get_xticklabels():
        lab.set_rotation(0)
    if synthetic:
        fig.text(0.5, 0.5, "SYNTHETIC FIXTURE — NOT EXPERIMENT OUTPUT", fontsize=26, color="#ee0000",
                 alpha=0.18, ha="center", va="center", rotation=18, weight="bold")
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for ext in ("svg", "pdf", "png"):
        p = out_dir / f"{stem}{'_synthetic' if synthetic else ''}.{ext}"
        fig.savefig(p, dpi=300 if ext == "png" else None, bbox_inches="tight")
        paths.append(p)
    plt.close(fig)
    return paths
