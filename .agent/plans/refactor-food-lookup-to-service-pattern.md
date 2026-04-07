# Feature: Refactor `food_lookup` to Service + Tool Co-located Pattern

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Eliminate the architectural inconsistency between `src/tools/food_lookup.py` (standalone tools, no service layer) and the rest of the codebase, where every other DB-touching domain follows the **service + co-located @tool wrappers** pattern in `src/services/<domain>_service.py` (see `daily_log_service.py`, `personal_stats_service.py`).

This refactor:

1. Extracts service functions from `food_lookup.py` that accept an explicit `AsyncSession` (DI/testability).
2. Creates `src/services/food_service.py` with services + co-located `@tool` wrappers + the existing pure `compute_food_macros` helper.
3. Deletes `src/tools/food_lookup.py` and the now-empty `src/tools/` directory.
4. Updates all imports in nodes, tests, state schema comment, and the test-engineering skill reference.
5. Updates the project structure tree in `CLAUDE.md`.

The goal is **a single, consistent tool-first pattern across the entire codebase**, so that `.claude/patterns/tool-first.md` can be written against a clean state and not contradict reality on day one.

## User Story

As a FitPal contributor (human or AI agent)
I want every DB-touching domain to follow the same service + co-located tool pattern
So that I can open one file per domain and find services, tools, and helpers without hunting across `src/tools/` and `src/services/`, and so that food tools are testable via session DI like every other tool

## Problem Statement

`src/tools/food_lookup.py` defines three `@tool` functions (`search_food`, `calculate_food_macros`, `create_food_item`) plus a pure helper (`compute_food_macros`) that all touch the DB **directly inside the tool body**. There is no service layer. By contrast, `src/services/daily_log_service.py` and `src/services/personal_stats_service.py` define service functions that accept an explicit `AsyncSession`, with `@tool` wrappers underneath that own their session and delegate to the service.

This split creates two problems:

- **Inconsistent file organization**: food tools live in `src/tools/`, every other domain lives in `src/services/`. New contributors cannot predict where a given tool lives.
- **Lost DI/testability**: food tools cannot be called with an externally-managed session (e.g. for transactional rollback in tests, multi-step transactions, or future CLI/script usage). Tests currently work around this by patching `get_async_db_session` on the module — a fragile pattern that breaks if the import path changes.

A pattern doc (`.claude/patterns/tool-first.md`) is queued to be written next, and it cannot describe a single coherent pattern while `food_lookup.py` exists.

## Solution Statement

Mirror the `daily_log_service.py` template exactly:

1. Create `src/services/food_service.py` with three layers in this order:
   - **Pure helpers** (`compute_food_macros` — no DB, no I/O, used by both the service function and the tool wrapper)
   - **Service functions** (accept `session: AsyncSession`, return ORM objects or primitives) — `search_food_items`, `get_food_by_id`, `create_food_item_record`
   - **`@tool` wrappers** (own their session via `async with get_async_db_session()`, delegate to service functions, return JSON-serializable dicts) — `search_food`, `calculate_food_macros`, `create_food_item`

2. Update the four production import sites (one comment + four node files) and the one test file.

3. Rename `tests/integration/test_food_lookup.py` → `tests/integration/test_food_service.py` to match the module-under-test naming convention used elsewhere in `tests/integration/`.

4. Delete `src/tools/food_lookup.py`. Delete `src/tools/` if no other files remain.

5. Update `CLAUDE.md` project structure tree (remove `src/tools/`, add `food_service.py` under `services/`).

6. Update `.claude/skills/test-engineering/references/integration-testing.md` to use the new patch path in its example.

**No behavior changes.** Tool input schemas, return shapes, and DB queries are preserved exactly. This is purely a structural refactor.

## Feature Metadata

**Feature Type**: Refactor
**Estimated Complexity**: Low
**Primary Systems Affected**:
- `src/services/` (new file)
- `src/tools/` (deleted)
- `src/agents/nodes/` (4 import updates)
- `src/agents/state.py` (1 comment update)
- `tests/integration/` (1 test file rename + import updates)
- `CLAUDE.md` (project tree update)
- `.claude/skills/test-engineering/references/` (1 example update)

**Dependencies**: None — pure structural refactor, no new packages.

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `src/tools/food_lookup.py` (entire file, 101 lines) — **The file being refactored.** Contains `compute_food_macros` (pure helper, lines 13–23), `search_food` (lines 26–56), `calculate_food_macros` (lines 59–72), `create_food_item` (lines 75–100). Preserve every behavior, including the two-tier search (database first, then user-scoped estimated fallback).

