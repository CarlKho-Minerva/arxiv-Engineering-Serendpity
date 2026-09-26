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
