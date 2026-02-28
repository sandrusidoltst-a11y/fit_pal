# RCA: LangGraph Studio Checkpointer TypeError

## Problem Description
Running `uv run langgraph dev` starts the server but **crashes on every request** with:
```
TypeError: Invalid checkpointer provided. Expected an instance of `BaseCheckpointSaver`, `True`, `False`, or `None`.
Received _AsyncGeneratorContextManager.
```

## Reproduction Steps
1. `cd c:\Users\User\Desktop\fit_pal`
2. `uv run langgraph dev`
3. Open LangSmith Studio in browser and send any message
4. Server returns 500 with the TypeError above

## Root Cause Analysis
**File**: `src/agents/nutritionist.py`, lines 86-88

```python
memory = AsyncSqliteSaver.from_conn_string("data/checkpoints.sqlite")
return workflow.compile(checkpointer=memory)
```

`AsyncSqliteSaver.from_conn_string()` returns an **async context manager** (`_AsyncGeneratorContextManager`), NOT a direct `AsyncSqliteSaver` instance. It must be consumed via `async with`:

```python
async with AsyncSqliteSaver.from_conn_string("...") as memory:
    # `memory` is the actual saver here
```

When passed directly to `workflow.compile()`, LangGraph rejects it because it's not a valid `BaseCheckpointSaver`.

**Additionally**: When using `langgraph dev`, the runtime provides its own in-memory checkpointer automatically. The graph definition should not hardcode its own.

## Broader Codebase Scan

### Affected Files
| File | Impact |
|---|---|
| `src/agents/nutritionist.py` (L86-88) | **Primary bug** — broken checkpointer creation |
| `tests/unit/test_feedback_integration.py` (L23-26) | Mocks `AsyncSqliteSaver` — must be updated to match new signature |
| `src/main.py` (L13) | Calls `define_graph()` — must pass checkpointer for standalone use |
| `inspect_memory.py` (L13) | Legacy sync call — already broken (calls sync on async function) |
| `langgraph.json` (L4) | References `define_graph` — no change needed |

## Proposed Fix
**Strategy**: Separation of concerns — `define_graph()` accepts an optional `checkpointer` parameter.

1. **`nutritionist.py`**: Add `checkpointer=None` parameter to `define_graph()`, remove hardcoded `AsyncSqliteSaver` creation. Keep the import for future callers.
2. **`test_feedback_integration.py`**: Update to pass `MemorySaver` directly instead of mocking `AsyncSqliteSaver`.
3. **`src/main.py`**: Update to create and pass checkpointer via `async with`.

## Validation Commands
```bash
uv run python -m pytest tests/unit/test_feedback_integration.py -v
uv run python -m pytest tests/ -v
uv run langgraph dev  # Manual: verify Studio loads and responds
```
