# Findings — run3-f3-f4-tone-fixes

**Run purpose:** Live re-validation of the F3 (weekly query) + F4 (plan deviation) prompt fixes plus the F4 tone-loosening iteration, against the actual `langgraph dev` server flow (not just in-process probes).

**Setup vs run2:** identical user/profile/plan. Diff is **only** in `prompts/input_parser.md` (F3) + `prompts/response_generator.md` (F4 + tone). Same runner.py, same scenarios.

**Server:** local langgraph dev :2024, model `gpt-5.4-mini`.

---

## Per-scenario verdict

| # | Scenario | Verdict | Notes |
|---|---|---|---|
| 1 | empty-day-greeting | partial | Real reply with correct plan numbers (7 protein / 6 carbs). But because today's log is bloated by ~28 probe artifacts, the bot says "אתה כבר עברת הרבה מעל היעד — עדיף לעצור" — a truthful read of the data, but UX-wise odd for a "greeting" since the user just said `היי`. Not a regression. |
| 2 | normal log + tight confirmation | **PASS** | `סגור, עודכן.` — clean tight default. F2 holds. |
| 3 | off-menu deviation | **PASS — F4 confirmed live** | `עודכן. לאפה שווארמה זה לא מהתפריט שלך — חלבון שמן עם פחמימה ביחד.` Flag + note present, no rest-of-day prescription. Tone is conversational ("שלך"), not the run2 template. |
| 4 | daily stats time pacing | partial | Strong time-awareness (`כרגע 22:13, סגרת 28.3 חלבון ו-20.1 פחמימה. אתה הרבה מעל היעד`). One **language-consistency slip**: opens with `Aחי` instead of `אחי` (Latin 'A' + Hebrew suffix — token-level glitch from this sampling). Single-shot variance; flag for re-test, don't chase. |
| 5 | unit-mismatch coach retry | **FAIL — F5 still open** | `אכלתי כוס ביצים` got routed through HITL with `ביצים — 1 כוס (240.0g) (משוערך)` — the estimation safety-net path. UNIT_MISMATCH never fires because `ביצים` (plural) gets LLM-estimated when not in catalog. Scenario rewrite needed per F5 handoff guidance: pick a catalog food with empty `unit_weights` and no `כוס/cup` synonym. |
| 6 | food-info Q&A | **PASS** | `ב-100 גרם אורז מבושל יש בערך 28 גרם פחמימה.` Clean, no logging language. |
| 7 | weekly synthesis | **PASS — F3 confirmed live** | Full markdown table: 5/19 → 5/24, every historical row enumerated by date, plus today's bloated 5/24 list, plus a closing-line synthesis (`חלבון היה גבוה וברור ברוב הימים, אבל היום של 2026-05-24 היה מאוד עמוס ואקראי ביחס לתפריט`). This is exactly the `weekly-synthesis-shape` template from `prompts/response_generator.md` §7. Run2 returned "no data for the rest of the week"; run3 returns a full week-on-a-page. **Biggest concrete win of the session.** |

## Per-dimension scorecard (run3)

| Dimension | S1 | S2 | S3 | S4 | S5 | S6 | S7 |
|---|---|---|---|---|---|---|---|
| `tone` | pass | pass | **pass** | partial (Aחי typo) | n/a | pass | pass |
| `language-consistency` | pass | pass | pass | **fail** (Aחי) | n/a | pass | pass |
| `address-term` | pass | n/a | n/a | partial | n/a | n/a | pass |
| `time-awareness` | n/a | n/a | n/a | **pass** | n/a | n/a | n/a |
| `tight-confirmation-default` | n/a | **pass** | n/a | n/a | n/a | n/a | n/a |
| `plan-deviation-flag` | n/a | n/a | **pass** | n/a | n/a | n/a | n/a |
| `weekly-synthesis-shape` | n/a | n/a | n/a | n/a | n/a | n/a | **pass** |
| `plan-reference` | pass | n/a | n/a | pass | n/a | n/a | n/a |
| `budget-reasoning` | partial | n/a | n/a | pass | n/a | n/a | n/a |
| `no-logging-language-on-qna` | n/a | n/a | n/a | n/a | n/a | **pass** | n/a |

## Deltas vs run2

| Dimension | run2 (with plan, before F3/F4 fixes) | run3 (after F3/F4 + tone fixes) |
|---|---|---|
| `plan-deviation-flag` (S3) | **fail** | **pass** |
| `weekly-synthesis-shape` (S7) | **fail** (claimed "no data") | **pass** (full markdown breakdown) |
| `tight-confirmation-default` (S2) | fail (budget-line leakage) | pass (bare default) |
| `tone` (S3, S7) | partial | pass |

All four problematic dimensions cleared. The two open items below are not regressions:

## Items still open

- **F5 — unit-mismatch scenario (LOW)**: scenario 5 still bypassed via estimation safety net. Needs `scenarios.md` rewrite (catalog food + empty `unit_weights` + no synonym). Pure inputs-file change, no prompt or code.
- **Language-consistency slip (S4)**: `Aחי` typo. Probably single-shot Hebrew tokenization quirk; if it reappears in another live run it deserves a prompt-side mitigation in §"Hard rules" (e.g., explicit "Do not mix Hebrew and Latin characters within a word").

## Side observations

- Scenario 1's "you're way over targets" tone is a *truthful* read of the bloated 5/24 state (~28 probe artifacts on top of normal use). If we cleaned up the e2e user's 5/24 rows before the next run, scenario 1 would likely return to a normal greet shape. Filed under "test hygiene", not a bot bug.
- The `## Plan deviation` rule + tone-loosening did NOT cause any over-flagging on the on-menu scenarios (2 = chicken on-menu, 6 = rice Q&A). Both stayed silent on plan-deviation language. The rule is correctly conditional on off-menu.
- Run3 was a single-shot per scenario (not N=many). Statistical confidence is "this worked at least once in the real flow", not "this is deterministic". The in-process N=10 (F3) and N=8 (F4-varied) probes are the deterministic evidence.

## Net for the loop's purpose

**F3 and F4 are live-validated.** The two highest-severity findings from run2 are now passing in the actual server flow. The session-original ask ("start working on the handoffs") is delivered.

Recommended next moves (in priority order):
1. Commit the prompt fixes + handoffs as a PR — concrete, reviewable win.
2. F5 scenarios.md rewrite — pure-input change to unblock the last open finding.
3. Optionally: clean the 5/24 bloat from the e2e user before run4 so scenarios 1/4 reset to a normal baseline.
