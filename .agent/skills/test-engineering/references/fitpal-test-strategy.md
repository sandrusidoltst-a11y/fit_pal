# FitPal Test Strategy — Rulebook

## 1. Guiding Principle

> **"Test your logic, not your dependencies."**
>
> Unit tests verify code transforms inputs into outputs correctly.
> Integration tests verify the real interface with an external system.
> Graph-api tests verify the graph runs correctly through its HTTP API runtime.
> Never blur the boundary.

---

## 2. Folder Structure

```
tests/
├── conftest.py               # Shared fixtures for ALL test types
├── unit/                     # Fast, deterministic, zero real I/O
├── integration/              # Real DB or real LLM, run deliberately
└── graph_api/                # Full graph flow via langgraph-sdk — see graph-api-testing.md
```

**Rule**: The folder name IS the test type. No `@pytest.mark` decorators needed.

---

## 3. The Three Test Types

### Unit (`tests/unit/`)

- No real LLM API calls — always mock via `patch("src.agents.nodes.X.get_llm_for_node")`
- No real file-based DB — use `async_test_db_session` fixture or mock the service
- Runs in milliseconds — no network, no disk I/O beyond in-memory SQLite
- Deterministic — same input → same result
- Tests ONE unit: a node function, a service method, or a routing function

### Integration (`tests/integration/`)

- Removes exactly one mock to test the real interface with an external system
- Prompt quality: does the real LLM return valid structured output?
- DB access: does `food_search_node` return results from the real `nutrition.db`?
- Graph compilation: does `define_graph()` compile with `MemorySaver`?

### Graph-API (`tests/graph_api/`)

- Runs against a live `langgraph dev` server on `http://localhost:2024`
- Uses `langgraph-sdk` client (`get_client`) — same API surface as LangSmith Studio
- Tests full graph execution through all routing paths
- Catches errors that only surface at API runtime (not at compile time)
- See [graph-api-testing.md](graph-api-testing.md) for full setup and patterns

---

## 4. Mock Boundary Rules

### 4.1 Always Mock in Unit Tests

| Dependency | How to Mock |
|---|---|
| LLM calls | `patch("src.agents.nodes.X.get_llm_for_node")` returning `MagicMock()` |
| Async DB session | `patch("src.agents.nodes.X.get_async_db_session")` + `AsyncMock` for `__aenter__`/`__aexit__` |
| Service layer | `patch("src.agents.nodes.X.daily_log_service")` with `AsyncMock` methods |
| LangChain tools | `patch("src.agents.nodes.X.calculate_food_macros")` + `.invoke.return_value` |

### 4.2 Never Mock These

| Thing | Why |
|---|---|
| `workflow.compile()` | Compilation IS the thing being tested — mocking defeats the purpose |
| `AsyncSession` in service layer tests | Use `async_test_db_session` — mocking session means you're not testing SQL |
| Pydantic schemas | Always use real model instances |
| The `langgraph dev` server in graph-api tests | The server IS the boundary under test |

### 4.3 The Golden Rule

> **Never mock the thing you are directly testing.**
>
> Testing `input_parser_node` → mock its LLM.
> Testing `daily_log_service.create_log_entry` → give it a real DB session.
> Testing `define_graph()` → compile with a real `MemorySaver`.
> Testing a graph routing path → run through the real API server.

---

## 5. Critical Paths — Must Always Have Test Coverage

| Critical Path | Test File | What to Watch |
|---|---|---|
| `define_graph()` compilation | `integration/test_graph_compilation.py` | Must compile with `MemorySaver()` without `TypeError` |
| Input parsing → all `GraphAction` outcomes | `unit/test_input_parser.py` | `LOG_FOOD`, `QUERY_DAILY_STATS`, `CHITCHAT` |
| Routing functions (all branches) | `unit/test_feedback_logic.py` | Every `GraphAction` maps to a valid next node |
| Multi-item loop drain | `unit/test_multi_item_loop.py` | `pending_food_items` reaches `[]` after N iterations |
| Schema enum consistency | `unit/test_state_consistency.py` | `ActionType`, `SelectionStatus`, `GraphAction` stay in sync |
| Service layer write → read | `unit/test_daily_log_service.py` | `create_log_entry` → `get_logs_by_date` returns record |
| Full graph — all routing paths | `graph_api/test_graph_flows.py` | Each path covered: food log, stats, chitchat, no-match |

---

## 6. Shared Fixtures (conftest.py)

**Never duplicate fixtures.** If a fixture appears in more than one test file → it belongs in `tests/conftest.py`.

| Fixture | What it provides |
|---|---|
| `basic_state` | Complete `AgentState` dict with all keys set to empty defaults |
| `async_test_db_session` | Real async in-memory SQLite with `FoodItem(id=1)` seeded |
| `mock_calculate_log_db_session` | Mock `AsyncSession` for `calculate_log_node` |
| `mock_daily_log_service_for_calc` | Mock `daily_log_service` for `calculate_log_node` |
| `mock_calculate_macros` | Mock `calculate_food_macros` tool |
| `mock_stats_db_session` | Mock `AsyncSession` for `stats_node` |
| `mock_daily_log_service_for_stats` | Mock `daily_log_service` for `stats_node` |

---

## 7. When to Write Which Test

| You are writing... | Write in |
|---|---|
| A new node | Unit test mocking LLM + services |
| A new routing function | Unit test with all `GraphAction` branches |
| A new prompt | Integration test (real LLM) verifying structured output shape |
| A new Pydantic schema field | Unit test for node handling + integration test for LLM parsing |
| A new service method | Unit test with `async_test_db_session` |
| A new graph edge or compile change | Integration test with `MemorySaver` + graph-api test for the new path |

---

## 8. When to Run Which Suite

| Trigger | Command | Suite |
|---|---|---|
| After any code change | `uv run pytest tests/unit/ -v` | Unit only |
| After changing a prompt file | `uv run pytest tests/integration/ -v` | Integration only |
| After changing a schema | `uv run pytest tests/ -v` | Unit + Integration |
| Before `/commit` | `uv run pytest tests/unit/ -v` | Unit only — mandatory gate |
| Before PR merge | `uv run pytest tests/ -v && uv run pytest tests/graph_api/ -v -s` | All tiers |
| After changing graph edges/nodes | `uv run pytest tests/graph_api/ -v -s` | Graph-api |