- `src/services/daily_log_service.py` (entire file, 220 lines) — **The template to mirror.** Note structure:
  - Module docstring (lines 1–9) explains the dual-layer pattern
  - Imports (lines 11–20)
  - `logger = structlog.get_logger(__name__)` (line 23)
  - Service functions accepting `session: AsyncSession` (lines 26–155)
  - `# ---` separator + `_serialize_log` helper (lines 158–175)
  - `@tool` wrappers (lines 178–220)

- `src/services/personal_stats_service.py` (entire file, 185 lines) — Second example of the same template. Confirms the pattern (separator at line 122–124, service functions above, `@tool` wrappers below).

- `src/agents/nodes/food_search_node.py` (line 6) — `from src.tools.food_lookup import search_food` — needs update.

- `src/agents/nodes/calculate_macros_node.py` (line 11) — `from src.tools.food_lookup import calculate_food_macros` — needs update.

- `src/agents/nodes/confirmation_node.py` (line 13) — `from src.tools.food_lookup import calculate_food_macros` — needs update.

- `src/agents/nodes/commit_node.py` (line 9) — `from src.tools.food_lookup import create_food_item` — needs update.

- `tests/integration/test_food_lookup.py` (entire file, 119 lines) — Tests use `from src.tools.food_lookup import create_food_item, search_food` (line 17) and patch `src.tools.food_lookup.get_async_db_session` (line 26). Both need updating. File should be renamed to `test_food_service.py`.

- `src/agents/state.py` (lines 21–30) — Docstring on `SearchResult` TypedDict says "Mirrors the return type of search_food tool from src/tools/food_lookup.py." Update the path reference.

- `.claude/skills/test-engineering/references/integration-testing.md` (lines 90–117) — Section "3.2 Tool Tests (session patch)" uses `src.tools.food_lookup.get_async_db_session` as the example patch path. Update.

- `CLAUDE.md` (line 65 in the project structure tree) — `│   │   └── food_lookup.py         # Async @tool: search_food, calculate_food_macros, create_food_item + compute_food_macros helper` — needs to be removed from `src/tools/` block and added under `src/services/` block.

- `tests/conftest.py` — Read to understand `async_test_db_session` fixture and `TEST_USER_A`/`TEST_USER_B` constants used by the food tests. No changes needed; just understand the wiring.

### New Files to Create

- `src/services/food_service.py` — New canonical home for food domain. Mirrors `daily_log_service.py` structure: docstring → imports → logger → pure helpers → service functions → separator → `@tool` wrappers.

### Files to Rename

- `tests/integration/test_food_lookup.py` → `tests/integration/test_food_service.py`

### Files to Delete

- `src/tools/food_lookup.py`
- `src/tools/__init__.py` (if it exists)
- `src/tools/` directory itself (only if empty after deletion)

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- `.claude/patterns/runtime-context.md` — Confirms tools accept `user_id: str` (plain string), not `RunnableConfig`. The new service functions and tool wrappers must follow this rule.
- `.claude/patterns/async-patterns.md` — Confirms every node, tool, and service must be `async def` and use `get_async_db_session()`. The new file must comply.
- `.claude/skills/test-engineering/references/integration-testing.md` (sections 3.1 "Service Tests" and 3.2 "Tool Tests") — Two test patterns: services accept session directly, tools require `_patch_session`. Tests for the new file should follow the same split (though for this refactor we keep the existing tool-level tests; service-level tests are out of scope).

### Patterns to Follow

**File structure (mirror `daily_log_service.py` exactly):**

