"""Figure 1: the belief / clone / explore loop with algorithmic mirrors.

Pure matplotlib. Grayscale ink with one accent for the exploration branch and one
for the algorithmic-mirror channel, chosen for print and colour-blind legibility.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

INK = "#171717"
BODY = "#4d4d4d"
MUTE = "#888888"
HAIR = "#cfcfcf"
EXPLORE = "#0070f3"   # accent: exploration branch
MIRROR = "#ab570a"    # accent: algorithmic-mirror channel


def _box(ax, xy, w, h, title, sub=None, *, ec=INK, lw=1.2, fc="white", title_size=10, sub_size=8, mono=False):
    x, y = xy
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.12",
                                ec=ec, fc=fc, lw=lw))
    ax.text(x + w / 2, y + h / 2 + (0.16 if sub else 0), title, ha="center", va="center",
            fontsize=title_size, color=ec if ec != INK else INK, weight="bold",
            family="monospace" if mono else None)
    if sub:
        ax.text(x + w / 2, y + h / 2 - (0.24 if "\n" in sub else 0.2), sub, ha="center", va="center",
                fontsize=sub_size, color=BODY, style="italic", linespacing=1.15)


def _arrow(ax, a, b, *, color=INK, lw=1.2, style="-|>", rad=0.0, ls="-"):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle=style, mutation_scale=12, color=color, lw=lw,
                                 connectionstyle=f"arc3,rad={rad}", linestyle=ls, shrinkA=2, shrinkB=2))


def draw(out_dir: Path, stem: str = "fig1_architecture") -> list[Path]:
    fig, ax = plt.subplots(figsize=(10, 6.4))
    ax.set_xlim(-0.75, 10); ax.set_ylim(0, 6.3); ax.axis("off")

    # --- column 1: experience -> observations -> belief, mirror channel below
    _box(ax, (0.4, 5.1), 2.6, 0.8, "Human experience stream", "lived, continuous, mostly unrecorded")
    _box(ax, (0.4, 3.7), 2.6, 0.9, "Multimodal observations $O_{1:t}$",
         "screen · input · text · social · video · sensors")
    _box(ax, (0.4, 2.2), 2.6, 0.9, "Belief / representation $b_t$",
         r"$b_t \approx P(S_t \mid O_{1:t}, A_{1:t-1})$", lw=1.8)
    _box(ax, (0.4, 0.45), 2.6, 1.0, "Algorithmic mirror $Y_t$",
         "$Y_t = f(z_t^{plat}, C_t)$:  $z$ hidden, $Y$ visible\nanother estimator of the same person", ec=MIRROR, lw=1.6)
    _arrow(ax, (1.7, 5.1), (1.7, 4.6))
    _arrow(ax, (1.7, 3.7), (1.7, 3.1))
    # mirror channel joins the observation stream around the left margin
    _arrow(ax, (0.6, 1.45), (0.6, 3.7), color=MIRROR, rad=-0.75, ls="--")
    ax.text(-0.72, 2.65, "one more\nobservation\nchannel", fontsize=7, color=MIRROR, ha="left", va="center")

    # --- column 2: the two policies, platforms below
    _box(ax, (4.0, 3.7), 2.6, 1.0, r"Behavioral clone $\pi_{clone}(a \mid b_t)$",
         '"what would I do?"')
    _box(ax, (4.0, 2.0), 2.6, 1.0, r"Exploration policy $\pi_{explore}(a \mid b_t)$",
         '"what should I inspect because I don\'t know?"', ec=EXPLORE, lw=1.8)
    _arrow(ax, (3.0, 2.8), (4.0, 4.2), rad=-0.15)
    _arrow(ax, (3.0, 2.5), (4.0, 2.5), color=EXPLORE)
    _box(ax, (4.0, 0.45), 2.6, 1.0, "External platforms", "Meta · Google · YouTube · Spotify …\nyears of logs; objective unknown",
         ec=MIRROR)
    _arrow(ax, (4.0, 0.95), (3.0, 0.95), color=MIRROR)
    ax.text(3.5, 1.5, "their\nrecommendations", ha="center", va="bottom", fontsize=7.5, color=MIRROR)

    # --- column 3: candidates -> human chooses -> outcome
    _box(ax, (7.4, 2.7), 2.2, 1.0, "Exposure candidates", "ranked under a budget $k$")
    _arrow(ax, (6.6, 4.2), (7.4, 3.4), rad=0.15)
    _arrow(ax, (6.6, 2.5), (7.4, 3.0), color=EXPLORE, rad=-0.15)
    _box(ax, (7.4, 5.1), 2.2, 0.8, "Human chooses", "engage · ignore · defer")
    _arrow(ax, (8.5, 3.7), (8.5, 5.1))
    _arrow(ax, (7.4, 5.5), (3.0, 5.5))
    ax.text(5.2, 5.62, "outcome becomes new experience; the loop repeats", ha="center", fontsize=8, color=BODY,
            style="italic")

    ax.text(9.6, 1.9, "prediction asks: what will I do?\naugmentation asks: what am I failing to consider?",
            ha="right", va="bottom", fontsize=8, color=BODY)
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for ext in ("svg", "pdf", "png"):
        p = out_dir / f"{stem}.{ext}"
        fig.savefig(p, dpi=300 if ext == "png" else None, bbox_inches="tight")
        paths.append(p)
    plt.close(fig)
    return paths
