# FitPal Test Strategy

A project-specific testing contract for the FitPal LangGraph agent. This document defines **what to test, how to test it, where to put tests, and when to run them**. It is the source of truth for all testing decisions.

---

## 1. Guiding Principle

> **"Test your logic, not your dependencies."**
>
> Unit tests verify that your code correctly transforms inputs into outputs.
> Integration tests verify that your code correctly interfaces with external systems.
> Never blur the boundary.

---

## 2. Folder Structure & Responsibilities

```
tests/
├── conftest.py               # Shared fixtures for ALL test types
├── unit/                     # Fast, deterministic, zero real I/O
│   ├── test_input_parser.py       # Node logic, not LLM behavior
│   ├── test_food_search_node.py   # Node logic, not real DB
│   ├── test_agent_selection.py
│   ├── test_calculate_log_node.py
│   ├── test_multi_item_loop.py
│   ├── test_response_node.py
│   ├── test_daily_log_service.py
│   ├── test_daily_log_model.py
│   ├── test_feedback_integration.py  # Graph-level flow test
│   ├── test_feedback_logic.py
│   ├── test_state_consistency.py
│   └── test_stats_node.py
└── integration/              # Slower, real LLM or real DB file, run deliberately
    └── test_llm_prompts.py   # Prompt quality tests — real LLM calls
```

**Rule**: The folder name is the test type. No `@pytest.mark.llm` decorators needed — the folder structure is the organiser.

---

## 3. The Two Test Types

### 3.1 Unit Tests (`tests/unit/`)

**Definition**: A test that calls one function/node directly and mocks all external dependencies.

**Constraints (all must be true):**
- ✅ No real LLM API calls (always mock the LLM)
- ✅ No real file-based DB reads (`nutrition.db`) — use `async_test_db_session` fixture or mock the service
- ✅ Runs in milliseconds — no network, no disk I/O beyond in-memory SQLite
- ✅ Deterministic — same input always produces same result
- ✅ Tests ONE unit (node, service function, routing function)

**What to test:**
- Each node's state mutations (what keys are updated, what values)
- Routing functions — do they return the correct next node for each `GraphAction`?
- Service layer methods with mocked `AsyncSession`
- Schema contract: does the node correctly transform a well-formed LLM response into state?
- Edge cases: empty input, missing fields, error conditions

**What NOT to test in unit tests:**
- Whether the real LLM returns the expected structured output
- Whether the full graph routes end-to-end correctly (→ use integration test)
- Whether `nutrition.db` actually contains food data

### 3.2 Integration Tests (`tests/integration/`)

**Definition**: A test that removes at least one mock and tests the real interface with an external system.

**What to test:**
- **LLM Prompt Quality**: Does the real LLM return a valid `FoodIntakeEvent` for a given user message? Tests in this category call the real API and are explicitly allowed to be slow and occasionally flaky.
- **Graph Compilation**: Does `define_graph()` compile without error using `MemorySaver`? ← **This was the bug we missed.**
- **DB File Access**: Does `food_search_node` return results from the real `nutrition.db`?

**Example:**
```python
# tests/integration/test_llm_prompts.py
async def test_input_parser_real_llm_log_food():
    """Verify real LLM returns valid LOG_FOOD structured output."""
    state = basic_state_factory()
    state["messages"] = [HumanMessage(content="I had 200g of chicken breast")]
    result = input_parser_node(state)
    assert result["last_action"] == "LOG_FOOD"
    assert len(result["pending_food_items"]) >= 1
```

---

## 4. Mock Boundary Rules

These rules determine what must be mocked vs. what must be real.

### 4.1 Always Mock in Unit Tests

| Dependency | How to Mock |
|---|---|
| LLM calls (`get_llm_for_node`) | `patch("src.agents.nodes.X.get_llm_for_node")` returning `MagicMock()` |
| Async DB session (`get_async_db_session`) | `patch` + `AsyncMock` for `__aenter__`/`__aexit__` |
| Service layer functions (in node tests) | `patch("src.agents.nodes.X.daily_log_service")` with `AsyncMock` methods |
| LangChain tools (`calculate_food_macros`) | `patch` + set `.invoke.return_value` |

### 4.2 Never Mock These

| Thing | Why |
|---|---|
| `workflow.compile()` | Compilation IS the thing being tested in graph-level tests — mocking it defeats the purpose |
| `AsyncSession` interface in **service layer tests** | Use `async_test_db_session` fixture (real in-memory SQLite) — mocking session in service tests means you're not testing the SQL |
| Pydantic schemas | Never mock schema validation — test with real model instances |

