# Transcript — run2-after-seed

Driven against `http://127.0.0.1:2024` after seeding the dev user profile + Clean Bulk Plan (12,127 chars) and 5 days of historical logs (5/19–5/23, 21 rows; one anomaly day on 5/20 — light intake).

Branch `ux-loop/hebrew-friend-coach-tone-2026-05-24`. Same merged prompt as run1.

---

## Scenario 1 — empty-day-greeting
**Thread:** `(run2)`

- **User:** `היי`
- **Bot:** היי אחי. היום כבר סגרת 2.2 מנות חלבון ו-1.4 מנות פחמימה, אז החלבון עוד סביר והפחמימות כבר נכנסו חזק בארוחה אחת. עכשיו תישאר נקי להמשך היום.

*Note: not really an "empty-log opener" anymore — today's DB already has 4 logs from run1 + this session. Bot correctly noticed and switched modes. Reasonable behavior given state.*

---

## Scenario 2 — normal-log-tight-confirmation
- **User:** `אכלתי 200 גרם עוף`
- **Bot (interrupt):** רגע, בוא נוודא שתפסתי נכון לפני שאני שומר:
  - item: `חזה עוף — 200.0g` src=database cat=protein servings=2.0
- **User (resume):** `כן`
- **Bot (final):** עודכן, אחי. סגרת עכשיו 4.4 מנות חלבון מתוך 6, ועוד 1.4 מנות פחמימה מתוך 3 להיום.

*REGRESSION vs run1: run1 said "סגור, עודכן" (perfect tight default). Run2 added a budget line even though no numeric trigger was justified (4.4/6 protein = 73%, under 80%; 1.4 carb servings < 3). The bot is also reporting **wrong targets** — plan says 7 protein servings / 5–6 carb servings, bot says 6 / 3.*

---

## Scenario 3 — off-menu-plan-deviation
- **User:** `דפקתי עכשיו לאפה שווארמה`
- **Bot (interrupt):** רגע, בוא נוודא שתפסתי נכון לפני שאני שומר:
  - item: `לאפה שווארמה — 1 serving (350.0g) (משוערך)` src=estimated cat=carb
- **User (resume):** `כן`
- **Bot (final):** עודכן, אחי. סגרת כבר 2.8 מנות פחמימה ו-4.4 מנות חלבון היום.

*Improvement vs run1: dropped the rest-of-day prescription. But still no plan-deviation flag — no "לא מהתפריט" / "לא באופציות". Plus another budget line on a non-triggering log (same regression as #2).*

---

## Scenario 4 — daily-stats-time-pacing
- **User:** `מה מצבי להיום?`
- **Bot:** אחי, כרגע 88.0 גרם חלבון מתוך 120 ו-142.0 גרם פחמימות מתוך 150. השעה 14:48 — אתה עדיין בצהריים, אז אתה קצת מאחור בחלבון והפחמימות כמעט סגורות להיום.

*Time-awareness still strong: quoted hour ("14:48") + bucket ("בצהריים") + pacing ("קצת מאחור בחלבון"). But **targets are wrong**: plan says 140g protein, bot says 120g; plan says 250–300g carbs, bot says 150g. And **142g carbs reported** doesn't match DB (today's logs total 71g carbs). Plan-reference is broken in a way that wasn't broken in run1.*

---

## Scenario 5 — unit-mismatch-coach-retry
- **User:** `אכלתי כוס ביצים`
- **Bot (interrupt — DIVERGENCE from expected=final):** רגע, בוא נוודא שתפסתי נכון לפני שאני שומר:
  - item: `ביצים — 1 כוס (240.0g) (משוערך)` src=estimated cat=protein

*The food got LLM-estimated (plural "ביצים" not in catalog, only singular "ביצה"). The estimation path accepted "1 כוס" → 240g, so no UNIT_MISMATCH fired. The scenario STILL can't test the retry path — the issue isn't the food, it's that the parser+estimator have a safety net that absorbs unit mismatches via `amount_g`. Fixing this scenario probably requires a food that's in the catalog with no `unit_weights` AND no `כוס` synonym (e.g., `חזה הודו` whose `unit_weights` is `{}`).*

Resume cleanup was not attempted in run2 (was attempted in run1).

---

## Scenario 6 — food-info-qna
- **User:** `תגיד, כמה פחמימה יש באורז?`
- **Bot:** ב־158 גרם אורז מבושל יש בערך 44.2 גרם פחמימה.

*Same as run1: bot picks 158g as the reference amount. Catalog default-serving artifact, technically correct.*

---

## Scenario 7 — weekly-synthesis
- **User:** `מה אכלתי השבוע?`
- **Bot:**
  ```
  היום יש לי רק את ה-24/5 ברשומה, אחי:

  **24/5:**
  - 200 גרם עוף
  - 200 גרם עוף
  - לאפה שווארמה
  - לאפה שווארמה

  אין לי נתונים על שאר השבוע במבנה הזה.
  ```

*The items listed for 5/24 are real (DB confirms 4 rows after running scenarios 2+3 twice across runs). BUT: bot claimed "no data for the rest of the week" while DB has **19 rows for 5/19–5/23 from the seed**. This is a pipeline-level issue — the bot is reading only today's logs (`daily_log_today` context field) and either isn't invoking `query_food_logs` for the multi-day range, or the parser routed `השבוע` to a today-only stats query.*
