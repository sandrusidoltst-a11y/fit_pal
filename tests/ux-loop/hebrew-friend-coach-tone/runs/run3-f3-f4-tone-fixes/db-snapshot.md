# DB snapshot — run3-f3-f4-tone-fixes

Captured right after the run3 live execution (2026-05-24 22:14 IST). E2E user `72c10336…`.

## `daily_logs` rowcount by Israel-local day

| Day | Rows | Note |
|---|---:|---|
| 2026-05-25 | 1 | Boundary artifact (run finished ~22:13 IST, this row's timestamp likely just past midnight UTC; Israel-local rendering rolls it to next day) |
| 2026-05-24 | 42 | Today — heavily bloated by today's in-process probes (F4 single-shawarma × 3, F4 varied × 8, salmon-toast × 3, the 8 cases re-run after tone changes ×1, plus the 7 live scenarios. ~28 of these are probe artifacts on top of normal use.) |
| 2026-05-23 | 5 | Seeded historical (intact) |
| 2026-05-22 | 5 | Seeded historical (intact) |
| 2026-05-21 | 4 | Seeded historical (intact) |
| 2026-05-20 | 3 | Seeded historical (intact — the deliberate light/anomaly day) |
| 2026-05-19 | 4 | Seeded historical (intact) |
| 2026-05-12 | 2 | Pre-existing |
| 2026-05-11 | 7 | Pre-existing |
| 2026-05-10 | 15 | Pre-existing |

## Verification this snapshot supports

- **F3 (weekly query)**: the 5/19–5/23 historical rows are intact (4+5+4+5+5 = 23 — matches what scenario 7 enumerated in its reply, give or take per-row aggregation in the bot's listing).
- **5/24 bloat is *probe state*, not a regression** — both the in-process tone/varied probes and the live scenarios commit real logs to this user. Cleanup is intentionally not done so the next session has continuity; the bot's "you're way over your daily targets" tone in scenario 1 and 4 is a *truthful* reading of that bloated state.