### 4.3 The Golden Rule

> **Never mock the thing you are directly testing.**
>
> If you are testing `input_parser_node`, mock its LLM dependency.
> If you are testing `daily_log_service.create_log_entry`, give it a real DB session.
> If you are testing `define_graph()`, compile it with a real `MemorySaver`.

---

## 5. Critical Paths — Must Always Have Test Coverage

These flows must never lose test coverage. If you touch these areas, verify their tests still pass.

| Critical Path | Test File | What to Watch |
|---|---|---|
| `define_graph()` compilation | `test_feedback_integration.py` | Must compile with `MemorySaver()` without `TypeError` |
| Input parsing → all `GraphAction` outcomes | `test_input_parser.py` | `LOG_FOOD`, `QUERY_DAILY_STATS`, `CHITCHAT`, `CONFIRM_ESTIMATION` |
| Routing functions (all branches) | `test_feedback_logic.py` | Every `GraphAction` must map to a valid next node |
| Multi-item loop drain | `test_multi_item_loop.py` | `pending_food_items` reaches `[]` after N iterations |
| HITL flow | `test_calculate_log_node.py` | `CONFIRM_ESTIMATION` → `calculate_log_node` → `LOGGED` with `food_id=None` |
| Schema enum consistency | `test_state_consistency.py` | `ActionType`, `SelectionStatus`, `GraphAction` stay in sync |
| Service layer write → read | `test_daily_log_service.py` | `create_log_entry` → `get_logs_by_date` returns correct record |

---

## 6. Shared Fixtures (conftest.py)

**Never duplicate fixtures.** If a fixture appears in more than one test file, it belongs in `conftest.py`.

| Fixture | Location | What it provides |
|---|---|---|
| `basic_state` | `tests/conftest.py` | A complete `AgentState` dict with all keys set to empty defaults |
| `async_test_db_session` | `tests/conftest.py` | Real async in-memory SQLite with `FoodItem(id=1)` seeded |

**Anti-pattern to avoid**: `mock_db_session` and `mock_calculate_macros` are currently duplicated in `test_calculate_log_node.py` and `test_multi_item_loop.py`. These should be moved to `conftest.py`.

---

## 7. When to Write Which Test

**Decision rule:**

> **If you have to mock it to make the test work → it belongs in `unit/`.**
> **If removing the mock IS the whole point → it belongs in `integration/`.**

| You are writing... | Write in |
|---|---|
| A new node | Unit test mocking LLM + services |
| A new routing function | Unit test with all `GraphAction` branches |
| A new prompt | Integration test (real LLM) verifying structured output shape |
| A new Pydantic schema field | Unit test for node handling + integration test for LLM parsing |
| A new service method | Unit test with `async_test_db_session` |
| A new graph edge/compile change | Unit graph-level test with `MemorySaver` |

---

## 8. When to Run Which Suite

| Trigger | Command | Suite |
|---|---|---|
| After **any code change** | `uv run pytest tests/unit/ -v` | Unit only |
| After **changing a prompt file** | `uv run pytest tests/integration/ -v` | Integration only |
| After **changing a schema** (state, input schema) | `uv run pytest tests/ -v` | Both |
| Before **`/commit`** | `uv run pytest tests/unit/ -v` | Unit only — mandatory gate |
| Before **deploying / PR merge** | `uv run pytest tests/ -v` | Both |
| During **active development** of a feature | `uv run pytest tests/unit/test_<specific>.py` | Single file |

### Validation Commands Summary

```bash
# Pre-commit (mandatory, fast ~15s)
uv run pytest tests/unit/ -v

# Full suite (before deploy, ~60s+)
uv run pytest tests/ -v

# Single file (during development)
uv run pytest tests/unit/test_calculate_log_node.py -v

# Last-failed only (fix-and-retry loop)
uv run pytest --lf -v
```

---

## 9. Known Tech Debt

These are existing test files that violate the rules above. They should be refactored when their area of code is next touched.

| File | Issue | Required Fix |
|---|---|---|
| `tests/unit/test_input_parser.py` | Calls real LLM — non-deterministic in unit suite | Refactor to mock `get_llm_for_node`, move real-LLM version to `tests/integration/` |
| `tests/unit/test_food_search_node.py` | Hits real `nutrition.db` file on disk | Mock the DB tool, or move to `tests/integration/` |
| `test_calculate_log_node.py` + `test_multi_item_loop.py` | Duplicate `mock_db_session` and `mock_calculate_macros` fixtures | Move shared fixtures to `tests/conftest.py` |
