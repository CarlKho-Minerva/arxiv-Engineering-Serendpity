"""Figure 4: pre-registered paired differences, validation vs held-out test, both pools."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

INK, BODY, MUTE, HAIR = "#171717", "#4d4d4d", "#888888", "#d9d9d9"
VAL, TEST = "#888888", "#0070f3"

ROWS = [("relevance-random", "H-PREM: relevance-only − random"),
        ("hybrid-random_diversity", "H-SER: hybrid exploration score − random with diversity"),
        ("novelty-random_diversity", "H-NOV: new-person-first − random with diversity")]


def draw(results: Path, out_dir: Path, stem: str = "fig4_preregistered") -> list[Path]:
    runs = {("val", "primary"): "metrics_val_primary.json", ("test", "primary"): "metrics_test_primary.json",
            ("val", "full"): "metrics_val_secondary_fullpool.json", ("test", "full"): "metrics_test_secondary_fullpool.json"}
    data = {k: json.loads((results / v).read_text())["paired"] for k, v in runs.items()}
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True, sharex=True)
    for ax, pool, title in ((axes[0], "primary", "Primary pool (automated messages removed)"),
                            (axes[1], "full", "Secondary pool (all weak-tie exposures)")):
        for i, (key, label) in enumerate(ROWS):
            y = len(ROWS) - 1 - i
            for dy, split, col in ((0.14, "val", VAL), (-0.14, "test", TEST)):
                st = data[(split, pool)][key]["mrr"]
                ax.plot(st["ci95"], [y + dy, y + dy], color=col, lw=2.2, solid_capstyle="butt")
                ax.scatter([st["diff"]], [y + dy], color=col, s=34, zorder=3,
                           label=("validation 2021–22" if split == "val" else "held-out test 2024–25") if i == 0 else None)
        ax.axvline(0, color=INK, lw=0.8)
        ax.set_title(title, fontsize=9, color=BODY)
        ax.set_xlabel("difference in MRR", fontsize=8)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
    axes[0].set_yticks(range(len(ROWS)))
    axes[0].set_yticklabels([lab for _, lab in reversed(ROWS)], fontsize=8)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, frameon=False, fontsize=8, loc="lower center", ncol=2, bbox_to_anchor=(0.62, -0.06))
    fig.text(0.62, -0.12, "points: mean paired per-week difference; bars: 95% cluster-bootstrap CI over weeks", ha="center",
             fontsize=7.5, color=BODY)
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for ext in ("svg", "pdf", "png"):
        p = out_dir / f"{stem}.{ext}"
        fig.savefig(p, dpi=300 if ext == "png" else None, bbox_inches="tight")
        paths.append(p)
    plt.close(fig)
    return paths
