# DB Snapshot — run2-after-seed

Captured immediately after run2 completed.

## Setup performed between runs

```sql
-- INSERT user_profiles row (none existed before — confirmed by run1 db-snapshot)
INSERT INTO user_profiles (user_id, name, age, gender, height_cm, nutrition_plan)
VALUES ('72c10336-9d61-4357-9851-20cbb4d32b1a', 'Dolev', 23, 'male', 170.0, <plan_md>);

-- 21 historical daily_logs rows seeded across 5 days (5/19–5/23)
-- Done via /Users/dolevsa/.claude/jobs/b3484ed1/seed_history.py
-- Pattern: 4 days roughly on-target, Wed 5/20 is a "light day" (P=26g, C=39g vs ~100g+ elsewhere)
```

The seed script lives in the job dir (not committed). Day-by-day:

| Date | Day type | Items | Protein g | Carbs g | Cal |
|---|---|---|---|---|---|
| 5/23 | Sat training | 5 | 122.1 | 127.6 | 1239 |
| 5/22 | Fri rest | 5 | 101.6 | 95.2 | 999 |
| 5/21 | Thu training | 4 | 109.7 | 100.0 | 988 |
| 5/20 | Wed rest (LIGHT) | 3 | **26.4** | **39.2** | 389 |
| 5/19 | Tue training | 4 | 112.0 | 101.6 | 1027 |

## Today's logs (5/24)

```sql
SELECT timestamp::text, amount_g, original_text
FROM daily_logs
WHERE user_id = '72c10336-9d61-4357-9851-20cbb4d32b1a'
  AND DATE(timestamp AT TIME ZONE 'Asia/Jerusalem') = '2026-05-24'
ORDER BY timestamp;
```

| timestamp | amount_g | text |
|---|---|---|
| 10:37 UTC | 200 | `200 גרם עוף` (run1) |
| 11:48 UTC | 200 | `200 גרם עוף` (run2) |
| 13:37 UTC | 350 | `לאפה שווארמה` (run1) |
| 14:48 UTC | 350 | `לאפה שווארמה` (run2) |

4 rows for today total. Scenario 7's bot reply correctly listed these (with duplicates) — *not* a hallucination; the duplicates are real DB rows. But the bot's claim "no data for the rest of the week" is wrong vs the seed.

## Profile state

```sql
SELECT name, age, gender, height_cm, length(nutrition_plan) AS plan_chars
FROM user_profiles
WHERE user_id = '72c10336-9d61-4357-9851-20cbb4d32b1a';
```

| name | age | gender | height_cm | plan_chars |
|---|---|---|---|---|
| Dolev | 23 | male | 170.0 | 12,127 |
