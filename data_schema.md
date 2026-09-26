# Normalized event schema

Implemented in `src/schema.py`. Persisted as `data/derived/events.parquet`
(git-ignored). Raw references are local paths; model-ready features live in a
separate table `data/derived/features_<split>.parquet` produced only through
`features_at(t, …)`.

| field | type | notes |
|---|---|---|
| event_id | str | sha256(source, raw locator)[:16] |
| timestamp_start | datetime (tz-aware, UTC) | required |
| timestamp_end | datetime | optional |
| source | str | e.g. `msg_messenger`, `fb_events`, `omi_screen`, `mirror_fb_feed` |
| modality | enum | see `MODALITIES` |
| actor | enum | self / other / platform |
| context_id | str | thread / session / day grouping |
| raw_reference | str | local path + locator; never leaves the machine |
| text_summary_local | str | local-model summary or redacted snippet; never raw PII |
| embedding | list[float] | local model only |
| topic | str | local topic label |
| entities_redacted | list[str] | salted hashes of counterpart ids |
| action_family | enum | see `ACTION_FAMILIES` |
| candidate_opportunity / candidate_person / candidate_content | bool | what kind of exposure this is |
| observed_action | enum | engaged / ignored / unknown |
| metadata | dict | source-specific, feature-safe only |
| **followup_event_ids** | list[str] | **label only** |
| **outcome_labels** | list[str] | **label only** |

`FUTURE_ONLY_FIELDS` in `src/schema.py` enumerates every label column. The leakage
filter refuses any feature frame containing one. `tests/test_no_future_leakage.py`
injects each of them and asserts rejection.

## Mapping from the carl-model 17-field stream

`carl-model/events/*.jsonl` rows (`event_id, source, kind, t_start, t_end,
available_at, host, app, session, actor, attribution_basis, content, alternatives,
numeric, raw_ref, derived_from, meta`) map as: `t_start→timestamp_start`,
`available_at` is checked ≤ decision time (a second leakage guard), `actor` maps
carl→self, other→other, assistant/machine→platform, `content` is **not** copied
(only its local embedding / hashed counterpart), `raw_ref→raw_reference`.
