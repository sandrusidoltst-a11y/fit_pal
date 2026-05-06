# Feature: Rename `FoodIntakeEvent` → `UserIntent` and `daily_log_report` → `query_logs`

The following plan should be complete, but it's important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils, types, and models. Import from the right files.

> **Branch**: `refactor/discriminated-action-state` (PR #26 already open with the discriminated-action-state refactor commits). The two renames land as **two atomic commits on this branch**, pushed to the same PR.
>
> **Commit policy** — read carefully:
> - Two commits, in order:
>   1. `refactor: rename FoodIntakeEvent to UserIntent`
>   2. `refactor: rename daily_log_report to query_logs`
> - Each commit is **pure rename** — no logic change, no behavior change.
> - After each commit, run unit tests; both should stay green throughout.
> - Do NOT squash. Two separate commits make each rename independently reviewable on the PR's Commits tab.

## Feature Description

Two pure-rename refactors that resolve PR review comments on PR #26. Both names became misleading after the discriminated-action-state refactor introduced multi-action support and per-action sub-states. The renames clarify intent without changing behavior.

1. **`FoodIntakeEvent` → `UserIntent`**: the wrapper class is the LLM-output shape for *every* user message classification (LogFood, QueryStats, QueryFoodInfo, LogPersonalStats, Chitchat), not just food intake. The "FoodIntake" name is a leftover from when the schema only covered LOG_FOOD.

2. **`daily_log_report` → `query_logs`**: the state field holds whatever logs `stats_lookup_node` returned for a QUERY_DAILY_STATS turn. *"daily"* implies single-day scope, but the field can hold multi-day ranges. *"report"* is vague. `query_logs` describes its actual role — the answer payload for a stats query — and pairs naturally with the existing `query_stats` sub-state.

## User Story

As **Dolev (the developer)**,
I want field and class names that describe their actual current role,
So that future readers (including me, six months out) don't have to mentally translate from a leftover name to the real semantics every time they touch the code.

## Problem Statement

PR #26 review surfaced two names that no longer match what the code does:

- `FoodIntakeEvent` reads like a LOG_FOOD-only schema. Post-refactor, every user message — including pure chitchat — is parsed through it. The name suggests a narrower role than the class actually plays.
- `daily_log_report`'s prefix *"daily"* implies single-day scope. Post-refactor, range queries (`start_date`/`end_date`, e.g., *"last 7 days"*) populate this field too. The "daily" prefix is a lie of omission.

Both invite cognitive overhead during review and onboarding. They also weaken the LLM-prompt signal: when `response_node` injects `daily_log_report` into the JSON context on a QUERY turn, the field's name doesn't tell the model *"this is the answer to the user's question."* The current naming relies on the LLM inferring intent from `last_action` alone; a clearer name (`query_logs`) reinforces the role.

## Solution Statement

Rename both via mechanical find-and-replace, in two atomic commits:

1. **Commit 1**: `FoodIntakeEvent` → `UserIntent`. Touches `src/schemas/input_schema.py` (class definition), `src/agents/nodes/input_node.py` (import + `with_structured_output(UserIntent)` + one comment). No tests reference the wrapper directly — they construct variants (`LogFoodEvent`, `QueryStatsEvent`, etc.) so test files don't change. Plus a few docs that mention the name (CLAUDE.md, docs/patterns/llm-config.md, docs/adr/0004-...md, .claude/skills/test-engineering/references/unit-testing.md, PRD.md).

2. **Commit 2**: `daily_log_report` → `query_logs`. State field rename. Touches `src/agents/state.py` (TypedDict field + docstring), `src/agents/nodes/{input_node,stats_node,commit_node,response_node}.py` (writes + reads), `tests/conftest.py` (basic_state fixture), `tests/unit/test_{stats_node,response_node}.py`, `tests/integration/test_log_yesterday_e2e.py`. Plus docs/adr/0004-...md.

After both commits:
- Pure rename — `git diff` shows only identifier changes, no logic or behavior change.
- All three test tiers green (unit, integration, graph_api).
- Eval driver unchanged (it doesn't reference these names).
- Manual smoke not required (no graph-flow change).

## Feature Metadata

**Feature Type**: Refactor (two pure renames, no behavior change)
**Estimated Complexity**: Low — mechanical find-and-replace, two atomic commits, no logic.
**Primary Systems Affected**:
- `src/schemas/input_schema.py`
- `src/agents/state.py`
- `src/agents/nodes/{input_node,stats_node,commit_node,response_node}.py`
- `tests/conftest.py`, `tests/unit/test_{stats_node,response_node}.py`, `tests/integration/test_log_yesterday_e2e.py`
- Docs: `CLAUDE.md`, `docs/patterns/llm-config.md`, `docs/adr/0004-schema-to-state-translation-ownership.md` (uncommitted), `.claude/skills/test-engineering/references/unit-testing.md`, `PRD.md`

**Dependencies**: None new.

**Resolves**: Two PR-26 inline comments (linked from `src/schemas/input_schema.py:96` and `src/agents/state.py:162`).

**Does NOT change**:
- Variant class names (`LogFoodEvent`, `QueryStatsEvent`, etc.) — keep the `Event` suffix for now; renaming those is a bigger surface and out of scope.
- The wrapper's `event` field name (would touch every isinstance read site).
- `last_action` (mentioned as a candidate for a future rename like `graph_phase`, but explicitly out of scope here).
- Any behavior, prompt, or eval logic.

---

## CONTEXT REFERENCES

### Relevant Codebase Files — IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

**Schema/state layer**:
- `src/schemas/input_schema.py` (full file, ~100 lines) — `FoodIntakeEvent` defined at line 96. Variant classes above it. After rename, the class becomes `UserIntent`.
- `src/agents/state.py` (lines 137-185) — `daily_log_report: List[QueriedLog]` is a flat field on `AgentState`. After rename, becomes `query_logs: List[QueriedLog]`. Update the docstring entry (line 165).

**Nodes**:
- `src/agents/nodes/input_node.py` (full file, ~110 lines) — imports `FoodIntakeEvent` (line 11), calls `llm.with_structured_output(FoodIntakeEvent)` (line 46), one comment references the name (line 63). Also writes `"daily_log_report": []` in the turn-entry clears (line 99).
- `src/agents/nodes/stats_node.py` (full file, ~37 lines) — sole writer of `daily_log_report` (line 44: `return {"daily_log_report": report}`).
- `src/agents/nodes/commit_node.py` (line 96) — comment references `daily_log_report`.
- `src/agents/nodes/response_node.py` (lines 179-180) — sole reader of `daily_log_report` (`_build_context` injects into the QUERY context JSON).

**Tests**:
- `tests/conftest.py` (line 49) — `basic_state` fixture has `"daily_log_report": []`.
- `tests/unit/test_stats_node.py` (lines 50-51, 78, 101) — asserts on `daily_log_report` return value.
- `tests/unit/test_response_node.py` (lines 67, 101-102, 119, 131, 148, 440, 462, 476) — multiple test names + assertions reference the field. **Note: a test method name `test_query_stats_includes_daily_log_report` should be renamed to `test_query_stats_includes_query_logs`.**
- `tests/integration/test_log_yesterday_e2e.py` (line 78) — fixture state literal.

**Docs (rename-mention only — content stays accurate)**:
- `docs/adr/0004-schema-to-state-translation-ownership.md` (uncommitted, multiple references throughout) — update inline; ADR is still in draft state on the working tree.
- `CLAUDE.md` (line 68) — directory comment references `FoodIntakeEvent schema`.
- `docs/patterns/llm-config.md` (lines 27, 109, 111) — example code uses `FoodIntakeEvent`.
- `.claude/skills/test-engineering/references/unit-testing.md` (line 87) — example code uses `FoodIntakeEvent`.
- `PRD.md` (lines 166, 284, 327) — references `FoodIntakeEvent` in narrative.

### New Files to Create

None.

### Patterns to Follow

**Find-and-replace per commit, narrow scope per commit.** Each commit touches only the identifier being renamed, not the other one. The mechanical pattern:

```bash
# Commit 1: scoped grep
grep -rln "FoodIntakeEvent" --include="*.py" --include="*.md"

# Commit 2: scoped grep
grep -rln "daily_log_report" --include="*.py" --include="*.md"
```

For each match, prefer the `Edit` tool with `old_string` / `new_string` per file rather than `sed -i`. Reason: a few hits are inside long comments or docstrings that need contextual judgment (e.g., the ADR's prose may refer to the rename-event-class concept, not just the literal name).

**Order matters within commit 2.** When renaming `daily_log_report`:
1. Update `src/agents/state.py` first (the type definition).
2. Then writers (`stats_node.py`, `input_node.py` turn-entry clear).
3. Then readers (`response_node.py`).
4. Then test fixtures and assertions.
5. Then comments (`commit_node.py:96`) and docs.

This order means partial intermediate states are still importable — Python doesn't fail on the type itself before all references update, but logically following the data-flow direction makes for easier review.

**No semantic changes.** If you're tempted to "improve while renaming" (rewrite a comment, fix a typo, restructure an import block), STOP. Pure rename = pure rename. Drift makes the diff less reviewable. Save those for a separate cleanup commit.

---

## IMPLEMENTATION PLAN

### Commit 1 — `FoodIntakeEvent` → `UserIntent`

**Goal**: rename the wrapper class. Pure mechanical rename.

**Tasks**: 1–3.

### Commit 2 — `daily_log_report` → `query_logs`

**Goal**: rename the state field across writers, readers, tests, and docstring.

**Tasks**: 4–9.

### Final verification gate (after both commits)

- `uv run ruff check .` — clean.
- `uv run pytest tests/unit/ -v` — all green.
- `uv run pytest tests/integration/ -v` — all green.
- `uv run pytest tests/graph_api/ -v -s` — all green.
- `git diff main..HEAD --stat` — every file in the diff has only identifier changes; no behavior changes.

**No eval re-run required.** The eval doesn't reference either renamed identifier.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order. Each task is atomic and independently testable.

### Commit 1: rename `FoodIntakeEvent` → `UserIntent`

#### 1. RENAME class in `src/schemas/input_schema.py`

- **IMPLEMENT**: Rename `class FoodIntakeEvent(BaseModel):` to `class UserIntent(BaseModel):` (line 96). Update the docstring of the class — the existing docstring describes the wrapper's role; replace any literal mention of `FoodIntakeEvent` with `UserIntent` so the docstring is internally consistent.
- **PATTERN**: Pure class rename.
- **IMPORTS**: None change in this file.
- **GOTCHA**:
  - The leading underscore alias `_EventUnion` stays unchanged.
  - Pydantic `BaseModel` subclass name appears in the JSON Schema's `title` field. After rename, OpenAI receives a payload with `"title": "UserIntent"` instead of `"title": "FoodIntakeEvent"`. Functionally irrelevant (OpenAI doesn't gate on `title`), but visible in LangSmith trace metadata.
- **VALIDATE**:
  - `uv run python -c "from src.schemas.input_schema import UserIntent; print(UserIntent.model_json_schema()['title'])"` prints `UserIntent`.

#### 2. UPDATE `src/agents/nodes/input_node.py`

- **IMPLEMENT**: In the import block (around line 11), replace `FoodIntakeEvent` with `UserIntent`. Update the call site `llm.with_structured_output(FoodIntakeEvent)` (line 46) to `llm.with_structured_output(UserIntent)`. Update the inline comment at line 63 that references `FoodIntakeEvent wrapper` to say `UserIntent wrapper`.
- **PATTERN**: Mechanical reference rename.
- **IMPORTS**: One.
- **GOTCHA**: Other variant imports (`LogFoodEvent`, `QueryStatsEvent`, `QueryFoodInfoEvent`, `LogPersonalStatsEvent`, `ChitchatEvent`) stay unchanged — they're imported alongside `UserIntent`.
- **VALIDATE**:
  - `uv run pytest tests/unit/test_input_parser.py tests/unit/test_state_substates.py -v` — green.
  - `grep -rn "FoodIntakeEvent" src/ tests/ --include="*.py"` — zero hits.

#### 3. UPDATE doc references

- **IMPLEMENT**: Replace `FoodIntakeEvent` with `UserIntent` in:
  - `docs/adr/0004-schema-to-state-translation-ownership.md` (uncommitted; multiple mentions in Context, Decision, and Consequences sections).
  - `CLAUDE.md` (line 68 directory comment).
  - `docs/patterns/llm-config.md` (lines 27, 109, 111 — including a code example that calls `with_structured_output(FoodIntakeEvent)`).
  - `.claude/skills/test-engineering/references/unit-testing.md` (line 87 — `mock_llm.invoke.return_value = FoodIntakeEvent(...)` — replace with `UserIntent(...)`).
  - `PRD.md` (lines 166, 284, 327) — narrative references.
- **PATTERN**: Search-and-replace per file. Use `Edit` tool with `replace_all=True` per file *only* when no false positives exist (verify by reading the file first).
- **IMPORTS**: N/A.
- **GOTCHA**:
  - PRD.md line 327 talks about *"updating `FoodIntakeEvent` parsing"* in the context of a past task. Rename the literal but keep the historical accuracy of the bullet — don't rewrite the surrounding narrative.
  - `docs/plans/discriminated-action-state-refactor.md` references `FoodIntakeEvent` heavily (it predates this rename). **Leave that plan as-is** — it's a historical artifact pinned to the names that existed when the plan was written. ADRs and CLAUDE.md are the live docs that should reflect current names; planning docs are immutable post-execution.
- **VALIDATE**:
  - `grep -rn "FoodIntakeEvent" --include="*.md" .` — only hits should be in `docs/plans/discriminated-action-state-refactor.md` and possibly `commit_logs/`.

#### COMMIT 1: `git commit -m "refactor: rename FoodIntakeEvent to UserIntent"`

- Stage the changed files explicitly (avoid `git add .` to keep the commit scoped).
- Commit body should be one paragraph: *"Rename the wrapper class for the LLM-output union from FoodIntakeEvent to UserIntent. The class covers all five user-intent variants (LogFood, QueryStats, QueryFoodInfo, LogPersonalStats, Chitchat) — the prior name implied a LOG_FOOD-only role and was a leftover from the original schema. Pure rename: no behavior change."*
- Co-author trailer: `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`

---

### Commit 2: rename `daily_log_report` → `query_logs`

#### 4. UPDATE `src/agents/state.py`

- **IMPLEMENT**:
  - Rename the field at line 181: `daily_log_report: List[QueriedLog]` → `query_logs: List[QueriedLog]`.
  - Update the `Attributes:` docstring entry (line 165): replace `daily_log_report:` with `query_logs:` and update the description to *"Logs returned by `stats_lookup_node` for a QUERY_DAILY_STATS turn (single-day or range)."*
- **PATTERN**: TypedDict field rename.
- **IMPORTS**: None.
- **GOTCHA**: The `QueriedLog` element type stays the same.
- **VALIDATE**:
  - `uv run python -c "from src.agents.state import AgentState; assert 'query_logs' in AgentState.__annotations__; assert 'daily_log_report' not in AgentState.__annotations__; print('ok')"`.

#### 5. UPDATE `src/agents/nodes/stats_node.py`

- **IMPLEMENT**: Replace the return statement at line 44: `return {"daily_log_report": report}` → `return {"query_logs": report}`.
- **PATTERN**: Single-line rename.
- **IMPORTS**: None.
- **GOTCHA**: None.
- **VALIDATE**: `uv run pytest tests/unit/test_stats_node.py -v` — fails until Task 7 updates the tests; that's expected. Re-run at the end of Task 7.

#### 6. UPDATE `src/agents/nodes/input_node.py` turn-entry clear

- **IMPLEMENT**: In the `return {...}` block (around line 99), rename the key `"daily_log_report": []` to `"query_logs": []`.
- **PATTERN**: Single-line rename inside the return dict.
- **IMPORTS**: None.
- **GOTCHA**: Don't touch any other field in the return dict.
- **VALIDATE**: `uv run pytest tests/unit/test_state_substates.py -v` — should stay green (the test doesn't assert on `daily_log_report`).

#### 7. UPDATE `src/agents/nodes/response_node.py` reader

- **IMPLEMENT**: In `_build_context` (lines 178-180), update both the variable read and the context-key write:
  ```python
  # Before
  daily_log_report = state.get("daily_log_report", [])
  context["daily_log_report"] = daily_log_report

  # After
  query_logs = state.get("query_logs", [])
  context["query_logs"] = query_logs
  ```
  The local variable `daily_log_report` should also be renamed to `query_logs` for internal consistency.
- **PATTERN**: Read+write rename in the QUERY_DAILY_STATS branch of `_build_context`.
- **IMPORTS**: None.
- **GOTCHA**:
  - Renaming the JSON-context key (`context["query_logs"] = ...`) means the LLM sees `"query_logs": [...]` in the system-prompt JSON instead of `"daily_log_report": [...]`. **This is a prompt-shape change** that the LLM might respond to differently. Mitigated by: the reformat is only on QUERY turns, the LLM has been observed to use `last_action` as the primary routing signal, and the value's structure (list of QueriedLog dicts) is unchanged. Worth noting in the PR review for the response-prompt-style follow-up smoke.
  - **Do not edit `prompts/response_generator.md`.** The current prompt doesn't reference either field name literally (verified earlier); the LLM picks up the JSON key name dynamically.
- **VALIDATE**:
  - `uv run pytest tests/unit/test_response_node.py -v` — fails until Task 8 updates the tests; that's expected. Re-run at the end of Task 8.

#### 8. UPDATE all test files

- **IMPLEMENT**: Rename `daily_log_report` → `query_logs` in the following test files. Approach: per-file `replace_all=True` on the literal string `"daily_log_report"` is safe in these files (verified by inspection):
  - `tests/conftest.py` (line 49: `basic_state` fixture).
  - `tests/unit/test_stats_node.py` (lines 50, 51, 78, 101 — assertions on the return dict).
  - `tests/unit/test_response_node.py` (lines 67, 101-102, 119, 131, 148, 440, 462, 476). **Also rename the test method `test_query_stats_includes_daily_log_report` → `test_query_stats_includes_query_logs`** (line 101).
  - `tests/integration/test_log_yesterday_e2e.py` (line 78: state literal in the test fixture).
- **PATTERN**: Per-file `Edit` with `replace_all=True`. Verify by reading each file before applying.
- **IMPORTS**: None.
- **GOTCHA**:
  - The test method rename (`test_query_stats_includes_daily_log_report` → `test_query_stats_includes_query_logs`) requires a separate `Edit` since it's an identifier, not just a string literal.
  - `tests/unit/test_response_node.py:102` has `daily_log_report` inside a docstring — `replace_all=True` will rename it correctly; verify by re-reading after.
- **VALIDATE**:
  - `uv run pytest tests/unit/test_stats_node.py tests/unit/test_response_node.py tests/integration/test_log_yesterday_e2e.py -v` — all green.
  - `grep -rn "daily_log_report" --include="*.py" .` — zero hits.

#### 9. UPDATE comments and docs

- **IMPLEMENT**: Replace `daily_log_report` with `query_logs` in:
  - `src/agents/nodes/commit_node.py` (line 96 — comment references `daily_log_report`).
  - `docs/adr/0004-schema-to-state-translation-ownership.md` (uncommitted; check the Related section anchors and any prose that mentions the field).
- **PATTERN**: Comment + doc rename.
- **IMPORTS**: N/A.
- **GOTCHA**:
  - `docs/plans/discriminated-action-state-refactor.md` references `daily_log_report` — leave it; it's a historical planning artifact.
  - `commit_logs/2026-05-06_…_refactor-discriminated-action-state.md` references `daily_log_report` — leave it; commit logs document the state at the time of the commit.
- **VALIDATE**:
  - `grep -rn "daily_log_report" --include="*.py" --include="*.md" .` — only hits in `docs/plans/discriminated-action-state-refactor.md` and `commit_logs/`.

#### COMMIT 2: `git commit -m "refactor: rename daily_log_report to query_logs"`

- Stage the changed files explicitly.
- Commit body: *"Rename the AgentState field that holds logs returned by stats_lookup_node from daily_log_report to query_logs. The 'daily' prefix was misleading — the field can hold multi-day ranges (e.g., 'last 7 days'). 'query_logs' pairs naturally with the existing query_stats sub-state, forming a clearer triad: query_stats holds the user's date-scope input, query_logs holds the answer payload, last_action signals which turn type. Pure rename: no behavior change. Note: the JSON context key the response LLM sees changes from 'daily_log_report' to 'query_logs' on QUERY turns; no prompt edit needed since the prompt doesn't reference either name literally."*
- Co-author trailer.

---

## TESTING STRATEGY

### Unit Tests

All affected unit tests already exist; the rename only changes their assertion strings and method name. No new tests required — this is a pure rename.

- `tests/unit/test_stats_node.py` — verifies `query_logs` key in return dict.
- `tests/unit/test_response_node.py` — verifies `query_logs` injection in QUERY context JSON.
- `tests/unit/test_state_substates.py` — should stay green; doesn't reference the renamed field.
- `tests/unit/test_input_parser.py` — should stay green; doesn't reference the renamed field directly.

### Integration Tests

- `tests/integration/test_log_yesterday_e2e.py` — state-shape rename in the test fixture; behavior unchanged.

### Graph-API Tests

- No graph-api test directly asserts on `daily_log_report` or `FoodIntakeEvent` by name. Re-run as a regression guard since state-shape changes (even renames) should always go through the full server path.

### Edge Cases

- **Reading old checkpointed state**: if any LangGraph checkpoint database has rows with the old field name `daily_log_report`, the new code reading `state.get("query_logs", [])` will return `[]` instead of the stored data. This is acceptable for FitPal's POC stage (no checkpoint migration story needed; existing threads won't preserve their daily_log_report across the rename). **If the user has live threads they care about, run a one-time SQL update on the Postgres checkpoint store** — but for POC this is unlikely to matter. Flag in the PR review notes.

---

## VALIDATION COMMANDS

Execute every command after both commits land. Zero regressions, 100% feature correctness.

### Level 1: Syntax & Style

```bash
uv run ruff check src/schemas/input_schema.py src/agents/state.py \
  src/agents/nodes/input_node.py src/agents/nodes/commit_node.py \
  src/agents/nodes/stats_node.py src/agents/nodes/response_node.py \
  tests/conftest.py tests/unit/test_stats_node.py tests/unit/test_response_node.py \
  tests/integration/test_log_yesterday_e2e.py
```

### Level 2: Unit Tests

```bash
uv run pytest tests/unit/ -v
```

### Level 3: Integration Tests

```bash
uv run pytest tests/integration/ -v
```

### Level 4: Graph-API Tests (mandatory — state-shape change)

```bash
uv run pytest tests/graph_api/ -v -s
```

### Level 5: Final grep audit

```bash
# Should return zero hits in src/ and tests/
grep -rn "FoodIntakeEvent" src/ tests/
grep -rn "daily_log_report" src/ tests/

# In docs/, only historical planning/commit-log artifacts should match
grep -rn "FoodIntakeEvent\|daily_log_report" docs/ CLAUDE.md PRD.md
```

### Level 6: Branch state check (handoff)

```bash
git log refactor/discriminated-action-state ^main --oneline   # 4 commits expected:
                                                              #   refactor: per-action state via discriminated FoodIntakeEvent + sub-states
                                                              #   docs: add commit log for discriminated-action-state refactor
                                                              #   refactor: rename FoodIntakeEvent to UserIntent
                                                              #   refactor: rename daily_log_report to query_logs
git diff main..HEAD --stat                                    # Renames should show as small line-counts per file
```

---

## ACCEPTANCE CRITERIA

- [ ] `class UserIntent(BaseModel)` defined in `src/schemas/input_schema.py`; no remaining references to `FoodIntakeEvent` in `src/` or `tests/`.
- [ ] `query_logs: List[QueriedLog]` field on `AgentState`; no remaining references to `daily_log_report` in `src/` or `tests/`.
- [ ] All three test tiers green.
- [ ] `git diff main..HEAD` shows only identifier renames + minor docstring/comment touch-ups; no logic changes.
- [ ] Two atomic commits on `refactor/discriminated-action-state`, in order:
  1. `refactor: rename FoodIntakeEvent to UserIntent`
  2. `refactor: rename daily_log_report to query_logs`
- [ ] PR #26 inline comments addressed (push triggers GitHub to mark them as outdated; reviewer can resolve).
- [ ] No new files created.
- [ ] `docs/adr/0004-schema-to-state-translation-ownership.md` updated inline (still uncommitted; add to commit 2 or commit 1 — whichever introduces its primary referent first; suggest commit 2 since the field rename is the bigger change).

---

## COMPLETION CHECKLIST

- [ ] All 9 tasks completed in order
- [ ] Each task's `VALIDATE` step passed
- [ ] `uv run ruff check` clean on every modified file
- [ ] Both commits made on `refactor/discriminated-action-state` (not main, not a new branch)
- [ ] Final grep audit confirms no stale references
- [ ] `git push` to `origin/refactor/discriminated-action-state` (PR #26 picks up the new commits)
- [ ] PR-26 inline comments verified resolved on GitHub UI

---

## NOTES

### Why two commits, not one

Each rename is mechanically independent and individually reviewable. Splitting them lets the reviewer (you, or anyone else) inspect each rename's diff in isolation on the PR's Commits tab. If something looks off in one, you can `git revert <sha>` for just that commit without losing the other.

The cost is two `git commit` invocations and two test-suite runs vs. one. For a low-risk pure rename, the marginal cost is negligible.

### Why now and not after merge

PR #26 is open; the rename comments came from your own self-review. Adding the renames to the same PR:
- Avoids a second merge to `main` (your stated preference).
- Keeps the final shipped state of `main` coherent — no half-step where one rename landed and the other is pending.
- Self-resolves the PR comments when pushed.

The trade-off is that the PR's title and description don't explicitly mention the renames. Consider updating the PR description to add: *"Also renames `FoodIntakeEvent` → `UserIntent` and `daily_log_report` → `query_logs` for clarity (see commits 3-4)."*

### What is *not* changing

- Variant class names (`LogFoodEvent`, `QueryStatsEvent`, etc.) — keep the `Event` suffix. Renaming variants would touch every isinstance dispatch site and is a bigger surface for negligible value.
- The wrapper's `event` field name (`UserIntent.event: _EventUnion`) — touching this would require updating every isinstance unwrap. Not worth it.
- `last_action` (mentioned in conversation as a candidate for `graph_phase` rename) — out of scope for this PR.
- Any prompt, eval, or behavior — pure rename only.

### Risks

- **Checkpoint migration**: existing LangGraph threads in the Postgres checkpoint store will have rows with the old field names. New code reading `state["query_logs"]` returns `[]` instead of stored data. For POC this is acceptable; for prod-stable threads, run a one-time `UPDATE` on the checkpoint table.
- **Prompt-shape sensitivity**: changing the JSON context key the response LLM sees from `daily_log_report` to `query_logs` is technically a prompt change. The current `prompts/response_generator.md` doesn't reference either name literally, so the LLM picks up the new key dynamically. Manual smoke after merge is sufficient confirmation.

### Confidence

**9.5/10** for one-pass success. This is a mechanical rename with full grep coverage of both touch points. The only realistic failure modes are typos or accidentally renaming an unrelated string match — mitigated by the per-file `Edit` tool + post-rename grep audit.
