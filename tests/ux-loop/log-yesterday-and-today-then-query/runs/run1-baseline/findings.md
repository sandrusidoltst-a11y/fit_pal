# Run 1 — baseline — Findings

**Scenario**: log-yesterday-and-today-then-query
**Date**: 2026-05-08
**Thread (baseline conversation)**: `f33691ea-2a28-4e6b-a78a-813c19146263`
**Run tag**: `baseline` — chosen at session start as observational; in-loop fixes were applied during the session (see "In-loop fixes" section below).
**Eval baseline**: experiment `ee5723d2-dc46-4011-8a98-56f6b5bdc5a7` (`input-parser-hebrew-gpt-5.4-mini-ca909381`) — read-existing mode

## Summary

Five-turn scenario covering log-to-yesterday, log-to-today, and three historical queries (yesterday, this-week, today). Baseline conversation surfaced three findings: HITL preview missing date (Pipeline → handoff), input parser failed to extract date range from `"השבוע"` (Reasoning → fixed in-loop), today-query reply omitted time-of-day (Reasoning → fixed in-loop). After two prompt commits and three iteration attempts on the time-of-day fix, both Reasoning findings now pass.

## Per-dimension verdict — baseline conversation

These verdicts are from the baseline conversation, before any in-loop fixes:

| Dimension | Verdict | Severity (on fail) | Notes |
|---|---|---|---|
| `log-correctness` | **pass** | — | T1 chicken landed at `2026-05-07 12:00:00`; T2 rice landed at `2026-05-08 08:18:28`. Both confirmed via DB query (Step 3). |
| `historical-query-retrieval` | **partial fail** | high | T3 (yesterday) ✅ pass — returned the chicken. T4 (week) ❌ fail — bot framed reply as "I don't have the full week" and asked for screenshots; trace shows query_stats sub-state was empty. T5 (today) ✅ pass — returned the rice. |
| `time-and-intake-awareness` | **fail** | high | T5 today-query checklist 3/4 — bot referenced consumed items and plan targets but did NOT reference time-of-day at all. Failed item: "references the current time-of-day". |
| `tone` | **2** (of 3) | med | Mostly natural, but `"0.3/150 גר׳"` mixes servings/grams in T2 closer (confusing); T4 asking the user to send screenshots breaks the coach illusion. T1, T3, T5 closes were appropriately conversational. |
| `language-consistency` | **pass** | — | All replies fully Hebrew. Numbers in Western digits (standard); `ג׳`/`גרם` used consistently for grams; no English nutrition vocabulary leaked. |

## Bug attributions

### Finding 1 — HITL preview missing date — bucket: Pipeline → handoff
**Status**: handoff record persisted at `handoffs/hitl-preview-missing-date.md`. Not fixed in this session — requires graph code change in `confirmation_node._build_interrupt_payload` plus a corresponding gateway formatter update.
**Where**: `src/agents/nodes/confirmation_node.py` (line ~51) + `bot/gateway.py` (`_format_interrupt_value`)
**Symptom**: T1 (and T2) interrupt dict shows item + macros + servings + category but no `consumed_at` field. User has no way to see what date the bot routed the log to before confirming.

### Finding 2 — input parser fails to extract dates from "השבוע" — bucket: Reasoning → fixed in-loop
**Status**: fixed in commit `6040628` (attempt 2 of 3).
**Where**: `prompts/input_parser.md`
**Original symptom**: T4 trace showed `last_action: QUERY_DAILY_STATS` (correct) but `query_stats: {start_date: None, end_date: None, target_date: None}` — parser correctly identified action but did not extract a week-range from the literal Hebrew word `"השבוע"`. Downstream, `stats_lookup_node` ran with no dates and `response_node` rationalized as "I don't have the full week" + asked user for screenshots.
**Fix**: added Hebrew time-range expressions (`השבוע`, `השבוע האחרון`, `החודש`, `החודש האחרון`, `N ימים אחרונים`) with explicit input → output worked examples, plus a critical-rule callout that range words must always produce `start_date` + `end_date`. Attempt 1 added rules in prose form — LLM ignored them. Attempt 2 added a worked-examples block with concrete date arithmetic and an imperative "Critical" rule — LLM followed it.
**Verification**: post-fix run trace shows `query_stats: {start_date: '2026-05-03', end_date: '2026-05-08'}` for `"מה אכלתי השבוע"`. Bot's reply enumerates both items grouped by date, no screenshot request.

