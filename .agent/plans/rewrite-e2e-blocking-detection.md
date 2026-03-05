# Feature: Rewrite E2E Tests for Blocking Error Detection via HTTP API

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Rewrite the graph-api E2E test suite to run ALL graph paths through the real HTTP API (matching LangSmith Studio behavior), handle multi-turn HITL interrupt flows, and surface meaningful blocking error details when they occur.

## User Story

As a developer
I want E2E tests that detect BlockingErrors through the same HTTP API path that Studio uses
So that I catch sync-in-async bugs before they reach production

## Problem Statement

The current test suite has two broken pieces:
1. `test_blocking_detection.py` runs in-process via `ainvoke()` with `MemorySaver` — bypasses the HTTP server entirely, never catches real `BlockingError`s
2. `test_graph_flows.py` uses HTTP but doesn't handle HITL interrupt flows — food logging tests crash with opaque errors

Additionally, `BlockingError` is NOT in the server's whitelisted exception types (`langgraph_api/serde.py:87-110`), so its message always gets replaced with `"An internal error occurred"`. The error type field (`"BlockingError"`) IS preserved though.

## Solution Statement

- Delete in-process tests (useless for real blocking detection)
- Single test file with a shared helper that uses `raise_error=False` on `runs.wait()` to capture the full error dict
- Test every graph path through HTTP with proper multi-turn HITL handling
- On `BlockingError`, fail with a descriptive message explaining it's a sync-in-async issue and directing to Studio for the full trace

## Feature Metadata

**Feature Type**: Refactor
**Estimated Complexity**: Medium
**Primary Systems Affected**: `tests/graph_api/`
**Dependencies**: langgraph-sdk (existing), langgraph dev server (via conftest)

---

## CONTEXT REFERENCES

### Relevant Codebase Files — MUST READ BEFORE IMPLEMENTING

- `tests/graph_api/conftest.py` — Server lifecycle fixtures (`auto_start_langgraph_server`, `lg_client`, `thread`). Remove `in_process_graph` fixture and `MemorySaver` import.
- `tests/graph_api/test_graph_flows.py` — Current test structure to rewrite
- `tests/graph_api/test_blocking_detection.py` — Delete entirely
- `src/agents/nutritionist.py` — Graph definition with all routes and conditional edges
- `src/agents/nodes/confirmation_node.py` — HITL `interrupt()` loop, `Command` routing to `commit` or `response`
- `src/agents/state.py` — `GraphAction` literals, `AgentState` fields

### New Files to Create

None — rewrite existing files only.

### Files to Delete

- `tests/graph_api/test_blocking_detection.py`
- `tests/graph_api/test_debug_trace.py`

### SDK Error Handling — Key Finding

**Server serialization** (`langgraph_api/serde.py:87-110`):
- Whitelisted errors (ValueError, TypeError, etc.) → `{"error": "TypeName", "message": str(exc)}`
- Non-whitelisted errors (including `BlockingError`) → `{"error": "TypeName", "message": "An internal error occurred"}`
- **No traceback or stacktrace is ever included in the HTTP response**

**Client handling** (`langgraph_sdk/_async/runs.py:737-745`):
- `raise_error=True` (default): raises `Exception(f"{error}: {message}")`
- `raise_error=False`: returns raw response dict with `__error__` key

**BlockingError** (`blockbuster/blockbuster.py:36-46`):
- Originates from `blockbuster` package that detects sync calls inside async context
- Message format: `"Blocking call to <function_name>"` — but this gets replaced with generic message by server serializer
- We CAN detect it via `response["__error__"]["error"] == "BlockingError"`

### Patterns to Follow

**Test docstring pattern (AAA)** from test-engineering skill:
```python
async def test_name(self, lg_client, thread):
    """
    arrange: <setup description>
    act:     <action description>
    assert:  <expected outcome>
    """
```

**Fixture usage**: All tests use `lg_client` and `thread` fixtures from conftest. `thread` creates a fresh thread per test and cleans up after.

**HITL resume via SDK**: Use `command={"resume": "<text>"}` parameter on `runs.wait()` to resume from interrupt.

**Interrupt verification**: After Turn 1, check `await lg_client.threads.get_state(thread)` for `tasks` field to confirm graph is paused at interrupt.

---

## IMPLEMENTATION PLAN

### Phase 1: Cleanup

Remove the in-process test file and debug trace file. Clean up conftest by removing `in_process_graph` fixture and `MemorySaver` import.

