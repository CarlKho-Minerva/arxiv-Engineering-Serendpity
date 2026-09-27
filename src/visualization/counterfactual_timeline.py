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
         synthetic: bool = False, log_ranks: bool = True, exploit_label: str = "relevance-only (exploit) rank",
         explore_label: str = "serendipity policy rank", hybrid_label: str | None = None,
         stream_label: str = "exposure stream  (gray = ordinary · ring = later consequential · fan-out = downstream events)",
         stack_stream: bool = False, rank_unit: str = "day") -> list[Path]:
    df = df.sort_values("t").reset_index(drop=True)
    t = pd.to_datetime(df["t"], utc=True)
    fig, (ax0, ax1) = plt.subplots(2, 1, figsize=(11, 6.0), sharex=True,
                                   gridspec_kw={"height_ratios": [1.0, 2.4], "hspace": 0.06})
    # top strip: exposure stream
    ordinary = df["consequential"] == 0
    if stack_stream and "week" in df.columns:
        ypos = df.groupby("week").cumcount().to_numpy().astype(float)
        ymax = max(ypos.max(), 1.0)
        ypos = ypos / ymax * 0.9
    else:
        ypos = np.zeros(len(df))
    ax0.scatter(t[ordinary], ypos[ordinary.to_numpy()], s=10, color="#bdbdbd", zorder=1)
    ax0.scatter(t[~ordinary], ypos[(~ordinary).to_numpy()], s=46, facecolor="white", edgecolor=INK,
                lw=1.3, zorder=3)
    if "downstream" in df.columns:
        n_down = int(sum(len(r or []) for r in df.loc[~ordinary, "downstream"]))
        for _, row in df[~ordinary].iterrows():
            for (dt_, lab) in (row["downstream"] or []):
                dt_ = pd.Timestamp(dt_, tz="UTC")
                ax0.plot([pd.Timestamp(row["t"], tz="UTC"), dt_], [0, 0.55], color=BODY, lw=0.8, alpha=0.6)
                ax0.scatter([dt_], [0.55], s=14, color=BODY, zorder=2)
                if n_down <= 8:
                    ax0.text(dt_, 0.62, lab, fontsize=6.5, rotation=30, ha="left", va="bottom", color=BODY)
    ax0.set_ylim(-0.12, 1.25 if stack_stream else 1.4); ax0.set_yticks([]); ax0.spines[:].set_visible(False)
    ax0.text(0.0, 1.0, stream_label, transform=ax0.transAxes, fontsize=8, color=BODY, va="top")

    # bottom: ranks for consequential exposures under both policies
    cons = df[~ordinary]
    tc = pd.to_datetime(cons["t"], utc=True)
    for x, r0, r1 in zip(tc, cons["rank_exploit"], cons["rank_explore"]):
        ax1.plot([x, x], [r0, r1], color=HAIR, lw=1.0, zorder=1)
    ax1.scatter(tc, cons["rank_exploit"], s=40, color=EXPLOIT, label=exploit_label, zorder=2)
    ax1.scatter(tc, cons["rank_explore"], s=40, color=EXPLORE, label=explore_label, zorder=3)
    if hybrid_label and "rank_hybrid" in cons.columns:
        ax1.scatter(tc, cons["rank_hybrid"], s=46, facecolor="none", edgecolor="#ab570a", lw=1.3,
                    label=hybrid_label, zorder=4)
    ax1.axhspan(0.5, k + 0.5, color=EXPLORE, alpha=0.06, lw=0)
    ax1.axhline(k + 0.5, color=EXPLORE, lw=0.8, ls="--")
    ax1.text(0.73, 0.55 + 0.05, f"exposure budget k={k}", transform=ax1.get_yaxis_transform(), fontsize=8,
             color=EXPLORE, va="top", ha="center")
    from matplotlib.ticker import FixedLocator, MaxNLocator, NullFormatter, ScalarFormatter
    if log_ranks:
        ax1.set_yscale("log")
        ax1.yaxis.set_major_locator(FixedLocator([1, 2, 5, 10, 20, 50, 100]))
        ax1.yaxis.set_major_formatter(ScalarFormatter()); ax1.yaxis.set_minor_formatter(NullFormatter())
    else:
        ax1.set_ylim(0.5, max(cons[["rank_exploit", "rank_explore"]].max().max(), k) + 0.8)
        ax1.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax1.invert_yaxis()
    ax1.set_ylabel(f"rank among that {rank_unit}'s candidates (1 = top)")
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
