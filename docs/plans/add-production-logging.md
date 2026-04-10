# Feature: Add Production Logging to src/ Layer

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Add structured Python `logging` throughout the `src/` layer to provide production-level observability. The `bot/` layer already has proper logging; the entire `src/` layer (agents, tools, services, config, database, auth) currently has zero `logging` usage — only scattered `print()` statements. This must be fixed before Docker deployment (Step 7) so that operators can diagnose issues without relying solely on LangSmith traces.

## User Story

As an operator running FitPal in production (Docker Compose)
I want structured logs with proper levels across all application layers
So that I can diagnose auth failures, DB issues, and unexpected behavior without SSH-ing into the container

## Problem Statement

The `src/` layer has no `logging` module usage. All diagnostic output is via `print()` — which has no levels, no structured context, and cannot be filtered in production. LangSmith covers LLM/graph tracing well, but does not cover infrastructure concerns (DB connectivity, auth failures, SSL config, estimation fallback rates).

## Solution Statement

Add `logging.getLogger(__name__)` to each `src/` module that needs it, following the exact pattern already established in `bot/gateway.py` and `bot/supabase_admin.py`. Replace all existing `print()` warnings with proper `logger.warning()` calls. Add targeted INFO/WARNING/ERROR/DEBUG logs at key decision points identified during the file-by-file walkthrough.

## Feature Metadata

**Feature Type**: Enhancement
**Estimated Complexity**: Low
**Primary Systems Affected**: All `src/` modules (config, database, security, agents/nodes, tools, services)
**Dependencies**: None — Python `logging` is stdlib

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `bot/gateway.py` (lines 9, 22) - Why: Reference pattern for logger setup (`import logging` + `logger = logging.getLogger(__name__)`)
- `bot/supabase_admin.py` (lines 10, 16) - Why: Same reference pattern, shows structured log messages with context params
- `src/config.py` - Why: Startup config, DB URL resolution, LLM factory — needs startup logs
- `src/database.py` - Why: Engine creation, SSL workaround — needs startup + SSL warning
- `src/security/auth.py` - Why: JWT validation, highest-priority logging target (security boundary)
- `src/agents/nodes/input_node.py` (line 22) - Why: Has `print()` to replace, needs parsed action log
- `src/agents/nodes/food_search_node.py` - Why: Needs empty-queue warning
- `src/tools/food_lookup.py` - Why: DB access layer, needs search miss/create/not-found logs
- `src/agents/nodes/selection_node.py` (lines 43, 64, 71) - Why: Has 3 `print()` statements to replace
- `src/agents/nodes/calculate_macros_node.py` - Why: Needs estimation trigger + failure logs
- `src/agents/nodes/confirmation_node.py` - Why: HITL decision logging (confirm/reject/edit)
- `src/agents/nodes/commit_node.py` - Why: Batch commit event logging
- `src/services/daily_log_service.py` - Why: Write + query logging at tool wrapper level
- `src/agents/nodes/response_node.py` (line 79) - Why: Has `print()` to replace

### New Files to Create

None — all changes are additions to existing files.

### Patterns to Follow

**Logger Setup** (from `bot/gateway.py`):
```python
import logging

logger = logging.getLogger(__name__)
```

**Structured Messages with Context** (from `bot/gateway.py`):
```python
logger.info("Created new thread %s for chat_id=%s", session["thread_id"], chat_id)
logger.exception("Failed to create thread for chat_id=%s", chat_id)
```

**Key conventions:**
- Use `%s` string formatting (lazy evaluation), NOT f-strings in log calls
- Include contextual identifiers (user_id, food_name, etc.) as parameters
- Use `logger.exception()` inside `except` blocks (auto-includes traceback)
- Never log secrets (tokens, API keys, full DATABASE_URL)

**Log Level Usage:**
- `DEBUG`: Happy-path detail useful only during development (query results, resolved params)
- `INFO`: Key business events (food logged, estimation triggered, batch committed, parsed action)
- `WARNING`: Unexpected-but-recoverable situations (dev fallback in production, empty queues, LLM misbehavior, missing prompt files, disabled SSL verification)
- `ERROR`: Infrastructure failures (Supabase unreachable, DB lookup failures for valid IDs)

