# Run 1 — baseline — DB snapshot

Captured during Step 3 (DB verification) after the conversation completed. All queries scoped to dev user `72c10336-9d61-4357-9851-20cbb4d32b1a`.

## Pre-run state

Before the run started, a cleanup `DELETE` was applied to remove polluting rows from the past week (2026-05-01 → 2026-05-08). The dev user retained 56 rows from earlier April dates (untouched) and zero rows in the target date range.

## Post-run state — yesterday (2026-05-07)

```sql
SELECT timestamp, food_id, amount_g, calories, protein, carbs, fat
FROM daily_logs
WHERE user_id = '72c10336-9d61-4357-9851-20cbb4d32b1a'
  AND date(timestamp) = '2026-05-07'
ORDER BY timestamp;
```

| timestamp | food_id | amount_g | calories | protein | carbs | fat |
|---|---|---|---|---|---|---|
| `2026-05-07 12:00:00+00:00` | `8f2b2cad-3c1c-46d7-ac22-3b7372f6c556` | 100.0 | 120.0 | 22.0 | 0.0 | 2.6 |

✅ **Exactly one row, on the right date.** Bot defaulted timestamp to noon when the user said "אתמול" without a specific time.

## Post-run state — today (2026-05-08)

```sql
SELECT timestamp, food_id, amount_g, calories, protein, carbs, fat
FROM daily_logs
WHERE user_id = '72c10336-9d61-4357-9851-20cbb4d32b1a'
  AND date(timestamp) = '2026-05-08'
ORDER BY timestamp;
```

| timestamp | food_id | amount_g | calories | protein | carbs | fat |
|---|---|---|---|---|---|---|
| `2026-05-08 08:18:28.528529+00:00` | `d0d3e823-8cb6-405d-98ce-b84736ff3776` | 50.0 | 65.0 | 1.35 | 14.0 | 0.15 |

✅ **Exactly one row, on the right date.** Timestamp matches when the user message was sent.

## Cross-checks against bot claims

| Bot claimed | DB confirms | Match |
|---|---|---|
| T1 closer: "אתמול נכנס ללוג שלך 100 גרם חזה עוף" | Row exists 2026-05-07 with amount=100, P=22 | ✅ |
| T2 closer: "נרשם לך 50 גרם אורז מבושל היום" | Row exists 2026-05-08 with amount=50, C=14 | ✅ |
| T3 reply: "אתמול נכנס ללוג שלך 100 גרם חזה עוף (120 קק״ל, 22 גרם חלבון)" | Row matches values | ✅ |
| T4 reply enumerated: "היום: 50 גרם אורז · אתמול: 100 גרם חזה עוף" | Both rows present in DB | ✅ on data, ⚠️ T4 reply *also* claimed "I don't have full week" which contradicts the DB having the data — this is the Pipeline bug captured in Finding 2 |
| T5 reply: "היום נכנס ללוג שלך רק 50 גרם אורז" | Row matches | ✅ |

## Conclusion

DB writes are correct. The `log-correctness` dimension passes for both logged turns. The Pipeline bug surfaced in T4 is *not* a write-side issue — it's a read-side bug in `query_stats` date extraction.
