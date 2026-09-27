# Pre-registration: test-split evaluation (frozen 2026-09-27)

Everything below was fixed **before any policy was run on the test split**. The
choices were informed by the train and validation splits only; that history is in
`results/tables/E1_report.md`. This file, `annotations/PROTOCOL.md`, and the code at
the tagged commit (`annotation-v1`) define the test analysis. The test split was
opened exactly once, by the commands in section 6.

## 1. Data and split
- Unit: inbound contact event (inbound message after >= 24 h of thread silence),
  message metadata from 9 sources, 2011-11 to 2026-09-15.
- Candidates: weak-tie exposures (first message in a thread, or thread silent >= 180 d).
- Split (unchanged since E1): train <= 2019-12-31; 366-day embargo; validation
  2021-01-01 to 2022-12-31; 366-day embargo; **test >= 2024-01-01**. Horizon 365 d,
  so test exposures run 2024-01-01 to 2025-09-15 (labels complete).
- Ranking unit: ISO week. Weeks without a positive are skipped (recall undefined).

## 2. Label (primary)
Tier A, automatic: `consequential = tie_persisted_365 AND bursts_365 >= 5`
(`src/ingest/exposures_from_messages.py`). Tier B manual labels (300-exposure blind
sample, `annotations/tier_b_sample_v1.ids.txt`) are a secondary label, collected
after this freeze, analysed with the identical pipeline and reported separately.

## 3. Candidate pools
- **Primary pool:** weak-tie exposures with AnyJev L0 Gemma 4 31B `p_automated <= 0.5`
  (`src/features/judgments_anyjev.py`, `--exclude-automated 0.5`).
- Secondary pool: all weak-tie exposures (no automated filter).

## 4. Features and policies
- Reply model: 5-member bootstrap logistic ensemble, fit on **train only**, on all
  train-period exposures (`--train-on all`), features = metadata + local MiniLM
  content features + AnyJev judgment features (`--judgments --content`).
- Policies: `src/policies/scoring.py` DEFAULT_POLICIES plus random-with-diversity.
  Hybrid weights tuned on the **validation** split by grid search on recall@5
  (runner default when `--split-eval test`).
- Stochastic and tie-heavy policies (random, random_diversity, epsilon_greedy,
  thompson, novelty, popularity) averaged over 20 seeds per week.

## 5. Endpoints and decision rules
Statistic: mean over weeks of the paired per-week difference, 95% cluster-bootstrap
CI over weeks (5,000 resamples), `scripts/run_retrospective.py` `paired()`.

| Hypothesis | Endpoint (primary pool) | Supported if | Rejected if |
|---|---|---|---|
| **H-PREM** (relevance buries later-consequential weak ties) | MRR(relevance) − MRR(random) | CI entirely < 0 | CI entirely > 0 |
| **H-SER** (hybrid exploration score beats equal-diversity random exploration) | MRR(hybrid) − MRR(random_diversity) | CI entirely > 0 | CI includes 0 or lies below it |
| **H-NOV** (new-person-first beats equal-diversity random exploration) | MRR(novelty) − MRR(random_diversity) | CI entirely > 0 | CI entirely < 0; inconclusive otherwise |

Secondary, reported without decision rules: recall@1, recall@3, recall@5 for the same
pairs; the same endpoints on the secondary pool; reply-model AUC on test.

Validation results that motivated these rules (for transparency): H-PREM MRR diff
−0.061 [−0.113, −0.002]; H-SER −0.044 [−0.107, +0.028]; H-NOV +0.021 [−0.018, +0.060].

## 6. Negative controls (mandatory, run on test)
1. Within-week label permutation (seed 12345): all paired differences should include 0.
2. Leakage tests (`tests/test_no_future_leakage.py`) must pass at the tagged commit.
3. Random-with-diversity is itself the control for "exploration with coverage".

## 7. Commands (run once, after the tag)
```
.venv/bin/python -m pytest -q
.venv/bin/python src/features/exposure_features.py --judgments --content --train-on all --exclude-automated 0.5 --post-freeze
.venv/bin/python scripts/run_retrospective.py --real data/derived/exposures_features.parquet --split-eval test --tag primary --export-ranks
.venv/bin/python scripts/run_retrospective.py --real data/derived/exposures_features.parquet --split-eval test --tag primary_permuted --permute-labels
.venv/bin/python src/features/exposure_features.py --judgments --content --train-on all --post-freeze
.venv/bin/python scripts/run_retrospective.py --real data/derived/exposures_features.parquet --split-eval test --tag secondary_fullpool
```

## 8. What will be reported regardless of outcome
All three hypotheses with their CIs, both pools, the permutation control, and the
number of test weeks and positives. No test-informed change to any choice above.
