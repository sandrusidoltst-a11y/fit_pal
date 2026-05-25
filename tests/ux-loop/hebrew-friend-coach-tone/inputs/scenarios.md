# Scenarios — Hebrew Friend-Coach Tone

Scenarios for the `hebrew-friend-coach-tone` UX loop. Each scenario exercises one reply mode from `prompts/response_generator.md` against its Hebrew worked example, to validate that the persona + tight-confirmation rules + time/budget reasoning actually land in real conversation.

Dimensions referenced below are defined in `expectations.md` in the same folder.

---

## Scenario: empty-day greeting
**Goal:** when no logs exist for today, the bot should open with coach voice — greet, reference today's target from the plan, and invite the first meal aligned to time-of-day.
**Dimensions:** tone, language-consistency, address-term, time-awareness, plan-reference

1. User: "היי"
   Probes for: does the bot open as a coach (אחי), reference today's protein/carb targets from the plan, and condition on `Current time:` (fasting window if before wake+3h, otherwise invite a protein-forward meal)?
   *(expect: final)*

---

## Scenario: normal log — tight confirmation default
**Goal:** a routine food log should commit through HITL and produce a default tight confirmation ("סגור" / "עודכן"), with no extra commentary when no budget-line trigger fires.
**Dimensions:** tight-confirmation-default, tone, language-consistency

1. User: "אכלתי 200 גרם עוף"
   Probes for: the bot's post-commit final reply (the AI message after the resume). Should be 1-3 words, no macros, no budget line — none of the three Tight-confirmation triggers (80% target, 3+ servings, free-cal cap) fire on a single 200g chicken log against a typical clean-bulk plan.
   *(expect: interrupt)*
   Resume: "כן"
2. *(no User turn — the post-commit final reply is the test target)*

---

## Scenario: off-menu food log — plan-deviation flag
**Goal:** when the user logs a food that's not in the plan's Protein Options or Carb Options lists, the bot should explicitly flag it as not from the plan and add one short informational remark about the food itself — without prescribing how to adjust the rest of the day.
**Dimensions:** plan-deviation-flag, tone, language-consistency, address-term

1. User: "דפקתי עכשיו לאפה שווארמה"
   Probes for: post-commit final reply after the resume. Should hit three checks:
   (a) **Flag the deviation explicitly** — reply names that the food isn't from the plan ("זה לא מהתפריט" / "שווארמה לא באופציות").
   (b) **One informational note about the food itself** — describes what the food *is* in plan-relevant terms ("חלבון שמן, לא רזה", "פחמימה + שומן ביחד"). NOT a substitution suggestion, NOT a rest-of-day guidance.
   (c) **No rest-of-day prescription** — any pattern like "בשאר היום ניצמד ל...", "מעכשיו תאכל...", "תפצה עם..." is a failure.

   Note: the current prompt does NOT have a plan-deviation rule (only numeric budget triggers). This scenario is expected to FAIL on baseline; the in-loop fix adds the rule to `prompts/response_generator.md`.

   *(expect: interrupt)*
   Resume: "כן"
2. *(no User turn — the post-commit final reply is the test target)*

---

## Scenario: daily stats query — time + pacing
**Goal:** when asked about today's status, the bot must compute remaining = target − consumed, explicitly name the time bucket (or quote the hour), and add a pacing assessment grounded in that bucket.
**Dimensions:** budget-reasoning, time-awareness, plan-reference, tone, language-consistency, address-term

1. User: "מה מצבי להיום?"
   Probes for: did the bot (a) name a time bucket explicitly — "בוקר" / "צהריים" / "אחה״צ" / "ערב" or a quoted hour ("כרגע 11:30"), and (b) say something about pacing relative to that bucket (on pace / behind / ahead)? Implicit "בהמשך היום" does NOT count. A reply that enumerates intake + targets without naming the bucket is a budget-reasoning failure.
   *(expect: final)*

---

## Scenario: weird-unit input — safety-net estimate + HITL correction
**Goal:** when the user gives a semantically-mismatched unit (`כוס ביצים`), the bot does NOT fail. The parser emits a best-guess gram total via the `amount_g` safety net; the bot HITL-previews that estimate marked `(משוערך)`; the user corrects it via natural language; the bot reconfirms.
**Dimensions:** weird-unit-hitl-correction, tone, language-consistency

1. User: "אכלתי כוס ביצים"
   Probes for: `ביצה` has `unit_weights={"piece": 50}` (no `כוס` mapping, verified vs catalog 2026-05-24). Parser-side, `prompts/input_parser.md` requires `amount_g` for any non-gram unit, so the parser emits something like `{count: 1, unit: "cup", amount_g: 240}`. Bot should return a HITL `interrupt` whose item description shows the gram estimate plus `(משוערך)` — NOT a `final` reply, NOT an English `"Unit mismatch:"` error, NOT an apology.
   *(expect: interrupt)*

2. User (correction in natural Hebrew): "לא, התכוונתי 2 ביצים"
   Probes for: bot re-parses the corrected input as `2 piece` of egg → catalog hit → ~100g (2 × 50g). Returns another HITL `interrupt` with the corrected item shape. Verifies the safety-net / HITL flow IS the correction mechanism (no separate retry routing needed).
   *(expect: interrupt, then resume: "כן")*

*Background — why this design and not a "Unit mismatch:" failure path: as of 2026-05-24 the response prompt previously referenced a `"Unit mismatch:"` error string, but that string is never emitted by any code path. The resolver chain in `src/services/food_service.py:resolve_amount_g` has a `llm_estimated_amount_g` step that always succeeds when the parser fills `amount_g` (which it always does by contract). The architectural decision is: never block on a unit resolution failure — surface the safety-net estimate via HITL and let the user correct in conversation. This scenario tests that contract. The dead `UNIT_MISMATCH` references were removed from `prompts/response_generator.md` (lines 24 + Hard rule §6) in the same change that landed this scenario.*

---

## Scenario: food info Q&A — direct answer, no logging language
**Goal:** when the user asks a nutrition question (not logging), the bot should answer with macros only and NOT use any logging language ("נרשם", "תרצה לרשום", "האם אכלת").
**Dimensions:** tone, language-consistency, no-logging-language-on-qna

1. User: "תגיד, כמה פחמימה יש באורז?"
   Probes for: 1-2 sentence answer with the macro value; no logging language; no "תרצה לרשום?"; matches the user's language (full Hebrew).
   *(expect: final)*

---

## Scenario: historical / weekly query — synthesis on top + items + closing
**Goal:** for a multi-day/weekly query, the bot should open with a 1-2 sentence pattern synthesis ("השבוע: חלבון יציב ב-5 ימים, פחמימות התפזרו פחות טוב"), enumerate items grouped by date, then close with the one thing to tighten — not raw enumeration only and not synthesis without the data.
**Dimensions:** weekly-synthesis-shape, tone, language-consistency, address-term

1. User: "מה אכלתי השבוע?"
   Probes for: structure of the reply — does it open with a synthesis line about patterns (not a list)? Does it then enumerate items grouped by date (not summarize "you had chicken, rice, etc.")? Does it close with a 1-sentence "one thing to tighten" remark? An empty-result case (no rows returned) should be stated plainly with no screenshot request.
   *(expect: final)*