### Finding 3 — today-query reply omits time-of-day reasoning — bucket: Reasoning → fixed in-loop
**Status**: fixed in commit `330a4d6` (attempt 3 of 3).
**Where**: `prompts/response_generator.md`
**Original symptom**: T5 reply referenced intake + plan targets + asked for next meal but never mentioned time-of-day. Despite the system prompt injecting Israel-local time, `response_node` didn't surface or reason about it. The scenario was specifically designed to test this.
**Fix journey**:
- Attempt 1: added a strong "Skipping this is a bug" directive to the existing budget-reasoning template. T5 passed (`"בשלב הזה זה צהריים"`) but T4 regressed — the model started compressing the historical-query reply (listed only the chicken, dropped the rice).
- Attempt 2: split the template into a today-only path and a separate historical-query path that requires enumeration. T4 enumeration returned, but T5 lost the time-of-day reference because the wording softened.
- Attempt 3 (final): kept the today/historical split AND restored strong directive language for the today branch — explicit time-bucket requirement (`"בוקר"` / `"צהריים"` / `"אחה״צ"` / `"ערב"` or quoted hour), explicit "implicit phrasing doesn't count" warning, self-check rule. Both T4 and T5 pass.
**Verification**: post-fix T5 reply: `"כרגע (11:43)... אתה בתחילת היום עם 0.3 מנות פחמימות..."` — explicit hour, time-bucket equivalent, pacing assessment, forward guidance. All four checklist items pass.

## In-loop fixes applied this session

| Commit | Finding | File touched | Attempts |
|---|---|---|---|
| `6040628` | Finding 2 (week date extraction) | `prompts/input_parser.md` | 2 of 3 |
| `330a4d6` | Finding 3 (time-of-day on today-query) | `prompts/response_generator.md` | 3 of 3 |

## Per-dimension verdict — post-fix

After both prompt fixes landed:

| Dimension | Pre-fix | Post-fix |
|---|---|---|
| `log-correctness` | pass | pass (unchanged) |
| `historical-query-retrieval` | partial fail | **pass** — T4 now enumerates both items grouped by date |
| `time-and-intake-awareness` | fail | **pass** — T5 includes explicit hour `"כרגע (11:43)"` + pacing reasoning |
| `tone` | 2 of 3 | 2 of 3 (no targeted fix attempted; some by-products noted) |
| `language-consistency` | pass | pass (unchanged) |

## Eval delta (Step 7 regression check)

Full per-metric scores live in `eval-scores.json`. Headline:

| Metric | Baseline | Final | Δ | Threshold | Status |
|---|---|---|---|---|---|
| `correct_action` | 0.9714 | 1.0000 | +2.86pp | `max -2pp` | ✅ improved |
| `correct_dates` | 0.8857 | 0.9143 | +2.86pp | `max -3pp` | ✅ improved |
| `correct_item_count` | 1.0000 | 1.0000 | 0 | `no drop` | ✅ |
| `correct_serving` | 0.8571 | 0.8286 | -2.85pp | `max -3pp` | ✅ within (variance) |
| `food_name_quality` | 1.0000 | 0.9857 | -1.43pp | `no drop` | ⚠️ technically over threshold |
| `no_consumed_at_on_query` | 1.0000 | 1.0000 | 0 | `no drop` | ✅ |
| `no_query_dates_on_log_food` | 1.0000 | 1.0000 | 0 | `no drop` | ✅ |

The single `food_name_quality` regression was investigated per-example. The failing case was `"שתי פיתות ושלוש ביצים"` — the LLM produced `food_name: "פיתה לבנה"` (white pita) instead of the baseline's `"פיתה"` (pita). Same food, slightly more specific name; both resolve to the same DB row downstream. The LLM-as-judge marked it as a partial mismatch (0.5 instead of 1.0). **Verdict: benign — accepted, not reverted.** See `eval-scores.json` for the full investigation record.

A meta-note on the eval setup: the first regression-eval run executed on `gpt-5.4-nano` (the prior local default) before the user noticed the model mismatch with the `gpt-5.4-mini` baseline. The local default was switched to `gpt-5.4-mini` and the eval re-run for an apples-to-apples comparison. Only the mini-on-mini scores are recorded in `eval-scores.json`.

## Suggested next runs

- `run2-fix-hitl-preview-date` — pick up the handoff record `handoffs/hitl-preview-missing-date.md` and address Finding 1 in code (not in this skill — requires `plan-feature` or similar planning flow). Once code lands and is merged, a follow-up live-ux-loop session would re-run the scenario and verify the HITL interrupt now shows the date.
- Future runs targeting other dimensions (`tone` polish, `0.3/150 גר׳` confusion) — separate sessions tagged appropriately.
