# E1 report: exposure–action–outcome table and first validation-only run

Generated 2026-09-26T19:40:53+00:00. Everything here is computed from message *metadata* (timestamps, direction, hashed thread ids, character counts). No message content was read. Test-split numbers were not computed and must not be until `annotations/PROTOCOL.md` is frozen.

## E1 table (data/derived/exposures.parquet, git-ignored)

- Messages: 3,082,593 across 9 sources, 7,139 threads, 2011-11-08 → 2026-09-15 (locked window after 2026-09-16 excluded).
- Contact events (inbound message after ≥ 24 h thread silence): **35,168**. New-thread exposures 2,856; dormant-thread (≥ 180 d) exposures 863; together the **weak-tie candidate pool = 3,719**.
- Observed action: reply within 7 d. Reply rate: all 0.53, new threads 0.53, dormant 0.55.
- Tier A label (365 d): tie persisted in the last 90 d of the horizon ∧ ≥ 5 later bursts. Base rate among all exposures 0.63 (dominated by existing strong ties, as expected); among weak-tie exposures **0.13**. The retrospective experiment therefore ranks weak-tie exposures only.
- Per source: discord 2,467, gchat 71, gmail 1,114, gvoice 405, instagram 4,491, linkedin 489, messenger 20,156, telegram 5,759, twitter 216.
- Not computable from this table: the protocol's `new_context` clause (thread hashes are per source, so the same person on two platforms cannot be linked without reading names). Documented as a Tier A limitation.

## Facebook supplement (results/facebook_monthly.json)

Friendships 2,195 with timestamps; event invitations 94 (no receipt timestamp, only event start); events joined 43, interested 66; groups joined 358; pending received friend requests 533; rejected 129. Usable for RQ6 (friends added and groups joined per month) and as a partial exposure table; accepted friendships lack the initiator.

## Split (results/split.json), fixed before any evaluation

train ≤ 2019-12-31 (n=776, positives 140); embargo 366 d; val 2021-01-01 → 2022-12-31 (n=905, positives 134, 63 weeks with a positive); embargo; test from 2024-01-01 (n=738, positives 52; **not evaluated**). Horizon 365 d, so every label is complete.

Relevance model: 5-member bootstrap logistic ensemble on 30 history features predicting reply-within-7-days. **Validation AUC 0.544**: reply to a weak tie is barely predictable from metadata. Every relevance-based policy inherits this weakness.

## Validation-only retrospective run (results/metrics_val.json)

Candidate set = weak-tie exposures per ISO week: mean 8.6, median 8, p90 16. Budgets k ≥ 10 therefore exhaust most weeks; k ∈ {1, 3, 5} is the informative range. Hybrid weights tuned on train weeks by recall@5 grid search: {'relevance': 1.0, 'uncertainty': 0.0, 'novelty': 0.0, 'info_gain': 0.0, 'option_value': 0.25, 'cost': 0.25}. CIs: cluster bootstrap over weeks.

| policy | recall@1 | recall@3 | recall@5 | MRR | coverage@5 | novelty@5 |
|---|---|---|---|---|---|---|
| random | 0.112 [0.05, 0.18] | 0.354 [0.25, 0.45] | 0.647 [0.54, 0.74] | 0.323 | 0.84 | 0.86 |
| random_diversity | 0.185 [0.11, 0.27] | 0.504 [0.40, 0.61] | 0.661 [0.56, 0.75] | 0.389 | 0.98 | 0.86 |
| popularity | 0.151 [0.07, 0.23] | 0.418 [0.31, 0.53] | 0.636 [0.52, 0.75] | 0.356 | 0.62 | 0.79 |
| relevance | 0.050 [0.01, 0.10] | 0.372 [0.27, 0.48] | 0.576 [0.46, 0.69] | 0.278 | 0.76 | 0.81 |
| clone | 0.050 [0.01, 0.10] | 0.372 [0.27, 0.48] | 0.576 [0.46, 0.69] | 0.278 | 0.76 | 0.81 |
| epsilon_greedy | 0.080 [0.04, 0.13] | 0.424 [0.32, 0.53] | 0.579 [0.47, 0.68] | 0.295 | 0.82 | 0.84 |
| novelty | 0.142 [0.07, 0.22] | 0.464 [0.36, 0.57] | 0.659 [0.56, 0.76] | 0.365 | 0.84 | 0.95 |
| ucb | 0.050 [0.01, 0.10] | 0.370 [0.26, 0.48] | 0.576 [0.46, 0.69] | 0.276 | 0.77 | 0.81 |
| thompson | 0.054 [0.01, 0.11] | 0.362 [0.26, 0.47] | 0.554 [0.44, 0.67] | 0.277 | 0.78 | 0.81 |
| hybrid | 0.085 [0.02, 0.15] | 0.409 [0.29, 0.52] | 0.576 [0.46, 0.69] | 0.308 | 0.76 | 0.84 |

