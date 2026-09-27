# Trajectory-event annotation protocol (v1.0, FROZEN 2026-09-27, git tag `annotation-v1`)

**Status: FROZEN** at git tag `annotation-v1` before any policy was run on the test
period. Test-split analysis plan: `PREREGISTRATION.md`. Tier A thresholds as implemented
in `src/ingest/exposures_from_messages.py`: `tie_persisted_365 AND bursts_365 >= 5`. The
`new_context` clause could not be computed (thread hashes are per source) and is dropped.

## Unit

One logged exposure (see EXPERIMENT_PLAN.md E1). Annotation is per exposure, never
per "life event": a life event is only ever the *outcome* column of one or more
exposure rows.

## Two tiers

**Tier A, automatic.** Computed from data in `(t, t+H]`:
`consequential_auto = tie_persisted ∧ repeat_interactions ≥ 5 ∧ new_context`.
Thresholds are set on the training period only and frozen.

**Tier B, manual.** The annotator (the subject) labels exposures sampled from the
candidate pool **blind to every policy ranking** and blind to Tier A. Sampling:
all exposures with `repeat_interactions ≥ 1` in the horizon plus an equal number
of random exposures, shuffled. For each row record the columns of
`trajectory_events.template.csv`. `evidence_direct_or_inferred` is *direct* only
when a logged artifact (thread, calendar entry, application record, commit,
payment) within the horizon links the exposure to the outcome; otherwise *inferred*.

## What counts as an outcome (closed list)

repeat interactions; resulting project; resulting application; money or prize;
publication; new collaborator; sustained topic shift (measured, not felt); repeated
behavior (e.g. attending ≥2 further events of the same community).

## What does not count

Feelings of significance without a logged downstream artifact; outcomes outside
the horizon; outcomes that precede the exposure.

## Reporting

Tier A and Tier B results are always reported separately, with their agreement
(Cohen's κ on the overlap). The number of manual labels and the sampling rule are
reported. No row is added or removed after the freeze.