---

## IMPLEMENTATION PLAN

### Phase 1: Startup Layer (config.py, database.py)

Add startup-time logs that confirm which DB backend and LLM provider are active, plus the SSL verification warning.

### Phase 2: Security Boundary (auth.py)

Add comprehensive auth logging — this is the highest-priority file with 5 log points covering every failure path.

### Phase 3: Graph Nodes (input, food_search, selection, calculate_macros, confirmation, commit, response)

Replace all `print()` statements with proper `logger.warning()` and add targeted INFO/WARNING/ERROR logs at decision points.

### Phase 4: Tool & Service Layer (food_lookup.py, daily_log_service.py)

Add DB operation logs — search misses, food creation, write confirmation, query results.

### Phase 5: Validation

Run unit tests to verify no regressions. Verify no `print()` statements remain in non-script `src/` files.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

---

### Task 1: UPDATE `src/config.py` — Add startup logging

- **IMPLEMENT**: Add logger setup at module level. Add `INFO` log after DB URL resolution (line 41 area) logging which backend resolved (`asyncpg` or `sqlite`) — do NOT log the actual URL. Add `INFO` log for LLM provider/model (line 44 area). Add `WARNING` log in `get_user_id()` when falling back to `DEFAULT_DEV_USER_ID` (line 35).
- **PATTERN**: `bot/gateway.py:9,22` — logger setup pattern
- **IMPORTS**: `import logging`
- **GOTCHA**: Do NOT log `DATABASE_URL` — it contains credentials. Log only the backend type (e.g., "asyncpg" or "sqlite+aiosqlite"). For `get_user_id()` fallback warning, only log once-style or at WARNING — this runs on every request in dev, but in production it signals auth misconfiguration.
- **LOG POINTS**:
  1. `logger.info("Database backend: %s", "asyncpg (Supabase)" if _supabase_url else "sqlite (local)")` — after line 41
  2. `logger.info("LLM provider=%s model=%s", GLOBAL_PROVIDER, GLOBAL_MODEL)` — after line 44
  3. `logger.warning("No auth user in config, falling back to DEFAULT_DEV_USER_ID")` — at line 35
- **VALIDATE**: `uv run pytest tests/unit/ -v -x`

---

### Task 2: UPDATE `src/database.py` — Add engine creation and SSL warning

- **IMPLEMENT**: Add logger setup. Add `WARNING` log inside the SSL branch (after line 20) noting that SSL certificate verification is disabled. Add `INFO` log after engine creation (after line 22).
- **PATTERN**: `bot/supabase_admin.py:10,16` — logger setup pattern
- **IMPORTS**: `import logging`
- **GOTCHA**: Do NOT log the DATABASE_URL. The SSL warning should be `WARNING` level — it's a security trade-off that should be visible in production logs.
- **LOG POINTS**:
  1. `logger.warning("SSL certificate verification disabled for asyncpg connection")` — after line 20
  2. `logger.info("Async database engine created")` — after line 22
- **VALIDATE**: `uv run pytest tests/unit/ -v -x`

---

### Task 3: UPDATE `src/security/auth.py` — Add comprehensive auth logging

- **IMPLEMENT**: Add logger setup. Add logging at every failure path and a DEBUG log on success. Add startup WARNING if `SUPABASE_URL` is empty.
- **PATTERN**: `bot/gateway.py:111-183` — structured logging with context params
- **IMPORTS**: `import logging`
- **GOTCHA**: NEVER log the token value or `SUPABASE_SERVICE_KEY`. Log `user_id` on success only at `DEBUG` level. Use `logger.exception()` in the `except` block for automatic traceback inclusion.
- **LOG POINTS**:
  1. `logger.warning("SUPABASE_URL not configured — auth will reject all requests")` — after line 7, guarded by `if not SUPABASE_URL`
  2. `logger.warning("Auth rejected: missing authorization header")` — at line 22, before raise
  3. `logger.warning("Auth rejected: invalid authorization scheme")` — at line 28, before raise
  4. `logger.error("Auth failed: could not reach Supabase")` — in except block at line 43 (use `logger.exception` to include traceback)
  5. `logger.warning("Auth rejected: invalid or expired token, status=%s", response.status_code)` — at line 48, before raise
  6. `logger.debug("Auth successful user_id=%s", user["id"])` — at line 54, before return