## Reading (preliminary; validation split; Tier A labels only)

1. **RQ3 premise holds directionally.** Relevance-only ranks later-consequential weak-tie exposures *lower* than ordinary ones (mean rank 6.2 vs 5.0 on val; `scripts/run_baselines.py --split-eval val`) and is the worst policy at recall@1 and MRR, below random.
2. **H-SER is not supported on validation as currently operationalized.** The hybrid (uncertainty, information-gain, option-value terms) does not beat random exploration with an equal diversity budget; random-with-diversity and plain novelty are the best policies. Under the pre-stated falsifier this would count against the central hypothesis if it replicates on test.
3. **The reason is probably the relevance model, not the idea.** With AUC 0.54 the ensemble's uncertainty and BALD terms carry almost no signal, and the train-tuned hybrid collapses to relevance + small option-value. A relevance model with content (local embeddings) or with the personal LoRA on the 2026 window is the obvious next step before the test run.
4. Tier A labels are structural (tie persisted, ≥ 5 bursts). They reward exposures that became sustained conversations, which favours group threads and repeat correspondents; manual Tier B labels (project, application, collaborator) may behave differently. Both must be reported.
5. Candidate sets are small (median 8 per week). Weekly budgets of 1–3 are the realistic regime; report daily budgets only for the dense 2026 window.

## Next

- Content-aware novelty/relevance via local embeddings over message text (never leaves the machine), then re-run val.
- Freeze `annotations/PROTOCOL.md` (Tier A definition above + Tier B sampling) as git tag `annotation-v1`; only then run `--split-eval test`.
- Tier B manual labels: sample from the val+test weak-tie pool blind to rankings (Carl).
- Link counterparts across sources (hashed name join on the raw exports, on the PC) to recover the `new_context` clause.

## Addendum 2026-09-26: local content embeddings (validation split)

Encoder: `paraphrase-multilingual-MiniLM-L12-v2` on the Mac (MPS), 35,168 exposure texts + 396,381 subject messages ≥ 20 chars, `src/features/embed_messages.py`. Content features: 32 PCA components of the inbound message embedding, mean/max cosine to the subject's own messages in the prior 90 days, window size. Content novelty = 1 − max cosine.

| variant | reply-model val AUC | relevance r@3 | novelty r@3 | hybrid r@3 | random-diversity r@3 | hybrid MRR |
|---|---|---|---|---|---|---|
| metadata only | 0.544 | 0.372 [0.27, 0.48] | 0.464 [0.36, 0.57] | 0.409 [0.29, 0.52] | 0.504 [0.40, 0.61] | 0.308 |
| content, reply model on candidates (AUC 0.593) | 0.593 | 0.319 [0.22, 0.43] | 0.381 [0.27, 0.49] | 0.331 [0.23, 0.44] | 0.504 [0.40, 0.61] | 0.308 |
| content, reply model on all exposures (AUC 0.643) | 0.643 | 0.353 [0.25, 0.46] | 0.381 [0.27, 0.49] | 0.344 [0.25, 0.44] | 0.504 [0.40, 0.61] | 0.312 |

