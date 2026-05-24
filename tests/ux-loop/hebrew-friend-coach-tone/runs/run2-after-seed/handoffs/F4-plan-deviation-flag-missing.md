# Handoff F4 — Plan-deviation flag missing

**Bucket:** reasoning (prompt-side)
**Severity:** medium
**Status:** open — predicted baseline failure, prompt section needs to be added
**Surfaced in:** `runs/run2-after-seed/transcript.md` scenario 3
**Originally documented as expected in:** `inputs/scenarios.md` (scenario 3 note)

---

## The gap

When a user logs a food that is **not in the plan's Protein Options or Carb Options lists**, the bot should:

1. **Flag the deviation explicitly** — e.g. `"לא מהתפריט"` / `"לא באופציות"`.
2. **Add one informational note about the food itself** — what it is in plan-relevant terms (e.g. `"חלבון שמן, לא רזה"`, `"פחמימה + שומן ביחד"`).
3. **NOT prescribe rest-of-day adjustments** — patterns like `"בשאר היום ניצמד ל..."` are forbidden.

The current `prompts/response_generator.md` has no rule for this. The bot just reports macros normally for off-menu foods.

## User-visible transcript

```
USER: דפקתי עכשיו לאפה שווארמה

BOT (HITL preview):
  item: לאפה שווארמה — 1 serving (350.0g) (משוערך) src=estimated cat=carb

USER (resume): כן

BOT (final): עודכן, אחי. סגרת כבר 2.8 מנות פחמימה ו-4.4 מנות חלבון היום.
```

The bot:
- Acknowledged the commit ✓
- Reported daily totals (debatable — see F2 discussion in `findings.md`, but with real profile injected this stayed silent in V2 reruns)
- Did NOT flag that שווארמה isn't on the plan's options lists ✗
- Did NOT add an informational note about the food ✗

(In run2, the bot also slipped in a rest-of-day prescription on this scenario. After the F1 test-infra fix and a few V2 reruns of S4, the prescription leakage seems to come and go — borderline tone issue, not the deviation-flag gap.)

## Why this is a baseline gap (not a regression)

This was flagged in `inputs/scenarios.md` scenario 3's note before run1 even started:

> Note: the current prompt does NOT have a plan-deviation rule (only numeric budget triggers). This scenario is expected to FAIL on baseline; the in-loop fix adds the rule to `prompts/response_generator.md`.

Confirmed in both run1 (no profile) and run2 (with profile). The fix is to add the rule.

## Suggested prompt change

Add a new section to `prompts/response_generator.md` between `## Tight confirmation` and `## Nutrition Q&A`:

```markdown
## Plan deviation

When the user logs a food that is NOT in the plan's `Protein Options` or `Carb Options` lists:

1. **Flag the deviation explicitly.** One short line: `"שווארמה לא מהאופציות בתפריט"` / `"זה לא מהתוכנית"` / equivalent.
2. **Add one informational note about the food itself.** Describe what the food *is* in plan-relevant terms (`"חלבון שמן, לא רזה"`, `"פחמימה + שומן ביחד"`). NOT a substitution suggestion. NOT a quantity/frequency note.
3. **Do NOT prescribe rest-of-day adjustments.** No `"בשאר היום ניצמד ל..."`, `"מעכשיו תאכל..."`, `"תפצה עם..."`.

Identification of off-menu foods: check the food's `name_he` / `name_en` against the plan's Protein Options + Carb Options sections (literal string match is enough — the plan lists curated foods by name).

If the food *is* in the plan options lists, this section doesn't apply — fall through to the normal post-commit flow.
```

Add a worked example to `## Conversation Examples (Hebrew Tone & Slang)`. Suggested wording:

```markdown
**3b. Off-menu food log (plan-deviation flag)**

> **User:** דפקתי עכשיו לאפה שווארמה
> **Agent:** עודכן. שווארמה לא מהאופציות בתפריט — זה חלבון שמן עם פחמימה.
```

## Re-test plan after fix

Re-run scenario 3 with the new section in place. Score `plan-deviation-flag`:

- [ ] Reply contains a deviation flag (`"לא מהתפריט"` / `"לא באופציות"` / `"זה לא מהתוכנית"`).
- [ ] Reply contains one informational note about the food (`"חלבון שמן"`, `"פחמימה ושומן ביחד"`, etc.) — not a substitution or rest-of-day note.
- [ ] Reply does NOT contain rest-of-day language (`"בשאר היום..."`, `"מעכשיו..."`).

If 3/3 pass — F4 closed. If 1-2/3, iterate prompt wording up to 3 attempts; if still failing, demote to a deeper investigation handoff.

## Iteration cap reminder

Per skill spec, 3 prompt attempts max on this kind of finding. If still failing after 3 tries, the issue is deeper than copy — likely needs structured-output to identify off-menu foods (a parser-side enrichment that tags items with `is_off_menu`), which would move this from "prompt fix" to "code fix."

## Files most likely to need edits

- `prompts/response_generator.md` (the rule + the example)
- `tests/ux-loop/hebrew-friend-coach-tone/inputs/expectations.md` (the `plan-deviation-flag` dimension already exists — no change needed)
- `tests/ux-loop/hebrew-friend-coach-tone/inputs/scenarios.md` (note in scenario 3 about "predicted failure" can be removed once F4 is fixed)
