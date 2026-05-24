# Transcript — run1-baseline

Driven against `http://127.0.0.1:2024` (langgraph dev) on branch `ux-loop/hebrew-friend-coach-tone-2026-05-24`, against the merged prompt at `prompts/response_generator.md` (PR #35).

Dev user: `72c10336-9d61-4357-9851-20cbb4d32b1a` (`e2e@test.fitpal.bot`).

---

## Scenario 1 — empty-day-greeting
**Thread:** `a0574c74`

- **User:** `היי`
- **Bot:** היי אחי. היום על השולחן 120 גרם חלבון ו-150 גרם פחמימות. תתחיל בארוחה ראשונה שמתאימה לשעה ולעדיף חלבון, ואז נמשיך משם.

---

## Scenario 2 — normal-log-tight-confirmation
**Thread:** `bd8fa7c4`

- **User:** `אכלתי 200 גרם עוף`
- **Bot (interrupt):** רגע, בוא נוודא שתפסתי נכון לפני שאני שומר:
  - item: `חזה עוף — 200.0g` src=database cat=protein servings=2.0
- **User (resume):** `כן`
- **Bot (final):** סגור, עודכן.

---

## Scenario 3 — off-menu-plan-deviation
**Thread:** `bf8aeae8`

- **User:** `דפקתי עכשיו לאפה שווארמה`
- **Bot (interrupt):** רגע, בוא נוודא שתפסתי נכון לפני שאני שומר:
  - item: `לאפה שווארמה — 1 serving (350.0g) (משוערך)` src=estimated cat=carb
- **User (resume):** `כן`
- **Bot (final):** עודכן, אחי. סגרת 1.4 מנות פחמימה בארוחה אחת, אז שאר היום תן עדיפות לחלבון.

---

## Scenario 4 — daily-stats-time-pacing
**Thread:** `7368b3d9`

- **User:** `מה מצבי להיום?`
- **Bot:** אחי, כרגע 13:38 — אכלת 2.2 מנות חלבון ו-1.4 מנות פחמימה מתוך היעד היומי. לצהריים אתה קצת לפני הקצב בחלבון, והפחמימות כבר קיבלו בוסט רציני מארוחת הלאפה, אז שאר היום תן עדיפות לחלבון נקי.

---

## Scenario 5 — unit-mismatch-coach-retry
**Thread:** `abdce65c`

- **User:** `אכלתי כוס אחת של חזה עוף`
- **Bot (interrupt — DIVERGENCE from expected=final):** רגע, בוא נוודא שתפסתי נכון לפני שאני שומר:
  - item: `חזה עוף מבושל — 1 כוס (240.0g)` src=database cat=protein servings=3.2
- **User (resume — cleanup):** `ביטול`
- **Bot (final):** אחי, אי אפשר למדוד חזה עוף בכוסות. תזרוק לי משקל בגרמים ונסגור את זה.

*Note: divergence is real but it's because the catalog's `unit_weights` registered `כוס` for chicken breast (PR #30 multi-unit work). Scenario premise is now outdated — there's no UNIT_MISMATCH to retry from. Also notable: the bot's final reply is **verbatim** from `prompts/response_generator.md` `## Conversation Examples` #4.*

---

## Scenario 6 — food-info-qna
**Thread:** `37732545`

- **User:** `תגיד, כמה פחמימה יש באורז?`
- **Bot:** ב־158 גרם אורז מבושל יש בערך 44.2 גרם פחמימה.

*Note: bot picked 158g as the reference amount, not 100g. Likely catalog `default_serving` weight. Technically correct math but odd UX for an "X per what?" question.*

---

## Scenario 7 — weekly-synthesis
**Thread:** `f9ced12b`

- **User:** `מה אכלתי השבוע?`
- **Bot:**
  ```
  אחי, היום אכלת:
  - 200 גרם עוף
  - לאפה שווארמה
  ```

*Note: bot reframed `השבוע` (this week) → `היום` (today). DB confirms only today's 2 logs exist in the last 7 days (prior data is 5/10–5/12, 12+ days ago), so data-wise the reply isn't false — but the **scope was silently changed** and the **three-part synthesis shape was not used**.*
