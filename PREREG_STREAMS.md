# Pre-registration: stream archive analyses (frozen 2026-09-27, before any stream outcome was computed)

Written while the stream pipeline (`scripts/streams/`) was still running. At the time of the freeze no
entity had been matched between watch history and streams, and no stream-side outcome, rate, or
per-entity result had been computed or looked at. Pipeline checks so far used counts only (videos
processed, frames captioned, JSON validity). This file and the code at tag `streams-prereg-v1` define the
confirmatory analysis. Everything else in section 6 is labelled exploratory.

## 1. Data
- **Streams:** carlcrafters YouTube Takeout (2026-09-06), 915 video files, about 700 h, 2016 to 2026,
  heavy from 2021. Step 0 reads each video once; outputs per video: keyframe every 10 s, Gemma 4 31B
  captions (JSON fields `setting, activity, app_or_game, topic, people_visible, caption`; one per 30 s
  for work-like videos, one per 60 s when at least 80 % of a 2-minute probe is gameplay), Apple Vision
  screen text for every keyframe, Whisper large-v3-turbo transcripts where VAD finds at least 10 s of
  speech. A video's date is its YouTube `Video Create Timestamp` (for videos whose title matched
  several metadata rows, the row whose duration matches within 2 %; unresolved videos are excluded).
- **Exposures:** YouTube watch history, the union of every export in the file catalog (carlcrafters
  account 2026-08-20, 09-06, 09-15; Minerva account 2026-07-22), deduplicated by (timestamp, URL):
  74,009 watches from 2020-10 onward. Google My Activity Search and YouTube search history, same union
  (37,873 and 7,741 searches), used for the passive/sought split only. Parsed by
  `scripts/streams/pc_history_extract.py` (counts above were the only thing printed).
- **Stream-day:** a calendar day (America/Los_Angeles) with at least one stream. Rates below are per
  observed stream-day, so days without streams carry no information rather than zeros.

## 2. Entities (defined from the exposure side only)
- Universe U: software tools, apps, websites, programming languages or frameworks, and video games named
  in watch-history video titles. Extraction: the eGPU vLLM Gemma 4 31B, temperature 0, one fixed prompt
  (in `scripts/streams/adoption.py` at the tag), output a JSON list of names or `[]`.
- Normalization: lowercase, strip punctuation and a trailing version number, collapse whitespace. Two
  names are the same entity only when their normalized forms are identical (no fuzzy matching).
- Exclusions, fixed now: names shorter than 3 characters; the generic words in the `STOP` list in
  `adoption.py` (for example "youtube", "google", "video", "game", "app", "tutorial").
- First exposure `X_e`: the earliest watch-history timestamp whose title yields entity e.

## 3. Outcome (stream side)
- Entity e **appears on stream on day d** when, on a stream from day d, the normalized `app_or_game`
  or `topic` caption field equals e or contains e as a whole-token sequence.
- Secondary outcome definition: the same with Apple Vision screen text (lines with confidence >= 0.5,
  entity names of at least 5 characters only), reported separately.

## 4. Confirmatory hypotheses and decision rules

**H-ADOPT (primary).** After Carl first watches something about e, e shows up in what he does on stream
more often than before.
- Eligible entities: `2020-07-01 <= X_e <= 2026-03-01` and at least one observed stream-day in both
  the 180 days before and the 180 days after `X_e`.
- Per entity: `pre_e` = share of observed stream-days in `[X_e - 180 d, X_e)` on which e appears;
  `post_e` = the same over `(X_e, X_e + 180 d]`.
- Endpoint: mean over eligible entities of `post_e - pre_e`; 95 % bootstrap CI over entities
  (5,000 resamples, seed 20260927).
- **Supported** if the CI lies entirely above 0. **Rejected** if it includes 0 or lies below it.
- **Placebo, mandatory:** the same endpoint with every `X_e` shifted by +365 d (and, separately, -365 d).
  H-ADOPT is only reported as exposure-linked if, in addition, the paired difference
  (real minus +365 d placebo, per entity, same bootstrap) has a CI entirely above 0. Otherwise the
  result is reported as "consistent with a persistent interest, not with the exposure".

**H-PASSIVE (secondary, decision rule stated).** First exposures that were not sought show the effect
less than sought ones.
- Sought: a Google or YouTube search whose normalized text contains e in the 30 days before `X_e`.
  Passive: no such search.
- Endpoint: mean(`post - pre` | sought) minus mean(`post - pre` | passive); bootstrap CI as above.
- Supported if CI entirely above 0; the opposite sign is reported as its own finding.

Stratified reporting without decision rules: games vs everything else; H-ADOPT with the screen-text
outcome; cluster bootstrap by calendar month of `X_e` as a sensitivity analysis.

## 5. Order of operations
1. Tag this file and the code (`streams-prereg-v1`).
2. Run the entity extraction on watch-history titles (exposure side only).
3. Wait until the pipeline has captioned every video (`D:\streams\CAPTIONS_DONE`).
4. Run `scripts/streams/adoption.py --run` exactly once; its output file records the tag commit.
No peeking: until step 4, only counts of entities and videos may be printed.

## 6. Exploratory work (no hypotheses, reported as exploratory)
- Attention curve 2016-2026: app per 10 s from captions and screen text; dwell and switch statistics
  by year, compared descriptively with published figures (Mark 2023; Reeves et al. 2019). No clinical
  interpretation of any kind.
- Stream state lane: per 5-minute bin, SigLIP 2 and V-JEPA 2 embeddings (PCA), AnyJev typed
  probabilities, speech and loudness; next-bin prediction versus persistence and mean baselines.
- Game choice as explore/exploit: new-game versus returning-game sessions over time.
- Think-aloud corpus and a personal language model from transcripts (perplexity on held-out months).
- A private question set for long-horizon recall over the archive.
- Action labels for screen streams with a public inverse-dynamics labeler, checked against the 49
  minutes of Screen Studio recordings that have logged input.

## 7. Known limits, stated now
- Watch history is what Carl played, not what YouTube showed him, so every exposure is already his
  choice; H-ADOPT measures exposure-to-behaviour, not recommendation-to-behaviour.
- Shared interest drives both watching and streaming (homophily-style confounding, Aral et al. 2009);
  the +/-365 d placebo only partly addresses this.
- Stream dates are upload/creation dates, which may lag the live date.
- Watch history begins in 2020 and appears to lose entries between exports.
