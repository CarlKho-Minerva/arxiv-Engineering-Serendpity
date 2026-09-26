# Trajectory-event annotation protocol (v0.1, to be frozen before test-period evaluation)

**Status: DRAFT. Not yet frozen.** Freezing = tagging this file `annotation-v1` in git
and recording the commit hash in `results/split.json` before any policy is run on
the test period.

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
