# UX-loop: F3 + F4 + F5 prompt fixes (hebrew-friend-coach-tone)

**Branch:** `ux-loop/f3-f4-f5-prompt-fixes`
**Date:** 2026-05-25
**Loop:** `tests/ux-loop/hebrew-friend-coach-tone`

Resolves the three open findings from `run2-after-seed` plus one bug surfaced
during F5 investigation. All fixes are prompt-side or test-side — no `src/`
code changed.

---

## What changed and why

### F3 — Weekly query ignored historical logs (`prompts/input_parser.md`)

**Symptom:** `"מה אכלתי השבוע?"` returned "no data for the rest of the week"
even though 21 historical rows existed.

**Root cause (not a pipeline bug):** today (2026-05-24) is Sunday, the start of
the Israel-local week. The parser rule `"השבוע" → Sunday → today` collapsed to a
1-day range on Sundays. The parser followed it literally 6/10 runs (empty range)
and generalized 4/10 (correct) — intermittent, and masked because the prompt's
worked examples used a Saturday date.

**Fix:** redefined `"השבוע"` as a **trailing 7-day window** (`today-6 → today`),
deterministic across all weekdays. Added rationale + a Sunday worked example.

**Verification:** parser N=10 probe → 10/10 emit `5/18 → 5/24`. Full graph
in-process → bot returns the full date-grouped weekly breakdown.

### F4 — Plan-deviation flag missing (`prompts/response_generator.md`)

**Symptom:** logging an off-menu food (e.g. `לאפה שווארמה`) produced a normal
confirmation with no signal that the food wasn't on the plan.

**Fix (three iterations):**
1. Added `## Plan deviation` section (flag + informational note, no rest-of-day
   prescription) + example 3b. → 3/3 שווארמה pass, but overfit.
2. Varied-foods probe (פלאפל/פיצה/בורקס/נקניקיות/צ'יפס/שניצל + 2 on-menu
   controls) caught two failure modes: budget-line cannibalizing the flag, and
   note-without-flag. Strengthened the rule (mandatory two-part, stackable with
   budget, composite/cooking-method guidance) + added examples 3c/3d. → 8/8.
3. Tone-loosening: replies were templating the examples verbatim (model size and
   temperature didn't help — it's a prompt-structure issue). Added "do NOT
   template" guidance + rewrote 3b/3c/3d with varied sentence shapes. → 8/8
   maintained, replies sound conversational.

**Verification:** varied probe 8/8; live run3 scenario 3 confirmed.

### F5 — UNIT_MISMATCH was unreachable dead code (`prompts/response_generator.md`)

**Finding:** `response_generator.md` referenced a `"Unit mismatch:"` failure path
(routing rule + Hard rule §6) that **no code in `src/` ever produces**. The
resolver chain (`food_service.py:resolve_amount_g`) has a safety-net step that
always succeeds because the parser is contractually required to emit `amount_g`
for non-gram units. The UNIT_MISMATCH branch could never fire.

This is by design — the architecture chose "never block on unit resolution;
surface the safety-net estimate via HITL and let the user correct in
conversation" over a hard failure. The prompt just hadn't been updated.

**Fix:**
- Removed the dead UNIT_MISMATCH references; replaced Hard rule §6 with a note
  documenting the safety-net + HITL-correction contract.
- Redesigned scenario 5 from "expect UNIT_MISMATCH retry" to
  `weird-unit input → safety-net estimate → HITL correction → reconfirm`, which
  tests the behavior the architecture actually has.
- Added a `weird-unit-hitl-correction` dimension to `expectations.md` with a
  4-item turn-by-turn checklist.
- Extended `runner.py` to support a list of sequential resumes per turn
  (backwards-compatible with the single-string form).

### Bonus — confirmation edit-parser dropped unit changes (`prompts/confirmation_parser.md`)

**Surfaced by the new scenario 5.** When the user corrected `כוס ביצים` with
`"לא, התכוונתי 2 ביצים"`, the edit-parser read it as `count=2, unit=cup`
(inherited the wrong original unit, just bumped the count) → committed 480g
instead of ~100g.

**Fix:** added a correction-signal rule — phrases like `"לא, התכוונתי"` /
`"actually"` invalidate the inherit-original-unit behavior and force the LLM to
re-infer the unit from the corrected wording. Added the egg worked example.

**Verification:** F5 probe → `2 ביצים → 2 יחידות (100g)`, committed 142 kcal,
tight `סגור, עודכן.` reply.

---

## Validation

- `uv run pytest tests/unit/` → **196 passed** (after every change).
- In-process probes (parser N=10, F4 varied N=8, F5 multi-turn) all green.
- Live `langgraph dev` re-validation (run3) → F3 + F4 confirmed in the real
  server flow; artifacts in `runs/run3-f3-f4-tone-fixes/`.

## Run3 artifacts added

`tests/ux-loop/hebrew-friend-coach-tone/runs/run3-f3-f4-tone-fixes/`:
`transcript.md`, `findings.md`, `db-snapshot.md`, `summary.html`,
`scenario_*.json`, `all_scenarios.json`.

## Handoffs closed

`runs/run2-after-seed/handoffs/F3-*.md` and `F4-*.md` updated with full
resolution sections (diagnosis, fix, verification, iteration notes).

## Next steps

- Run a fresh run4 once the e2e user's bloated 5/24 logs are cleaned, so
  scenarios 1/4 reset to a normal baseline (the "you're over target" tone is a
  truthful read of ~30 probe-artifact logs, not a bot regression).
- Watch the S4 `Aחי` Latin/Hebrew code-switch slip; add a Hard-rules line if it
  recurs in another live run.