```python
"""Service layer for FoodItem CRUD and macro calculation.

Provides async functions for searching food items, fetching by ID, computing
macros for a given amount, and creating new food entries. All service functions
accept an explicit SQLAlchemy AsyncSession for testability.

Also provides @tool wrappers (search_food, calculate_food_macros, create_food_item)
that own their own session — these are used by graph nodes and are available
for LLM tool-calling.
"""

import uuid as uuid_mod
from typing import Optional

import structlog
from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_async_db_session
from src.models import FoodItem

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Pure helpers — no DB, no I/O
# ---------------------------------------------------------------------------

def compute_food_macros(food: FoodItem, amount_g: float) -> dict:
    """Pure macro calculation — no DB, no I/O."""
    ratio = amount_g / 100.0
    return {
        "name": food.name,
        "amount_g": amount_g,
        "calories": round((food.calories or 0.0) * ratio, 2),
        "protein": round((food.protein or 0.0) * ratio, 2),
        "fat": round((food.fat or 0.0) * ratio, 2),
        "carbs": round((food.carbs or 0.0) * ratio, 2),
    }


# ---------------------------------------------------------------------------
# Service functions — accept session, return ORM objects or primitives
# ---------------------------------------------------------------------------

async def search_food_items(
    session: AsyncSession,
    query: str,
    user_id: str,
) -> list[FoodItem]:
    """Search food items by name. Two-tier: shared database foods first,
    then user-scoped estimated foods as fallback.

    Returns up to 10 FoodItem rows. Empty list if no matches.
    """
    # First: search shared database foods (no user filter)
    stmt = (
        select(FoodItem)
        .where(FoodItem.name.ilike(f"%{query}%"), FoodItem.source == "database")
        .limit(10)
    )
    rows = (await session.execute(stmt)).scalars().all()
    if rows:
        return list(rows)

    # Fallback: search THIS USER's estimated foods
    stmt = (
        select(FoodItem)
        .where(
            FoodItem.name.ilike(f"%{query}%"),
            FoodItem.source == "estimated",
            FoodItem.user_id == uuid_mod.UUID(user_id),
        )
        .limit(10)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def get_food_by_id(
    session: AsyncSession,
    food_id: str,
) -> Optional[FoodItem]:
    """Fetch a single FoodItem by UUID string. Returns None if not found."""
    return await session.get(FoodItem, uuid_mod.UUID(food_id))


async def create_food_item_record(
    session: AsyncSession,
    name: str,
    calories_per_100g: float,
    protein_per_100g: float,
    carbs_per_100g: float,
    fat_per_100g: float,
    user_id: str,
    source: str = "estimated",
) -> FoodItem:
    """Create and persist a new FoodItem row. Commits the session."""
    food_item = FoodItem(
        name=name,
        calories=calories_per_100g,
        protein=protein_per_100g,
        fat=fat_per_100g,
        carbs=carbs_per_100g,
        source=source,
        user_id=uuid_mod.UUID(user_id),
    )
    session.add(food_item)
    await session.commit()
    await session.refresh(food_item)
    return food_item


# ---------------------------------------------------------------------------
# @tool wrappers — own their session, used by graph nodes and LLM tool-calling
# ---------------------------------------------------------------------------

@tool
async def search_food(query: str, user_id: str) -> list[dict]:
    """
    Search for food items by name.
    Returns a list of candidates with ID, Name, and source.
    Searches database foods first, then falls back to estimated foods.
    Use this to find the correct food_id before calculating macros.
    """
    async with get_async_db_session() as session:
        items = await search_food_items(session, query, user_id)
        if items:
            logger.debug("search_food matched", query=query, matched=len(items), source=items[0].source)
        else:
            logger.info("search_food no results from DB or estimated foods", query=query)
        return [{"id": str(i.id), "name": i.name, "source": i.source} for i in items]


@tool
async def calculate_food_macros(food_id: str, amount_g: float) -> dict:
    """
    Calculate nutritional values for a specific food item and amount (in grams).
    Returns dictionary with Name, Calories, Protein, Fat, Carbs.
    """
    async with get_async_db_session() as session:
        food = await get_food_by_id(session, food_id)
        if not food:
            logger.warning("calculate_food_macros: food not found", food_id=food_id)
            return {"error": f"Food item with ID {food_id} not found"}
        result = compute_food_macros(food, amount_g)
        result["source"] = food.source
        return result


@tool
async def create_food_item(
    name: str,
    calories_per_100g: float,
    protein_per_100g: float,
    carbs_per_100g: float,
    fat_per_100g: float,
    source: str = "estimated",
    user_id: str = "",
) -> dict:
    """Create a new FoodItem in the database. Returns the created item's id and name."""
    async with get_async_db_session() as session:
        food_item = await create_food_item_record(
            session=session,
            name=name,
            calories_per_100g=calories_per_100g,
            protein_per_100g=protein_per_100g,
            carbs_per_100g=carbs_per_100g,
            fat_per_100g=fat_per_100g,
            user_id=user_id,
            source=source,
        )
        logger.info("Created food item", name=name, food_id=str(food_item.id), source=source)
        return {"id": str(food_item.id), "name": food_item.name}
```

