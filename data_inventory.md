# Data inventory

Compiled 2026-09-26 by read-only inspection of the Mac, the LifeOS state
directory, and the PC file catalog (`~/.local/state/lifeos/catalog/catalog_all.db`,
paths/sizes/CRCs only). Nothing here was uploaded, and no message or document
content was printed during inspection. All paths are local. Dates are ISO.

Privacy levels: **raw-private** (verbatim personal content), **derived**
(aggregates, captions, labels; may still contain speech/text), **public**.

## 0. Headline findings that shape the study

1. **The prior behavioral-clone result is real and reproduced.** See §1. All seven
   reported numbers were recomputed from raw per-case scores by
   `scripts/verify_carl_model.py` (aggregates in `results/carl_model_verified.json`).
2. **Recommendation-system outputs exist only as single 2026 snapshots.** Every
   platform export (Meta feed log, suggested friends, ad interests, YouTube/My
   Activity, Twitter personalization) was taken Jul–Sep 2026. There is **no
   historical series** of what any recommender surfaced. Longitudinal
   "algorithmic mirror" analysis (RQ2, RQ7) is therefore not currently testable
   as a time series. A cross-sectional test at 2026 is possible.
3. **Logged exposures with logged choices exist for 15 years, but only in one
   family: inbound communication.** Messenger (2011→2026, 2.6M messages),
   Instagram DMs (2017→), Twitter DMs (2016→), Gmail (2013→), Discord (2020→),
   Telegram (2016→), LinkedIn (2020→), plus Facebook event invitations, group
   join records, friend requests received. Each is an exposure (someone reaches
   the subject / invites him) with an observable action (reply / accept / attend)
   and observable downstream (repeat interaction, sustained tie). This is the
   dataset for the retrospective serendipity experiment (RQ3–RQ6).
4. **Dense multimodal capture is short.** Wide LifeOS capture starts ~2026-08-10;
   the dense lanes (attention, input, location, cameras) start 2026-09-04/05.
   Messages are the only modality with years of depth.
5. **The high-school-era Google Takeouts (<account-B> account) are the missing
   piece for early-era recommendation evidence** and have never been indexed
   file-by-file (they sit on the PC as zips).

## 1. Prior experiment artifacts (carl-model, "carl world model")

| item | path | status |
|---|---|---|
| Pre-registration | `~/CODELocalProjects/carl-model/PROTOCOL.md` (committed, `fcca9bd`, 2026-09-15) | frozen; Amendments 1–12 |
| Draft next protocol | `~/CODELocalProjects/carl-model/PROTOCOL_M3_DRAFT.md` (untracked) | defines a **locked test window: every day after 2026-09-16**. Not read, scored, or trained on by this repo. |
| Results (M2, test split) | `~/.local/state/lifeos/carl-model/runs/m2/results_test_M2_full.json` (2026-09-15 22:04) | source of the reported numbers |
| Raw per-case prompts / scores | `runs/m2/prompts_test_M2_full.jsonl` (71 MB), `runs/m2/scores_test_M2_all.jsonl` (13 MB) | used by `scripts/verify_carl_model.py` |
| Event-model results | `runs/m2-all/em_results_test.json`, `em_meta_test.jsonl`, `em_scores_test.jsonl` | verified |
| Training data | `runs/lora-m2/lora_train.jsonl` (44,130 rows, all ≤ 2026-08-17) | exists |
| Adapter (H3, step 600) | master `PC:D:/carl-model/runs/lora-8b-s600/best_adapter`; local copy `~/.local/state/lifeos/carl-model/serve/peft/adapter_model.safetensors` (175 MB, r16/α32, base `unsloth/Qwen3-8B-unsloth-bnb-4bit`) | exists locally |
| Private report | `~/Documents/Codex/2026-09-14/see/outputs/CARL_MODEL_RESULTS.md` | second-hand; not cited |

