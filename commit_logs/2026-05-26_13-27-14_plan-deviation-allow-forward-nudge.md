# Plan deviation: allow forward-looking nudge (reconcile rule with edited examples)

**Branch:** `ux-loop/f3-f4-f5-prompt-fixes` (follow-up on PR #37)
**Date:** 2026-05-26

## Why

The user hand-edited the F4 `## Conversation Examples` (3c נקניקיות, 3c שניצל,
3d פיצה) to add a gentle forward-looking coaching nudge — `"שים לב בפעם הבאה"`,
`"תשתדל להימנע בפעמים הבאות..."`, `"במיוחד אם זה לא אחרי אימון"`. But the
`## Plan deviation` rule text still forbade exactly that ("NOT a quantity/frequency
note", "Do NOT prescribe rest-of-day adjustments"), so a strict reader of the rule
would mark the user's own examples as fails. This commit reconciles the rule with
the intended behavior.

## What changed

### `prompts/response_generator.md` — `## Plan deviation`
- Added an explicit **optional third element**: a brief forward-looking nudge
  (mindfulness / frequency / method tie-in), one short clause, omitted for minor
  deviations.
- Reframed the hard constraint from "no rest-of-day adjustments" to "no
  **same-day compensation**". The line is now explicit: today-compensation
  (`בשאר היום ניצמד`, `תפצה עם`) is forbidden; a future-habit nudge is allowed.
- Element 2 still bans **substitution** suggestions (distinct from a habit nudge).

### `tests/ux-loop/.../inputs/expectations.md` — `plan-deviation-flag` dimension
- Updated checklist item 3 (same-day compensation = fail; forward nudge = allowed).
- Added an "Allowed (optional) — forward-looking nudge" block + two new pass
  examples (שניצל + נקניקיות with nudges) so the scorer matches the new rule.

### Typo / formatting fixes in the edited examples
- `מהקלוירות` → `מהקלוריות` (שניצל example).
- Missing spaces after periods: `שלך.תשתדל` → `שלך. תשתדל`,
  `להיום.במיוחד` → `להיום. במיוחד`. These sit inside prompt examples, so the
  model could otherwise copy the misspelling/run-on into real replies.

## Validation

- Varied-foods probe (6 off-menu + 2 on-menu controls) → **8/8 pass**; rule and
  examples are coherent, nudges no longer penalized.
- Prompt-text-only change; no `src/` touched, no unit-test impact.

## Note

One unrelated English-leak slip observed in the probe (on-menu חזה עוף control
replied in English) — same family as the run3 `Aחי` slip, not caused by this
change. Watch in the next live run; add a Hard-rules line if it recurs.
