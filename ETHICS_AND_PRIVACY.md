# Ethics and privacy

## Data handling rules (enforced, not aspirational)

1. All personal data stays on the subject's machines. No raw export, message,
   face, contact, health record, or credential is sent to any external API.
   Embeddings, summaries, topic labels, and annotations are produced by local models.
2. The repository tracks code, aggregates, synthetic fixtures, and the paper.
   `.gitignore` excludes `data/`, every `*.jsonl/*.parquet/*.db`, annotation CSVs
   other than the template, and any `demo/real_*.json`.
3. Counterpart identities are salted hashes. The salt lives in
   `~/.config/carl-life-os/.env`, never in the repo.
4. Figures and demo screenshots that show individual exposures use synthetic
   fixtures or redacted summaries. The watermark "SYNTHETIC" is drawn on any figure
   built from the fixture.
5. Nothing in this study sends messages, accepts invitations, or acts on the
   subject's accounts. The scientific object is retrospective ranking.
6. The locked evaluation window of the sibling carl-model study (days after
   2026-09-16) is not read.

## Ethical position

- **N = 1 and the researcher is the subject.** Every finding is a case study.
  Effect sizes are about one person and generalize only as a method.
- **Retrospective label bias.** "Consequential" is judged from the present. The
  annotation protocol is frozen before policies run on the test period, uses a
  fixed horizon, separates automatic from manual labels, and reports inter-tier
  agreement. It cannot remove hindsight; it can make it explicit and bounded.
- **Cherry-picking.** Candidate sets are every logged exposure in the window, not
  a hand-picked list of famous events. The manual tier is capped and its
  rationale recorded per row.
- **Non-independence.** Exposures cluster in weeks, threads, and people. All CIs
  are cluster bootstraps.
- **Recommendation-system confounding.** What the subject was exposed to was
  itself selected by platforms with unknown objectives. Rankings are compared
  among logged exposures only; we make no claim about exposures that never occurred.
- **No causal claims.** "Preceded and was followed by" is the strongest language
  used. Self-reported links are labelled as such.
- **ADHD** is context for why the subject began recording. No clinical claim is
  made or implied, and no health data enters the experiments.
- **Third parties.** Other people appear in this data without consent. They are
  never named, never embedded as identifiable text, and never modelled
  individually; only hashed tie structure and aggregate interaction counts are used.
- **Dual role.** The subject can stop, redact, or withdraw any part of the data at
  any time; the code never depends on a particular row existing.