### Phase 2: Core Implementation

Rewrite `test_graph_flows.py` with:
1. A shared `_run` async helper that wraps `runs.wait(raise_error=False)` and produces clear failure messages on `BlockingError`
2. Test classes covering all graph paths (non-interrupt + interrupt with confirm/reject/edit)

### Phase 3: Validation

Run the full suite and verify non-interrupt paths pass, interrupt paths either pass or fail with descriptive error messages.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### Task 1: DELETE `tests/graph_api/test_blocking_detection.py`

Remove the in-process blocking detection tests entirely. They run via `ainvoke()` with `MemorySaver`, bypassing the HTTP server, and cannot detect real `BlockingError`s.

- **VALIDATE**: File no longer exists

### Task 2: DELETE `tests/graph_api/test_debug_trace.py`

Remove the debug trace test file created during this session.

- **VALIDATE**: File no longer exists

### Task 3: UPDATE `tests/graph_api/conftest.py`

- **REMOVE**: `from langgraph.checkpoint.memory import MemorySaver` import
- **REMOVE**: Entire `in_process_graph` fixture
- **KEEP**: `auto_start_langgraph_server`, `lg_client`, `thread` fixtures unchanged
- **VALIDATE**: `uv run pytest tests/graph_api/test_graph_compilation.py -v` still passes

### Task 4: REWRITE `tests/graph_api/test_graph_flows.py`

Complete rewrite with the following structure:

#### 4a: Module docstring and imports

```python
"""
E2E flow tests for the FitPal graph via HTTP API.

Scope:
    Every test goes through the real langgraph dev server (auto-started by conftest).
    This matches the LangSmith Studio execution path, so BlockingErrors that appear
    in Studio will also appear here.

LLM Usage:
    LIVE — all LLM calls are real. Run deliberately, not in pre-commit gate.

HITL Pattern:
    Food-logging paths hit interrupt() at confirmation_node. Tests use a two-turn
    pattern: Turn 1 sends food input (pauses at interrupt), Turn 2 resumes with
    confirm/reject/edit via command={"resume": "<text>"}.
"""
```

#### 4b: Shared `_run` helper

```python
ASSISTANT_ID = "fitpal"

async def _run(lg_client, thread, *, input=None, command=None):
    """Execute a graph run via HTTP and fail clearly on BlockingError.

    Uses raise_error=False so we get the raw error dict instead of an opaque
    Exception. If BlockingError is detected, pytest.fail() with a descriptive
    message including the thread ID for Studio lookup.
    """
    kwargs = {"raise_error": False}
    if input is not None:
        kwargs["input"] = input
    if command is not None:
        kwargs["command"] = command

    result = await lg_client.runs.wait(thread, ASSISTANT_ID, **kwargs)

    if isinstance(result, dict) and "__error__" in result:
        err = result["__error__"]
        error_type = err.get("error", "Unknown")
        error_msg = err.get("message", "")
        if error_type == "BlockingError":
            pytest.fail(
                f"BlockingError detected (sync call inside async context).\n"
                f"Thread: {thread}\n"
                f"Server message: {error_msg}\n"
                f"Debug: Open this thread in LangSmith Studio for the full trace.\n"
                f"Hint: A node or tool is making a synchronous call that blocks the event loop."
            )
        else:
            pytest.fail(
                f"Graph error: {error_type}: {error_msg}\n"
                f"Thread: {thread}"
            )

    return result
```

#### 4c: `_assert_interrupted` helper

```python
async def _assert_interrupted(lg_client, thread):
    """Verify the graph is paused at an interrupt (confirmation_node)."""
    state = await lg_client.threads.get_state(thread)
    tasks = state.get("tasks", [])
    assert tasks, (
        f"Expected graph to pause at interrupt but it didn't.\n"
        f"Thread: {thread}\n"
        f"Next: {state.get('next', [])}"
    )
    return state
```

#### 4d: Test classes

**`TestNonInterruptPaths`** — single turn, complete without HITL:

| Test | Input | Key Assertions |
|------|-------|----------------|
| `test_chitchat` | "Hello, how are you?" | No error, ≥2 messages, non-empty last message |
| `test_stats_query` | "What did I eat today?" | No error, ≥2 messages, non-empty last message |

**`TestFoodLoggingConfirm`** — 2 turns (log → confirm):

