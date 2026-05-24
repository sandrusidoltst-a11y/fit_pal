# Handoff F3 — Weekly query ignores historical logs

**Bucket:** pipeline
**Severity:** high
**Status:** open — needs investigation in a separate session
**Surfaced in:** `runs/run2-after-seed/transcript.md` scenario 7

---

## The bug

User asked `מה אכלתי השבוע?` ("what did I eat this week?"). Bot reported only today's logs and stated `אין לי נתונים על שאר השבוע במבנה הזה` ("I have no data for the rest of the week in this structure").

DB ground truth (verified via Supabase MCP at run2 time):

| Date | n rows |
|---|---|
| 2026-05-24 (today) | 4 |
| 2026-05-23 | 5 (seeded) |
| 2026-05-22 | 5 (seeded) |
| 2026-05-21 | 4 (seeded) |
| 2026-05-20 | 3 (seeded — light day, the anomaly we designed in) |
| 2026-05-19 | 4 (seeded) |

**19 historical rows existed across the prior 5 days. The bot acted as if they didn't.**

## User-visible transcript

```
USER: מה אכלתי השבוע?

BOT:
היום יש לי רק את ה-24/5 ברשומה, אחי:

**24/5:**
- 200 גרם עוף
- 200 גרם עוף
- לאפה שווארמה
- לאפה שווארמה

אין לי נתונים על שאר השבוע במבנה הזה.
```

The duplicates ("200 גרם עוף" × 2, "לאפה שווארמה" × 2) are real — both scenarios 2 and 3 were run twice (run1 + run2), producing 4 rows for 5/24. **That part is correct.** The "no data for the rest of the week" claim is the bug.

## Trace excerpt

The `## Today's Log` section of the SystemMessage delivered to the LLM **only contained today's 4 entries.** The seeded historical days were NOT present in the system prompt at all. So from the LLM's perspective, the bot truthfully reported what it could see.

```
## Today's Log
- 2026-05-24T13:37:47.794755+03:00 — 200 גרם עוף — 240 kcal, 44.0g protein, 0.0g carbs, 5.2g fat [protein,lean]
- 2026-05-24T14:48:00.785965+03:00 — 200 גרם עוף — 240 kcal, 44.0g protein, 0.0g carbs, 5.2g fat [protein,lean]
- 2026-05-24T16:37:51+03:00 — לאפה שווארמה — 825 kcal, 39.0g protein, 71.0g carbs, 43.0g fat [carb]
- 2026-05-24T17:48:03+03:00 — לאפה שווארמה — 825 kcal, 39.0g protein, 71.0g carbs, 43.0g fat [carb]
```

This is the `daily_log_today` context field (loaded by the `load_daily_context` node — fresh per message, today's logs only).

## Where the bug lives

Three plausible locations, none yet confirmed without deeper trace inspection:

1. **`prompts/input_parser.md`** — date-range extraction for `השבוע`. The parser may be routing all queries to `QUERY_DAILY_STATS` without extracting a multi-day `range_start_date` / `range_end_date`, defaulting to today.
2. **`src/agents/nodes/stats_node.py`** — even if the parser emits a multi-day range, `stats_node` may not invoke `query_food_logs` with that range. Or it may invoke it but not propagate the result into `response_node`'s context.
3. **`src/services/daily_log_service.py:query_food_logs`** — the tool itself may have a bug in the date-range filter (timezone, off-by-one, etc.).

Suggested investigation order: (1) → (2) → (3). The parser is the most upstream and the easiest to verify with a trace inspection.

## Cross-scenario pattern check

In run1 (before historical data was seeded), scenario 7 also reframed to "today" with no synthesis. So the failure mode predates the historical-data state. This isn't a "the data has problems" bug — it's a "the bot can't fetch historical data" bug.

## Suggested fix path

1. Fetch a trace of scenario 7 (thread_id available in `transcript.md` for run2 if needed; or run a fresh `מה אכלתי השבוע?` query against the dev server).
2. Inspect `input_parser`'s output for the message. Verify whether `range_start_date` + `range_end_date` were extracted.
3. If they were extracted: trace whether `stats_node` invoked `query_food_logs` with those dates.
4. If `query_food_logs` was invoked: verify the SQL produced the right window.
5. Either fix the upstream miss or wire the result into `response_node`'s context.

## Not in scope for this handoff

- Whether to **also** load historical logs as part of `load_daily_context` (vs. only on stats queries). Architectural call.
- The `weekly-synthesis-shape` dimension in `expectations.md` checks the reply's *shape* (synthesis line + items by date + closing line). Even after F3 is fixed, that shape rule may need its own iteration.

## Files most likely to need edits

- `prompts/input_parser.md`
- `src/agents/nodes/stats_node.py`
- `src/services/daily_log_service.py`
- Possibly `src/agents/state.py` (if a new state field for `query_logs` needs adding)
