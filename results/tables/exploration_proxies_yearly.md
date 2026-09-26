# Exploration proxies by year (EXPLORATORY, not pre-registered; counts only; content never read)

Source: results/exploration_proxies_monthly.json from src/ingest/message_aggregates.py, 3,082,593 message rows across 9 sources, 2011-11 → 2026-09-15 (locked window excluded).

Caveats: (1) counts are dominated by Messenger until ~2023 and by Telegram after; a change in platform is not a change in behaviour. (2) 'thread' includes group threads. (3) Before 2016 the monthly n is tiny; 2026 is a partial year. (4) reply rate = share of other-initiated NEW threads that received a self message within 7 days.

| year | new threads (other-init) | new threads (self-init) | self-init share | reply rate to new inbound | dormant ties reactivated (self / all) | msgs out | msgs in |
|---|---|---|---|---|---|---|---|
| 2011 | 2 | 5 | 0.71 | 1.0 | 0 / 0 | 22 | 15 |
| 2012 | 13 | 14 | 0.52 | 0.69 | 1 / 3 | 624 | 628 |
| 2013 | 7 | 11 | 0.61 | 0.43 | 5 / 7 | 750 | 819 |
| 2014 | 2 | 12 | 0.86 | 1.0 | 6 / 9 | 1017 | 782 |
| 2015 | 13 | 30 | 0.7 | 0.85 | 8 / 13 | 4432 | 13299 |
| 2016 | 49 | 101 | 0.67 | 0.71 | 12 / 21 | 21065 | 81207 |
| 2017 | 102 | 310 | 0.75 | 0.46 | 75 / 91 | 53274 | 71439 |
| 2018 | 190 | 322 | 0.63 | 0.51 | 64 / 135 | 63830 | 201922 |
| 2019 | 215 | 311 | 0.59 | 0.57 | 182 / 257 | 144877 | 348742 |
| 2020 | 221 | 434 | 0.66 | 0.54 | 190 / 261 | 192793 | 319142 |
| 2021 | 296 | 288 | 0.49 | 0.6 | 185 / 290 | 173135 | 334891 |
| 2022 | 413 | 429 | 0.51 | 0.54 | 105 / 197 | 111845 | 236453 |
| 2023 | 368 | 578 | 0.61 | 0.54 | 157 / 300 | 82476 | 172963 |
| 2024 | 284 | 368 | 0.56 | 0.48 | 249 / 355 | 55277 | 136317 |
| 2025 | 372 | 479 | 0.56 | 0.48 | 120 / 211 | 46060 | 117060 |
| 2026 | 313 | 587 | 0.65 | 0.5 | 36 / 111 | 24113 | 71324 |
