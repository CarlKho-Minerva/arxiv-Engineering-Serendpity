"""Ranking metrics for the retrospective serendipity experiment."""
from __future__ import annotations

import numpy as np


def recall_at_k(ranks: np.ndarray, positive: np.ndarray, k: int) -> float:
    pos = positive.astype(bool)
    if pos.sum() == 0:
        return float("nan")
    return float((ranks[pos] <= k).mean())


def mrr(ranks: np.ndarray, positive: np.ndarray) -> float:
    pos = positive.astype(bool)
    if pos.sum() == 0:
        return float("nan")
    return float((1.0 / ranks[pos]).mean())


def ndcg_at_k(ranks: np.ndarray, gains: np.ndarray, k: int) -> float:
    """NDCG with arbitrary non-negative gains (e.g. delayed-outcome weights)."""
    gains = np.asarray(gains, dtype=float)
    if gains.sum() == 0:
        return float("nan")
    in_k = ranks <= k
    dcg = (gains[in_k] / np.log2(ranks[in_k] + 1)).sum()
    ideal = np.sort(gains)[::-1][:k]
    idcg = (ideal / np.log2(np.arange(2, len(ideal) + 2))).sum()
    return float(dcg / idcg) if idcg > 0 else float("nan")


def coverage_at_k(ranks: np.ndarray, categories: np.ndarray, k: int) -> float:
    """Fraction of distinct categories represented in the top-k."""
    cats = np.asarray(categories)
    if len(set(cats)) == 0:
        return float("nan")
    return len(set(cats[ranks <= k])) / len(set(cats))


def topk_novelty(ranks: np.ndarray, novelty: np.ndarray, k: int) -> float:
    return float(np.asarray(novelty, dtype=float)[ranks <= k].mean()) if (ranks <= k).any() else float("nan")