**Behavior preservation rules (non-negotiable):**

- `search_food` two-tier logic: shared database foods first; if any matches, return them. Only fall back to user-scoped estimated foods if zero database matches. Do **not** combine both sources.
- `search_food` returns dicts with exactly three keys: `id`, `name`, `source`. Match the existing shape.
- `search_food` returns `[]` (not `None`, not error) when nothing is found. Existing behavior.
- `calculate_food_macros` error path returns `{"error": "..."}` — `calculate_macros_node` checks for `"error" in macros` (calculate_macros_node.py:51). Do not change to raising exceptions.
- `compute_food_macros` is a **pure** function. Do not move it inside the tool body. It must remain importable as a standalone helper (even if no node currently imports it directly — keeps the option open).
- `create_food_item` defaults `source="estimated"` and accepts `user_id` as a default-empty string for `@tool` schema compatibility. Do not change defaults.
- `uuid_mod.UUID(user_id)` conversion happens inside service functions (not tool wrappers) — same as `daily_log_service.py::create_log_entry`.

**Naming Conventions:**

- File name: `food_service.py` (matches `daily_log_service.py`, `personal_stats_service.py`, `user_profile_service.py`).
- Service function names: `search_food_items`, `get_food_by_id`, `create_food_item_record` (verb-noun, full domain noun, no abbreviation). Suffix `_record` on `create_food_item_record` disambiguates from the `@tool` named `create_food_item`.
- Tool names: keep existing — `search_food`, `calculate_food_macros`, `create_food_item`. **Do not rename tools.** They are part of the @tool surface and renaming would break the LLM tool-calling contract if anything ever binds them.

**Logging Pattern:**

- `logger = structlog.get_logger(__name__)` at module level.
- Inside `@tool` wrappers, log structured events (`logger.info`, `logger.debug`, `logger.warning`) with kwargs — same as existing food_lookup.py and daily_log_service.py.
- Service functions: no logging required (the wrapper logs).

**Error Handling:**

