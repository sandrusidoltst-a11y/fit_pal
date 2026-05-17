# fix(parser): "last N days" / "אחרון" range queries exclude today

## Why

Hebrew input-parser eval flagged 3/35 failures on `correct_dates`, all on
"אחרון" range queries:

- `סטטיסטיקות של 3 ימים אחרונים`
- `מה אכלתי בשבוע האחרון`
- `כמה גרם חלבון אכלתי בממוצע בשבוע האחרון`

Investigation showed the parser was doing exactly what the prompt said
(today-2 → today, today-6 → today — "inclusive of today"). The eval expected
otherwise, but its own sentinels were off-by-one and inconsistent with
themselves (`days=3` start paired with `TODAY` end = 4-day span).

Product call: "if I ask about last week, today shouldn't be included." So
the prompt was wrong, not the parser. "אחרון/last/past" phrases describe a
closed past window ending yesterday.

## What changed

### `prompts/input_parser.md`

Range section restructured into two explicit families:

- **Current period — INCLUDES today** — no qualifier:
  `השבוע` / `this week` → Sunday-of-current-week → today.
  `החודש` / `this month` → 1st-of-current-month → today.
- **Past period — EXCLUDES today, rolling N days ending yesterday** — uses
  "last / past / אחרון":
  `3 ימים אחרונים` → today-3 → today-1.
  `השבוע האחרון` / `last week` → today-7 → today-1.
  `החודש האחרון` / `last month` → today-30 → today-1.

Worked examples updated to today = 2026-05-16 (Saturday), now covering both
families side-by-side. Critical-rule line gains an emphasis clause:
"אחרון/last/past phrases NEVER include today — end_date must be yesterday,
not today."

### `notebooks/evals/eval_input_parser_hebrew.py`

Three `end_date: "TODAY"` → `"YESTERDAY"` on the three failing examples.
Start-date sentinels (`RELATIVE_3_DAYS_AGO = today-3`,
`RELATIVE_7_DAYS_AGO = today-7`) were already correct under the new
semantics; only the end-date was wrong.

## Validation

| Dimension | Before | After |
|---|---|---|
| correct_action | 100% | 100% |
| correct_item_count | 100% | 100% |
| food_name_quality | 100% | 100% |
| no_consumed_at_on_query | 100% | 100% |
| no_query_dates_on_log_food | 100% | 100% |
| **correct_dates** | **91%** | **100%** ✅ |
| correct_serving | 90% | 87% (run-to-run variance; serving path untouched) |

LangSmith experiment: `input-parser-hebrew-gpt-5.4-mini-abb49abc`.

## What's next

- Investigate the serving cluster — 4–5 short natural-language inputs
  (`מעדן חלבון`, `חצי בננה`, `שתי פרוסות גבינה עם מעדן חלבון`,
  `פסטה עם גבינה לצהריים`, `אכלתי כוס אורז`) consistently miss. Likely a
  mix of parser-side default-serving handling and downstream `resolve_amount_g`
  behavior — needs per-row trace inspection to split prompt vs. resolver bugs.
- No unit-test exposure for these range phrases (`tests/unit/test_input_parser.py`
  doesn't cover them); LangSmith eval is currently the only regression guard.
  Worth adding a unit-level guard if we touch the date logic again.