- **VALIDATE**: `uv run pytest tests/unit/test_auth_handler.py -v`

---

### Task 4: UPDATE `src/agents/nodes/input_node.py` — Replace print + add parse log

- **IMPLEMENT**: Add logger setup. Replace `print()` on line 22 with `logger.warning()`. Add `INFO` log after LLM parse (after line 47) with parsed action and item count.
- **IMPORTS**: `import logging`
- **GOTCHA**: The node is sync (not async). No special considerations.
- **LOG POINTS**:
  1. `logger.warning("Prompt file not found at %s, using fallback", prompt_path)` — replace line 22
  2. `logger.info("Input parsed: action=%s items=%d", result.action.value, len(result.items))` — after line 42
- **VALIDATE**: `uv run pytest tests/unit/test_input_parser.py -v`

---

### Task 5: UPDATE `src/agents/nodes/food_search_node.py` — Add empty queue warning

- **IMPLEMENT**: Add logger setup. Add `WARNING` log when `pending_items` is empty (line 16-17).
- **IMPORTS**: `import logging`
- **LOG POINTS**:
  1. `logger.warning("food_search_node called with empty pending_food_items")` — at line 16, before return
- **VALIDATE**: `uv run pytest tests/unit/test_food_search_node.py -v`

---

### Task 6: UPDATE `src/tools/food_lookup.py` — Add DB operation logs

- **IMPLEMENT**: Add logger setup. Add `DEBUG` log on search hit. Add `INFO` log when search returns zero results (both tiers empty). Add `WARNING` on food not found in `calculate_food_macros`. Add `INFO` on food item creation in `create_food_item`.
- **IMPORTS**: `import logging`
- **GOTCHA**: `search_food` is called frequently — keep happy path at `DEBUG`, not `INFO`. The zero-results `INFO` is important because it triggers the estimation path.
- **LOG POINTS**:
  1. `logger.debug("search_food query=%r matched=%d source=database", query, len(results))` — after line 42, inside `if results`
  2. `logger.info("search_food query=%r no results from DB or estimated foods", query)` — after line 53, when returning empty list (check `if not results` before return)
  3. `logger.warning("calculate_food_macros: food not found food_id=%s", food_id)` — at line 64-65, before returning error dict
  4. `logger.info("Created food item name=%r food_id=%s source=%s", name, food_item.id, source)` — after line 95, before return
- **VALIDATE**: `uv run pytest tests/unit/ -v -x`

---

### Task 7: UPDATE `src/agents/nodes/selection_node.py` — Replace all 3 print() statements

- **IMPLEMENT**: Add logger setup. Replace all three `print()` calls with `logger.warning()`.
- **IMPORTS**: `import logging`
- **LOG POINTS**:
  1. `logger.warning("Prompt file not found at %s, using fallback", prompt_path)` — replace line 43
  2. `logger.warning("LLM returned SELECTED without food_id, treating as NO_MATCH")` — replace line 64
  3. `logger.warning("LLM returned AMBIGUOUS (not supported in MVP), treating as NO_MATCH")` — replace line 71
- **VALIDATE**: `uv run pytest tests/unit/test_agent_selection.py -v`

---

### Task 8: UPDATE `src/agents/nodes/calculate_macros_node.py` — Add estimation + failure logs

- **IMPLEMENT**: Add logger setup. Add `ERROR` log when macro calculation fails. Add `INFO` when estimation path triggers. Add `WARNING` for missing prompt file.
- **IMPORTS**: `import logging`
- **LOG POINTS**:
  1. `logger.error("Macro calculation failed food=%r error=%s", food_name, macros["error"])` — at line 36-37, when `"error" in macros`
  2. `logger.info("Estimating macros via LLM food=%r amount=%.1fg", food_name, amount)` — at line 65, before `_estimate_macros` call
  3. `logger.warning("Estimation prompt file not found, using fallback")` — at line 92, inside `except FileNotFoundError`
