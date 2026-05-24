# Findings — run1-baseline

**Status:** PARTIAL — loop aborted at Step 6 (routing findings). The dev user has no `user_profiles` row, which means several scenarios were run against unrealistic context. The decision was to stop, seed a plan, and re-run as `run2-<tag>` rather than score on noisy state.

**Session branch:** `ux-loop/hebrew-friend-coach-tone-2026-05-24`

## Summary

| # | Scenario | Bot reply (short) | Status |
|---|---|---|---|
| 1 | empty-day-greeting | "היי אחי. היום על השולחן 120 גרם חלבון…" | invented targets |
| 2 | normal-log | "סגור, עודכן." | clean pass |
| 3 | off-menu-deviation | "עודכן, אחי. סגרת 1.4 מנות פחמימה… שאר היום תן עדיפות לחלבון." | no deviation flag + rest-of-day prescription |
| 4 | daily-stats | "אחי, כרגע 13:38 — אכלת 2.2 מנות חלבון ו-1.4 מנות פחמימה מתוך היעד היומי…" | strong time-bucket + pacing, but invented target |
| 5 | unit-mismatch | bot accepted `כוס` → went to HITL preview (expect: final) | scenario premise outdated by PR #30 |
| 6 | food-info-qna | "ב־158 גרם אורז מבושל יש בערך 44.2 גרם פחמימה." | pass, odd serving size |
| 7 | weekly-synthesis | "אחי, היום אכלת:" + flat list (only today's items) | scope reframed, no synthesis shape |

## Critical cross-cutting finding

**The bot invents plan context when none exists.** With `user_profiles` empty for the dev user, the bot still produced replies referencing `120 גרם חלבון / 150 גרם פחמימות`, `מתוך היעד היומי`, `1.4 מנות פחמימה`, and made coaching recommendations. This violates:

- `prompts/response_generator.md` `## Hard rules §1`: *"Never invent numbers. Only reference calories, macros, or targets that appear in the Context JSON or the plan."*
- `prompts/response_generator.md` `## Read the plan before responding`: *"If no plan is injected, respond conversationally. Don't coach against rules you can't see."*

The serving math itself (2.2 protein servings from 200g chicken @ 44g) is correct — that's from today's log. But the "out of daily target" framing and any rest-of-day guidance is hallucinated because no plan exists in context.

**Bucket:** REASONING (right context arrived — empty plan — bot ignored the empty-plan rule).
**Severity:** high (real users in a no-profile state would get fabricated coaching).
**Suggested fix location:** `prompts/response_generator.md` — strengthen the empty-plan rule, add a `## Empty plan` worked example showing the bot replying conversationally without invented numbers.

**Caveat:** this finding is only directly testable if we keep the dev user without a profile. After seeding (planned next step), we won't be able to re-test this dimension on `run2`. If we want regression coverage on no-plan state, it needs its own scenario / dataset / test path.

## Per-scenario notes

### Scenario 3 — off-menu plan deviation (predicted failure)
Even ignoring the invented-target problem, the reply fails the `plan-deviation-flag` checklist:
- (a) Deviation explicitly named? **NO** — no `"לא מהתפריט"` / `"לא באופציות"` mention.
- (b) One informational note about the food itself? **NO** — no description of `שווארמה` as a food (fatty + carb-heavy etc.).
- (c) No rest-of-day prescription? **FAIL** — `"שאר היום תן עדיפות לחלבון"` is a prescription.

This is the predicted baseline failure documented in `scenarios.md`. The prompt has no plan-deviation rule. Fix path is to add a `## Plan deviation` section + a worked example to `## Conversation Examples`.

### Scenario 5 — outdated scenario premise
PR #30 (multi-unit weights + synonyms) added a `כוס` mapping for chicken breast. `אכלתי כוס אחת של חזה עוף` no longer triggers `UNIT_MISMATCH` — it resolves to 240g. The scenario's `expect: final` (because UNIT_MISMATCH retry is a `final` reply path) is therefore wrong.

**Resolution:** update `scenarios.md`. Either change the test food to one without a `כוס` mapping (e.g., `חזה הודו` if not in catalog), or replace with a different unit-mismatch case (e.g., a food without `unit_weights` entries). Not a bot bug.

Also notable: after the cleanup `ביטול` resume, the bot's final reply was **verbatim** from `prompts/response_generator.md` `## Conversation Examples` #4. Possible example overfit — worth watching but inconclusive from one data point.

### Scenario 7 — weekly scope reframed
User asked `מה אכלתי השבוע?`. Bot replied with `היום אכלת:` and listed only today's 2 items.

DB confirms only 2 items in last 7 days (both today's, both from this session). So data-wise the listing isn't false — but:
- The scope was silently reframed from "this week" to "today" — user wanted weekly, got daily.
- No synthesis line, no date grouping, no closing line (the three-part shape).

Likely buckets:
- **Pipeline** if the input parser routed `השבוע` to a today-only `QUERY_DAILY_STATS` instead of a multi-day range.
- **Reasoning** if the parser correctly extracted a 7-day range but `response_node` collapsed empty days and reframed.

Trace inspection would tell us which. Deferred to a follow-up session (or to run2 if we ensure prior-week data is present).

## Decision

User chose to stop, seed a nutrition plan for the dev user, then re-run as `run2`. The aborted state is preserved here for reference; no in-loop prompt fixes were applied this run.

## What's preserved
- `transcript.md` — full per-scenario conversations
- `db-snapshot.md` — DB state at time of run
- (this file) `findings.md` — partial findings + critical cross-cutting issue
- Per-scenario raw JSON at `$CLAUDE_JOB_DIR/scenarios/` (job-local, not committed)