| Test | Turn 1 Input | Turn 2 Resume | Key Assertions |
|------|-------------|---------------|----------------|
| `test_single_db_item_confirm` | "I ate 200g of chicken" | "yes" | Turn 1 interrupted, Turn 2 completes with ≥2 messages |
| `test_off_menu_item_confirm` | "I ate 200g of dragon fruit açaí bowl" | "yes" | Same — exercises LLM estimation path |
| `test_multi_item_confirm` | "I had 150g of chicken and 100g of rice" | "yes" | Multi-item loop → batch → confirm |

**`TestFoodLoggingReject`** — 2 turns (log → reject):

| Test | Turn 1 Input | Turn 2 Resume | Key Assertions |
|------|-------------|---------------|----------------|
| `test_single_item_reject` | "I ate 200g of chicken" | "no cancel it" | Turn 2 completes, non-empty response |

**`TestFoodLoggingEdit`** — 3 turns (log → edit → confirm):

| Test | Turn 1 | Turn 2 | Turn 3 | Key Assertions |
|------|--------|--------|--------|----------------|
| `test_edit_then_confirm` | "I ate 200g of chicken" | "change chicken to 300g" | "yes confirm" | Turn 2 re-interrupts, Turn 3 completes |

**`TestConversationMemory`** — keep existing test, update to use `_run` helper:

| Test | Flow | Key Assertions |
|------|------|----------------|
| `test_memory_persists_across_turns` | "Hi my name is Bob" → "What's my name?" | ≥4 messages in state, "Bob" in last message |

---

## TESTING STRATEGY

### Test Execution

```bash
# Full graph-api suite
uv run pytest tests/graph_api/ -v -s

# Single test for debugging
uv run pytest tests/graph_api/test_graph_flows.py::TestFoodLoggingConfirm::test_single_db_item_confirm -v -s
```

### What Success Looks Like

- **Non-interrupt paths**: Pass cleanly
- **Interrupt paths (if no blocking bug)**: Pass with multi-turn flow
- **Interrupt paths (if blocking bug exists)**: Fail with clear message like:
  ```
  FAILED - BlockingError detected (sync call inside async context).
  Thread: abc-123-def
  Debug: Open this thread in LangSmith Studio for the full trace.
  Hint: A node or tool is making a synchronous call that blocks the event loop.
  ```

### Edge Cases

- Graph completes without interrupt when expected → `_assert_interrupted` catches this
- Server not running → conftest auto-starts it
- LLM returns unexpected output → test fails at assertion level, not silently

---

## VALIDATION COMMANDS

### Level 1: Unit Tests (no regressions)
```bash
uv run pytest tests/unit/ -v
```

### Level 2: Graph Compilation (still works)
```bash
uv run pytest tests/graph_api/test_graph_compilation.py -v
```

### Level 3: Full E2E Suite
```bash
uv run pytest tests/graph_api/ -v -s
```

---

## ACCEPTANCE CRITERIA

- [ ] `test_blocking_detection.py` and `test_debug_trace.py` deleted
- [ ] `conftest.py` has no `in_process_graph` fixture or `MemorySaver` import
- [ ] All tests go through HTTP API via `lg_client` (no in-process `ainvoke`)
- [ ] `_run` helper uses `raise_error=False` and produces clear failure messages
- [ ] `BlockingError` failures include thread ID for Studio lookup
- [ ] Non-interrupt paths (chitchat, stats) tested
- [ ] Interrupt paths tested: confirm, reject, edit flows
- [ ] Conversation memory test preserved
- [ ] `uv run pytest tests/unit/ -v` passes (no regressions)

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full test suite passes (unit + graph-api)
- [ ] No linting or type checking errors
- [ ] Acceptance criteria all met

---

## NOTES

- `BlockingError` messages are always generic ("An internal error occurred") because the `blockbuster` package's error type is not whitelisted in `langgraph_api/serde.py`. We can detect the error TYPE but not the original message (e.g., "Blocking call to sqlite3.connect"). For the actual trace, developers must check LangSmith Studio.
- The `_run` helper is the key design decision — centralizing error handling means every path gets blocking detection for free.
- Edit flow test (3 turns) is the most expensive (3+ LLM calls) but also the path most likely to trigger blocking errors since `_apply_edits` calls `calculate_food_macros.ainvoke()`.

**Confidence Score**: 8/10 — The plan is detailed and the patterns are well-understood. Main risk is LLM non-determinism in HITL parsing (e.g., LLM might misinterpret "change chicken to 300g" as confirm instead of edit).
