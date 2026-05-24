# DB Snapshot — run1-baseline

Queries scoped to dev user `72c10336-9d61-4357-9851-20cbb4d32b1a`. Captured immediately after the 7-scenario run completed.

## Critical finding

```sql
SELECT * FROM user_profiles WHERE user_id = '72c10336-9d61-4357-9851-20cbb4d32b1a';
-- returns [] — NO row exists
```

The dev user has **no `user_profiles` row at all**: no plan, no name, no gender, no targets, no anything. Yet the bot generated confident replies referencing plan targets (see `findings.md` and `transcript.md`). This invalidates several scenarios' premises.

## Logs committed during the run

```sql
SELECT timestamp, amount_g, calories, protein, carbs, fat, original_text
FROM daily_logs
WHERE user_id = '72c10336-9d61-4357-9851-20cbb4d32b1a'
  AND timestamp >= NOW() - INTERVAL '2 hours';
```

| timestamp | amount_g | cal | P | C | F | original_text |
|---|---|---|---|---|---|---|
| 2026-05-24 13:37:51+00 | 350 | 825 | 39 | 71 | 43 | `לאפה שווארמה` |
| 2026-05-24 10:37:47+00 | 200 | 240 | 44 | 0 | 5.2 | `200 גרם עוף` |

Scenario 2's chicken and scenario 3's lafa shawarma both committed correctly. Scenario 5's `כוס חזה עוף` was cancelled via `ביטול` resume — DB confirms no row from it.

## Recent log activity (14 days)

```sql
SELECT DATE(timestamp AT TIME ZONE 'Asia/Jerusalem') AS d, COUNT(*) AS n
FROM daily_logs
WHERE user_id = '72c10336-9d61-4357-9851-20cbb4d32b1a'
  AND timestamp >= NOW() - INTERVAL '14 days'
GROUP BY 1 ORDER BY d DESC;
```

| date | n |
|---|---|
| 2026-05-24 | 2 (this run) |
| 2026-05-12 | 2 |
| 2026-05-11 | 7 |
| 2026-05-10 | 15 |

The "last 7 days" window (2026-05-17 → 2026-05-24) contains only today's 2 logs. Scenario 7's weekly synthesis was therefore tested against an effectively single-day window — partial cause of the bot's "היום אכלת" reframe (but the scope re-interpretation is still a finding regardless of data density).
