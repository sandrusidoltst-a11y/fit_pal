# Handoff — HITL preview missing date

**Bucket**: Pipeline (graph code change required)
**Severity**: high
**Suggested fix location**: `src/agents/nodes/confirmation_node.py` (`_build_interrupt_payload`, line ~51) + `bot/gateway.py` (`_format_interrupt_value`, line ~159)
**Source run**: `tests/ux-loop/log-yesterday-and-today-then-query/runs/run1-baseline/`

## What's wrong

When a user logs a meal with a date qualifier (e.g., *"אתמול אכלתי 100 גרם חזה עוף"*), the HITL preview shown to the user includes the food name, amount, macros, servings, and category — but **no date**. The user has no signal about what date the bot has routed the log to before confirming. This becomes especially risky on edge phrasings ("yesterday", "5 days ago", "for Tuesday") where the bot's date-extraction may diverge from what the user meant.

## Evidence

T1 of the run sent: `"אתמול אכלתי 100 גרם חזה עוף"`.

Raw interrupt dict captured at `tasks[0].interrupts[0].value`:

```json
{
  "question": "רגע, בוא נוודא שתפסתי נכון לפני שאני שומר:",
  "items": [
    {
      "index": 0,
      "description": "חזה עוף — 100.0g",
      "calories": 120.0,
      "protein": 22.0,
      "carbs": 0.0,
      "fat": 2.6,
      "source": "database",
      "servings": 1.0,
      "category": "protein"
    }
  ],
  "totals": { "calories": 120.0, "protein": 22.0, "carbs": 0.0, "fat": 2.6 }
}
```

No `consumed_at` field, no date in `description`. The user is asked to confirm a payload they cannot fully verify.

The DB write actually landed correctly (`2026-05-07 12:00:00` — yesterday at noon). So the bug isn't routing — it's purely the preview being incomplete. But "trust the bot to route correctly without showing what it did" is exactly the wrong UX shape for a confirmation step.

## Suggested fix

Two-part change:

1. **Graph-side** (`src/agents/nodes/confirmation_node.py`): include the date the bot will write to in the per-item payload.
   - Read `state["log_food"]["consumed_at"]` (or fall back to today if missing).
   - Either embed it into the existing `description` string (e.g., `"חזה עוף — 100.0g (אתמול, 7.5)"`) or add a separate `consumed_at` / `date_label` field for the gateway to render explicitly.

2. **Gateway-side** (`bot/gateway.py:_format_interrupt_value`): render the new field. If the field is omitted (existing logs without dates), fall back to the current shape — don't crash on missing field.

Recommend the separate-field approach (cleaner separation): `items[].consumed_at` as ISO date, gateway formats as `"לאתמול"` / `"להיום"` / `"ל-7.5"` based on relation to today.

## Cross-scenario relevance

Any scenario that logs with a date qualifier exercises this. The current scenario (`log-yesterday-and-today-then-query`) has two such turns (T1 yesterday, T2 today). For T2 the missing date is less impactful (defaulting to today is the normal case), but for T1 it's a real UX hole.

## What's NOT this bug

- This isn't a date-extraction bug. The bot extracts "yesterday" correctly and writes the right row. Don't go looking in `prompts/input_parser.md` or `commit_node.py` for the cause — the preview rendering is the only thing wrong.
