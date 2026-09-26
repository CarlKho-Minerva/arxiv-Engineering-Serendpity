# Algorithmic Mirrors: Engineering Serendipity in Personal Agents Under Partial Observability

A longitudinal single-subject study. The subject is the author. The question is
not whether an agent can optimize a life; it is whether an agent that models what
the subject would ordinarily do (a behavioral clone) must be kept separate from
an agent that surfaces what the subject is failing to consider (an exploration
policy), and whether that difference is measurable retrospectively on fifteen
years of logged exposures and choices.

**Status (2026-09-26, session 2):** inventory complete; prior clone result reproduced;
E1 exposure table built from message metadata; validation-only retrospective run
done (preliminary, unfavourable to the exploration terms as operationalized);
demo and Figure 2 still on a synthetic fixture. No test-split result exists.

## What is measured vs. proposed

| | status |
|---|---|
| Behavioral clone (RQ1): personal LoRA lifts 5-way next-action top-1 from 28.0% to 37.8% (+9.8, CI [6.8, 13.4], 20/21 days) | **measured**, reproduced by `scripts/verify_carl_model.py` → `results/carl_model_verified.json` |
| Retrospective serendipity ranking (RQ3–RQ5) | **E1 table built** (35,168 contact events 2011–2026; 3,719 weak-tie). **Validation-only runs** with metadata, local content embeddings, and AnyJev typed judgments (Gemma 4 31B on the subject's PC): relevance-only at or below random; hybrid never beats random-with-diversity; novelty-only beats it once automated messages are filtered from the pool (overlapping CIs). Consequential weak-tie exposures are *less* opportunity-like by the judgments. See `results/tables/E1_report.md`. Test split untouched until the annotation freeze. |
| Algorithmic-mirror time series (RQ2, RQ7) | **not testable**: recommendation exports are single 2026 snapshots |
| Exploration rate across life periods (RQ6) | **exploratory pass done**: fig3 + yearly tables (messages) + Facebook friends/groups per month |

## Layout

```
data_inventory.md          every local source: range, size, format, privacy, gaps
RESEARCH_QUESTIONS.md      RQ1–RQ7, testability, the falsification statement
EXPERIMENT_PLAN.md         E0–E5: exposure table, features, policies, controls
data_schema.md             normalized event schema; label-only fields
ETHICS_AND_PRIVACY.md      rules that are enforced, and the N=1 position
annotations/PROTOCOL.md    trajectory-event annotation protocol (draft, to freeze)
annotations/trajectory_events.template.csv
src/schema.py              Event dataclass, ACTION_FAMILIES, FUTURE_ONLY_FIELDS
src/evaluation/leakage.py  features_at(t, …): the only sanctioned feature builder
src/evaluation/splits.py   chronological split with embargo ≥ horizon
src/evaluation/metrics.py  recall@k, MRR, NDCG, coverage, novelty
src/policies/scoring.py    random, popularity, relevance, clone, ε-greedy, novelty, UCB, Thompson, hybrid
src/visualization/         fig1 architecture, fig2 counterfactual timeline
scripts/verify_carl_model.py   independent recomputation of the prior result
scripts/run_retrospective.py   the centrepiece experiment (synthetic until real table exists)
scripts/run_baselines.py       RQ3 premise check
scripts/build_figures.py       SVG + PDF + PNG into paper/figures/
demo/app.py                Streamlit demo; demo/sample_data.json is SYNTHETIC
demo/label_tier_b.py       Tier B labelling page (local, resumable, blind to rankings)
src/features/judgments_anyjev.py  AnyJev L0 typed judgments via the PC's vLLM (Gemma 4 31B)
src/features/embed_messages.py    local MiniLM embeddings (MPS)
paper/main.tex, refs.bib   skeleton; every claim tagged measured / proposed / hypothesis
results/                   aggregates only (metrics.json is synthetic until stated otherwise)
tests/                     leakage injection, split monotonicity, policy scoring
```

## Run

```bash
uv venv .venv && uv pip install -p .venv/bin/python numpy pandas pyarrow scikit-learn scipy matplotlib streamlit pytest orjson
.venv/bin/python -m pytest -q
.venv/bin/python scripts/verify_carl_model.py      # needs ~/.local/state/lifeos/carl-model/runs/m2
.venv/bin/python demo/make_synthetic_fixture.py
.venv/bin/python scripts/build_figures.py
.venv/bin/python scripts/run_retrospective.py       # synthetic until --real is given
.venv/bin/streamlit run demo/app.py
cd paper && tectonic main.tex
```

## Privacy

Everything under `data/`, every `*.jsonl`/`*.parquet`/`*.db`, real annotation CSVs,
and `demo/real_*.json` are git-ignored. No personal data leaves the machine. See
`ETHICS_AND_PRIVACY.md`.
