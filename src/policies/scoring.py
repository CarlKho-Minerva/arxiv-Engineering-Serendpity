"""Exposure-ranking policies.

Every policy maps a candidate frame (rows = candidate exposures available at
decision time t) to a score vector. Higher = surfaced earlier. All inputs are
*per-candidate feature columns* that must have been produced by
`src.evaluation.leakage.features_at`; the policies never touch timestamps or
labels themselves.

Expected columns (all in [0,1] unless noted):
  relevance      P(engage | history)      -- from the clone / relevance model
  clone_loglik   log pi_clone(x | b_t)    -- behavioral-clone likelihood (any real)
  novelty        1 - max cosine sim to own past activity
  uncertainty    epistemic std / disagreement of the relevance estimate
  info_gain      proxy: expected entropy reduction (see EXPERIMENT_PLAN.md)
  option_value   proxy: reachable-set growth (see EXPERIMENT_PLAN.md)
  cost           exposure cost (time, attention)
  popularity     frequency of this candidate type in own history
  n_seen         int, how often this candidate type has been observed (for UCB)

The provisional hybrid score is

  score = w_r*relevance + w_u*uncertainty + w_n*novelty + w_i*info_gain
        + w_o*option_value - w_c*cost

and its terms are ablated, not assumed, in scripts/run_retrospective.py.
"""
from __future__ import annotations

import dataclasses
from typing import Callable

import numpy as np
import pandas as pd

Policy = Callable[[pd.DataFrame, np.random.Generator], np.ndarray]


@dataclasses.dataclass(frozen=True)
class Weights:
    relevance: float = 1.0
    uncertainty: float = 0.0
    novelty: float = 0.0
    info_gain: float = 0.0
    option_value: float = 0.0
    cost: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return dataclasses.asdict(self)


def _col(df: pd.DataFrame, name: str, default: float = 0.0) -> np.ndarray:
    if name in df.columns:
        return df[name].to_numpy(dtype=float)
    return np.full(len(df), default, dtype=float)


# ---- baselines ------------------------------------------------------------

def random_policy(df: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    return rng.random(len(df))


def popularity_policy(df: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    return _col(df, "popularity") + 1e-9 * rng.random(len(df))


def relevance_policy(df: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    return _col(df, "relevance") + 1e-9 * rng.random(len(df))


def clone_policy(df: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    """Rank by behavioral-clone likelihood. Falls back to relevance if absent."""
    if "clone_loglik" in df.columns:
        return _col(df, "clone_loglik") + 1e-9 * rng.random(len(df))
    return relevance_policy(df, rng)


def epsilon_greedy(eps: float = 0.2) -> Policy:
    def _p(df: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
        base = relevance_policy(df, rng)
        explore = rng.random(len(df)) < eps
        # exploring candidates get a random score drawn above the exploit range
        out = base.copy()
        out[explore] = 1.0 + rng.random(explore.sum())
        return out
    _p.__name__ = f"epsilon_greedy_{eps}"
    return _p


def novelty_policy(df: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    return _col(df, "novelty") + 1e-9 * rng.random(len(df))


def ucb_policy(c: float = 1.0) -> Policy:
    """UCB-style: relevance + c * uncertainty. If `uncertainty` is absent, use a
    count-based bonus sqrt(log(N)/n_seen)."""
    def _p(df: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
        rel = _col(df, "relevance")
        if "uncertainty" in df.columns:
            bonus = _col(df, "uncertainty")
        else:
            n = np.maximum(_col(df, "n_seen", 1.0), 1.0)
            bonus = np.sqrt(np.log(n.sum() + 1.0) / n)
        return rel + c * bonus + 1e-9 * rng.random(len(df))
    _p.__name__ = f"ucb_c{c}"
    return _p


def thompson_policy(df: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    """Thompson sampling with a Gaussian posterior N(relevance, uncertainty^2).

    Only probabilistically coherent when `uncertainty` is a posterior std of the
    relevance estimate (e.g. from an ensemble). If it is a heuristic, this is
    just noisy relevance and should be reported as such.
    """
    mu = _col(df, "relevance")
    sd = np.maximum(_col(df, "uncertainty"), 1e-6)
    return rng.normal(mu, sd)


def hybrid_policy(w: Weights) -> Policy:
    def _p(df: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
        s = (w.relevance * _col(df, "relevance")
             + w.uncertainty * _col(df, "uncertainty")
             + w.novelty * _col(df, "novelty")
             + w.info_gain * _col(df, "info_gain")
             + w.option_value * _col(df, "option_value")
             - w.cost * _col(df, "cost"))
        return s + 1e-9 * rng.random(len(df))
    _p.__name__ = "hybrid"
    return _p


def ranks_from_scores(scores: np.ndarray) -> np.ndarray:
    """1-based rank; rank 1 = highest score."""
    order = np.argsort(-scores, kind="stable")
    ranks = np.empty(len(scores), dtype=int)
    ranks[order] = np.arange(1, len(scores) + 1)
    return ranks


DEFAULT_POLICIES: dict[str, Policy] = {
    "random": random_policy,
    "popularity": popularity_policy,
    "relevance": relevance_policy,
    "clone": clone_policy,
    "epsilon_greedy": epsilon_greedy(0.2),
    "novelty": novelty_policy,
    "ucb": ucb_policy(1.0),
    "thompson": thompson_policy,
    "hybrid": hybrid_policy(Weights(relevance=1.0, uncertainty=0.5, novelty=0.5,
                                    info_gain=0.5, option_value=0.5, cost=0.25)),
}
