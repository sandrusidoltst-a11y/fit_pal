# Findings — run2-after-seed

**Status:** scoring complete, no in-loop fixes applied. Run paused for direction from user given the volume + severity of findings.

**Session branch:** `ux-loop/hebrew-friend-coach-tone-2026-05-24`
**Setup vs run1:** seeded `user_profiles` row (Dolev, 23, male, 170cm) + Clean Bulk Plan (12,127 chars) + 5 historical days of logs (5/19–5/23, 21 rows, one anomaly day on Wed 5/20).

## High-level deltas vs run1

| | run1 (no plan) | run2 (plan + history) |
|---|---|---|
| Scenario 1 — empty greet | "120 גרם חלבון" invented | "2.2 מנות חלבון" real (today's logs exist) |
| Scenario 2 — tight log | "סגור, עודכן" perfect | Budget line on a non-triggering log; wrong targets |
| Scenario 3 — deviation | Had rest-of-day prescription | Dropped prescription; still no deviation flag |
| Scenario 4 — daily stats | Strong time + invented "מתוך היעד" | Strong time, WRONG plan numbers (120/150 vs 140/250) |
| Scenario 5 — unit mismatch | Bypassed via catalog mapping | Bypassed via estimation safety net |
| Scenario 7 — weekly | Reframed to today | Reframed to today + claims no historical data |

## Per-dimension scorecard (run2)

| Dimension | S1 | S2 | S3 | S4 | S5 | S6 | S7 |
|---|---|---|---|---|---|---|---|
| `tone` | pass | partial | partial | pass | n/a | pass | partial |
| `language-consistency` | pass | pass | pass | pass | n/a | pass | pass |
| `address-term` | pass | pass | pass | pass | n/a | pass | pass |
| `time-awareness` | n/a | n/a | n/a | **pass** | n/a | n/a | n/a |
| `tight-confirmation-default` | n/a | **fail** | **fail** | n/a | n/a | n/a | n/a |
| `weekly-synthesis-shape` | n/a | n/a | n/a | n/a | n/a | n/a | **fail** |
| `plan-reference` | partial | **fail** | n/a | **fail** | n/a | n/a | n/a |
| `budget-reasoning` | n/a | n/a | n/a | **fail** | n/a | n/a | n/a |
| `no-logging-language-on-qna` | n/a | n/a | n/a | n/a | n/a | pass | n/a |
| `plan-deviation-flag` | n/a | n/a | **fail** | n/a | n/a | n/a | n/a |

## Findings ranked by severity

### F1 — Bot misreads the plan's daily targets (HIGH)
**Bucket:** REASONING.
**Evidence:**
- Plan markdown clearly states: `Protein 7 servings (140 g)`, `Carbs 5 servings (~250 g)` rest / `6 servings (~300 g)` training.
- Scenario 2 reply: `4.4 מנות חלבון מתוך **6**, ועוד 1.4 מנות פחמימה מתוך **3**` — wrong targets (6 vs 7, 3 vs 5–6).
- Scenario 4 reply: `88.0 גרם חלבון מתוך **120** ו-142.0 גרם פחמימות מתוך **150**` — wrong targets (120 vs 140, 150 vs 250).
- Scenario 4 also reported `142 גרם פחמימות` for today, but DB has only `71 גרם carbs` for 5/24 — the consumed total is also wrong.

**Suggested fix location:** `prompts/response_generator.md` — strengthen the "read the plan" rules, possibly with a worked example of citing target numbers verbatim. Investigate if the plan markdown is being injected verbatim into the system prompt (the bot may be paraphrasing it rather than reading the numbers).

**Iteration cap reminder:** if 3 prompt attempts don't move this, demote to handoff (could be a structural issue — long plan markdown buried in 8k+ token system prompt).

### F2 — Tight-confirmation default broke when plan was injected (HIGH)
**Bucket:** REASONING.
**Evidence:**
- Run1 (no plan): scenario 2 → `"סגור, עודכן"` (perfect tight default).
- Run2 (with plan): scenario 2 → adds a budget line even though none of the three numeric triggers fired (80% of macro target / 3+ servings / free-cal cap).
- Scenario 3 also adds a budget line on the שווארמה log when no trigger justifies it.

**Hypothesis:** the `## Tight confirmation` section's "Add ONLY when…" rule is being overridden by the model's tendency to always reason about budget when plan data is available. The rule needs to be stronger — maybe "Default is silent unless one of the three triggers is mathematically true. Do not add status updates 'as a courtesy'."

**Suggested fix location:** `prompts/response_generator.md` `## Tight confirmation` — tighten the rule, add a fail anchor in `## Conversation Examples` (a log that does NOT trigger but shows the bot still adding a budget line — clearly labeled as fail).

### F3 — Weekly query doesn't see historical logs (HIGH)
**Bucket:** PIPELINE → **handoff record**.
**Evidence:**
- Scenario 7 user message: `מה אכלתי השבוע?`.
- Bot reply: `אין לי נתונים על שאר השבוע במבנה הזה` ("I don't have data for the rest of the week").
- DB ground truth (verified via Supabase MCP): 19 rows for the 5 historical days (5/19–5/23).

**Likely root cause** (without a trace yet): the `daily_log_today` context field injected into `response_node` only includes today's logs. For multi-day queries, the bot is supposed to invoke the `query_food_logs` tool (or be routed through `stats_node`). One or more steps in that chain isn't working — either the parser is routing `השבוע` to a today-only stats query, or the stats path is wired but the result isn't reaching `response_node`.

**This goes to handoff** — fix lives in code/pipeline, not in the prompt. Suggested fix area: `src/agents/nodes/stats_node.py`, `src/services/daily_log_service.py:query_food_logs`, or `prompts/input_parser.md` (date-range extraction).

### F4 — Plan-deviation flag still missing (MEDIUM)
**Bucket:** REASONING.
**Evidence:** scenario 3 reply on `דפקתי עכשיו לאפה שווארמה` — no `"לא מהתפריט"` / `"לא באופציות"` mention. The dev user's plan has explicit Protein Options and Carb Options lists; lafa shawarma isn't on either.

This was the **predicted baseline failure** documented in `scenarios.md`. The current prompt has no plan-deviation rule.

**Suggested fix location:** add `## Plan deviation` section to `prompts/response_generator.md` (between `## Tight confirmation` and `## Nutrition Q&A`), plus a worked example #3b in `## Conversation Examples` showing the deviation-flag pattern.

### F5 — Scenario 5 still can't trigger UNIT_MISMATCH (LOW — scenario issue)
**Bucket:** scenarios.md drafting bug, not a bot bug.
**Evidence:** `כוס ביצים` got LLM-estimated (since `ביצים` plural isn't in catalog, only `ביצה` singular). Estimation accepted "1 כוס" → 240g via the parser's `amount_g` safety net.

**Suggested fix:** swap to a food guaranteed to be in the catalog with empty `unit_weights` (`חזה הודו` is `{}`) AND no synonym for `כוס`. Then the resolver chain has no path → UNIT_MISMATCH fires.

This is a documentation / scenarios.md update for run3+, not a prompt or code fix.

## Wins worth noting

- **Time-awareness landed strong** (scenario 4): explicit hour quote + bucket name + pacing assessment all present. The strong "REQUIRED" framing in `## Budget-reasoning template` step 4 is working.
- **`language-consistency` clean across all scenarios.** No English leaks.
- **`address-term` clean.** One `אחי` per reply max, no off-list terms.
- **`no-logging-language-on-qna` clean** (scenario 6).
- **Rest-of-day prescription dropped** between run1 and run2 in scenario 3 — small win, possibly due to plan context giving the model something concrete to anchor on instead of generic coaching.

## Net for the loop's purpose

Both `tone` (broadly) and `address-term` work. The harder problems are structural:
- The bot can't read plan targets accurately (F1).
- The bot adds budget lines too eagerly (F2).
- The pipeline doesn't surface historical data on weekly queries (F3 — handoff).
- The bot doesn't flag plan deviations (F4 — predicted).

F1 + F2 are the right candidates for in-loop prompt iteration. F3 is handoff. F4 is also prompt territory.

## Decision point

User paused the run after seeing the findings. Open questions:
1. Apply in-loop fixes for F1, F2, F4 now? (3 separate commits, each followed by re-running the affected scenarios.)
2. Or absorb the findings, open the PR with run2 documented, and tackle fixes in a follow-up session?
3. F3 (weekly pipeline) — write the handoff record now, or pause until F1/F2/F4 are resolved?
