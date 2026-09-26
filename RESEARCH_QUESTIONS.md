# Research questions, testability, and falsification

Status legend: **TESTABLE NOW** (data on disk, protocol below), **TESTABLE AFTER
INGEST** (data exists on the PC, needs parsing), **NOT CURRENTLY TESTABLE** (data
does not exist), **HYPOTHESIS** (motivation only).

## The one-page specification

**Setting.** One subject, ~15 years of logged inbound communication and social
exposures (2011→2026), ~7 weeks of wide multimodal capture, ~3 weeks of dense
capture, one verified behavioral-clone result, and single-snapshot recommendation
exports from four platforms.

**Objects.** Observations `O_{1:t}`; a representation `b_t`; a behavioral clone
`π_clone(a|b_t)` ("what would he do"); an exploration policy `π_explore(a|b_t)`
("what should be surfaced given what is unknown"). The paper's claim is that these
are different objects that must be evaluated differently, and it tests that
difference retrospectively.

**Unit of analysis for the centrepiece.** An *exposure* `x` at time `t`: an
inbound message from a person, an event invitation, a group invitation, a friend
request, an inbound email, an opportunity encountered (tracker). Each has an
observed action (replied / accepted / attended / applied / ignored) and a set of
downstream signals measurable after a fixed horizon `H`.

**Central hypothesis (H-SER).** Among exposures later labelled consequential
under a frozen protocol, a relevance-only ranking (trained to predict the
subject's engagement) places them systematically lower than an exploration-aware
ranking at the same budget `k`, on chronologically held-out periods.

**What would falsify it.** H-SER is false if, on the held-out test periods, the
best exploration-aware policy does not improve recall@k of consequential
exposures over the relevance-only policy by more than the improvement achieved by
*random exploration with the same diversity budget*, for every k ∈ {1,3,5,10}.
Concretely: if `recall@k(hybrid) − recall@k(relevance) ≤ recall@k(random-with-
diversity) − recall@k(relevance)` with the 95% cluster-bootstrap CI covering zero,
we report the negative result. A second falsifier: if consequential exposures are
*not* lower-ranked by relevance-only than ordinary engaged exposures (RQ3), the
premise that exploitation misses them is wrong and the exploration policy has
nothing to recover.

**What would NOT count as support.** Any result where the annotation of
"consequential" was made after seeing policy rankings; any result on periods used
for tuning weights; any result where random-with-diversity is not reported.

## RQ table

| RQ | Question | Status | Data | Primary metric |
|---|---|---|---|---|
| RQ1 | Does a learned representation of the subject improve held-out action prediction beyond immediate context? | **VERIFIED** (prior result reproduced; see `results/carl_model_verified.json`) | carl-model M2 | top-1 in 5-way choice: A 28.0% → L 37.8% (+9.8, CI [6.8, 13.4]) |
| RQ2 | Do recommendation outputs add predictive information beyond behavioral history? | **NOT CURRENTLY TESTABLE longitudinally.** Cross-sectional variant TESTABLE AFTER INGEST: does the 2026 platform snapshot (ad interests, feed log, suggested friends) improve prediction of Aug–Sep 2026 engagement beyond history? | 4a exports (2026 snapshots) + carl-model events | Δ top-1 / Δ log-lik with vs. without mirror features, chronological |
| RQ3 | Are consequential exposures systematically lower-ranked by relevance-only than ordinary consumed content? | **TESTABLE AFTER INGEST** | inbound messages, invitations, requests 2011→2026; annotations | rank distribution of consequential vs. engaged-ordinary under π_rel |
| RQ4 | Does exploration-aware ranking recover more consequential exposures at equal budget? | **TESTABLE AFTER INGEST** (centrepiece) | same | recall@k, MRR, NDCG(delayed weights) vs. relevance and vs. random-with-diversity |
| RQ5 | Which exploration term matters? | **TESTABLE AFTER INGEST** | same | ablation of novelty / uncertainty / IG-proxy / option-value / random |
| RQ6 | Does the subject's empirical exploration rate change across life periods? | **TESTABLE NOW** from the normalized message stream (aggregates only) | msg_* events 2011→2026; FB groups/friends with timestamps | new contacts/month, reply rate to weak ties, communities entered/year, topic entropy |
| RQ7 | Does mirror–self-model disagreement predict later behavioral change? | **NOT CURRENTLY TESTABLE** (no mirror time series) | — | — |

## Hypotheses that stay hypotheses

- "Younger Carl: poor model + higher exploration; present Carl: better model + lower
  exploration." RQ6 measures the exploration half only. The "better model" half
  has no measurement and is not claimed.
- "Platforms know him better." Not claimed; representational similarity ≠ accuracy.
- Causal attribution of any life outcome to any exposure. Not claimed.

## Do we need RL?

No. The logged data contains exposures, actions, and delayed outcomes under the
subject's own (unknown) policy, with no interventions. The honest framing is
longitudinal representation learning + counterfactual ranking + contextual-bandit
style exploration terms, evaluated retrospectively with chronological splits.
The eventual problem is POMDP-shaped; this dataset supports only the narrower tests.
