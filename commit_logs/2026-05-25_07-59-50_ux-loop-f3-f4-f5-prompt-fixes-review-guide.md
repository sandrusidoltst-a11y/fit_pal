# PR reading guide — F3 + F4 + F5 prompt fixes

Read in this order. All changes are prompt-side or test-side; no `src/` code changed.

## 1. Why (start here)
- `commit_logs/2026-05-25_07-59-50_ux-loop-f3-f4-f5-prompt-fixes.md` — the full
  story: three findings + one surfaced bug, each with root cause + verification.
- `runs/run2-after-seed/handoffs/F3-weekly-query-ignores-history.md` and
  `F4-plan-deviation-flag-missing.md` — the resolution sections at the bottom of
  each are the investigation trail.

## 2. The three prompt fixes — in increasing subtlety

### `prompts/input_parser.md` (F3) — smallest, read first
One rule change: `"השבוע"` calendar-anchor → trailing-7-day window. The diff is
the `Current period` bullet + one new worked example. The interesting part is
*why* (Sunday edge), which is in the rationale paragraph and the commit log.

### `prompts/confirmation_parser.md` (edit-parser bug) — self-contained
A new sub-bullet under rule 4 ("correction signals override inherit") + three
egg worked examples. Read rule 4 top-to-bottom to see how the correction-signal
clause interacts with the existing count-only inherit clause.

### `prompts/response_generator.md` (F4 + F5) — largest, read last
Two distinct changes in one file:
- **F5 (removal):** the `## Before every reply` routing list loses its
  UNIT_MISMATCH branch; Hard rule §6 is rewritten from "handle UNIT_MISMATCH" to
  "weird units go through HITL." This is *deleting dead code* — confirm nothing
  else references the removed string (`grep "Unit mismatch" src/` → zero hits).
- **F4 (addition):** the `## Plan deviation` section + examples 3b/3c/3d. Read
  the section first, then the examples — the examples deliberately vary sentence
  shape (that's the tone fix, not redundancy).

## 3. The test redesign — the contract made testable
- `inputs/expectations.md` — new `weird-unit-hitl-correction` dimension. The
  4-item checklist *is* the spec for the F5 behavior.
- `inputs/scenarios.md` — scenario 5 rewritten to match. The background
  paragraph explains the architecture decision.
- `runner.py` — `run_scenario` now accepts a list of resumes per turn (the
  multi-step HITL flow). Backwards-compatible: a string `resume` still works.

## 4. Evidence (skim)
- `runs/run3-f3-f4-tone-fixes/` — live re-validation. `findings.md` has the
  per-scenario verdicts; `summary.html` is the visual version; the `*.json` are
  raw runner output.

---

## Things worth flagging while reviewing

1. **F3 changes `"השבוע"` semantics.** It now means "trailing 7 days" not
   "calendar week from Sunday." `"השבוע האחרון"` is unchanged, so the two are now
   offset-by-1 of the same thing — semantically very close. If a user clearly
   wants calendar-week, this needs re-splitting. Chosen because it's
   deterministic and matches "show me the past week of eating."

2. **F5 is a *deletion* of a feature that never worked.** If you expected
   UNIT_MISMATCH to be a real failure mode, it wasn't — the safety-net `amount_g`
   contract made it unreachable. The PR makes the prompt honest about that. Push
   back here if you think the bot *should* hard-fail on weird units instead of
   estimating + HITL.

3. **The edit-parser fix is prompt-only.** `ItemEdit` schema is unchanged; the
   fix is teaching the LLM that "לא, התכוונתי" invalidates the inherited unit. If
   you'd prefer a structural guard (e.g. a `correction: bool` field), that's a
   bigger change deferred.

4. **F4 examples intentionally vary sentence shape.** 3b/3c/3d look repetitive
   but each demonstrates a different structure (opener variation, order
   variation, stacking with budget line). Collapsing them back to one template
   would reintroduce the robotic-tone problem.

5. **run3 was single-shot per scenario.** The deterministic evidence is the
   in-process N-probes (parser N=10, F4 N=8). run3 proves "works at least once in
   the real server flow," not statistical stability.

6. **The e2e user's 5/24 logs are bloated** by ~30 probe artifacts from this
   session. That's why run3 scenarios 1/4 show "you're over target" — truthful,
   not a regression. A cleanup before run4 is noted in the commit log.

## Skip-able
- `runs/run3-f3-f4-tone-fixes/scenario_*.json` + `all_scenarios.json` — raw
  runner output, already summarized in `findings.md` / `transcript.md`.
- `runs/run3-f3-f4-tone-fixes/summary.html` — visual restatement of
  `findings.md`; skim only if you want the rendered before/after.