- **VALIDATE**: `uv run pytest tests/unit/test_calculate_macros_node.py -v`

---

### Task 9: UPDATE `src/agents/nodes/confirmation_node.py` — Add HITL decision logs

- **IMPLEMENT**: Add logger setup. Add `WARNING` for empty batch. Add `INFO` log for user decision (confirm/reject/edit). Add `INFO` for individual edit actions. Add `WARNING` for missing prompt file.
- **IMPORTS**: `import logging`
- **GOTCHA**: The confirmation loop can iterate multiple times (edit → re-show). Each decision should be logged.
- **LOG POINTS**:
  1. `logger.warning("Confirmation node called with empty batch, skipping to response")` — at line 58, before return
  2. `logger.info("User confirmation: action=%s items=%d", decision.action, len(batch))` — after line 67, after `_parse_confirmation` returns
  3. `logger.warning("Confirmation prompt file not found, using fallback")` — at line 120, inside `except FileNotFoundError`
  4. `logger.info("User edit: removed item index=%d", idx)` — inside the remove loop at line 154, after `batch.pop(idx)`
  5. `logger.info("User edit: changed amount index=%d old=%.1fg new=%.1fg", edit.item_index, old_amount, new_amount)` — at line 162, after extracting old/new amounts
- **VALIDATE**: `uv run pytest tests/unit/test_confirmation_node.py -v`

---

### Task 10: UPDATE `src/agents/nodes/commit_node.py` — Add batch commit logs

- **IMPLEMENT**: Add logger setup. Add `INFO` for batch commit start. Add `WARNING` for empty batch.
- **IMPORTS**: `import logging`
- **LOG POINTS**:
  1. `logger.warning("Commit node called with empty batch")` — at line 18, before return
  2. `logger.info("Committing confirmed batch items=%d", len(batch))` — after line 16, when batch is non-empty
- **VALIDATE**: `uv run pytest tests/unit/test_commit_node.py -v`

---

### Task 11: UPDATE `src/services/daily_log_service.py` — Add tool wrapper logs

- **IMPLEMENT**: Add logger setup. Add `INFO` log in `log_food_entry` after successful write. Add `DEBUG` log in `query_food_logs` with result count.
- **IMPORTS**: `import logging`
- **GOTCHA**: Log in the `@tool` wrappers only, NOT in the raw service functions (those are called directly by tests with injected sessions — logging there would pollute test output).
- **LOG POINTS**:
  1. `logger.info("Daily log created log_id=%s user_id=%s calories=%.1f", log.id, user_id, calories)` — after line 204, before return in `log_food_entry`
  2. `logger.debug("Queried food logs user_id=%s date=%s results=%d", user_id, target_date, len(logs))` — after line 218 area, before return in `query_food_logs` (note: `logs` is the variable holding the query result before serialization)
- **VALIDATE**: `uv run pytest tests/unit/ -v -x`

---

### Task 12: UPDATE `src/agents/nodes/response_node.py` — Replace print()

- **IMPLEMENT**: Add logger setup. Replace `print()` on line 79 with `logger.warning()`.
- **IMPORTS**: `import logging`
- **LOG POINTS**:
  1. `logger.warning("Response prompt file not found at %s, using fallback", prompt_path)` — replace line 79
- **VALIDATE**: `uv run pytest tests/unit/test_response_node.py -v`

---

### Task 13: VERIFY — No print() statements remain in src/ (excluding scripts)

- **IMPLEMENT**: Search for remaining `print()` calls in `src/` excluding `src/scripts/`. All should be replaced.
- **VALIDATE**: `grep -rn "print(" src/ --include="*.py" --exclude-dir=scripts` — should return zero results

---

## TESTING STRATEGY

### Unit Tests

No new test files needed. All existing unit tests should pass unchanged — logging does not alter return values or control flow.

If any test mocks `builtins.print` or captures stdout to assert on `print()` output, those assertions may need updating to use `caplog` fixture instead. Check:
- `tests/unit/test_agent_selection.py`
- `tests/unit/test_input_parser.py`
- `tests/unit/test_response_node.py`

### Integration Tests

Run integration suite to verify DB-hitting code still works with logging added:
```bash
uv run pytest tests/integration/ -v
```

