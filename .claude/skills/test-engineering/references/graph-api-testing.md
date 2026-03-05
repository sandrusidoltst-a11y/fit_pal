# Graph-API Testing — FitPal

Tests in `tests/graph_api/` cover two categories:

1. **Compilation tests** (`test_graph_compilation.py`): Verify the graph compiles with a real checkpointer and all nodes are registered. Fast, no server needed.
2. **E2E flow tests** (`test_graph_flows.py`): Run the full graph through the `langgraph dev` HTTP server using `langgraph-sdk`. Same API surface as LangSmith Studio.

**Bugs this tier catches that unit tests don't:**
- Import errors or TypedDict mismatches that only surface at compile time
- BlockingErrors (sync-in-async) that only surface under the ASGI server
- Routing failures that occur only on specific graph paths
- State serialization issues across the checkpointer boundary
- HITL interrupt/resume flow failures

---

## 1. Prerequisites

The `langgraph dev` server is **auto-started** by the `conftest.py` session fixture.
No manual server startup is needed — just run the tests:

```bash
uv run pytest tests/graph_api/ -v -s
```

The conftest will:
1. Check if a server is already running on port 2024
2. If not, clean up any orphaned processes on that port
3. Start `uv run langgraph dev` as a subprocess (output → `logs/server.log`)
4. Wait up to 30s for the `/ok` healthcheck to pass
5. Tear down the server (with full process tree cleanup) when tests finish

The assistant name in `langgraph.json` must match the `ASSISTANT_ID` used in tests.

---

## 2. Conftest Fixtures

| Fixture | Scope | Purpose |
|---|---|---|
| `auto_start_langgraph_server` | session, autouse | Auto-starts server if not running; captures output to `logs/server.log`; tears down on exit |
| `lg_client` | function | Returns a `langgraph-sdk` client connected to `http://127.0.0.1:2024` |
| `thread` | function | Creates a fresh thread per test and cleans it up after |

Key implementation details:
- Server stdout/stderr → `tests/graph_api/logs/server.log` (enables traceback extraction on failure)
- On Windows, uses `taskkill /F /T /PID` to kill the entire process tree
- Registers `atexit` handler as a safety net for abnormal exits
- `lg_client` fails fast if the server goes down unexpectedly
- Exposes `_server_log_path` module-level variable for test files to read

**IMPORTANT — conftest import pitfall:** Pytest loads conftest as `graph_api.conftest`, NOT `tests.graph_api.conftest`. When importing from test files, always use:
```python
from graph_api import conftest as _conftest
```

---

## 3. The `_run()` Helper

All tests use the `_run()` helper instead of calling `lg_client.runs.wait()` directly. This centralizes error handling and BlockingError detection.

```python
result = await _run(
    lg_client, thread,
    input={"messages": [{"role": "human", "content": "I ate 200g of chicken"}]},
    test_name="test_single_db_item_confirm",
)
```

**What `_run()` does:**
1. Calls `runs.wait()` with `raise_error=False` to get the raw error dict
2. On any error: extracts the server traceback from `server.log`, saves it as a `.txt` file in `tests/graph_api/logs/`, then calls `pytest.fail()` with the file path
3. On `BlockingError`: the fail message explicitly says it's a sync-in-async issue

**Why `raise_error=False`:** The default `raise_error=True` raises an opaque `Exception("BlockingError: An internal error occurred")`. With `False`, we get the raw `{"__error__": {"error": "BlockingError", "message": "..."}}` dict and can dispatch on error type.

**Why error messages are generic:** `BlockingError` is not whitelisted in `langgraph_api/serde.py`, so the server replaces the message with "An internal error occurred". The error TYPE is preserved. The full traceback with file/line info is only available in the server's stderr, which we capture via `server.log`.

---

## 4. HITL Interrupt Testing Pattern

Food-logging paths hit `interrupt()` at `confirmation_node`. Tests use a multi-turn pattern:

```python
# Turn 1 — send food input, pauses at interrupt
await _run(lg_client, thread, input={...}, test_name=tn)
await _assert_interrupted(lg_client, thread)

# Turn 2 — resume with confirm/reject/edit
result = await _run(lg_client, thread, command={"resume": "yes"}, test_name=tn)
```

`_assert_interrupted()` verifies the graph is paused by checking the `tasks` field from `threads.get_state()`.

For **edit flows** (3 turns): Turn 2 sends an edit (re-interrupts), Turn 3 confirms.

---

## 5. Error Log Structure

On failure, a `.txt` file is saved to `tests/graph_api/logs/`:

```
Test: test_single_item_reject
Thread: 51f079e1-8a60-4e46-867c-7f205ef10d79
Error: BlockingError

Traceback (most recent call last):
  File ".../confirmation_node.py", line 115, in _parse_confirmation
    prompt_path = os.path.join(os.getcwd(), ...)
  ...
blockbuster.blockbuster.BlockingError: Blocking call to os.getcwd
```

The `logs/` directory is gitignored. `server.log` is truncated on each test session.

---

## 6. FitPal Path Matrix — Required Coverage

Every routing path through the graph must have at least one graph-api test.

| Test Class | Path | Turns | Key Behavior |
|---|---|---|---|
| `TestNonInterruptPaths` | `input_parser → response` | 1 | Chitchat, stats — no HITL |
| `TestFoodLoggingConfirm` | `input_parser → ... → confirmation → commit → response` | 2 | DB item, off-menu, multi-item |
| `TestFoodLoggingReject` | `input_parser → ... → confirmation → response` | 2 | Reject skips commit |
| `TestFoodLoggingEdit` | `input_parser → ... → confirmation → (edit loop) → commit → response` | 3 | Edit re-interrupts |
| `TestConversationMemory` | Two chitchat turns on same thread | 2 | Thread state persistence |

---

## 7. Keeping Graph-API Tests Durable

- **Assert on structure, not exact content.** LLM responses are non-deterministic. Assert that a response exists, is non-empty, and doesn't raise — not its exact wording.
- **One path per class.** Each `Test<Path>` class tests one routing branch. Adding a new graph edge = add a new test class.
- **Always use `_run()`.** Never call `runs.wait()` directly — every path gets blocking detection for free.
- **Pass `test_name`.** Food-logging tests should pass `test_name=` so error logs have readable filenames.
- **Server is auto-managed.** The conftest handles startup and teardown. Don't add manual server management to test files.
- **Use a fresh thread per test.** The `thread` fixture is function-scoped so state never bleeds between tests.
- **Run deliberately.** Graph-api tests are slow (real LLM, real server). Never include them in the pre-commit gate. Run with `uv run pytest tests/graph_api/ -v -s`.
