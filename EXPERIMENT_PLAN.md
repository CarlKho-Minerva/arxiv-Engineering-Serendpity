# Experiment plan

Phases follow the brief. Every experiment reads only `data/derived/events.parquet`
(built by `src/ingest/`) and writes aggregates to `results/`. No raw content is
copied into the repo.

## E0. Verification of the prior clone result — DONE

`scripts/verify_carl_model.py` → `results/carl_model_verified.json`. Independent
recomputation from raw per-case scores. Matches the reported numbers (RQ1).

## E1. Exposure–action–outcome table (Phase 3, 5)

**Exposure types and their observed action** (all from logged data):

| exposure | source | observed action | action window |
|---|---|---|---|
| inbound message from person P (first message of an inbound burst) | msg_messenger, msg_instagram, msg_twitter, msg_telegram, msg_discord, msg_gmail, msg_linkedin, msg_gchat | subject sent ≥1 message to P within 7 days | 7 d |
| event invitation | FB `events/event_invitations.json` | responded going/interested; attended (self-report) | until event |
| group invitation / group discovered | FB `groups/…` | joined; posted within 30 d | 30 d |
| friend request received | FB `connections/friends/received_friend_requests.json` + `your_friends.json` | accepted | 30 d |
| opportunity encountered | md-cv tracker (2025-10→2026-09) | applied / submitted | until deadline |

**Candidate set at time t.** All exposures with `timestamp_start` in the window
`[t − 7d, t]` (weekly budget) or the day (daily budget). Only exposures that were
*logged as received* are candidates. We do not synthesize hypothetical exposures.

**Downstream signals at horizon H ∈ {90, 365} days**, all computed from data
timestamped in `(t, t+H]`:

- `repeat_interactions`: number of later inbound+outbound bursts with P
- `tie_persisted`: interaction with P in the last 90 days of the horizon
- `new_context`: P or the group appears in a new source (e.g. first Messenger then email/LinkedIn) 
- `topic_shift`: KL divergence of the subject's outbound topic distribution before vs after, relative to a matched control window
- `project / application / money / publication`: from annotations only (manual, direct evidence required)

**Consequential label.** Frozen in `annotations/PROTOCOL.md` before any policy is
run on the test period. Two tiers: *automatic* (tie_persisted ∧ repeat_interactions ≥ 5
∧ new_context) and *manual* (annotator-labelled with direct evidence). Both are
reported separately. Manual labels are made blind to policy rankings.

## E2. Features at time t (leakage-safe)

Every feature is computed by `src.evaluation.leakage.features_at(t, …)`. Per candidate:

- `relevance`: P(engage | history ≤ t), from a logistic model over (prior contact
  count, recency, source, hour, thread length, reciprocity) fit on train only, and
  optionally the clone log-likelihood of replying (LoRA, only for the 2026 window).
- `popularity`: frequency of the source/type in the subject's history ≤ t.
- `novelty`: 1 − max cosine(embedding(x), embeddings of subject's outbound text in
  [t−90d, t]) using a local sentence-embedding model; or, for people, 1 if P has no
  prior contact, else a decreasing function of prior contact count.
- `uncertainty`: std of `relevance` across a 5-model bootstrap ensemble (epistemic
  proxy). Thompson sampling is only reported with this definition.
- `info_gain` proxy: expected reduction in ensemble disagreement over the *pool of
  future candidates* if x's label were revealed (BALD-style, approximated by
  ensemble mutual information on x).
- `option_value` proxy: size of the reachable set: number of distinct new
  people/communities/topics reachable within one hop of x in the graph ≤ t,
  normalized. Explicitly a proxy; ablated.
- `cost`: expected reply length (tokens) for messages, travel/time for events; unit-scaled.

## E3. Policies and evaluation (Phase 6, 7)

Policies: `src/policies/scoring.py` (random, popularity, relevance, clone,
ε-greedy, novelty, UCB, Thompson, hybrid). Weights of the hybrid are tuned on the
validation period only, by grid search on recall@5, then frozen.

Split: `make_chrono_split(embargo_days = H)`; train ≤ 2019-12, val 2020→2022, test
2023→2026-07 (exact boundaries set by data volume, fixed before running any test
evaluation; recorded in `results/split.json`).

Metrics per k ∈ {1,3,5,10}: recall@k, MRR, NDCG with gain = log(1+repeat_interactions),
coverage@k over sources, mean novelty@k, exposure cost@k. CIs by cluster bootstrap
over weeks.

Negative controls (all mandatory): timestamp-shuffled labels; shuffled
representation; random candidate histories; injected-future-feature control (must
be rejected by tests); identity-free model (no subject-specific features);
−mirror features; −social features; −LoRA; random exploration with equal
diversity budget.

## E4. Exploration-rate proxies across periods (RQ6) — first exploratory pass this session

From the normalized message stream, per calendar month, **aggregates only**:
new contacts (first inbound or outbound with a hashed counterpart id), reply rate
to first-time contacts, reply rate to dormant ties (no contact in 180 d),
outbound-initiated contacts, number of distinct counterparts, entropy of
counterpart distribution. Reported as a time series with the export coverage of
each source overlaid, so that platform migration is not read as behavior change.

## E5. Cross-sectional algorithmic-mirror test (RQ2, reduced form)

Only after E1–E3. Parse the 2026 platform snapshots into interest/topic vectors;
test whether they improve prediction of engagement in Aug–Sep 2026 (held out by
week) beyond behavioral features. Report representational similarity between the
platform interest vector and the subject's own outbound-topic vector as a
descriptive, not evidential, statistic.

## Compute

All embedding and scoring local: Apple Silicon (MLX) or the PC (RTX 5090, GPU1
only after checking `gpu.json` for running tasks). No frontier-API calls on raw
personal data.