### Edge Cases

- Verify `config.py` WARNING doesn't fire on every request in tests (it should only fire when `get_user_id` falls back to dev default — tests may trigger this, which is fine)
- Verify auth.py logs don't leak tokens (code review check)

---

## VALIDATION COMMANDS

### Level 1: No print() in src/ (excluding scripts)

```bash
grep -rn "print(" src/ --include="*.py" --exclude-dir=scripts
```

Expected: zero results

### Level 2: Unit Tests

```bash
uv run pytest tests/unit/ -v
```

### Level 3: Integration Tests

```bash
uv run pytest tests/integration/ -v
```

### Level 4: Verify logging imports

```bash
grep -rn "import logging" src/ --include="*.py"
```

Expected: matches in config.py, database.py, auth.py, all node files, food_lookup.py, daily_log_service.py (12 files)

---

## ACCEPTANCE CRITERIA

- [ ] All `print()` statements in `src/` (excluding `src/scripts/`) replaced with proper `logger` calls
- [ ] Every `src/` module that has logging uses `logger = logging.getLogger(__name__)` pattern
- [ ] Log levels follow the convention: DEBUG (happy-path detail), INFO (business events), WARNING (unexpected-but-recoverable), ERROR (infrastructure failures)
- [ ] No secrets logged (tokens, API keys, DATABASE_URL)
- [ ] `%s` lazy formatting used in all log calls (no f-strings)
- [ ] All existing unit tests pass without modification (or minimal caplog adjustments)
- [ ] All integration tests pass
- [ ] Zero `print()` statements remain in non-script `src/` files

---

## COMPLETION CHECKLIST

- [ ] All 13 tasks completed in order
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full test suite passes (unit + integration)
- [ ] No secrets in any log statement (manual review)
- [ ] `print()` fully eliminated from non-script src/ files

---

## NOTES

### Log Count Summary

| File | Log Points | Levels |
|---|---|---|
| `src/config.py` | 3 | 2x INFO, 1x WARNING |
| `src/database.py` | 2 | 1x INFO, 1x WARNING |
| `src/security/auth.py` | 6 | 1x DEBUG, 2x WARNING (reject), 1x WARNING (startup), 1x WARNING (token), 1x ERROR |
| `src/agents/nodes/input_node.py` | 2 | 1x INFO, 1x WARNING |
| `src/agents/nodes/food_search_node.py` | 1 | 1x WARNING |
| `src/tools/food_lookup.py` | 4 | 1x DEBUG, 2x INFO, 1x WARNING |
| `src/agents/nodes/selection_node.py` | 3 | 3x WARNING |
| `src/agents/nodes/calculate_macros_node.py` | 3 | 1x INFO, 1x WARNING, 1x ERROR |
| `src/agents/nodes/confirmation_node.py` | 5 | 2x INFO (decision + edits counted as group), 1x WARNING (empty), 1x WARNING (prompt) |
| `src/agents/nodes/commit_node.py` | 2 | 1x INFO, 1x WARNING |
| `src/services/daily_log_service.py` | 2 | 1x INFO, 1x DEBUG |
| `src/agents/nodes/response_node.py` | 1 | 1x WARNING |
| `src/agents/nodes/stats_node.py` | 0 | — |
| **Total** | **34** | |

### Design Decisions

1. **No logging configuration in application code.** Python's `logging.getLogger(__name__)` defers all config to the deployment environment. The Docker entrypoint or LangGraph server will configure handlers/formatters. This keeps the application layer clean.

2. **Tool wrappers, not service functions.** Logging lives in `@tool` wrappers, not raw service functions. Service functions accept injected sessions for testability — adding logging there would pollute test output.

3. **Complement LangSmith, don't duplicate.** LangSmith captures full LLM I/O, node state, and tool arguments. Our logs focus on what LangSmith does NOT cover: infrastructure health (DB, SSL, auth), business signals (estimation rate, user decisions), and error context (why something failed, not just that it failed).

4. **stats_node.py gets zero logs.** It's a thin pass-through to `query_food_logs` which already has a DEBUG log. No decisions, no failure paths beyond what the tool surfaces.