- `calculate_food_macros` returns `{"error": "..."}` for the not-found case. Caller checks for `"error" in macros`. **Preserve this contract** — it is consumed by `calculate_macros_node.py:51`.
- All other tools return success dicts. No exceptions raised from tools (the LangGraph runtime would translate them into ToolMessage errors which we don't currently handle).

---

## IMPLEMENTATION PLAN

### Phase 1: Create the new service file

Build `src/services/food_service.py` from scratch using the template above. No imports updated yet — the old `food_lookup.py` is still in place. Verify the new file is syntactically valid and importable.

### Phase 2: Update production imports

Update the four node files to import from `src.services.food_service` instead of `src.tools.food_lookup`. Update the comment in `src/agents/state.py`. Verify no remaining imports of `src.tools.food_lookup` in `src/`.

### Phase 3: Migrate the test file

Rename `tests/integration/test_food_lookup.py` → `tests/integration/test_food_service.py`. Update the import line and the patch path. Run the integration test file to confirm it still passes against the new module.

### Phase 4: Delete the old file and update docs

Delete `src/tools/food_lookup.py`. Delete `src/tools/__init__.py` if it exists. Delete the `src/tools/` directory if empty. Update `CLAUDE.md` project structure tree. Update `.claude/skills/test-engineering/references/integration-testing.md` example.

### Phase 5: Full validation

Run the unit + integration test suites to confirm zero regressions. Confirm the graph still compiles via `langgraph dev` (smoke test only — full graph_api suite optional).

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### Task 1 — CREATE `src/services/food_service.py`

- **IMPLEMENT**: New file containing the full module shown in the "Patterns to Follow" section above (docstring, imports, logger, `compute_food_macros`, three service functions, separator, three `@tool` wrappers). Match `daily_log_service.py` structure exactly.
- **PATTERN**: Mirror `src/services/daily_log_service.py` (entire file) and `src/services/personal_stats_service.py` (entire file).
- **IMPORTS**: `import uuid as uuid_mod`, `from typing import Optional`, `import structlog`, `from langchain_core.tools import tool`, `from sqlalchemy import select`, `from sqlalchemy.ext.asyncio import AsyncSession`, `from src.database import get_async_db_session`, `from src.models import FoodItem`.
- **GOTCHA**: Preserve the two-tier search behavior in `search_food_items` exactly — shared `database` foods first, **only fall back** to user-scoped `estimated` foods if zero database matches. Do not merge the two result sets.
- **GOTCHA**: `compute_food_macros` must remain a module-level pure function (not nested inside the tool). Keep it above the service functions or grouped with them — match `daily_log_service.py`'s `_serialize_log` placement style.
- **GOTCHA**: `create_food_item_record` must commit + refresh the session before returning — needed so the caller gets `food_item.id` populated. Mirror `create_log_entry` in `daily_log_service.py` lines 70–73.
- **GOTCHA**: The `@tool create_food_item` must have `source: str = "estimated"` and `user_id: str = ""` as defaults — these are part of the existing tool schema that nodes rely on.
- **VALIDATE**: `uv run python -c "from src.services.food_service import search_food, calculate_food_macros, create_food_item, compute_food_macros, search_food_items, get_food_by_id, create_food_item_record; print('OK')"`

### Task 2 — UPDATE `src/agents/nodes/food_search_node.py`

- **IMPLEMENT**: Change line 6 from `from src.tools.food_lookup import search_food` to `from src.services.food_service import search_food`.
- **PATTERN**: Same import shape, different module.
- **GOTCHA**: Do not change anything else in the file. The node call (`await search_food.ainvoke(...)`) is unchanged.
- **VALIDATE**: `uv run python -c "from src.agents.nodes.food_search_node import food_search_node; print('OK')"`

### Task 3 — UPDATE `src/agents/nodes/calculate_macros_node.py`

- **IMPLEMENT**: Change line 11 from `from src.tools.food_lookup import calculate_food_macros` to `from src.services.food_service import calculate_food_macros`.
- **GOTCHA**: Do not change anything else, including the `"error" in macros` check on line 51.
- **VALIDATE**: `uv run python -c "from src.agents.nodes.calculate_macros_node import calculate_macros_node; print('OK')"`

### Task 4 — UPDATE `src/agents/nodes/confirmation_node.py`

- **IMPLEMENT**: Change line 13 from `from src.tools.food_lookup import calculate_food_macros` to `from src.services.food_service import calculate_food_macros`.
- **VALIDATE**: `uv run python -c "from src.agents.nodes.confirmation_node import confirmation_node; print('OK')"`

### Task 5 — UPDATE `src/agents/nodes/commit_node.py`

- **IMPLEMENT**: Change line 9 from `from src.tools.food_lookup import create_food_item` to `from src.services.food_service import create_food_item`.
- **VALIDATE**: `uv run python -c "from src.agents.nodes.commit_node import commit_node; print('OK')"`

### Task 6 — UPDATE `src/agents/state.py` comment

- **IMPLEMENT**: In the `SearchResult` TypedDict docstring (lines 21–30), change `from src/tools/food_lookup.py.` to `from src/services/food_service.py.`
- **GOTCHA**: This is a docstring/comment only — no code change.
- **VALIDATE**: `grep -c "src/tools/food_lookup" src/agents/state.py` should print `0`. (Use the Grep tool, not bash grep.)

### Task 7 — RENAME `tests/integration/test_food_lookup.py` → `tests/integration/test_food_service.py`

- **IMPLEMENT**: Use `git mv tests/integration/test_food_lookup.py tests/integration/test_food_service.py` so the rename is tracked. Then update the contents:
  - Line 17: `from src.tools.food_lookup import create_food_item, search_food` → `from src.services.food_service import create_food_item, search_food`
  - Line 26: `return patch("src.tools.food_lookup.get_async_db_session", _fake_session)` → `return patch("src.services.food_service.get_async_db_session", _fake_session)`
  - Update the module docstring (lines 1–10) — change `food_lookup tools` to `food_service tools` and update the file's "Scope" line if it mentions the old path.
- **GOTCHA**: The patch path **must** match the module where `get_async_db_session` is **looked up at call time**, which is now `src.services.food_service`. Patching `src.database.get_async_db_session` would not work because `food_service.py` already imported the symbol into its own namespace.
- **VALIDATE**: `uv run pytest tests/integration/test_food_service.py -v`

### Task 8 — DELETE `src/tools/food_lookup.py` and the `src/tools/` directory

- **IMPLEMENT**: `git rm src/tools/food_lookup.py`. Then check if `src/tools/__init__.py` exists — if yes, `git rm src/tools/__init__.py`. Then check if `src/tools/` is empty (ignoring `__pycache__`) — if yes, remove the directory: `rm -rf src/tools/`.
- **GOTCHA**: Do **not** delete the `__pycache__` via git (it's gitignored). After removing the tracked files, the directory should only contain `__pycache__/`, which `rm -rf` will handle.
- **GOTCHA**: Run a final grep before deletion to confirm zero remaining imports in `src/`: see Task 9 validation.
- **VALIDATE**: `uv run python -c "import src.services.food_service; print('OK')"` and confirm `src/tools/` no longer exists: `test ! -d src/tools && echo OK`.

### Task 9 — VERIFY no stale `src.tools.food_lookup` references in source

- **IMPLEMENT**: Run the Grep tool with pattern `src\.tools\.food_lookup` over `src/` and `tests/`. There should be **zero** matches.
- **GOTCHA**: Ignore matches in `.agent/plans/`, `commit_logs/`, and `docs/rca/` — those are historical records and must not be edited.
- **VALIDATE**: Grep tool with pattern `src\.tools\.food_lookup`, paths `src/` and `tests/`, output_mode `files_with_matches` → must return zero files.

### Task 10 — UPDATE `CLAUDE.md` project structure tree

- **IMPLEMENT**: In the "Project Structure" section, locate the `src/services/` block and add this line (after `personal_stats_service.py`, alphabetically ordered):
  ```
  │   │   ├── food_service.py        # Async @tool: search_food, calculate_food_macros, create_food_item + compute_food_macros helper + service layer
  ```
  Then locate the `src/tools/` block (currently `│   ├── tools/` containing only `food_lookup.py`) and **delete those two lines entirely**.
- **GOTCHA**: Tree-character alignment matters for visual rendering. Match the existing indentation/box-drawing characters from the surrounding lines. Use the exact characters from the existing `daily_log_service.py` line.
- **GOTCHA**: Do not touch any other section of CLAUDE.md.
- **VALIDATE**: Read the file and visually confirm the tree renders correctly. Run Grep for `food_lookup` over `CLAUDE.md` — must return zero matches.

### Task 11 — UPDATE `.claude/skills/test-engineering/references/integration-testing.md`

- **IMPLEMENT**: In section "3.2 Tool Tests (session patch)" around lines 90–117, change the example patch path on line 104 from `return patch("src.tools.food_lookup.get_async_db_session", _fake_session)` to `return patch("src.services.food_service.get_async_db_session", _fake_session)`.
- **GOTCHA**: Only update the patch path string. Do not edit any surrounding prose unless it also references the old path.
- **VALIDATE**: Grep for `src.tools.food_lookup` over `.claude/skills/` — must return zero matches.

### Task 12 — RUN unit tests

- **IMPLEMENT**: Run the unit test suite to confirm zero regressions.
- **VALIDATE**: `uv run pytest tests/unit/ -v` → all green.

### Task 13 — RUN integration tests

- **IMPLEMENT**: Run the integration test suite (real Supabase). The renamed `test_food_service.py` is the most important file — it exercises the new module's import path and patch target.
- **VALIDATE**: `uv run pytest tests/integration/ -v` → all green. Pay special attention to `test_food_service.py` and any other test that touches food search/creation.

### Task 14 — SMOKE TEST graph compilation

- **IMPLEMENT**: Confirm the graph still compiles by importing the compiled graph module.
- **VALIDATE**: `uv run python -c "from src.agents.nutritionist import graph; print('graph compiled OK, nodes:', list(graph.nodes))"`.
- **OPTIONAL** (only run if other tasks revealed any issue): `uv run pytest tests/graph_api/ -v -s` for full E2E. Skip this in normal flow — graph_api is slow and is not necessary for a pure import refactor.

---

## TESTING STRATEGY

### Unit Tests

No new unit tests for this refactor. The renamed `test_food_service.py` (formerly `test_food_lookup.py`) lives in `tests/integration/` because it uses a real DB session — that placement is correct and matches the test-tier classification rule (integration = real DB, unit = no DB).

If, after the refactor, you have appetite to add **service-layer tests** (calling `search_food_items(session, ...)` directly without the patch helper), that is a follow-up task — out of scope here. Add a TODO comment in `test_food_service.py` if you want to flag it.

### Integration Tests

The existing 4 tests in `test_food_service.py` (renamed) must pass:

1. `TestSearchFoodSharedAccess::test_shared_db_food_visible_to_all_users` — exercises the database-tier search
2. `TestSearchFoodEstimatedIsolation::test_estimated_food_scoped_to_owner` — exercises user_id scoping on the estimated fallback
3. `TestSearchFoodEstimatedIsolation::test_estimated_food_visible_to_owner` — exercises the estimated-tier search positive case
4. `TestCreateFoodItemSetsUserId::test_created_item_has_user_id` — exercises `create_food_item` setting user_id correctly

These tests collectively verify that:
- The two-tier search behavior is preserved
- User scoping on estimated foods is preserved
- `create_food_item` writes the correct user_id

If any of these fail after the refactor, the new service function implementations have diverged from the old tool implementations — diff carefully against the original `food_lookup.py`.

### Edge Cases

- **Empty result set**: `search_food_items` should return `[]` (not `None`) when no matches. The tool wrapper should still return `[]`. Existing test `test_estimated_food_scoped_to_owner` covers this — it asserts `len(results_b) == 0`.
- **Food not found**: `calculate_food_macros` should return `{"error": "..."}`. No existing test covers this directly, but `calculate_macros_node.py:51` consumes the error path — if the contract changes, the node logic breaks. Verify by reading `calculate_macros_node.py` lines 46–66 after the refactor.
- **Estimated food + UUID conversion**: `search_food_items` calls `uuid_mod.UUID(user_id)`. If `user_id` is malformed, this raises `ValueError`. The original code has the same behavior — preserve it.

### Manual / Visual Verification

After all tasks pass:

1. Read the new `src/services/food_service.py` end-to-end and confirm structure matches `daily_log_service.py` (docstring → imports → logger → services → separator → tools).
2. Read the updated `CLAUDE.md` project structure tree section visually — confirm box-drawing characters render correctly and `src/tools/` is gone.
3. Run `git status` and confirm:
   - **Deleted**: `src/tools/food_lookup.py`
   - **Renamed** (or deleted+added): `tests/integration/test_food_lookup.py` → `tests/integration/test_food_service.py`
   - **Modified**: 4 node files, `state.py`, `CLAUDE.md`, `.claude/skills/test-engineering/references/integration-testing.md`
   - **Added**: `src/services/food_service.py`

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Import Validation

```bash
uv run python -c "from src.services.food_service import search_food, calculate_food_macros, create_food_item, compute_food_macros, search_food_items, get_food_by_id, create_food_item_record; print('food_service OK')"
uv run python -c "from src.agents.nodes.food_search_node import food_search_node; print('food_search_node OK')"
uv run python -c "from src.agents.nodes.calculate_macros_node import calculate_macros_node; print('calculate_macros_node OK')"
uv run python -c "from src.agents.nodes.confirmation_node import confirmation_node; print('confirmation_node OK')"
uv run python -c "from src.agents.nodes.commit_node import commit_node; print('commit_node OK')"
uv run python -c "from src.agents.nutritionist import graph; print('graph compiled, nodes:', list(graph.nodes))"
```

### Level 2: Lint

```bash
uv run ruff check src/services/food_service.py src/agents/nodes/ tests/integration/test_food_service.py
```

### Level 3: Unit Tests

```bash
uv run pytest tests/unit/ -v
```

### Level 4: Integration Tests

```bash
uv run pytest tests/integration/test_food_service.py -v
uv run pytest tests/integration/ -v
```

### Level 5: Stale Reference Check

Use the Grep tool (not bash grep):

- Pattern `src\.tools\.food_lookup`, paths `src/`, `tests/`, `CLAUDE.md`, `.claude/` — must return **zero** matches.
- Pattern `from src/tools/food_lookup`, path `src/agents/state.py` — must return zero matches.
- Pattern `food_lookup`, path `src/` — must return **zero** matches (the comment in `state.py` should be updated).

### Level 6: Filesystem Check

```bash
test ! -d src/tools && echo "src/tools/ removed OK"
test -f src/services/food_service.py && echo "food_service.py exists OK"
test -f tests/integration/test_food_service.py && echo "test_food_service.py exists OK"
test ! -f tests/integration/test_food_lookup.py && echo "test_food_lookup.py removed OK"
```

---

## ACCEPTANCE CRITERIA

- [ ] `src/services/food_service.py` exists and exports `search_food`, `calculate_food_macros`, `create_food_item`, `compute_food_macros`, `search_food_items`, `get_food_by_id`, `create_food_item_record`.
- [ ] `src/services/food_service.py` follows the same structure as `daily_log_service.py` and `personal_stats_service.py` (docstring → imports → logger → helpers/services → separator → `@tool` wrappers).
- [ ] `src/tools/food_lookup.py` is deleted.
- [ ] `src/tools/` directory is deleted (only if empty after removing `food_lookup.py` and `__init__.py`).
- [ ] All four node files import from `src.services.food_service` instead of `src.tools.food_lookup`.
- [ ] `src/agents/state.py` `SearchResult` docstring references the new path.
- [ ] `tests/integration/test_food_lookup.py` is renamed to `tests/integration/test_food_service.py` and its imports + patch path are updated.
- [ ] `CLAUDE.md` project structure tree shows `food_service.py` under `src/services/` and no longer shows `src/tools/`.
- [ ] `.claude/skills/test-engineering/references/integration-testing.md` example uses the new patch path.
- [ ] `uv run pytest tests/unit/ -v` passes with zero failures.
- [ ] `uv run pytest tests/integration/ -v` passes with zero failures.
- [ ] `uv run python -c "from src.agents.nutritionist import graph"` succeeds.
- [ ] Grep for `src.tools.food_lookup` over `src/`, `tests/`, `CLAUDE.md`, `.claude/` returns zero matches.
- [ ] No behavior changes to any tool (input schema, return shape, query semantics all preserved).

---

## COMPLETION CHECKLIST

- [ ] All 14 tasks completed in order
- [ ] Each task validation passed immediately
- [ ] Level 1 import validation passed for all 6 import statements
- [ ] Level 2 lint passed
- [ ] Level 3 unit tests passed
- [ ] Level 4 integration tests passed (especially `test_food_service.py`)
- [ ] Level 5 stale reference check returned zero matches
- [ ] Level 6 filesystem check passed
- [ ] Manual git status review confirms expected file changes
- [ ] CLAUDE.md tree visually rendered correctly

---

## NOTES

### Why this refactor exists

This unblocks `.claude/patterns/tool-first.md`, the next pattern doc in the queue. The doc cannot describe a single coherent "tool-first + service layer" pattern while `food_lookup.py` represents a second, contradictory pattern (tool-only, no service layer). Refactoring the code first means the doc can be written against the truth, not against an aspirational state.

### Why co-location, not split files

Decision made in the planning conversation: keep services and `@tool` wrappers in the same domain file (`*_service.py`). The user prefers one file per domain over a split between `src/services/` and `src/tools/`. Rationale: opening one file shows everything about a domain — services, tools, helpers — without cross-file hunting.

### Why rename the test file

Convention in `tests/integration/` is `test_<module-under-test>.py`. After the refactor, the module under test is `food_service`, so the test file should be `test_food_service.py`. This is a small but important consistency win — it makes the tests trivially discoverable by anyone reading the new service file.

### Why service functions take `session` first

Mirrors `daily_log_service.py::create_log_entry(session, user_id, ...)`. The session-first signature is the convention across all existing service files. This is what enables transactional rollback in tests (the test passes a session bound to a transaction that gets rolled back at teardown) and multi-step transactions (a caller can pass one session to multiple service calls).

### Why we keep `compute_food_macros` as a module-level function

It is pure (no DB, no I/O) and currently only called by `calculate_food_macros` internally. We keep it module-level (rather than nesting inside the tool) for two reasons:

1. **Testability**: Pure functions are trivially unit-testable without any session setup. If/when we add unit tests for macro math, they call `compute_food_macros` directly.
2. **Future flexibility**: If a node ever needs the pure calculation without a DB roundtrip (e.g. for an estimated food where the per-100g values are already known), it can import the helper directly. The RCA at `docs/rca/blocking-error-sync-tools-in-async-nodes.md` notes this was the original motivation for extracting the helper — preserve that.

### Out of scope

- **Service-layer tests** (calling `search_food_items(session, ...)` directly): worth adding as a follow-up but not required for this refactor.
- **Renaming the `@tool` functions**: tool names are part of the LLM tool-calling contract. Even if no LLM currently binds them, renaming them would be a breaking change for any future code that does. Keep `search_food`, `calculate_food_macros`, `create_food_item` exactly as-is.
- **Updating historical plans in `.agent/plans/`** and `commit_logs/`: those are append-only historical records of past decisions and must not be edited.
- **Updating `docs/rca/blocking-error-sync-tools-in-async-nodes.md`**: same — historical record. The reference to the old file is correct in its time-bound context.
- **Writing `.claude/patterns/tool-first.md`**: that is the **next** task after this refactor lands. Not part of this plan.
