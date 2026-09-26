import numpy as np
import pandas as pd
import pytest

from src.evaluation.metrics import coverage_at_k, mrr, ndcg_at_k, recall_at_k
from src.policies.scoring import (DEFAULT_POLICIES, Weights, hybrid_policy, ranks_from_scores,
                                  relevance_policy, thompson_policy, ucb_policy)


def _cands(n=50, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "relevance": rng.random(n), "novelty": rng.random(n), "uncertainty": rng.random(n) * 0.3,
        "info_gain": rng.random(n), "option_value": rng.random(n), "cost": rng.random(n),
        "popularity": rng.random(n), "n_seen": rng.integers(1, 20, n),
        "category": rng.choice(list("abcde"), n),
    })


def test_ranks_are_a_permutation_and_top_is_max():
    s = np.array([0.2, 0.9, 0.5])
    r = ranks_from_scores(s)
    assert sorted(r) == [1, 2, 3] and r[1] == 1


@pytest.mark.parametrize("name", sorted(DEFAULT_POLICIES))
def test_every_default_policy_returns_finite_scores(name):
    df = _cands()
    s = DEFAULT_POLICIES[name](df, np.random.default_rng(1))
    assert s.shape == (len(df),) and np.isfinite(s).all()


def test_relevance_only_ignores_novelty():
    df = _cands()
    df2 = df.copy(); df2["novelty"] = 1 - df2["novelty"]
    rng = np.random.default_rng(0)
    r1 = ranks_from_scores(relevance_policy(df, np.random.default_rng(0)))
    r2 = ranks_from_scores(relevance_policy(df2, np.random.default_rng(0)))
    assert (r1 == r2).all()


def test_hybrid_with_only_relevance_weight_equals_relevance():
    df = _cands()
    h = hybrid_policy(Weights(relevance=1.0))
    assert (ranks_from_scores(h(df, np.random.default_rng(0)))
            == ranks_from_scores(relevance_policy(df, np.random.default_rng(0)))).all()


def test_hybrid_novelty_weight_moves_novel_item_up():
    df = _cands()
    i = int(df["novelty"].idxmax())
    base = ranks_from_scores(hybrid_policy(Weights(relevance=1.0))(df, np.random.default_rng(0)))[i]
    boosted = ranks_from_scores(hybrid_policy(Weights(relevance=1.0, novelty=5.0))(df, np.random.default_rng(0)))[i]
    assert boosted <= base


def test_ucb_falls_back_to_count_bonus():
    df = _cands().drop(columns=["uncertainty"])
    s = ucb_policy(1.0)(df, np.random.default_rng(0))
    assert np.isfinite(s).all()


def test_thompson_is_seeded_and_stochastic():
    df = _cands()
    a = thompson_policy(df, np.random.default_rng(3)); b = thompson_policy(df, np.random.default_rng(3))
    c = thompson_policy(df, np.random.default_rng(4))
    assert np.allclose(a, b) and not np.allclose(a, c)


def test_metrics_basic():
    ranks = np.array([1, 2, 3, 4, 5]); pos = np.array([0, 1, 0, 0, 1])
    assert recall_at_k(ranks, pos, 2) == 0.5
    assert recall_at_k(ranks, pos, 5) == 1.0
    assert mrr(ranks, pos) == pytest.approx((1 / 2 + 1 / 5) / 2)
    assert ndcg_at_k(ranks, pos, 5) < 1.0 and ndcg_at_k(np.array([3, 1, 4, 5, 2]), pos, 5) == pytest.approx(1.0)
    assert coverage_at_k(ranks, np.array(list("aabbc")), 2) == pytest.approx(1 / 3)
    assert np.isnan(recall_at_k(ranks, np.zeros(5), 3))