Reading: content raises the reply model's AUC (0.54 → 0.59 → 0.64 when trained on all 15k train-period exposures), but no policy beats random-with-diversity, and **embedding novelty is worse than the metadata new-thread flag** (novelty r@3 0.464 → 0.381): "unlike what he recently wrote" is not the kind of novelty that predicts a lasting tie. The hybrid's train-tuned weights move toward uncertainty and information gain once the reply model has signal, without changing the outcome. Next: typed judgments (AnyJev L0 on the PC's Gemma 4 31B) as features; see `src/features/judgments_anyjev.py`.

## Addendum 2026-09-26 (later): AnyJev typed judgments (validation split)

Six typed questions per weak-tie exposure (invites action, expects reply, org/group, automated, option-value score, message-type choice), answered by AnyJev L0 (nokia-applied-research/AnyJev, zero labels, option-order bias averaged out) on the PC's vLLM Gemma 4 31B AWQ; 3,719 exposures, 0.6 s each. `src/features/judgments_anyjev.py`. Nothing left the subject's machines.

**What the judgments say about the Tier A label** (mean over weak-tie exposures with complete labels):

| judgment | ordinary | later-consequential (Tier A) | AUC for Tier A |
|---|---|---|---|
| P(invites action) | 0.261 | 0.120 | 0.47 |
| P(org or group) | 0.361 | 0.147 | 0.41 |
| P(automated / marketing) | 0.372 | 0.202 | 0.37 |
| E[option value] (0–3) | 1.135 | 1.051 | 0.49 |
| P(type = personal/social chat) | 0.365 | 0.565 | 0.63 |
| P(type = invitation/opportunity) | 0.070 | 0.030 | 0.57 |

Reading: among weak-tie inbound messages, the ones that became sustained ties were **less** often invitations, opportunities, or organizational messages and **more** often personal chat from a new person. The message-level "opportunity-ness" that the exploration score was built to reward is anti-correlated with the Tier A outcome. Also, ~37% of ordinary weak-tie exposures are judged automated or marketing, i.e. not exposures from a person; that is a candidate-set defect, fixed below by a filter.

**Policies (validation, Tier A labels, hybrid tuned on train weeks):**

| variant | relevance r@3 | novelty r@3 | hybrid r@3 | random-diversity r@3 | novelty MRR | random-diversity MRR |
|---|---|---|---|---|---|---|
| metadata only (baseline) | 0.372 [0.27, 0.48] | 0.464 [0.36, 0.57] | 0.409 [0.29, 0.52] | 0.504 [0.40, 0.61] | 0.365 | 0.389 |
| judgments, reply model on candidates (AUC 0.650) | 0.301 [0.20, 0.41] | 0.464 [0.36, 0.57] | 0.412 [0.31, 0.52] | 0.504 [0.40, 0.61] | 0.365 | 0.389 |
| judgments + content, reply model on all (AUC 0.646) | 0.393 [0.29, 0.50] | 0.464 [0.36, 0.57] | 0.388 [0.29, 0.49] | 0.504 [0.40, 0.61] | 0.365 | 0.389 |
| same, candidates with p_automated ≤ 0.5 (AUC 0.606; 56 weeks; median set 5) | 0.452 [0.34, 0.57] | 0.586 [0.48, 0.70] | 0.469 [0.36, 0.58] | 0.546 [0.43, 0.66] | 0.449 | 0.413 |

Reading:

1. Judgment features lift the reply model to AUC 0.65 (from 0.54 metadata-only), the best so far, but the reply model is not what ranks consequential exposures: relevance-only stays at or below random.
2. **Removing automated messages from the candidate pool is the first change that lets a non-random exploration policy beat random-with-diversity**: novelty-only r@3 0.586 vs 0.546, MRR 0.449 vs 0.413, r@5 0.785 vs 0.738. Intervals overlap; this is validation, not test, and the filter threshold was chosen after seeing the judgment distribution on the full candidate pool (including val), so it must be pre-registered before the test run rather than claimed from this table.
3. The hybrid never beats novelty-only. The train-tuned weights now put 1.0 on the AnyJev option-value score and 0 on novelty, and that choice is wrong on val. Uncertainty and information-gain terms never help. As operationalized, H-SER's *hybrid* form is unsupported; the surviving signal is "a new person wrote to him" (metadata novelty).
4. Candidate sets shrink to a median of 5 after the filter, so budgets k ≥ 5 saturate; r@1 and r@3 are the informative numbers.

Implication for the protocol freeze: (a) candidate pool = weak-tie exposures with p_automated ≤ 0.5 (pre-registered, a priori defensible: an exposure is a message from a person); (b) primary comparison = novelty-only and hybrid vs random-with-diversity at k ∈ {1, 3}; (c) Tier B labels (`annotations/private/tier_b_labels_v1.csv`, page at demo/label_tier_b.py) decide whether "consequential" as Carl judges it behaves like Tier A, and feed an AnyJev L2 head for the judgment itself.

## Addendum 2026-09-26 (late): judgments on all 35,168 exposures; stochastic baselines averaged over 20 seeds

AnyJev L0 (Gemma 4 31B AWQ, PC vLLM) now covers every exposure, so the reply model trains on all 15k train-period rows with judgment features and no imputation: **validation AUC 0.678**, the best so far (metadata 0.544, +content 0.643, +judgments 0.678).

Runner fix: policies with heavy ties (novelty, popularity) and the random/ε-greedy/Thompson baselines are now averaged over 20 seeds per week before the cluster bootstrap. Earlier tables in this file used a single seed and moved by up to 0.05 between identical runs; treat them as superseded by the two tables below.

**A. Full weak-tie pool** (63 weeks with a positive; candidate set mean 8.6, median 8; hybrid weights tuned on train: {'relevance': 1.0, 'uncertainty': 0.25, 'novelty': 0.0, 'info_gain': 0.25, 'option_value': 0.5, 'cost': 0.25})

| policy | recall@1 | recall@3 | recall@5 | MRR |
|---|---|---|---|---|
| relevance | 0.115 [0.06, 0.19] | 0.298 [0.20, 0.40] | 0.510 [0.40, 0.61] | 0.296 |
| ucb | 0.115 [0.05, 0.19] | 0.284 [0.19, 0.38] | 0.504 [0.39, 0.61] | 0.288 |
| thompson | 0.112 [0.06, 0.17] | 0.312 [0.22, 0.41] | 0.504 [0.40, 0.60] | 0.298 |
| epsilon_greedy | 0.136 [0.10, 0.17] | 0.366 [0.29, 0.45] | 0.546 [0.46, 0.63] | 0.329 |
| hybrid | 0.106 [0.04, 0.18] | 0.368 [0.27, 0.47] | 0.541 [0.44, 0.65] | 0.310 |
| popularity | 0.151 [0.07, 0.23] | 0.418 [0.31, 0.53] | 0.636 [0.52, 0.75] | 0.356 |
| novelty | 0.148 [0.12, 0.18] | 0.471 [0.40, 0.55] | 0.665 [0.59, 0.75] | 0.368 |
| random | 0.135 [0.10, 0.17] | 0.413 [0.35, 0.48] | 0.618 [0.55, 0.69] | 0.343 |
| random_diversity | 0.117 [0.10, 0.14] | 0.455 [0.39, 0.53] | 0.689 [0.61, 0.77] | 0.346 |

**B. Automated messages removed (Gemma p_automated ≤ 0.5)** (56 weeks; candidate set mean 6.4, median 5; hybrid weights: {'relevance': 1.0, 'uncertainty': 0.25, 'novelty': 0.0, 'info_gain': 0.0, 'option_value': 1.0, 'cost': 0.25})

| policy | recall@1 | recall@3 | recall@5 | MRR |
|---|---|---|---|---|
| relevance | 0.152 [0.07, 0.24] | 0.375 [0.26, 0.49] | 0.574 [0.46, 0.68] | 0.347 |
| ucb | 0.134 [0.06, 0.22] | 0.374 [0.26, 0.49] | 0.562 [0.45, 0.68] | 0.333 |
| thompson | 0.152 [0.09, 0.23] | 0.398 [0.30, 0.50] | 0.575 [0.47, 0.68] | 0.352 |
| epsilon_greedy | 0.189 [0.15, 0.24] | 0.459 [0.37, 0.55] | 0.601 [0.51, 0.69] | 0.389 |
| hybrid | 0.167 [0.08, 0.27] | 0.444 [0.33, 0.56] | 0.646 [0.55, 0.74] | 0.374 |
| popularity | 0.209 [0.11, 0.31] | 0.489 [0.36, 0.61] | 0.701 [0.59, 0.81] | 0.413 |
| novelty | 0.219 [0.17, 0.28] | 0.576 [0.49, 0.67] | 0.746 [0.66, 0.82] | 0.440 |
| random | 0.187 [0.15, 0.24] | 0.526 [0.45, 0.60] | 0.716 [0.64, 0.79] | 0.408 |
| random_diversity | 0.190 [0.15, 0.24] | 0.543 [0.46, 0.62] | 0.733 [0.66, 0.81] | 0.418 |

**Reading (validation split, Tier A labels, pre-registration pending):**

1. **RQ3 holds.** Relevance-only (= the behavioral-clone proxy here) is the worst or near-worst policy in both pools, below plain random: a ranker trained to predict engagement buries the weak-tie exposures that became lasting ties.
2. **H-SER's hybrid form is not supported.** With uncertainty, information-gain and option-value terms, the hybrid never beats random-with-diversity (A: MRR 0.310 vs 0.346; B: 0.374 vs 0.418). The pre-stated falsifier is met on validation.
3. **Plain novelty is the only exploration signal with an edge**, and it is small: MRR 0.368 vs 0.346 (A) and 0.440 vs 0.418 (B), recall@3 0.471 vs 0.455 and 0.576 vs 0.543, all with overlapping 95% intervals. Its tie-breaking is random within new threads, so "novelty" here means "new person first, then coin flip".
4. Removing automated messages helps every policy about equally; the ordering does not change. Gemma flags 36% of ordinary weak-tie messages as automated, Qwen3-8B 11% (κ 0.38 between judges), so the filter's threshold is judge-dependent and must be pre-registered with the judge named.
5. Second judge (Qwen3-8B, MLX, both Macs): the substantive finding replicates. On the same 1,610 labelled exposures, consequential weak ties are less often invitations (Qwen 0.05 vs 0.17; Gemma 0.11 vs 0.26), less often organizational (0.05 vs 0.23; 0.15 vs 0.36), and more often personal chat (0.56 vs 0.43; 0.59 vs 0.36). Inter-judge κ: invitation 0.68, organization 0.68, marketing 0.68, social 0.62, expects-reply 0.38, automated 0.38.

Implication: as a paper result, the honest statement is "on one subject's fifteen years of inbound messages, the exposures that became lasting ties were casual first messages from new people; a relevance ranker suppresses them, a novelty ranker recovers them slightly better than chance, and hand-built uncertainty/information-gain/option-value bonuses add nothing." The test split remains untouched pending Tier B labels and the protocol freeze (candidate pool: weak-tie ∧ Gemma p_automated ≤ 0.5; primary comparison: novelty and hybrid vs random-with-diversity at k ∈ {1, 3}; 20-seed averaging).

### Inter-judge agreement on all 3,719 weak-tie exposures (Qwen3-8B MLX on both Macs vs Gemma 4 31B on the PC, both AnyJev L0)

| judgment | mean Qwen3-8B | mean Gemma-31B | binary agreement | Cohen κ | Pearson r |
|---|---|---|---|---|---|
| p_invites_action | 0.177 | 0.263 | 0.898 | 0.705 | 0.738 |
| p_expects_reply | 0.44 | 0.552 | 0.687 | 0.383 | 0.417 |
| p_org_or_group | 0.234 | 0.374 | 0.856 | 0.668 | 0.72 |
| p_automated | 0.117 | 0.362 | 0.752 | 0.371 | 0.486 |
| p_exposure_type_social | 0.42 | 0.372 | 0.808 | 0.599 | 0.627 |
| p_exposure_type_invitation | 0.146 | 0.074 | 0.896 | 0.476 | 0.543 |
| p_exposure_type_transactional | 0.102 | 0.303 | 0.796 | 0.406 | 0.517 |
| p_exposure_type_marketing | 0.133 | 0.145 | 0.921 | 0.672 | 0.696 |
| ev_option_value | 1.819 | 1.13 |  |  | 0.515 |

### Robustness to the judge defining the automated filter (validation, 20-seed baselines)

Candidate pool filtered with **Qwen3-8B** p_automated ≤ 0.5 instead of Gemma's (Qwen flags 12% of weak-tie messages, Gemma 36%; κ 0.37): 63 weeks, candidate set mean 8.0. Reply model trained on candidates only (Qwen judgments cover candidates only), val AUC 0.585.

| policy | recall@1 | recall@3 | recall@5 | MRR |
|---|---|---|---|---|
| relevance | 0.077 [0.02, 0.15] | 0.339 [0.23, 0.45] | 0.551 [0.44, 0.66] | 0.293 |
| hybrid | 0.118 [0.05, 0.19] | 0.344 [0.25, 0.45] | 0.679 [0.58, 0.78] | 0.325 |
| random | 0.150 [0.12, 0.19] | 0.436 [0.37, 0.50] | 0.657 [0.59, 0.73] | 0.362 |
| random_diversity | 0.146 [0.12, 0.18] | 0.493 [0.42, 0.57] | 0.700 [0.63, 0.77] | 0.374 |
| novelty | 0.169 [0.14, 0.21] | 0.510 [0.42, 0.60] | 0.687 [0.61, 0.77] | 0.391 |

Same ordering as with Gemma's filter: relevance < hybrid < random ≤ random-with-diversity < novelty, intervals overlapping. The ordering is not an artifact of which model defines "automated". Files: `results/metrics_val_qwenfilter.json`, `data/derived/judgments_qwen8b.parquet` (git-ignored).

## TEST SPLIT (opened once, 2026-09-27 19:16 UTC, after freeze at tag `annotation-v1` = 8862642)

Pre-registration: `PREREGISTRATION.md`. Commands run exactly as listed there.

| hypothesis | validation | test | test, labels permuted | verdict |
|---|---|---|---|---|
| H-PREM relevance − random | -0.061 [-0.113, -0.002] | -0.138 [-0.200, -0.067] | +0.020 [-0.067, +0.110] | **supported** |
| H-SER hybrid − random_diversity | -0.044 [-0.107, +0.028] | -0.217 [-0.267, -0.164] | -0.013 [-0.114, +0.092] | **rejected** |
| H-NOV novelty − random_diversity | +0.021 [-0.018, +0.060] | -0.035 [-0.085, +0.013] | +0.007 [-0.058, +0.072] | **inconclusive** |

Primary pool test: 30 weeks, 393 exposures, 36 later-lasting, median set 4. Hybrid weights (tuned on val): {'relevance': 1.0, 'uncertainty': 0.0, 'novelty': 0.5, 'info_gain': 0.0, 'option_value': 1.0, 'cost': 0.25}. Reply-model AUC test 0.671.

Test MRR: clone 0.327, epsilon_greedy 0.399, hybrid 0.279, novelty 0.462, popularity 0.552, random 0.465, random_diversity 0.496, relevance 0.327, thompson 0.328, ucb 0.305

Secondary pool (all weak ties): relevance−random -0.126 [-0.174, -0.065], hybrid−rd -0.157 [-0.193, -0.116], novelty−rd -0.027 [-0.067, +0.014]. Same verdicts.

Exploratory (post-freeze, not pre-registered): platform popularity was the best test policy (MRR 0.552); popularity − random_diversity +0.056 [−0.040, +0.155] primary, +0.091 [−0.001, +0.186] secondary. Novelty's validation edge did not replicate.

Bottom line: relevance buries later-lasting weak ties (replicated on held-out years); hand-built exploration bonuses do worse than random-with-diversity; new-person-first is not reliably better than random. Manuscript: `paper/main.pdf`.