**Task definition (from PROTOCOL.md and `src/common.py`):** 5-way next-choice, 7
families (`reply, typed, said, copied, clicked, looked, sent`), true action plus 4
pre-specified negatives from the subject's own history (same family, other
day/session, length-matched, context-similar), candidate order shuffled per
case, scored by PMI under frozen Qwen3-8B 4-bit. Test days: reply/sent
2026-08-25→09-14 (21 days), dense families 2026-09-11→09-14. Pooled table
excludes `said`. Train ≤ 08-17 (reply/sent) or ≤ 09-08 (dense).

**Verified numbers (this repo's recomputation, pooled n=1695, chance 0.20):**

| variant | top-1 | Δ vs A | 95% cluster-bootstrap CI | days with gain |
|---|---|---|---|---|
| A immediate situation | 0.2802 | — | — | — |
| B / C / E (history, atlas, all layers, base model) | 0.258 / 0.245 / 0.256 | −2.2 / −3.5 / −2.4 | all ≤ 0 | 6–7 / 21 |
| E-shuf (shuffled context) | 0.2407 | −4.0 | [−6.1, −1.4] | 4/21 |
| F (random history) | 0.2478 | −3.2 | [−5.4, −1.2] | 5/21 |
| **L (A + personal LoRA)** | **0.3782** | **+9.8** | **[+6.8, +13.4]** | **20/21** |
| L+E (all layers + LoRA) | 0.3817 | +10.1 | [+7.0, +14.1] | 19/21 |
| EM-own / EM-all (event model) | 0.2891 / 0.2932 | — | EM-all vs EM-own +0.4, n.s. | — |

Caveats to carry into the paper: (i) 17 of the 21 test days contain only
`reply` and `sent` cases, so "20/21 days" is dominated by two families; (ii) per
family, L gains on reply (+21.0), sent (+11.6), typed (+12.1) and loses on copied
(−16.7, n=30), clicked (−4.3), looked (−2.7); (iii) the primary pre-registered
hypothesis H1 (E > A) **failed**; H3 (L > A) is the positive result; (iv) the
code on disk has small uncommitted diffs relative to the run.

## 2. Normalized event streams that exist

| source | path | modality | format | range | size / rows | privacy | gaps |
|---|---|---|---|---|---|---|---|
| carl-model event stream (17-field schema, `src/common.py:81-83`) | `~/.local/state/lifeos/carl-model/events/*.jsonl` (37 files) | mixed | JSONL | 2011-11 → 2026-09-15 | 2.9 GB, 3,429,022 rows | raw-private | frozen snapshot 09-15 |
| ├ msg_messenger | same | social/text | JSONL | 2011-11-02 → 2026-07-28 | 2,610,864 | raw-private | zips on PC; text in part 130 |
| ├ msg_telegram | | text | | 2016-05 → 2026-09-15 | 363,225 | | no tz in export (read as Pacific) |
| ├ msg_instagram | | text | | 2017-04 → 2026-09-08 | 72,345 | | |
| ├ ai_archive | | conversation | | 2023-04-15 → 2026-09-15 | 70,804 | | |
| ├ msg_discord / twitter / gmail / linkedin / gchat / gvoice | | text | | 2020-08 / 2016-05 / 2013-09 / 2020-12 / 2016-06 / 2024-03 → 2026 | 21,622 / 2,223 / 6,482 / 3,104 / 656 / 2,072 | | Gmail: 2 Workspace accounts never exported |
| ├ browser, presence, screen_clicks, input, attention, gaze, place, keylog, clipboard, vision, whisper, parakeet, harness, claude_code, codex, zsh… | | behavior | | 2026-07/08 → 09-15 | 5k–70k each | | weeks, not years |
| `lifeos.event.v1` schema | `~/CODELocalProjects/lifelog-os/schemas/event-v1.schema.json` | contract | JSON schema | — | — | — | **no persisted store** |
| Layer definitions | build layers 0–50: `_worktrees/lifelog-os-main/status_board/layers.json:1006-1262`; capture signals (24+3): `lifeos/capture_registry.json`; model layers (13): `carl-model/src/event_vectors.py:37-38` | meta | JSON/py | — | — | — | "52 lanes" matches none of the three counts |

## 3. Live / recent capture (LifeOS)

| source | path | modality | format | range | size / count | privacy | gaps |
|---|---|---|---|---|---|---|---|
| Omi screen frames + OCR | `~/Library/Application Support/Omi Dev Bundles/com.omi.omi-carl/users/<uid>/omi.db` → `screenshots` | screen | SQLite | 08-27 → 09-26 (30-day ring) | 116,156 rows, 77 apps | raw-private | 16.8% have OCR; embeddings NULL; **08-20→08-27 missing** |
| Omi backup | `~/CODELocalProjects/omi-db-backup-20260819/omi.db` | screen/speech | SQLite | 07-29 → 08-20 | 89,174 frames | raw-private | |
| Omi transcripts | same DB → `transcription_segments` | speech | SQLite | 07-30 → 09-26 | 11,711 segments / 433 sessions | raw-private | speaker id unverified |
| Audio tapes (room, system, glasses, phone) | `~/CODELocalProjects/omi-notes/audio*` | audio | FLAC | 09-11 → 09-26 | 24.7 GB | raw-private | 14–16-day rolling retention |
| Whisper second pass (durable) | `~/CODELocalProjects/omi-journal/whisper` | speech text | JSONL | 08-04 → 09-26 | 21,088 rows | derived | |
| Glasses POV photos / desk cam / dashcam | `omi-notes/photos-glasses`, `photos-phone`, `video-ride` | image/video | JPG/MP4 | 08-13 → 09-17 / 09-05 → 09-25 / 09-05 → 09-16 | 1,216 / 305 / 11 | raw-private | glasses stop 09-17 |
| Keystrokes / clipboard | `omi-notes/keylog`, `omi-notes/clipboard` | text | JSONL | 09-11 → 09-26 | 5,384 / 1,199 | raw-private | pruned ~15 days |
| Presence (app, idle, lock, place) | `~/.local/state/lifeos/recorder/presence` | device state | JSONL | 08-06 → 09-26 | 58,287 | raw-private | |
| Attention / gaze | `recorder/attention` | webcam gaze | JSONL | 09-04 → 09-26 | 118,619 | derived (no frames) | off with lid closed |
| Input dynamics | `recorder/input` | counts | JSONL | 09-05 → 09-26 | 147,425 | derived | |
| Location | `~/.local/state/lifeos/location` | GPS | JSONL | 09-04 → 09-26 | 7,544 fixes | raw-private | nothing before 09-04 |
| Apple Health | `~/.local/state/lifeos/health/apple` | health | JSONL | 06-01 → 09-23 | 114 daily / 72 sleep / 193 workouts | raw-private | workouts stop 09-03 |
| CCTV captions/tags | `omi-journal/cctv_captions`, `cctv_tags` | derived vision | JSONL | 09-01 → 09-17 | 10,628 / 126,479 | derived | video on PC `D:\cctv` |
| Journal (daily/weekly/meetings) | `omi-journal/{daily,weekly,monthly,meetings}` | narrative | Markdown | 07-26 → 09-25 | 62 / 8 / 2 / 13 | derived | |
| Thought graph, recall index, context, food, objects | `~/.local/state/lifeos/{thought-graph,recall,context,food,objects}` | derived | JSON/SQLite | 08 → 09-26 | small | derived | |
| Coverage (per-lane hourly) | `~/.local/state/lifeos/coverage` | meta | JSON | 09-03 → 09-26 | 24 days | derived | mean coverage: presence/location 85%, screen 80%, attention 40%, keys/mic/input ~33%, cctv 1% |
| AI conversation archive | `~/CODELocalProjects/ai-archive` | conversation | Markdown+YAML | 2023-04-15 → 2026-09-26 | chatgpt 2,873; aistudio 1,534; claude-code 6,229; codex 1,099; … | raw-private | tool payloads/thinking dropped |
| Move annotations (exploratory) | `~/.local/state/lifeos/carl-model/annotations/` | labels | JSONL | 09-19 | 6,573 moves; gold50; ref100 | derived | outside PROTOCOL |

## 4. Raw exports (mostly on the PC `the PC`: `D:`, `E:` (T7), `F:`, `C:\T7-mirror`)

### 4a. Recommendation-system outputs (the "algorithmic mirror" channel)

| source | path | format | snapshot date | size | notes |
|---|---|---|---|---|---|
| FB feed exposure log | `D:\data-exports-sep2026\meta-facebook-2026-09-20\extracted\logged_information\interactions\content_that_has_been_shown_to_you_in_your_feed.json` | JSON | 2026-09-20 | 106 KB | recent window only |
| FB people-you-may-know | `…\connections\friends\suggested_friends.json` | JSON | 2026-09-20 | 41 KB | |
| FB ads: preferences, interests, advertisers, categories, locations | `…\ads_information\*.json`, `…\other_logged_information\ads_interests.json`, `…\preferences\your_preferred_categories.json` | JSON | 2026-09-20 | 8 KB – 533 KB | inferred-interest lists |
| FB behavior logs (items viewed, groups/events visited, profile visits, reels, search, off-Meta activity) | `…\logged_information\…` | JSON | 2026-09-20 | up to 524 KB | behavior, not recommendations |
| YouTube watch + search history, subscriptions (<account-A>) | `D:\<account-A>-takeout-20260915\…\YouTube and YouTube Music\history\watch-history.html` | HTML | 08-20, 09-06, 09-15 | 48.5 / 68.5 / 64.5 MB | **shrinking between exports**: auto-delete suspected |
| YouTube (Minerva account) | `F:\GDrive-Archive-Jul2026\02_account_kho-at-uni.minerva.edu\takeout_20260722T222739Z` | HTML | 2026-07-22 | 5.5 MB | |
| Google My Activity (<account-A>): YouTube, Search, Ads, Discover, My Ad Center, News, Play, Image Search | `…\Takeout\My Activity\*\MyActivity.html` | HTML | 2026-09-15 | 85.7 / 57.7 / 4.0 / 0.3 / 0.15 / 0.2 / 3.6 / 9.1 MB | Discover CSVs 16–52 bytes (headers only) |
| Google My Activity (Minerva) | same layout | HTML | 2026-07-22 | Search 21 MB, Maps 19.9 MB, YouTube 5.6 MB | |
| Twitter inferred interests (2 handles) | `E:\twitter-export-aug2026\…\data\personalization.js` | JS | 2026-08-08/09 | 43 KB | ad-impressions/engagements empty |
| Instagram topics / suggested accounts | `D:\data-exports-sep2026\instagram-<ig-handle>-2026-09-14-*.zip` (3.16 GB) | zip | 2026-09-14 | — | **never unpacked; unknown** |
| Spotify inferences / Marquee | — | — | — | — | **absent** (only streaming history) |
| Google Location History | — | — | — | — | absent (Settings.json only) |
| YouTube homepage recommendations | — | — | — | — | not exportable |

### 4b. Social / communication history (exposure + choice)

| source | path | format | range | count (subject-sent) | privacy | gaps |
|---|---|---|---|---|---|---|
| Messenger (147 zips ×3 copies) | `E:\`, `C:\T7-mirror\`, `D:\T7-copy\meta-export-aug2026\` | JSON in zip | 2011-11-02 → 2026-07-28 | 2,610,864 (829,589) | raw-private | 313 GB; normalized copy in §2 |
| Facebook full export (Sep) | `D:\data-exports-sep2026\meta-facebook-2026-09-20\extracted\` | JSON | not measured (306 GB suggests all-time) | 291k files | raw-private | "All time" selection unverified |
| ├ messages | `…\your_facebook_activity\messages\` | JSON | | inbox 2,271 threads, e2ee 381, archived 56, requests 30 | | |
| ├ posts / albums / videos / trash / edits | `…\posts\` | JSON | | 15,478 files, 4.2 GB | | |
| ├ friends (with `timestamp`), sent/received/rejected/removed requests | `…\connections\friends\` | JSON | | `your_friends.json` 169 KB | | |
| ├ comments and reactions | `…\comments_and_reactions\` | JSON | | comments 3.5 MB; reactions ~22 MB | | |
| ├ events: invitations, responses, hosted | `…\events\` | JSON | | 1.4 MB | | |
| ├ groups: membership activity (join records), comments, posts, invites | `…\groups\` | JSON | | 76 KB + 440 KB + … | | |
| ├ pages liked / followed, stories, tags | `…\pages_you've_liked.json` … | JSON | | 342 KB / 396 KB / 3.9 MB | | |
| Instagram DMs | `D:\…\instagram-…-VgkRAziO.zip` | JSON | 2017-04-01 → 2026-09-08 | 72,345 (35,639) | raw-private | |
| Twitter (2 handles): DMs, tweets, likes, following | `E:\twitter-export-aug2026\` | JS | 2016-05-12 → 2026-08-05 | 2,223 DM events (1,346) | raw-private | |
| Gmail (3 accounts, mbox) | `D:\data-exports-sep2026\takeout-…zip`; <account-A> 3.43 GB; Minerva 6.76 GB | mbox | 2013-09-05 → 2026-09-12 | 6,482 paired (3,731) | raw-private | 2 Workspace accounts missing |
| Discord | `~/Downloads/discord package.zip`; PC tar + HTML | JSON/HTML | 2020-08-23 → 2026-08-07 | 21,622 (7,829) | raw-private | |
| Telegram | `~/Downloads/Telegram_Export_2026-09-14` (45 GB) | HTML | 2016-05-03 → 2026-09-15 | 363,225 (95,091) | raw-private | no timezone |
| LinkedIn | `D:\…\Complete_LinkedInDataExport_09-13-2026.zip.zip` | CSV | 2020-12 → 2026-09-12 | 3,104 (1,555) | raw-private | |
| WhatsApp (live) | `~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/ChatStorage.sqlite` | SQLite | 2023-11-14 → 2026-09-26 | 1,477 (327) | raw-private | |
| iMessage (live) | `~/Library/Messages/chat.db` | SQLite | 2026-05-02 → 2026-09-24 | 1,780 (1,033) | raw-private | 5 months |
| Google Chat / Voice (cvk) | cvk Takeout 07-22 | JSON | 2016-06 → 2026-05 / 2024-03 → 2026-07 | 656 (129) / 2,072 (681) | raw-private | |
| Spotify streaming (2 accounts) | `~/Downloads/my_spotify_data*.zip`; `D:\…\spotify\` | JSON | 2014 → 2026 | yearly | low-med | |
| Not found anywhere | Slack, Reddit, Signal, WeChat, LINE | — | — | — | — | |

### 4c. Browser, calendar, contacts, trackers

| source | path | range | count | notes |
|---|---|---|---|---|
| Dia (4 profiles) | `~/Library/Application Support/Dia/…/History` | 2026-07-01 → 09-26 | 60,750 + 8,221 + 4,185 + 7 visits | live only |
| Chrome / Safari | `…/Google/Chrome/Default/History`; `~/Library/Safari/History.db` | 07-23 → 09-25 / 06-01 → 09-16 | 204 / 1,497 | |
| Old-Mac snapshot (Dia, Chrome, Tor places.sqlite) | `E:\Mac_Transfer\cvk_2026-06-27\…` | ≤ 2026-06 | — | not inspected |
| Takeout Chrome History.json | in Takeout | short | 293 KB | |
| Calendar | Takeout `Calendar\<account>.ics` (58 KB); Minerva 5 files; `~/Downloads/carl/md-calendar` (markdown) | — | — | |
| Contacts | Takeout `Contacts\*.vcf`; FB `your_imported_contacts.json` (971 KB) | — | — | |
| Application tracker | `~/Downloads/carl/md-cv/applications/_tracker/tracker.json` + `tracker_log.jsonl` | 2025-10-26 → 2026-09-25 | 330 records; 10 submitted, 10 won, 9 lost, 134 dormant; 3,260 change events | opportunity-response ground truth for 2025–26 |
| Capstone progress list | `~/CODELocalProjects/md-capstonefall25_25TPE/master-progress-list/` | 2025-09 → 2026-04 | 42 + 71 entries | progress log, not tracker |
| Relationship graphs (kith, kindle) | OpenHost only; **no local DB** | — | — | schemas: people(name, role, org, status, met_where); interactions(person, summary, ts) | 

## 5. Known missingness (to state in the paper)

- Recommendation outputs: single snapshots (Jul–Sep 2026); no time series; Instagram
  topics unknown; Spotify inferences absent; Discover empty.
- High-school-era Google account (`<account-B>`): Takeouts exist on the PC (07-22:
  33 GB; 09-12: 22.6 GB) but only Mail/Chat/Voice confirmed; YouTube/My Activity
  unindexed. This is the only path to early-era mirror evidence.
- Dense multimodal lanes: ~3 weeks (from 2026-09-04). Wide capture: ~7 weeks.
  Messages: 15 years. Any "longitudinal" claim rests on messages, email, and
  social exports, not on the multimodal lanes.
- Screen frames missing 2026-08-20 → 08-27; embeddings NULL everywhere; raw audio,
  keystrokes, clipboard retained ~15 days.
- Facebook export "All time" selection unverified; August Meta zips not fully
  CRC-checked; T7 drive flagged dirty; PC RAM memtest showed errors (hashes advisory).
- <account-A> YouTube watch-history shrinks between exports (auto-delete suspected).
- No local relationship graph; kith/kindle data on OpenHost.
- Locked evaluation window (carl-model draft protocol): all days after 2026-09-16.
  This repo does not read them.

## 6. YouTube stream and upload archive (added 2026-09-27; missed in the first inventory)

| source | path | modality | format | range | size / count | privacy | status |
|---|---|---|---|---|---|---|---|
| Channel videos (<account-A> Takeout 2026-09-06, all archives CRC+sha256 verified) | `D:\<account-A>-takeout-20260906\*-5-*.zip` → `Takeout/YouTube and YouTube Music/videos/` | screen + camera video, audio | mp4 596, webm 318, mkv 2 | 2016-02 → 2026-09-03 | 916 videos, ~700 h, 2.5 TB | raw-private (third parties on screen and camera) | **not processed** |
| Video metadata | same zip, `video metadata/videos*.csv`, `video recordings*.csv`, `video texts*.csv` | metadata | CSV | same | 15 files | derived | copied to `data/raw/yt_meta/` (ignored) |

Hours by year: 2016–2020 ≈ 6 h; 2021 114; 2022 82; 2023 106; 2024 159; 2025 194; 2026 38. 257 videos ≥ 1 h (534 h). YouTube category (not reliable for work vs play): Gaming 415 h, People 208 h, other 76 h. Privacy: 418 unlisted, 413 public, 85 private.

## 7. Complete archive survey (2026-09-27)

Method: every store in the PC file catalog (`~/.local/state/lifeos/catalog/catalog_all.db`, 7.4 M entries: D:, E:, F:, C:\T7-mirror, three <account-A> Takeouts, the Minerva Takeout, the Mac restic backup, the 48 GB Mac, five Google Drives, Immich, B2), swept for video/audio collections and by keyword, plus the file tables of every export zip that was never indexed (the <account-B> Takeouts, Instagram, LinkedIn, capstone archives), plus timestamp spans read from the activity logs themselves. No message or document content was printed.

**Long-running records (≥ 3 years), by what they capture**

| record | span | size | captures | used in paper |
|---|---|---|---|---|
| Messages, 9 platforms | 2011–2026 | 3.08 M messages | who reached out, who replied | **yes** |
| YouTube channel videos, <account-A> | 2016–2026 (≈ 690 h since 2021) | 916 videos, ≈ 700 h, 2.5 TB | livestreams and uploads: work sessions, gameplay, daily life (titles do not separate them) | no |
| YouTube channel videos, <account-B> (high-school account) | ? | 17 videos, 20 GB | uploads | no |
| Google My Activity: YouTube | 2013–2026 | 85,042 entries | his YouTube actions | no |
| Google My Activity: Search | 2013–2026 | 64,587 entries | his searches | no |
| YouTube watch history | 2020–2026 | 67,806 entries | videos he watched | no |
| YouTube search history | 2019–2026 | 12,429 entries | his YouTube searches | no |
| Google My Activity: Play Store, Image Search, Maps, Lens, Assistant, … | 2014–2026 | ≈ 30 k entries | app and search actions | no |
| Google ad activity | 2017–2026 | 4,469 entries | ads he **visited or used** (not impressions) | no |
| Facebook groups and events visited | 2012–2026 | 1,181 entries | communities he opened | no |
| Facebook items viewed / shows watched | 2020–2026 / 2017–2023 | 74 / 102 | marketplace items, shows | no |
| Instagram suggested profiles viewed | **2017–2020** | 501 entries | **recommender output he engaged with** | no |
| Instagram "not interested" feedback | 2023–2026 | ≈ 10 entries | his feedback on recommendations | no |
| Gmail (3 accounts) | 2013–2026 | 6,482 paired messages (+ mbox 6.5 GB) | email | messages only |
| Photos and videos (Google Photos → Immich) | 2010–2026, mostly 2021–2026 | ≈ 80 k assets | camera roll | no |
| Google Drive (<account-B>, school) | 2009–2025 | ≈ 2,400 files incl. school presentations | schoolwork, personal files | no |
| Google Fit daily activity (<account-B>) | 2020–2025 | 836 days + 1,111 activities | steps, activity | no |
| Google Health export | 2023–2026 | ≈ 3,000 files | activity, health | no |
| Spotify streaming history (2 accounts) | 2014–2026 | yearly files | listening | no |
| AI conversations (ChatGPT, AI Studio, Claude, Codex) | 2023–2026 | ≈ 12 k conversations | intent, questions, work | no |

**Shorter but dense records**

| record | span | size | captures |
|---|---|---|---|
| Screen Studio projects | 2024-08 → 2026 | 53 projects | screen video **with keystroke and cursor logs** (`recording/keystrokes-0.json`) |
| Capstone pomodoro sessions | late 2025 | 253 sessions | per session: screenshots, audio, raw log (intent notes) |
| Capstone progress logs | 2025-09 → 2026-03 | ≈ 100 entries | project journal |
| Google Recorder (Minerva) | dates not read | 911 recordings, 15 GB | voice notes, meetings |
| Google Voice calls (<account-B>) | 2024–2026 | 1,095 records | calls |
| Notion export | content dates not read | 6,001 pages | notes |
| iPhone backup (iMazing, 2026-08-23) | message DB only 3.5 MB | — | short iMessage history |
| LifeOS capture lanes | 2026-07 → 2026-09 | see §3 | screen, input, audio, gaze, location, cameras |

**Gaps in this survey:** the 48 GB Mac's listing is incomplete (ssh blocked by an unaccepted Xcode license on that Mac), the legacy `gdrive:` remote is unauthorised, the Backblaze archive repo has no snapshots, and the 2026-09-15 <account-A> Takeout was catalogued but not separately profiled (it repeats the 09-06 contents).
