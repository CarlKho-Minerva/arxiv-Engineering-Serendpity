# DRAFT amendment to carl-model/PROTOCOL.md: stream archive as training history (not applied)

Status: draft written 2026-09-27 by an agent during the stream-archive run. Nothing reads it. Carl decides
whether to add it to `~/CODELocalProjects/carl-model/PROTOCOL.md` under **Amendments**. PROTOCOL.md says a
change to what the model reads is a protocol amendment, so this cannot be done as a refactor.

## What would change
Two new inputs, both built from the carlcrafters YouTube Takeout (2026-09-06), both training-only:
1. **Think-aloud corpus** (`arxiv-Engineering-Serendpity/data/derived/thinkaloud.jsonl`): speech segments from
   work streams with the screen caption before, the caption 30 to 90 s after, the app, and top screen-text
   lines. Use: extra LoRA training text of the "said" kind, and (screen, said, next screen) triples.
2. **Stream state lane** (`data/derived/stream_bins.parquet`): per 5-minute bin, SigLIP 2 / V-JEPA 2 PCA
   features, AnyJev typed probabilities, speech and loudness, screen-change rate.

## Why it does not touch the locked windows
The newest video in the Takeout is from 2026-09-06 or earlier. carl-model's validation days are
2026-09-09 to 09-10 and its test days come after, so every stream row falls in the training period. The
amendment adds no test cases and changes no negatives, attribution rules, or gates.

## What it would be labelled
Any carl-model run that reads these inputs is **exploratory** and is reported separately from the
pre-registered M1/M2 results. The stream speech is not speaker-verified (no diarization; calls,
teammates and played videos are mixed in), so it cannot enter the "said" test family, which requires
`isUser=1`.

## Open question for Carl
Whether stream speech from other people (hackathon teammates, calls) should be filtered before it is used
as "Carl text". Without a speaker model, the safe default is to keep it out of LoRA training and use only
the state lane.
