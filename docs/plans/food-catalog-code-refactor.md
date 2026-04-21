# Feature: Food Catalog Code Refactor (Phase D + E, prompts deferred)

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Complete refactor of the food-catalog code layer — services, tools, nodes, Pydantic schemas, state TypedDicts, i18n templates, bot HITL renderer, and tests — to consume the two-table schema (`food_items` + `coach_food_mappings`) that landed in Plan 1. Every food read now joins the coach's opinionated overlay (category, tag, serving_amount_g) with the universal food facts. Search is bilingual (Hebrew OR English). The legacy `food_items.name` column is dropped at the end. The LLM prompts that feed these new schemas (input parser, estimation, response generator, confirmation parser) are intentionally **deferred to Plan 3** — the bot will be in a broken end-to-end state between Plan 2 and Plan 3, which is accepted by Dolev.

This is **Plan 2 of 3** in the food catalog refactor:

| Plan | Scope | Status |
|---|---|---|
| Plan 1 | Schema + models + reseed | **Shipped** (commit `bc0f6cc`) |
| **Plan 2 (this doc)** | Services + tools + nodes + schemas + state + i18n + bot gateway + DROP legacy `name` + tests | Ready to execute |
| Plan 3 (later) | LLM prompts only (input parser, estimation, response, confirmation parser) + HITL Hebrew copy iteration + evals | Deferred |

## User Story

As **Dolev** (coach + only trainee during POC),
I want the bot to search foods in Hebrew or English, surface the coach's category and serving size for every food, and render HITL confirmations in the user's language with serving counts,
So that when Plan 3 ships the parser/estimation/response prompts, the bot reasons accurately about servings and renders natively in Hebrew — without any further code changes.

## Problem Statement

Plan 1 landed the two-table schema (93 canonical rows in `food_items` + 93 `coach_food_mappings` rows under `DEFAULT_COACH_ID`) but **no code consumes it yet**. The existing code has four blocking deficiencies:

1. **English-only search** — `food_service.search_food_items` queries `FoodItem.name.ilike(...)` — the legacy single-language column. Hebrew input hits the DB as-is and fails to match English-language catalog rows.
2. **No coach-method awareness** — tools return `{id, name, source}` with no `category` / `tag` / `serving_amount_g`. Downstream nodes can't reason about servings or flag a food as free/forbidden.
3. **No unit/count propagation** — `SingleFoodItem.amount: float` with `unit: Literal["g"]` forces the LLM to guess grams for "2 eggs". The new `default_unit` + `default_unit_weight_g` columns on `food_items` are unused.
4. **HITL renders in the wrong language** — `_format_batch_preview` hardcodes `"{food_name} — {amount_g}g"`. Hebrew users see English names. No serving info surfaces.

The `name` column on `food_items` is dead weight once services migrate to `name_en` / `name_he`, and its presence in the ORM forces callers to decide which column to use.

## Solution Statement

Refactor every file in the food-catalog code path:

1. **Pydantic schemas** (`input_schema.py`, `estimation_schema.py`) — parser emits `{count, unit}`; estimator emits `{name_en, name_he, category, default_unit, default_unit_weight_g, …macros}`.
2. **State TypedDicts** (`state.py`) — `PendingFoodItem`, `SearchResult`, `MacroResult` carry the new fields end-to-end through the graph.
3. **Service layer** (`food_service.py`) — bilingual search via `name_en ILIKE OR name_he ILIKE`; LEFT JOIN `coach_food_mappings` filtered by `coach_id` at SQL level; return `list[(FoodItem, Optional[CoachFoodMapping])]`. Add two pure helpers: `resolve_amount_g(food, unit, count)` (unit→grams) and `compute_servings(amount_g, serving_amount_g)` (grams→servings). Rewrite `create_food_item_record` to accept both languages + optional `category`/`tag` (creates the coach mapping atomically when category is provided).
4. **Tool wrappers** — enriched dicts with `name_en`, `name_he`, `category`, `tag`, `serving_amount_g`, `servings`, `default_unit`, `default_unit_weight_g`.
5. **Nodes** (input, search, selection, calculate_macros, confirmation, commit) — each consumes/produces the new shapes.
6. **i18n** — add `confirmation_serving_line` key; templates use `{servings}` and `{category}` placeholders.
7. **Bot gateway** — `_format_interrupt_value` renders the serving line beneath each item when `servings` is present.
8. **Schema cleanup** — after all code migrates, drop the legacy `food_items.name` column and its model field.
9. **Tests** — every unit + integration test that references the old shapes is updated; add new tests for helpers and bilingual search.

Since the LLM prompts are not touched in Plan 2, the bot will be in an end-to-end broken state between Plan 2 and Plan 3 (the parser prompt still says "extract grams" while the schema expects `count`/`unit`). All **unit and integration tests pass** — Plan 2's correctness gate is tests, not end-to-end bot behavior.

## Feature Metadata

**Feature Type**: Refactor (code-layer rewrite on top of existing schema)
**Estimated Complexity**: High — ~11 source files, ~8 test files, 1 bot file, 1 migration, 2 i18n YAMLs, ~25 tasks, one PR
**Primary Systems Affected**: `src/services/food_service.py`, `src/agents/nodes/*`, `src/schemas/*`, `src/agents/state.py`, `src/i18n/*`, `bot/gateway.py`, `src/scripts/seed_canonical_catalog.py`, `src/models.py`
**Dependencies**: Plan 1 shipped (commit `bc0f6cc`): `coach_food_mappings` table exists, `food_items` has `name_en`/`name_he`/`default_unit`/`default_unit_weight_g`, 93 canonical rows seeded, `DEFAULT_COACH_ID` constant in `src/config.py`

---

## CONTEXT REFERENCES

### Relevant Codebase Files — IMPORTANT: YOU MUST READ THESE BEFORE IMPLEMENTING

**Source (to modify):**
- `src/services/food_service.py` (entire file, ~190 lines) — current single-table English-only implementation. Every function + tool wrapper gets rewritten.
- `src/models.py` (lines 13-40 FoodItem, lines 66-109 CoachFoodMapping from Plan 1) — `name` field gets removed from `FoodItem`.
- `src/config.py` (lines 22-28 for `USER_TIMEZONE`, `DEFAULT_COACH_ID`; line 25-29 for `serialize_timestamp`) — import `DEFAULT_COACH_ID` for service layer.
- `src/agents/state.py` (lines 8-95) — TypedDicts that flow through graph; `PendingFoodItem`, `SearchResult`, `MacroResult`, `ProcessingResult` all need new fields.
- `src/schemas/input_schema.py` (lines 16-45) — `SingleFoodItem.unit` currently `Literal["g"]`; widen. Add `count`.
- `src/schemas/estimation_schema.py` (entire file, ~20 lines) — add name/category/unit fields.
- `src/schemas/selection_schema.py` — no changes (already returns `food_id` + status).
- `src/schemas/confirmation_schema.py` — no changes in Plan 2 (edits still use `new_amount_g`; unit-aware edits are Plan 3+).
- `src/agents/nodes/input_node.py` (lines 34-82) — parser node calls LLM with `FoodIntakeEvent` schema; state update propagates `pending_food_items`.
- `src/agents/nodes/food_search_node.py` (entire file, ~33 lines) — thin wrapper around `search_food` tool.
- `src/agents/nodes/selection_node.py` (entire file, ~84 lines) — builds `search_context` string with `{r['name']}`.
- `src/agents/nodes/calculate_macros_node.py` (entire file, ~126 lines) — DB path calls `calculate_food_macros`; estimation path calls LLM with `MacroEstimation` schema. Builds `MacroResult`.
- `src/agents/nodes/confirmation_node.py` (lines 30-58 `_format_batch_preview`, lines 61-128 main loop, lines 131-150 `_parse_confirmation`, lines 153-197 `_apply_edits`).
- `src/agents/nodes/commit_node.py` (lines 14-102) — iterates `pending_confirmations`, creates `FoodItem` for estimated rows, calls `log_food_entry`.
- `src/i18n/__init__.py` (lines 33-59 `Messages` TypedDict) — add new keys. Startup parity check refuses boot on drift.
- `src/i18n/en.yaml` and `src/i18n/he.yaml` (lines 32-38 and 35-42 respectively, HITL confirmation section).
- `src/scripts/seed_canonical_catalog.py` (lines 94-130 INSERT SQL) — remove `name` column from INSERT.
- `bot/gateway.py` (lines 156-193 `_format_interrupt_value`) — iterates `items`, formats via i18n template.

**Patterns (mandatory reading):**
- `docs/patterns/tool-first.md` (entire file) — service/tool dual-layer. Every DB access goes through `@tool` from async nodes.
- `docs/patterns/async-patterns.md` (entire file) — `async def`, `await tool.ainvoke(...)`, `async with get_async_db_session() as session`.
- `docs/patterns/runtime-context.md` (entire file) — `runtime.context.user_id` flows into tool params as a plain string.
- `docs/patterns/llm-config.md` (entire file) — `get_llm_for_node()` centralises models; `.with_structured_output(Schema)` for typed outputs.
- `docs/patterns/schema-management.md` (entire file) — migration rules (production uses Supabase migrations, never `create_all()`).
- `docs/patterns/hitl-confirmation.md` — preview payload format, `interrupt()` pattern, Command routing.

**Tests (to update):**
- `tests/conftest.py` (lines 40-112, SEED fixture) — seeded `Test Chicken` row must switch to `name_en`; add a paired `coach_food_mappings` row so tests exercise the JOIN.
- `tests/integration/test_food_service.py` (entire file, 118 lines) — assertions reference `r["name"]`; seeds raw `FoodItem(name="...")`.
- `tests/integration/test_daily_log_model.py` (line 148: `log.food_item.name == "Test Chicken"`).
- `tests/unit/test_food_search_node.py` (entire file, 60 lines).
- `tests/unit/test_calculate_macros_node.py` (entire file, ~230 lines) — mocks `calculate_food_macros`; extensive `PendingFoodItem` fixtures use `amount` / `unit: "g"`.
- `tests/unit/test_confirmation_node.py` (entire file, ~225 lines) — SAMPLE_BATCH, `_format_batch_preview` assertions.
- `tests/unit/test_commit_node.py` (entire file, ~275 lines) — `mock_create_food_item.ainvoke` call args assertions.
- `tests/unit/test_input_parser.py` — FoodIntakeEvent test fixtures (need to update unit/count).

### New Files to Create

- `tests/unit/test_food_service_helpers.py` — new unit tests for `resolve_amount_g` and `compute_servings` pure helpers.

### Files to Update

Comprehensive list (cross-reference against acceptance criteria):
```
src/services/food_service.py       # rewrite
src/models.py                      # drop `name` field from FoodItem
src/agents/state.py                # TypedDicts
src/schemas/input_schema.py        # SingleFoodItem
src/schemas/estimation_schema.py   # MacroEstimation
src/agents/nodes/input_node.py
src/agents/nodes/food_search_node.py
src/agents/nodes/selection_node.py
src/agents/nodes/calculate_macros_node.py
src/agents/nodes/confirmation_node.py
src/agents/nodes/commit_node.py
src/i18n/__init__.py               # Messages TypedDict
src/i18n/en.yaml
src/i18n/he.yaml
bot/gateway.py                     # _format_interrupt_value
src/scripts/seed_canonical_catalog.py  # drop name from INSERT
tests/conftest.py
tests/integration/test_food_service.py
tests/integration/test_daily_log_model.py
tests/unit/test_food_search_node.py
tests/unit/test_calculate_macros_node.py
tests/unit/test_confirmation_node.py
tests/unit/test_commit_node.py
tests/unit/test_input_parser.py
```

### Migrations to Apply (via Supabase MCP)

- **`drop_legacy_food_items_name_column`** — runs AFTER all code migrates. Single statement: `ALTER TABLE food_items DROP COLUMN name;`.

### Relevant Documentation (SHOULD READ)

- [SQLAlchemy 2.x Select with outerjoin (async)](https://docs.sqlalchemy.org/en/20/orm/queryguide/query.html#select) — LEFT JOIN returning tuples pattern
  - Why: `search_food_items` and `get_food_by_id` need `select(FoodItem, CoachFoodMapping).outerjoin(...)` that returns `(FoodItem, CoachFoodMapping | None)` tuples
- [Pydantic v2 Field + Literal](https://docs.pydantic.dev/2.0/api/fields/#pydantic.fields.Field) — schema definitions
  - Why: `SingleFoodItem.unit` widens from `Literal["g"]` to a larger set matching the canonical catalog's `default_unit` values

---

## PATTERNS TO FOLLOW

### Service-tool dual layer (from `docs/patterns/tool-first.md`)

Service functions accept `session: AsyncSession` for testability. @tool wrappers own their session via `async with get_async_db_session() as session:`. Nodes call tools via `await tool.ainvoke({"k": v, …})` — never import sessions directly.

### Async DB access (from `docs/patterns/async-patterns.md`)

- All services and nodes are `async def`.
- DB calls use `await session.execute(stmt)`.
- Never call a sync @tool from an async node (would trigger `BlockingError` in the ASGI sandbox — see `docs/rca/blocking-error-sync-tools-in-async-nodes.md`).

### Runtime context (from `docs/patterns/runtime-context.md`)

- `runtime: Runtime[ContextSchema]` flows through nodes.
- `runtime.context.user_id` is a string; nodes pass it to `tool.ainvoke({"user_id": user_id, …})`.

### Structured logging

```python
logger = structlog.get_logger(__name__)
logger.info("search_food matched", query=query, matched=len(items), language="he")
```

### LLM with structured output (from `docs/patterns/llm-config.md`)

```python
llm = get_llm_for_node("estimation_node")
structured_llm = llm.with_structured_output(MacroEstimation)
result = await structured_llm.ainvoke([SystemMessage(...), HumanMessage(...)])
# result is a Pydantic model — access fields as attributes; .model_dump() only at state-write boundary
```

### LEFT JOIN returning tuples (new pattern introduced by Plan 2)

```python
from sqlalchemy import select
from src.models import FoodItem, CoachFoodMapping
from src.config import DEFAULT_COACH_ID

stmt = (
    select(FoodItem, CoachFoodMapping)
    .outerjoin(
        CoachFoodMapping,
        (CoachFoodMapping.food_id == FoodItem.id)
        & (CoachFoodMapping.coach_id == coach_id),
    )
    .where(
        (FoodItem.name_en.ilike(f"%{query}%") | FoodItem.name_he.ilike(f"%{query}%"))
        & (FoodItem.source == "database")
    )
    .limit(10)
)
result = await session.execute(stmt)
rows = result.all()  # list[Row[(FoodItem, CoachFoodMapping | None)]]
return [(row[0], row[1]) for row in rows]
```

When LEFT JOIN has no match (food has no coach mapping yet), the second element of the tuple is `None` (SQLAlchemy detects NULL PK and returns None instead of constructing an empty object).

### Serialization pattern at @tool boundary

```python
def _serialize_food_with_mapping(
    food: FoodItem, mapping: Optional[CoachFoodMapping]
) -> dict:
    """Convert (FoodItem, Optional[CoachFoodMapping]) tuple to JSON-safe dict."""
    return {
        "id": str(food.id),
        "name_en": food.name_en,
        "name_he": food.name_he,
        "source": food.source,
        "default_unit": food.default_unit,
        "default_unit_weight_g": food.default_unit_weight_g,
        "category": mapping.category if mapping else None,
        "tag": mapping.tag if mapping else None,
        "serving_amount_g": mapping.serving_amount_g if mapping else None,
    }
```

### i18n parity check (from `src/i18n/__init__.py`)

Adding a new user-facing string requires:
1. Add key to `Messages` TypedDict
2. Add same key to BOTH `en.yaml` and `he.yaml` with non-empty string
3. Startup will refuse to boot on any drift

---

## IMPLEMENTATION PLAN

### Phase D.1 — Schemas (Pydantic)

**Why first**: Schemas are the contract that every downstream layer depends on. Widen `SingleFoodItem.unit`; rename `amount` → `count`; add optional `unit_count` semantics via `count`. Extend `MacroEstimation` with name + category + unit fields.

### Phase D.2 — State TypedDicts

**Why second**: `PendingFoodItem`, `SearchResult`, `MacroResult`, `ProcessingResult` propagate data across nodes. Update them to carry the new fields end-to-end.

### Phase D.3 — Service + helpers

**Why third**: `food_service.py` is the single source of truth for food data. Nodes can't be updated until the service returns the new shape. Helpers (`resolve_amount_g`, `compute_servings`) get added here.

### Phase D.4 — Tool wrappers

**Why fourth**: @tool wrappers bridge service output to tool dicts. Must be updated before nodes consume them.

### Phase D.5 — Nodes

**Why fifth**: Nodes consume tools + produce state. Update in dependency order: input → search → selection → calculate_macros → confirmation → commit.

### Phase D.6 — i18n + bot gateway

**Why sixth**: HITL message rendering depends on the preview payload shape from `confirmation_node`. The i18n keys must exist before the bot consumes them.

### Phase D.7 — Seed script + migration + model field drop

**Why seventh**: Drop the legacy `name` column ONLY after all code migrates. Order: update seed script → update model → apply migration → rerun seed → verify.

### Phase D.8 — Tests

**Why last**: Tests mirror the new shapes. Update every fixture + assertion. Add new helper tests.

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### Task 1 — UPDATE `src/schemas/input_schema.py`

- **IMPLEMENT**: Replace `SingleFoodItem.amount: float` and `SingleFoodItem.unit: Literal["g"]` with:
  - `count: float` — numeric quantity (preserves previous `amount` semantics for `unit="g"` callers)
  - `unit: Literal["g", "piece", "slice", "scoop", "bottle", "cup", "tbsp", "tsp", "can"]` — widened to match the canonical catalog's `default_unit` values
  - Keep `food_name`, `original_text` unchanged
- **PATTERN**: Mirror the pydantic style already in the file (Field with description). Keep `default_factory=list` on `FoodIntakeEvent.items`.
- **IMPORTS** (already present): `from pydantic import BaseModel, Field`; `from typing import Literal`.
- **GOTCHA**: The parser LLM still reads the old prompt that says "extract grams" — it may produce `unit="g"` with `count=100` for "2 eggs" (incorrect but schema-valid). That's fine — Plan 3 fixes the prompt.
- **VALIDATE**:
  ```bash
  uv run python -c "from src.schemas.input_schema import SingleFoodItem; \
    item = SingleFoodItem(food_name='egg', count=2.0, unit='piece', original_text='2 eggs'); \
    print(item.model_dump())"
  ```
  Expect: `{'food_name': 'egg', 'count': 2.0, 'unit': 'piece', 'original_text': '2 eggs'}`.

### Task 2 — UPDATE `src/schemas/estimation_schema.py`

- **IMPLEMENT**: Extend `MacroEstimation` with:
  - `name_en: str` — English name (LLM generates/translates)
  - `name_he: str` — Hebrew name (LLM generates/translates)
  - `category: Optional[Literal["protein", "carb", "fat", "free", "free_calories", "forbidden_main"]]` — LLM's best guess, optional
  - `tag: Optional[Literal["lean", "medium", "fatty"]]` — LLM's best guess, optional (applies to proteins)
  - `default_unit: Optional[Literal[…same set as input_schema…]]` — the unit the user would naturally say (e.g., "piece" for eggs)
  - `default_unit_weight_g: Optional[float]` — weight of one natural unit (e.g., 50 for an egg)
  - Keep existing `calories`, `protein`, `carbs`, `fat` fields (these are per-amount macros, not per-100g — the node back-calculates per-100g in `commit_node`)
- **PATTERN**: Mirror existing Field(description=...) style.
- **IMPORTS**: Add `from typing import Literal, Optional` (currently absent).
- **GOTCHA**: The estimation prompt (Plan 3) will teach the LLM to produce these fields correctly. In Plan 2, the LLM may emit nulls for the new fields — all are `Optional` so this doesn't break schema validation.
- **VALIDATE**:
  ```bash
  uv run python -c "from src.schemas.estimation_schema import MacroEstimation; \
    m = MacroEstimation(calories=200, protein=20, carbs=15, fat=5, \
      name_en='Test', name_he='בדיקה', category=None, tag=None, \
      default_unit=None, default_unit_weight_g=None); print(m.model_dump())"
  ```

### Task 3 — UPDATE `src/agents/state.py`

- **IMPLEMENT**: Four TypedDicts to update:
  - **`PendingFoodItem`**: rename `amount: float` → `count: float`; widen `unit: str` (already `str`, semantically now matches Pydantic Literal set)
  - **`SearchResult`**: replace `name: str` with `name_en: str` + `name_he: Optional[str]`. Add `category: Optional[str]`, `tag: Optional[str]`. Keep `id`, `source`. Intentionally do NOT include `serving_amount_g`, `default_unit`, or `default_unit_weight_g` — `selection_node` doesn't use them, and `calculate_macros_node` fetches them fresh via `get_food_by_id`. Keeping search "partial" and calculate "full" mirrors today's architecture (see note at end of this plan about the double-query pattern).
  - **`MacroResult`**: rename `food_name` → `name_en` + add `name_he: Optional[str]`. Add `category: Optional[str]`, `tag: Optional[str]`, `servings: Optional[float]`, `default_unit: Optional[str]`, `default_unit_weight_g: Optional[float]`. Keep `amount_g`, `calories`, `protein`, `carbs`, `fat`, `source`, `original_text`, `food_id`.
  - **`ProcessingResult`**: it inherits from `PendingFoodItem` so the rename `amount` → `count` flows automatically. But `ProcessingResult` is built in `commit_node` / `calculate_macros_node` with explicit keys — update those call sites to use `count` instead of `amount`.
- **PATTERN**: Mirror existing TypedDict style in the file.
- **IMPORTS** (already present): `from typing import Annotated, List, Literal, Optional, TypedDict`.
- **GOTCHA**: `PendingFoodItem` doc comment mentions "Mirrors SingleFoodItem". Update the comment to match new field names. `SearchResult` doc mentions "Mirrors search_food tool" — comment stays accurate (tool signature updates in Task 11).
- **VALIDATE**:
  ```bash
  uv run python -c "from src.agents.state import PendingFoodItem, SearchResult, MacroResult; \
    p: PendingFoodItem = {'food_name': 'egg', 'count': 2.0, 'unit': 'piece', 'original_text': '2 eggs'}; \
    print(p)"
  ```

### Task 4 — REWRITE `src/services/food_service.py` (core service functions + helpers)

- **IMPLEMENT**: Full rewrite of the pure helpers and service functions. Replace the entire file top-to-bottom. Structure:
  1. Imports (add `CoachFoodMapping`, `DEFAULT_COACH_ID`, `Tuple`)
  2. Pure helpers (no DB, no I/O): `resolve_amount_g`, `compute_servings`, `compute_food_macros`
  3. Service functions (accept `session`): `search_food_items`, `get_food_by_id`, `create_food_item_record`
  4. @tool wrappers (Task 11): `search_food`, `calculate_food_macros`, `create_food_item`
- **PATTERN**: Structure matches today's file layout (section comments separating layers). Preserve structlog logger.
- **IMPORTS**:
  ```python
  import uuid as uuid_mod
  from typing import Optional, Tuple

  import structlog
  from langchain_core.tools import tool
  from sqlalchemy import select
  from sqlalchemy.ext.asyncio import AsyncSession

  from src.config import DEFAULT_COACH_ID
  from src.database import get_async_db_session
  from src.models import CoachFoodMapping, FoodItem
  ```
- **GOTCHA**: `DEFAULT_COACH_ID` is `uuid.UUID` not string — pass directly to SQLAlchemy queries (which accept UUID objects for Uuid columns).
- Pure helpers specification:

```python
def resolve_amount_g(food: FoodItem, unit: str, count: float) -> float:
    """Convert a (unit, count) tuple to grams using the food's unit definition.

    - unit == "g" (or food has no default_unit): count is already grams → return count
    - unit matches food.default_unit: return count * food.default_unit_weight_g
    - unit mismatch: raise ValueError (caller handles as FAILED processing result)
    """
    if unit == "g":
        return count
    if food.default_unit is None or food.default_unit_weight_g is None:
        # Food has no per-unit weight; fall back to treating count as grams
        return count
    if unit != food.default_unit:
        raise ValueError(
            f"Unit mismatch: user gave {unit!r}, food {food.name_en!r} expects {food.default_unit!r}"
        )
    return count * food.default_unit_weight_g


def compute_servings(amount_g: float, serving_amount_g: Optional[float]) -> Optional[float]:
    """Compute serving count from grams; None when the food has no serving definition.

    None semantics: free veggies, forbidden_main foods — serving concept doesn't apply.
    """
    if serving_amount_g is None or serving_amount_g == 0:
        return None
    return round(amount_g / serving_amount_g, 2)


def compute_food_macros(
    food: FoodItem,
    mapping: Optional[CoachFoodMapping],
    amount_g: float,
) -> dict:
    """Pure macro calculation + mapping enrichment. No DB, no I/O.

    Returns the shape consumed by tools and nodes downstream.
    """
    ratio = amount_g / 100.0
    return {
        "id": str(food.id),
        "name_en": food.name_en,
        "name_he": food.name_he,
        "source": food.source,
        "amount_g": amount_g,
        "calories": round((food.calories or 0.0) * ratio, 2),
        "protein": round((food.protein or 0.0) * ratio, 2),
        "fat": round((food.fat or 0.0) * ratio, 2),
        "carbs": round((food.carbs or 0.0) * ratio, 2),
        "default_unit": food.default_unit,
        "default_unit_weight_g": food.default_unit_weight_g,
        "category": mapping.category if mapping else None,
        "tag": mapping.tag if mapping else None,
        "serving_amount_g": mapping.serving_amount_g if mapping else None,
        "servings": compute_servings(
            amount_g, mapping.serving_amount_g if mapping else None
        ),
    }
```

- **VALIDATE** (part 1 of 5):
  ```bash
  uv run ruff check src/services/food_service.py
  uv run python -c "from src.services.food_service import resolve_amount_g, compute_servings, compute_food_macros; print('helpers ok')"
  ```

### Task 5 — REWRITE `search_food_items` in `src/services/food_service.py`

- **IMPLEMENT**: Bilingual LEFT JOIN, two-tier (database → estimated fallback), returns list of tuples.

```python
async def search_food_items(
    session: AsyncSession,
    query: str,
    user_id: str,
    coach_id: uuid_mod.UUID = DEFAULT_COACH_ID,
) -> list[Tuple[FoodItem, Optional[CoachFoodMapping]]]:
    """Search food items by name (bilingual: EN or HE). Two-tier:
    1. Shared database foods first.
    2. User-scoped estimated foods as fallback.

    Each result tuple is (FoodItem, Optional[CoachFoodMapping]) — mapping is
    scoped to the given coach_id; None if the food has no mapping for that coach.
    """
    name_filter = FoodItem.name_en.ilike(f"%{query}%") | FoodItem.name_he.ilike(f"%{query}%")

    # Tier 1: shared database
    stmt_db = (
        select(FoodItem, CoachFoodMapping)
        .outerjoin(
            CoachFoodMapping,
            (CoachFoodMapping.food_id == FoodItem.id)
            & (CoachFoodMapping.coach_id == coach_id),
        )
        .where(name_filter & (FoodItem.source == "database"))
        .limit(10)
    )
    rows = (await session.execute(stmt_db)).all()
    if rows:
        logger.debug(
            "search_food_items matched database tier",
            query=query,
            matched=len(rows),
            with_mapping=sum(1 for r in rows if r[1] is not None),
        )
        return [(r[0], r[1]) for r in rows]

    # Tier 2: user-scoped estimated
    stmt_est = (
        select(FoodItem, CoachFoodMapping)
        .outerjoin(
            CoachFoodMapping,
            (CoachFoodMapping.food_id == FoodItem.id)
            & (CoachFoodMapping.coach_id == coach_id),
        )
        .where(
            name_filter
            & (FoodItem.source == "estimated")
            & (FoodItem.user_id == uuid_mod.UUID(user_id))
        )
        .limit(10)
    )
    rows = (await session.execute(stmt_est)).all()
    logger.debug(
        "search_food_items matched estimated tier",
        query=query,
        matched=len(rows),
        with_mapping=sum(1 for r in rows if r[1] is not None),
    )
    return [(r[0], r[1]) for r in rows]
```

- **PATTERN**: Two-tier behavior unchanged from current implementation (line 57-78 of old file).
- **IMPORTS**: Already covered by Task 4's imports.
- **GOTCHA**:
  - `FoodItem.name_en.ilike(...) | FoodItem.name_he.ilike(...)` — SQLAlchemy overloads `|` for OR. `NULL ILIKE` returns NULL, which in boolean context is treated as false — works correctly.
  - `uuid_mod.UUID(user_id)` — user_id comes in as a string; convert to UUID for the Uuid column.
  - `result.all()` returns `Row` objects; indexing `r[0]` (FoodItem) and `r[1]` (CoachFoodMapping | None) unpacks them.
- **VALIDATE**: Will run integration tests in Task 24 — no isolated validation.

### Task 6 — REWRITE `get_food_by_id` in `src/services/food_service.py`

- **IMPLEMENT**: Same LEFT JOIN pattern, scoped to a single food_id.

```python
async def get_food_by_id(
    session: AsyncSession,
    food_id: str,
    coach_id: uuid_mod.UUID = DEFAULT_COACH_ID,
) -> Optional[Tuple[FoodItem, Optional[CoachFoodMapping]]]:
    """Fetch a single FoodItem by UUID string, joined with its coach mapping
    (if any) for the given coach_id. Returns None if food not found.
    """
    stmt = (
        select(FoodItem, CoachFoodMapping)
        .outerjoin(
            CoachFoodMapping,
            (CoachFoodMapping.food_id == FoodItem.id)
            & (CoachFoodMapping.coach_id == coach_id),
        )
        .where(FoodItem.id == uuid_mod.UUID(food_id))
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    return (row[0], row[1])
```

- **GOTCHA**: `first()` returns None if no row. `row[0]` is FoodItem, `row[1]` is `Optional[CoachFoodMapping]`.
- **VALIDATE**: See Task 24.

### Task 7 — REWRITE `create_food_item_record` in `src/services/food_service.py`

- **IMPLEMENT**: New signature; creates food + optional coach mapping atomically.

```python
async def create_food_item_record(
    session: AsyncSession,
    name_en: str,
    name_he: Optional[str],
    calories_per_100g: float,
    protein_per_100g: float,
    carbs_per_100g: float,
    fat_per_100g: float,
    user_id: str,
    default_unit: Optional[str] = None,
    default_unit_weight_g: Optional[float] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    serving_amount_g: Optional[float] = None,
    source: str = "estimated",
    coach_id: uuid_mod.UUID = DEFAULT_COACH_ID,
) -> Tuple[FoodItem, Optional[CoachFoodMapping]]:
    """Create a FoodItem. If `category` is provided, also create the paired
    CoachFoodMapping row atomically in the same transaction.

    Returns (FoodItem, Optional[CoachFoodMapping]).
    """
    food_item = FoodItem(
        name_en=name_en,
        name_he=name_he,
        calories=calories_per_100g,
        protein=protein_per_100g,
        fat=fat_per_100g,
        carbs=carbs_per_100g,
        default_unit=default_unit,
        default_unit_weight_g=default_unit_weight_g,
        source=source,
        user_id=uuid_mod.UUID(user_id) if user_id else None,
    )
    session.add(food_item)
    await session.flush()  # make food_item.id available for the mapping FK

    mapping: Optional[CoachFoodMapping] = None
    if category is not None:
        mapping = CoachFoodMapping(
            food_id=food_item.id,
            coach_id=coach_id,
            category=category,
            tag=tag,
            serving_amount_g=serving_amount_g,
        )
        session.add(mapping)

    await session.commit()
    await session.refresh(food_item)
    if mapping is not None:
        await session.refresh(mapping)

    return (food_item, mapping)
```

- **PATTERN**: Session flush before FK-dependent insert — standard SQLAlchemy.
- **GOTCHA**: `user_id` is positional (string); `name_he` is positional (optional); all "overlay" fields (unit, unit_weight, category, tag, serving_amount_g) are kwargs with defaults. Don't accidentally make `user_id` optional — callers always know the user_id (commit_node passes runtime.context.user_id).
- **VALIDATE**: See Task 24 (integration test creates food item with all fields).

### Task 8 — UPDATE `@tool search_food` in `src/services/food_service.py`

- **IMPLEMENT**: Replace the existing wrapper:

```python
@tool
async def search_food(query: str, user_id: str) -> list[dict]:
    """Search for food items by name (bilingual — Hebrew or English).

    Returns a list of candidates with id, name_en, name_he, source, category, tag,
    serving_amount_g, default_unit, default_unit_weight_g. Database foods first,
    then estimated fallback. Use this to find the correct food_id before calculating macros.
    """
    async with get_async_db_session() as session:
        results = await search_food_items(session, query, user_id)
        if results:
            first_food, first_mapping = results[0]
            logger.debug(
                "search_food matched",
                query=query,
                matched=len(results),
                tier=first_food.source,
                first_has_mapping=first_mapping is not None,
            )
        else:
            logger.info("search_food no results from DB or estimated foods", query=query)
        return [_serialize_food_candidate(food, mapping) for food, mapping in results]


def _serialize_food_candidate(
    food: FoodItem, mapping: Optional[CoachFoodMapping]
) -> dict:
    """Convert (FoodItem, Optional[CoachFoodMapping]) tuple into a minimal
    JSON-safe candidate dict for selection_node.

    Intentionally omits serving_amount_g / default_unit / default_unit_weight_g:
    selection doesn't use them, and calculate_food_macros fetches them fresh
    via get_food_by_id. See plan note on the double-query pattern.
    """
    return {
        "id": str(food.id),
        "name_en": food.name_en,
        "name_he": food.name_he,
        "source": food.source,
        "category": mapping.category if mapping else None,
        "tag": mapping.tag if mapping else None,
    }
```

- **GOTCHA**: The serializer helper lives next to the @tool wrapper — keep it private (`_serialize_food_candidate`). Do NOT include full macros (calories/protein/etc.) in search results; nodes can call `calculate_food_macros` for that once they've selected an id.
- **VALIDATE**: See Task 24.

### Task 9 — UPDATE `@tool calculate_food_macros` in `src/services/food_service.py`

- **IMPLEMENT**:

```python
@tool
async def calculate_food_macros(food_id: str, amount_g: float) -> dict:
    """Calculate nutritional values + coach mapping fields for a food item at a given amount in grams.

    Returns a dict with: name_en, name_he, amount_g, calories, protein, fat, carbs,
    source, category, tag, serving_amount_g, servings, default_unit, default_unit_weight_g.
    Returns `{"error": "..."}` if food is not found.
    """
    async with get_async_db_session() as session:
        result = await get_food_by_id(session, food_id)
        if result is None:
            logger.warning("calculate_food_macros: food not found", food_id=food_id)
            return {"error": f"Food item with ID {food_id} not found"}
        food, mapping = result
        return compute_food_macros(food, mapping, amount_g)
```

- **GOTCHA**: `compute_food_macros` (pure helper from Task 4) already produces the enriched dict shape. No need for a separate serializer here.
- **VALIDATE**: See Task 24.

### Task 10 — UPDATE `@tool create_food_item` in `src/services/food_service.py`

- **IMPLEMENT**:

```python
@tool
async def create_food_item(
    name_en: str,
    calories_per_100g: float,
    protein_per_100g: float,
    carbs_per_100g: float,
    fat_per_100g: float,
    user_id: str,
    name_he: Optional[str] = None,
    default_unit: Optional[str] = None,
    default_unit_weight_g: Optional[float] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    serving_amount_g: Optional[float] = None,
    source: str = "estimated",
) -> dict:
    """Create a new FoodItem (optionally with a coach mapping).

    If `category` is provided, a paired coach_food_mappings row is also created
    atomically. Returns the created item's id, name_en, name_he, and whether a
    mapping was created.
    """
    async with get_async_db_session() as session:
        food, mapping = await create_food_item_record(
            session=session,
            name_en=name_en,
            name_he=name_he,
            calories_per_100g=calories_per_100g,
            protein_per_100g=protein_per_100g,
            carbs_per_100g=carbs_per_100g,
            fat_per_100g=fat_per_100g,
            user_id=user_id,
            default_unit=default_unit,
            default_unit_weight_g=default_unit_weight_g,
            category=category,
            tag=tag,
            serving_amount_g=serving_amount_g,
            source=source,
        )
        logger.info(
            "Created food item",
            name_en=name_en,
            name_he=name_he,
            food_id=str(food.id),
            source=source,
            mapping_created=mapping is not None,
        )
        return {
            "id": str(food.id),
            "name_en": food.name_en,
            "name_he": food.name_he,
            "mapping_created": mapping is not None,
        }
```

- **GOTCHA**: `user_id` is required (positional) — matches the model's `nullable=True` but the estimation path always has a user_id (from runtime context).
- **VALIDATE**:
  ```bash
  uv run ruff check src/services/food_service.py
  uv run python -c "from src.services.food_service import search_food, calculate_food_macros, create_food_item, resolve_amount_g, compute_servings, compute_food_macros; print('all exports ok')"
  ```

### Task 11 — UPDATE `src/agents/nodes/input_node.py`

- **IMPLEMENT**: State update uses new `PendingFoodItem` shape. The parser emits `SingleFoodItem` (with `count`/`unit`); the node calls `.model_dump()` which produces a dict matching the new TypedDict.
- The existing line 61 `"pending_food_items": [item.model_dump() for item in result.items]` works automatically once `SingleFoodItem` has `count`/`unit` — the model_dump reflects the new field names.
- **GOTCHA**: No prompt change — Plan 2 deliberately keeps `prompts/input_parser.md` untouched. Plan 3 updates it.
- **VALIDATE**:
  ```bash
  uv run python -c "from src.agents.nodes.input_node import input_parser_node; print('imports ok')"
  ```

### Task 12 — UPDATE `src/agents/nodes/food_search_node.py`

- **IMPLEMENT**: No functional changes — the node passes `food_name` to `search_food.ainvoke`. The enriched return shape flows automatically into `state["search_results"]`.
- **VALIDATE**:
  ```bash
  uv run python -c "from src.agents.nodes.food_search_node import food_search_node; print('imports ok')"
  ```

### Task 13 — UPDATE `src/agents/nodes/selection_node.py`

- **IMPLEMENT**: Update the `search_context` builder (line 54-56) to use `name_en` instead of `name`, and surface category/tag for LLM selection quality:

```python
search_context = "Search results:\n" + "\n".join(
    [
        f"- ID {r['id']}: {r['name_en']}"
        + (f" / {r['name_he']}" if r.get('name_he') else "")
        + (f" [{r['category']}{',' + r['tag'] if r.get('tag') else ''}]" if r.get('category') else "")
        for r in search_results
    ]
)
```

Example output for a Hebrew chicken breast row:
```
- ID uuid-123: Chicken breast / חזה עוף [protein,lean]
```

- **GOTCHA**: `r.get('name_he')` handles None (estimated foods may have no Hebrew name). `r.get('category')` handles missing mapping. Plan 3 updates `prompts/agent_selection.md` to teach the LLM to use category/tag for selection.
- **VALIDATE**:
  ```bash
  uv run python -c "from src.agents.nodes.selection_node import agent_selection_node; print('imports ok')"
  ```

### Task 14 — UPDATE `src/agents/nodes/calculate_macros_node.py`

- **IMPLEMENT**: Significant changes:
  1. DB path: resolve unit/count to amount_g via `resolve_amount_g`, then call `calculate_food_macros`, then build MacroResult with new fields (name_en, name_he, category, tag, servings, default_unit, default_unit_weight_g).
  2. Estimation path: call LLM with extended `MacroEstimation`, build MacroResult with the LLM-provided name_en/name_he/category/tag/default_unit/default_unit_weight_g.

- Concrete update (DB path, replacing lines 46-78):

```python
# current_item now has `count` and `unit` instead of `amount`
current_item = pending_items[0]
count = current_item.get("count", 0.0)
unit = current_item.get("unit", "g")
food_name = current_item.get("food_name", "")

if selected_food_id:
    # DB path — fetch food first to resolve unit, then calculate macros
    async with get_async_db_session() as session:
        row = await get_food_by_id(session, selected_food_id)
    if row is None:
        # food vanished — treat as NO_MATCH path
        result_item = {
            **current_item,
            "status": "FAILED",
            "message": f"Could not find food {food_name} with id {selected_food_id}",
        }
        remaining = pending_items[1:]
        return {
            "pending_food_items": remaining,
            "processing_results": state.get("processing_results", []) + [result_item],
            "last_action": "NO_MATCH",
            "selected_food_id": None,
        }
    food, mapping = row
    try:
        amount_g = resolve_amount_g(food, unit, count)
    except ValueError as e:
        logger.warning("Unit resolution failed", food=food.name_en, unit=unit, error=str(e))
        result_item = {
            **current_item,
            "status": "FAILED",
            "message": str(e),
        }
        remaining = pending_items[1:]
        return {
            "pending_food_items": remaining,
            "processing_results": state.get("processing_results", []) + [result_item],
            "last_action": "NO_MATCH",
            "selected_food_id": None,
        }

    macros = await calculate_food_macros.ainvoke(
        {"food_id": selected_food_id, "amount_g": amount_g}
    )
    # macros already contains name_en/name_he/category/tag/servings/etc.
    macro_result: MacroResult = {
        "name_en": macros["name_en"],
        "name_he": macros.get("name_he"),
        "amount_g": amount_g,
        "calories": macros["calories"],
        "protein": macros["protein"],
        "carbs": macros["carbs"],
        "fat": macros["fat"],
        "source": macros.get("source", "database"),
        "category": macros.get("category"),
        "tag": macros.get("tag"),
        "serving_amount_g": macros.get("serving_amount_g"),
        "servings": macros.get("servings"),
        "default_unit": macros.get("default_unit"),
        "default_unit_weight_g": macros.get("default_unit_weight_g"),
        "original_text": current_item.get("original_text", ""),
        "food_id": selected_food_id,
    }
```

- Estimation path update (replacing lines 79-85 and _estimate_macros):

```python
else:
    # Estimation path — use LLM. unit is "g" for estimated; count == amount_g.
    # (Plan 3 estimation prompt may ask LLM to generate default_unit + default_unit_weight_g
    #  so future logs of the same food can use natural units.)
    amount_g = count if unit == "g" else count  # fallback: treat count as grams when no food exists yet
    logger.info("Estimating macros via LLM", food=food_name, amount_g=amount_g)
    macro_result = await _estimate_macros(
        food_name, amount_g, current_item.get("original_text", "")
    )
```

And `_estimate_macros` is updated:

```python
async def _estimate_macros(
    food_name: str, amount_g: float, original_text: str
) -> MacroResult:
    """Use LLM to estimate macros for an off-menu food item."""
    llm = get_llm_for_node("estimation_node")
    structured_llm = llm.with_structured_output(MacroEstimation)

    messages = [
        SystemMessage(content=_ESTIMATION_PROMPT),
        HumanMessage(content=f"Estimate macros for: {food_name}, amount: {amount_g}g"),
    ]

    result = await structured_llm.ainvoke(messages)

    # serving_amount_g not surfaced by estimation schema (Plan 3 may add it);
    # compute_servings(amount_g, None) returns None — which is correct semantics.
    return {
        "name_en": result.name_en,
        "name_he": result.name_he,
        "amount_g": amount_g,
        "calories": round(result.calories, 1),
        "protein": round(result.protein, 1),
        "carbs": round(result.carbs, 1),
        "fat": round(result.fat, 1),
        "source": "estimated",
        "category": result.category,
        "tag": result.tag,
        "serving_amount_g": None,
        "servings": None,
        "default_unit": result.default_unit,
        "default_unit_weight_g": result.default_unit_weight_g,
        "original_text": original_text,
        "food_id": None,
    }
```

- **IMPORTS**: Add `from src.services.food_service import get_food_by_id, resolve_amount_g, calculate_food_macros` (keep `calculate_food_macros` import from before).
- **GOTCHA**: 
  - `get_food_by_id` is an async service function (not a @tool), so the node must open a session via `async with get_async_db_session() as session`.
  - The DB path now makes TWO queries per item (one for the food fetch, one for macros via `calculate_food_macros` which opens its own session). That's acceptable for Plan 2; Plan 3 may consolidate into a single call if needed.
  - Actually reconsider — the duplication is wasteful. Alternative: pass the (food, mapping) tuple through, compute macros inline. Since `calculate_food_macros` tool is still used by `confirmation_node._apply_edits` (line 178), we need to keep the tool. But inside this node, we can use the pure `compute_food_macros` helper directly:

```python
# Revised DB path — single query:
food, mapping = row
try:
    amount_g = resolve_amount_g(food, unit, count)
except ValueError as e:
    ...

macros = compute_food_macros(food, mapping, amount_g)  # pure function, no DB
macro_result: MacroResult = {
    "name_en": macros["name_en"],
    ...  # same as above
}
```

This is cleaner. The session opened for `get_food_by_id` closes after the fetch; `compute_food_macros` is pure. Two fewer round-trips to Supabase per item.

- **VALIDATE**:
  ```bash
  uv run python -c "from src.agents.nodes.calculate_macros_node import calculate_macros_node, _estimate_macros; print('imports ok')"
  ```

### Task 15 — UPDATE `src/agents/nodes/confirmation_node.py`

- **IMPLEMENT**: Update `_format_batch_preview` to render the user's language based on `BOT_LANGUAGE` env var, add servings info. Update `_apply_edits` to handle the new `MacroResult` shape.

`_format_batch_preview` replacement (lines 30-58):

```python
def _format_batch_preview(items: list[MacroResult]) -> dict:
    """Build human-readable batch preview payload for interrupt.

    Renders the food name in the user's language (he if BOT_LANGUAGE=he).
    Includes servings + category info per item when available.
    """
    lang = os.environ.get("BOT_LANGUAGE", "en").lower()
    formatted_items = []
    for i, item in enumerate(items):
        source_tag = MESSAGES["confirmation_estimated_tag"] if item["source"] == "estimated" else ""
        name = item.get("name_he") if lang == "he" and item.get("name_he") else item["name_en"]
        formatted_items.append(
            {
                "index": i,
                "description": f"{name} — {item['amount_g']}g{source_tag}",
                "calories": item["calories"],
                "protein": item["protein"],
                "carbs": item["carbs"],
                "fat": item["fat"],
                "source": item["source"],
                "servings": item.get("servings"),
                "category": item.get("category"),
            }
        )

    totals = {
        "calories": round(sum(it["calories"] for it in items), 1),
        "protein": round(sum(it["protein"] for it in items), 1),
        "carbs": round(sum(it["carbs"] for it in items), 1),
        "fat": round(sum(it["fat"] for it in items), 1),
    }

    return {
        "question": MESSAGES["confirmation_question"],
        "items": formatted_items,
        "totals": totals,
    }
```

`_apply_edits` update: `item["food_id"]` branch already works (still uses `calculate_food_macros` tool). For the estimated branch (lines 188-196), update the scaled values to use the new `name_en`/`name_he` keys — actually no, the scaling only touches macros (calories/protein/carbs/fat), not names. So `_apply_edits` doesn't need changes beyond the fact that `item` now has different keys for the name — but the function doesn't reference `item["food_name"]`, it only mutates numeric fields. ✅

Update `_parse_confirmation` batch_context string (lines 136-139):

```python
batch_context = "\n".join(
    f"[{i}] {item.get('name_he') or item['name_en']} — {item['amount_g']}g ({item['source']})"
    for i, item in enumerate(batch)
)
```

- **IMPORTS**: Add `import os` (already present).
- **GOTCHA**: The reject branch (lines 98-111) builds `failed_results` dicts with `"food_name": item["food_name"]` — this is the OLD key. Update to use the new shape:

```python
failed_results.append(
    {
        "food_name": item["name_en"],  # ProcessingResult's food_name (to be renamed in state update)
        "count": item["amount_g"],  # amount_g in grams after resolution
        "unit": "g",
        "original_text": item["original_text"],
        "status": "FAILED",
        "message": f"User rejected logging {item['name_en']}",
        "source": item.get("source"),
    }
)
```

Wait — ProcessingResult inherits from PendingFoodItem which now has `count`/`unit` (renamed from `amount`/`unit`). But the confirmation_node's rejected items have already gone through unit resolution (`amount_g` is set). So `count: item["amount_g"]` with `unit: "g"` is a post-resolution representation. That's consistent.

- **VALIDATE**:
  ```bash
  uv run python -c "from src.agents.nodes.confirmation_node import _format_batch_preview, confirmation_node; print('imports ok')"
  ```

### Task 16 — UPDATE `src/agents/nodes/commit_node.py`

- **IMPLEMENT**: Update `create_food_item.ainvoke` call (lines 48-60) with the new signature. Also update the `processing_results` append (lines 76-86) to use `name_en` instead of `food_name` (ProcessingResult keys align with PendingFoodItem's `count`/`unit`).

```python
# Replace lines 48-60:
if item.get("source") == "estimated" and food_id is None and item["amount_g"] > 0:
    amount_g = item["amount_g"]
    created = await create_food_item.ainvoke(
        {
            "name_en": item["name_en"],
            "name_he": item.get("name_he"),
            "calories_per_100g": round((item["calories"] / amount_g) * 100, 2),
            "protein_per_100g": round((item["protein"] / amount_g) * 100, 2),
            "carbs_per_100g": round((item["carbs"] / amount_g) * 100, 2),
            "fat_per_100g": round((item["fat"] / amount_g) * 100, 2),
            "default_unit": item.get("default_unit"),
            "default_unit_weight_g": item.get("default_unit_weight_g"),
            "category": item.get("category"),
            "tag": item.get("tag"),
            "serving_amount_g": item.get("serving_amount_g"),
            "user_id": user_id,
        },
    )
    food_id = created["id"]
```

Processing results append (replace lines 76-86):

```python
processing_results.append(
    {
        "food_name": item["name_en"],  # legacy key name, value is the English name
        "count": item["amount_g"],     # post-resolution grams
        "unit": "g",
        "original_text": item.get("original_text", ""),
        "status": "LOGGED",
        "message": f"Logged {item['name_en']} ({item['calories']}kcal)",
        "source": item.get("source"),
    }
)
```

- **GOTCHA**: `ProcessingResult` TypedDict inherits from `PendingFoodItem` which was renamed (`amount` → `count`). The key `food_name` remains in ProcessingResult for now as the display name — don't rename, just populate from `name_en`.
- Alternative consideration: should `ProcessingResult` also gain a `name_he` field? Yes — useful for response_node to acknowledge the logged meal in Hebrew. Add it.

Update `src/agents/state.py` `ProcessingResult`:
```python
class ProcessingResult(PendingFoodItem):
    status: Literal["LOGGED", "FAILED"]
    message: str
    source: Optional[Literal["database", "estimated"]]
    name_he: Optional[str]  # Hebrew name for bilingual response rendering
```

And commit_node appends with `"name_he": item.get("name_he")`:

```python
processing_results.append(
    {
        "food_name": item["name_en"],
        "name_he": item.get("name_he"),
        "count": item["amount_g"],
        "unit": "g",
        "original_text": item.get("original_text", ""),
        "status": "LOGGED",
        "message": f"Logged {item['name_en']} ({item['calories']}kcal)",
        "source": item.get("source"),
    }
)
```

- **VALIDATE**:
  ```bash
  uv run python -c "from src.agents.nodes.commit_node import commit_node; print('imports ok')"
  ```

### Task 17 — UPDATE `src/i18n/__init__.py`

- **IMPLEMENT**: Add two new keys to `Messages` TypedDict (between `confirmation_reply_hint` and the existing block closer):

```python
# --- HITL serving info (bot-rendered) ---
confirmation_serving_line: str
confirmation_category_label_protein: str
confirmation_category_label_carb: str
confirmation_category_label_free: str
confirmation_category_label_free_calories: str
confirmation_category_label_forbidden_main: str
```

- **GOTCHA**: Minimal scope — Plan 2 adds the keys and makes the bot gateway render them. Plan 3 may iterate on exact wording. Adding category labels as separate keys lets YAML specify the Hebrew word for each category (e.g., "מנת חלבון" for protein serving).
- **VALIDATE**:
  ```bash
  uv run python -c "from src.i18n import MESSAGES, Messages; \
    from typing import get_type_hints; \
    print(sorted(get_type_hints(Messages).keys()))"
  ```

### Task 18 — UPDATE `src/i18n/en.yaml` and `src/i18n/he.yaml`

- **IMPLEMENT**: Add the new keys to both files.

**en.yaml** (append to the HITL section):
```yaml
confirmation_serving_line: "~{servings} {category_label} serving(s)"
confirmation_category_label_protein: "protein"
confirmation_category_label_carb: "carb"
confirmation_category_label_free: "free"
confirmation_category_label_free_calories: "free-calorie"
confirmation_category_label_forbidden_main: "low-GI"
```

**he.yaml** (append to the HITL section):
```yaml
confirmation_serving_line: "~{servings} מנת {category_label}"
confirmation_category_label_protein: "חלבון"
confirmation_category_label_carb: "פחמימה"
confirmation_category_label_free: "חופשי"
confirmation_category_label_free_calories: "קלוריות חופשיות"
confirmation_category_label_forbidden_main: "GI נמוך"
```

- **GOTCHA**: Startup parity check refuses boot if any key is missing or empty. Add the SAME keys to BOTH YAMLs.
- **VALIDATE**:
  ```bash
  uv run python -c "from src.i18n import MESSAGES; print(MESSAGES['confirmation_serving_line'])"
  ```

### Task 19 — UPDATE `bot/gateway.py` `_format_interrupt_value`

- **IMPLEMENT**: Insert a servings line below the macro line for each item when `servings` is not None:

```python
def _format_interrupt_value(value: dict) -> str:
    sections: list[str] = []

    question = value.get("question", "")
    if question:
        sections.append(question)

    item_blocks: list[str] = []
    for item in value.get("items", []):
        desc = item.get("description", "")
        cals = item.get("calories", 0)
        protein = item.get("protein", 0)
        carbs = item.get("carbs", 0)
        fat = item.get("fat", 0)
        servings = item.get("servings")
        category = item.get("category")

        macro_line = MESSAGES["confirmation_macro_line"].format(
            cals=cals, protein=protein, carbs=carbs, fat=fat
        )

        lines = [desc, macro_line]
        if servings is not None and category is not None:
            category_label_key = f"confirmation_category_label_{category}"
            category_label = MESSAGES.get(category_label_key, category)  # fallback to raw category
            lines.append(
                MESSAGES["confirmation_serving_line"].format(
                    servings=servings, category_label=category_label
                )
            )
        item_blocks.append("\n".join(lines))

    if item_blocks:
        sections.append("\n\n".join(item_blocks))

    totals = value.get("totals")
    if totals:
        sections.append(
            MESSAGES["confirmation_total_line"].format(
                cals=totals.get("calories", 0),
                protein=totals.get("protein", 0),
                carbs=totals.get("carbs", 0),
                fat=totals.get("fat", 0),
            )
        )

    sections.append(MESSAGES["confirmation_reply_hint"])
    return "\n\n".join(sections)
```

- **GOTCHA**: `MESSAGES.get(key, fallback)` — if the category label key doesn't exist (e.g., LLM emits an unknown category in an estimated item), fall back to the raw string. `MESSAGES` is a TypedDict but at runtime it's a plain dict, so `.get` works.
- **VALIDATE**:
  ```bash
  uv run python -c "from bot.gateway import _format_interrupt_value; \
    payload = {'question': 'Q', 'items': [{'description': 'Chicken — 200g', 'calories': 330, 'protein': 62, 'carbs': 0, 'fat': 7.2, 'servings': 2.0, 'category': 'protein'}], 'totals': {'calories': 330, 'protein': 62, 'carbs': 0, 'fat': 7.2}}; \
    print(_format_interrupt_value(payload))"
  ```

### Task 20 — UPDATE `src/scripts/seed_canonical_catalog.py`

- **IMPLEMENT**: Remove the legacy `name` column from the INSERT SQL. Replace the INSERT block (lines 107-126):

```python
food_result = conn.execute(
    text(
        """
        INSERT INTO food_items (
            name_en, name_he, calories, protein, fat, carbs,
            default_unit, default_unit_weight_g, source
        )
        VALUES (
            :name_en, :name_he, :calories, :protein, :fat, :carbs,
            :default_unit, :default_unit_weight_g, 'database'
        )
        RETURNING id
        """
    ),
    {
        "name_en": item["name_en"],
        "name_he": item["name_he"],
        "calories": item["calories"],
        "protein": item["protein"],
        "fat": item["fat"],
        "carbs": item["carbs"],
        "default_unit": item["default_unit"],
        "default_unit_weight_g": item["default_unit_weight_g"],
    },
)
```

- **GOTCHA**: Do NOT run the script yet — the `name` column is still `NOT NULL` in Supabase at this point. Running would fail. The script is updated in preparation for Task 22 (after the column is dropped).
- **VALIDATE** (parse-only, don't seed):
  ```bash
  uv run ruff check src/scripts/seed_canonical_catalog.py
  uv run python -c "
  import sys; sys.path.insert(0, 'src/scripts')
  from seed_canonical_catalog import parse_csv
  items = parse_csv()
  assert len(items) == 93
  print('parsed', len(items), 'rows')
  "
  ```

### Task 21 — UPDATE `src/models.py` (remove legacy `name` field from FoodItem)

- **IMPLEMENT**: Delete the `name: Mapped[str] = mapped_column(String, nullable=False, index=True)` line from the `FoodItem` class. Keep `name_en` and `name_he`.
- **GOTCHA**:
  - Must happen AFTER all code references to `FoodItem.name` are removed. The grep in scoping pass shows: `food_service.py` (5 refs, all rewritten above), `tests/conftest.py`, `tests/integration/test_food_service.py`, `tests/integration/test_daily_log_model.py`, `notebooks/evaluate_lookup.ipynb`. All source + test files are updated in earlier / later tasks; the notebook is ignorable (stale eval artifact).
  - After dropping from the model, any lingering `FoodItem(name=...)` call raises `TypeError` at ORM layer — that's our correctness gate.
- **VALIDATE**:
  ```bash
  # Should show NO references to FoodItem.name or food_item.name in source (tests are updated in later tasks)
  grep -rn "FoodItem\.name\b\|food\.name\b\|food_item\.name\b" src/ bot/ | grep -v "name_en\|name_he"
  # Expect: zero hits (or hits only in test files, which are updated in Tasks 25+)
  uv run python -c "from src.models import FoodItem; \
    cols = [c.name for c in FoodItem.__table__.columns]; \
    assert 'name' not in cols, f'name still in columns: {cols}'; \
    assert 'name_en' in cols and 'name_he' in cols; \
    print('model OK')"
  ```

### Task 22 — APPLY Supabase migration: drop legacy `name` column

- **IMPLEMENT**: Use `mcp__supabase__apply_migration` with name `drop_legacy_food_items_name_column` and SQL:

```sql
ALTER TABLE food_items DROP COLUMN name;
```

- **GOTCHA**: If any Python code still references `FoodItem.name`, subsequent queries will fail with `UndefinedColumn`. Task 21 validation ensures zero references before this migration runs.
- **VALIDATE**:
  ```sql
  -- Via mcp__supabase__execute_sql
  SELECT column_name FROM information_schema.columns
  WHERE table_name = 'food_items' ORDER BY ordinal_position;
  -- Expect NOT to contain 'name'; should contain name_en, name_he, default_unit, default_unit_weight_g, etc.
  ```

### Task 23 — RERUN seed script

- **IMPLEMENT**: Execute the updated seed script against Supabase. This wipes the existing 93 `database`-source rows (which still had the now-dropped `name` column's values preserved via the original backfill) and reinserts them with the new INSERT SQL.
- **Command**:
  ```bash
  uv run python src/scripts/seed_canonical_catalog.py --target supabase
  ```
- **GOTCHA**: Script may run successfully but insert duplicate `coach_food_mappings` rows if re-run — protected by the `UNIQUE (food_id, coach_id)` constraint from Plan 1 (rerun fails on conflict). The script's `DELETE FROM coach_food_mappings WHERE coach_id = :coach_id` handles this.
- **VALIDATE**:
  ```sql
  -- Via mcp__supabase__execute_sql
  SELECT COUNT(*) FROM food_items WHERE source = 'database';
  -- Expect: 93
  SELECT COUNT(*) FROM coach_food_mappings;
  -- Expect: 93
  SELECT name_en, name_he FROM food_items WHERE source = 'database' LIMIT 3;
  -- Expect: English + Hebrew names for canonical foods
  ```

### Task 24 — UPDATE `tests/conftest.py`

- **IMPLEMENT**:
  1. `SEED_FOOD_ID` stays the same.
  2. Replace the `sample_food` fixture (lines 92-102) to use `name_en`/`name_he` and create a paired `coach_food_mappings` row under `DEFAULT_COACH_ID`:

```python
from src.models import CoachFoodMapping, FoodItem
from src.config import DEFAULT_COACH_ID

# ... inside async_test_db_session fixture, replace sample_food block:

# Seed with sample food item for testing (Plan 1 canonical shape)
sample_food = FoodItem(
    id=uuid_mod.UUID(SEED_FOOD_ID),
    name_en="Test Chicken",
    name_he="עוף לבדיקה",
    calories=165.0,
    protein=31.0,
    fat=3.6,
    carbs=0.0,
    default_unit="g",
    default_unit_weight_g=None,
    source="database",
    user_id=None,  # shared
)
session.add(sample_food)
await session.flush()

sample_mapping = CoachFoodMapping(
    food_id=sample_food.id,
    coach_id=DEFAULT_COACH_ID,
    category="protein",
    tag="lean",
    serving_amount_g=100.0,
    active=True,
)
session.add(sample_mapping)
await session.flush()  # visible within TX
```

- **GOTCHA**: `CoachFoodMapping.coach_id` must exist in `auth.users` via FK (Postgres-level). `DEFAULT_COACH_ID` = Dolev's production user UUID which definitely exists. ✅
- **VALIDATE** (will run full tests in later tasks):
  ```bash
  uv run python -c "from tests.conftest import async_test_db_session, SEED_FOOD_ID, TEST_USER_A; print('conftest imports ok')"
  ```

### Task 25 — UPDATE `tests/integration/test_food_service.py`

- **IMPLEMENT**: Update assertions and fixtures to use new field names and tuple return shapes. Key changes:
  - Line 17: import `create_food_item, search_food` stays; add `calculate_food_macros` if used
  - Line 44-45: `r["name"]` → `r["name_en"]` (or `r["name_he"]` for Hebrew tests)
  - Line 57-64: `FoodItem(name="User A Special Smoothie", …)` → `FoodItem(name_en="User A Special Smoothie", name_he=None, …)`
  - Line 77: same pattern
  - Line 90: `"Shake" in r["name"]` → `"Shake" in r["name_en"]`
  - Line 103-113: `create_food_item.ainvoke({"name": …})` → `{"name_en": …, "user_id": …}` (new signature)
  - Line 114: `result["name"]` → `result["name_en"]`
  
- **Add new test classes** for bilingual search and coach mapping join:

```python
class TestBilingualSearch:
    async def test_hebrew_query_matches_hebrew_name(self, async_test_db_session):
        """Searching by a Hebrew name hits the name_he column."""
        with _patch_session(async_test_db_session):
            results = await search_food.ainvoke({"query": "עוף", "user_id": TEST_USER_A})
        assert any("Test Chicken" == r["name_en"] for r in results)

    async def test_english_query_matches_english_name(self, async_test_db_session):
        """Searching by English hits name_en."""
        with _patch_session(async_test_db_session):
            results = await search_food.ainvoke({"query": "Chicken", "user_id": TEST_USER_A})
        assert any(r["name_en"] == "Test Chicken" for r in results)


class TestCoachMappingJoin:
    async def test_search_surfaces_coach_mapping_fields(self, async_test_db_session):
        """Seeded food has a coach mapping; search result exposes category + tag + serving."""
        with _patch_session(async_test_db_session):
            results = await search_food.ainvoke({"query": "Chicken", "user_id": TEST_USER_A})
        seed = next(r for r in results if r["name_en"] == "Test Chicken")
        assert seed["category"] == "protein"
        assert seed["tag"] == "lean"
        assert seed["serving_amount_g"] == 100.0
```

- **VALIDATE**:
  ```bash
  uv run pytest tests/integration/test_food_service.py -v
  ```

### Task 26 — UPDATE `tests/integration/test_daily_log_model.py`

- **IMPLEMENT**: Line 148: `log.food_item.name == "Test Chicken"` → `log.food_item.name_en == "Test Chicken"`.
- **VALIDATE**:
  ```bash
  uv run pytest tests/integration/test_daily_log_model.py -v
  ```

### Task 27 — UPDATE `tests/unit/test_food_search_node.py`

- **IMPLEMENT**: Update the mock return shape (lines 26-29):

```python
mock_search_food.ainvoke = AsyncMock(return_value=[
    {
        "id": "food-uuid-1", "name_en": "Chicken breast", "name_he": "חזה עוף",
        "source": "database", "category": "protein", "tag": "lean",
    },
    {
        "id": "food-uuid-2", "name_en": "Chicken thigh", "name_he": "שוקיים עוף",
        "source": "database", "category": "protein", "tag": "fatty",
    },
])
```

Update `pending_food_items` fixture to use `count`/`unit` instead of `amount`:

```python
basic_state["pending_food_items"] = [
    {"food_name": "chicken", "count": 100.0, "unit": "g", "original_text": "100g chicken"}
]
```

- **VALIDATE**:
  ```bash
  uv run pytest tests/unit/test_food_search_node.py -v
  ```

### Task 28 — UPDATE `tests/unit/test_calculate_macros_node.py`

- **IMPLEMENT**: Multiple changes throughout:
  1. All `mock_calculate_macros.ainvoke` return values gain new fields: `name_en`, `name_he`, `category`, `tag`, `serving_amount_g`, `servings`, `default_unit`, `default_unit_weight_g`.
  2. `pending_food_items` fixtures use `count`/`unit` (not `amount`/`unit`).
  3. `MacroResult` assertions use `macro["name_en"]` instead of `macro["food_name"]`.
  4. The DB path now calls `get_food_by_id` service function + `compute_food_macros` pure helper — the test must mock `get_food_by_id` (via `src.agents.nodes.calculate_macros_node.get_food_by_id`). Add a conftest fixture.
  5. `_estimate_macros` tests need to mock `MacroEstimation` with new fields (name_en, name_he, category, etc.).

- **Example revised test** (DB path success):

```python
async def test_db_path_success(self, basic_state, mock_get_food_by_id):
    """..."""
    # Arrange: get_food_by_id returns a (FoodItem, CoachFoodMapping) tuple
    food = MagicMock()
    food.id = uuid_mod.UUID("00000000-0000-0000-0000-000000000001")
    food.name_en = "Chicken breast"
    food.name_he = "חזה עוף"
    food.source = "database"
    food.calories = 165.0
    food.protein = 31.0
    food.fat = 3.6
    food.carbs = 0.0
    food.default_unit = "g"
    food.default_unit_weight_g = None

    mapping = MagicMock()
    mapping.category = "protein"
    mapping.tag = "lean"
    mapping.serving_amount_g = 100.0

    mock_get_food_by_id.return_value = (food, mapping)

    basic_state.update({
        "pending_food_items": [
            {"food_name": "chicken", "count": 200.0, "unit": "g", "original_text": "200g chicken"}
        ],
        "selected_food_id": "00000000-0000-0000-0000-000000000001",
    })

    result = await calculate_macros_node(basic_state, TEST_RUNTIME_A)

    macro = result["pending_confirmations"][0]
    assert macro["name_en"] == "Chicken breast"
    assert macro["name_he"] == "חזה עוף"
    assert macro["amount_g"] == 200.0
    assert macro["calories"] == 330.0
    assert macro["source"] == "database"
    assert macro["category"] == "protein"
    assert macro["tag"] == "lean"
    assert macro["servings"] == 2.0  # 200g / 100g serving
```

- **Add conftest fixture** for `mock_get_food_by_id`:

```python
@pytest.fixture
def mock_get_food_by_id():
    """Mock get_food_by_id service used by calculate_macros_node (async, not a @tool)."""
    with patch("src.agents.nodes.calculate_macros_node.get_food_by_id", new_callable=AsyncMock) as mock:
        yield mock
```

- **VALIDATE**:
  ```bash
  uv run pytest tests/unit/test_calculate_macros_node.py -v
  ```

### Task 29 — UPDATE `tests/unit/test_confirmation_node.py`

- **IMPLEMENT**: Update `SAMPLE_BATCH` (lines 23-46) to use new MacroResult fields (name_en, name_he, category, tag, servings, default_unit, default_unit_weight_g). Existing assertions about totals and source_tag stay valid.

```python
SAMPLE_BATCH = [
    {
        "name_en": "chicken",
        "name_he": "עוף",
        "amount_g": 200,
        "calories": 330,
        "protein": 62,
        "carbs": 0,
        "fat": 7.2,
        "source": "database",
        "category": "protein",
        "tag": "lean",
        "serving_amount_g": 100.0,
        "servings": 2.0,
        "default_unit": "g",
        "default_unit_weight_g": None,
        "original_text": "200g chicken",
        "food_id": "food-uuid-1",
    },
    {
        "name_en": "pizza",
        "name_he": None,
        "amount_g": 300,
        "calories": 750,
        "protein": 30,
        "carbs": 85,
        "fat": 32,
        "source": "estimated",
        "category": None,  # estimated items may have no category (mapping not created)
        "tag": None,
        "serving_amount_g": None,
        "servings": None,
        "default_unit": None,
        "default_unit_weight_g": None,
        "original_text": "3 slices of pizza",
        "food_id": None,
    },
]
```

Update `test_estimated_item_tag` to assert `description` now contains `name_en` instead of `food_name`:

```python
def test_estimated_item_tag(self):
    preview = _format_batch_preview(SAMPLE_BATCH)
    db_item = preview["items"][0]
    est_item = preview["items"][1]
    tag = MESSAGES["confirmation_estimated_tag"]
    assert tag not in db_item["description"]
    assert tag in est_item["description"]
    assert "chicken" in db_item["description"]  # name_en appears in desc
```

Add a new test for Hebrew rendering:

```python
def test_hebrew_rendering(self, monkeypatch):
    """When BOT_LANGUAGE=he, preview uses name_he for items that have it."""
    monkeypatch.setenv("BOT_LANGUAGE", "he")
    preview = _format_batch_preview(SAMPLE_BATCH)
    db_item = preview["items"][0]  # chicken — has name_he
    est_item = preview["items"][1]  # pizza — no name_he, falls back to name_en
    assert "עוף" in db_item["description"]
    assert "pizza" in est_item["description"]  # fallback
```

And a test for servings/category surfacing in the payload:

```python
def test_servings_and_category_in_payload(self):
    preview = _format_batch_preview(SAMPLE_BATCH)
    assert preview["items"][0]["servings"] == 2.0
    assert preview["items"][0]["category"] == "protein"
    assert preview["items"][1]["servings"] is None
    assert preview["items"][1]["category"] is None
```

Update `_apply_edits` tests for new MacroResult shape (existing behavior tests still work; the field names change from `food_name` → `name_en`).

- **VALIDATE**:
  ```bash
  uv run pytest tests/unit/test_confirmation_node.py -v
  ```

### Task 30 — UPDATE `tests/unit/test_commit_node.py`

- **IMPLEMENT**: Update all `pending_confirmations` fixtures (lines 30-53, 78-90, 119-131, 155-177, 198-210, 238-250) to use new MacroResult shape. Update `mock_create_food_item.ainvoke.call_args` assertions to verify the new parameter names.

Example revised fixture (test_commit_batch_success):
```python
basic_state.update({
    "pending_confirmations": [
        {
            "name_en": "chicken",
            "name_he": "עוף",
            "amount_g": 200,
            "calories": 330,
            "protein": 62,
            "carbs": 0,
            "fat": 7.2,
            "source": "database",
            "category": "protein",
            "tag": "lean",
            "serving_amount_g": 100.0,
            "servings": 2.0,
            "default_unit": "g",
            "default_unit_weight_g": None,
            "original_text": "200g chicken",
            "food_id": "food-uuid-1",
        },
        # ... similar for rice
    ],
    "consumed_at": datetime(2026, 3, 3, 12, 0, tzinfo=timezone.utc),
})
```

Update `test_commit_estimated_item_creates_food_item` assertions:
```python
create_args = mock_create_food_item.ainvoke.call_args[0][0]
assert create_args["name_en"] == "pizza"
assert "name_he" in create_args  # may be None for estimated pizza
assert create_args["calories_per_100g"] == round((750 / 300) * 100, 2)
# etc.
```

- **VALIDATE**:
  ```bash
  uv run pytest tests/unit/test_commit_node.py -v
  ```

### Task 31 — UPDATE `tests/unit/test_input_parser.py`

- **IMPLEMENT**: Update any FoodIntakeEvent / SingleFoodItem fixtures that use `amount`/`unit="g"` to use `count`/`unit="g"`. Most tests verify the prompt injection or date parsing; the items section likely only appears in structural tests.
- Pattern: grep within the test file for `amount=` and `"amount":` to find all fixtures.
- **VALIDATE**:
  ```bash
  uv run pytest tests/unit/test_input_parser.py -v
  ```

### Task 32 — CREATE `tests/unit/test_food_service_helpers.py`

- **IMPLEMENT**: New unit test file for the two pure helpers added in Task 4.

```python
"""
Unit tests for food_service pure helpers.

Scope:
    Pure function tests — no DB, no LLM, no I/O.

LLM Usage:
    NONE.
"""
from unittest.mock import MagicMock

import pytest

from src.services.food_service import compute_food_macros, compute_servings, resolve_amount_g


class TestResolveAmountG:
    def test_grams_passthrough(self):
        food = MagicMock(default_unit="g", default_unit_weight_g=None, name_en="Rice")
        assert resolve_amount_g(food, "g", 180.0) == 180.0

    def test_piece_unit_multiplies_weight(self):
        food = MagicMock(default_unit="piece", default_unit_weight_g=50.0, name_en="Egg")
        assert resolve_amount_g(food, "piece", 2.0) == 100.0

    def test_slice_unit(self):
        food = MagicMock(default_unit="slice", default_unit_weight_g=25.0, name_en="Yellow cheese")
        assert resolve_amount_g(food, "slice", 3.0) == 75.0

    def test_unit_mismatch_raises(self):
        food = MagicMock(default_unit="piece", default_unit_weight_g=50.0, name_en="Egg")
        with pytest.raises(ValueError, match="Unit mismatch"):
            resolve_amount_g(food, "slice", 2.0)

    def test_no_default_unit_falls_back_to_grams(self):
        food = MagicMock(default_unit=None, default_unit_weight_g=None, name_en="Mystery")
        assert resolve_amount_g(food, "piece", 2.0) == 2.0


class TestComputeServings:
    def test_none_when_serving_amount_g_is_none(self):
        assert compute_servings(100, None) is None

    def test_none_when_serving_amount_g_is_zero(self):
        assert compute_servings(100, 0) is None

    def test_simple_division(self):
        assert compute_servings(200, 100) == 2.0

    def test_fractional(self):
        assert compute_servings(50, 100) == 0.5

    def test_rounds_to_two_decimals(self):
        assert compute_servings(150, 100) == 1.5
        assert compute_servings(100, 150) == 0.67


class TestComputeFoodMacros:
    def test_full_dict_with_mapping(self):
        food = MagicMock(
            id="abc-123", name_en="Chicken breast", name_he="חזה עוף", source="database",
            calories=165.0, protein=31.0, fat=3.6, carbs=0.0,
            default_unit="g", default_unit_weight_g=None,
        )
        food.id.__str__ = lambda self: "abc-123"  # actual str repr
        mapping = MagicMock(category="protein", tag="lean", serving_amount_g=100.0)
        result = compute_food_macros(food, mapping, 200.0)
        assert result["amount_g"] == 200.0
        assert result["calories"] == 330.0
        assert result["category"] == "protein"
        assert result["servings"] == 2.0

    def test_no_mapping(self):
        food = MagicMock(
            id="abc-123", name_en="Estimated pizza", name_he=None, source="estimated",
            calories=250.0, protein=10.0, fat=12.0, carbs=30.0,
            default_unit=None, default_unit_weight_g=None,
        )
        result = compute_food_macros(food, None, 100.0)
        assert result["category"] is None
        assert result["tag"] is None
        assert result["serving_amount_g"] is None
        assert result["servings"] is None
```

- **VALIDATE**:
  ```bash
  uv run pytest tests/unit/test_food_service_helpers.py -v
  ```

### Task 33 — Run FULL test suite

- **IMPLEMENT**: Run unit + integration tests to verify no regressions.
- **Commands**:
  ```bash
  uv run ruff check src/ bot/ tests/
  uv run pytest tests/unit/ -v
  uv run pytest tests/integration/ -v
  ```
- **GOTCHA**: 
  - If unit tests fail with "KeyError: 'food_name'" or similar, a fixture wasn't updated — grep for the missing key.
  - If integration tests fail with "column food_items.name does not exist", the model still references it (Task 21 wasn't applied).
  - If integration tests fail with FK violation on coach_food_mappings, the test fixture isn't creating the mapping (Task 24).
  - **graph_api tests are NOT run in Plan 2** — they'd require end-to-end LLM calls with the old prompts against new schemas and would predictably fail. Defer to Plan 3.

---

## TESTING STRATEGY

### Unit Tests (must pass)

Scope:
- Schemas validate with new field sets
- State TypedDicts accept new keys
- `resolve_amount_g` and `compute_servings` helpers (new: `tests/unit/test_food_service_helpers.py`)
- Every graph node handles the new shapes correctly (input, food_search, selection, calculate_macros, confirmation, commit)

### Integration Tests (must pass)

Scope:
- `test_food_service.py` — bilingual search, coach mapping join, create_food_item with optional category, user_id scoping still works (estimated isolation)
- `test_daily_log_model.py` — FK relationship navigates via name_en

### Graph-API Tests (deferred)

**Skip for Plan 2.** The graph-api suite tests end-to-end bot behavior through LangGraph. Prompts are unchanged → LLM outputs won't match new schemas → tests predictably fail. Resume in Plan 3.

### Edge Cases (must be tested)

- Bilingual search with Hebrew-only name (estimated food has no English)
- Coach mapping missing (estimated foods have no mapping yet)
- `servings = None` when food has no serving_amount_g (free veggies)
- `resolve_amount_g` with unit mismatch raises ValueError
- `create_food_item` with `category=None` creates food only, no mapping
- `create_food_item` with `category="protein"` creates both atomically

---

## VALIDATION COMMANDS

Execute every command in order. Each verifies a specific post-condition.

### Level 1: Syntax & Style

```bash
uv run ruff check src/ bot/ tests/
```

### Level 2: Imports + Parse

```bash
uv run python -c "
from src.models import FoodItem, CoachFoodMapping
assert 'name' not in [c.name for c in FoodItem.__table__.columns], 'legacy name still present'
from src.services.food_service import search_food, calculate_food_macros, create_food_item
from src.services.food_service import resolve_amount_g, compute_servings, compute_food_macros
from src.agents.state import PendingFoodItem, SearchResult, MacroResult, ProcessingResult
from src.agents.nodes.calculate_macros_node import calculate_macros_node, _estimate_macros
from src.agents.nodes.confirmation_node import _format_batch_preview, confirmation_node
from src.agents.nodes.commit_node import commit_node
from bot.gateway import _format_interrupt_value
from src.i18n import MESSAGES
assert 'confirmation_serving_line' in MESSAGES, 'i18n key missing'
print('all imports ok')
"
```

### Level 3: Unit Tests

```bash
uv run pytest tests/unit/ -v
```

### Level 4: Integration Tests

```bash
uv run pytest tests/integration/ -v
```

### Level 5: DB State Verification (via mcp__supabase__execute_sql)

```sql
-- Legacy column dropped
SELECT column_name FROM information_schema.columns
WHERE table_name = 'food_items' AND column_name = 'name';
-- Expect: 0 rows

-- Canonical catalog repopulated after reseed
SELECT source, COUNT(*) FROM food_items GROUP BY source;
-- Expect: database=93, estimated=20 (or current estimated count)

-- Coach mappings intact
SELECT COUNT(*) FROM coach_food_mappings;
-- Expect: 93
```

### Level 6: Manual Smoke (optional — bot DOES NOT work end-to-end until Plan 3)

Not part of Plan 2's validation. The bot will hit prompt/schema mismatches as soon as the parser runs. This is expected.

---

## ACCEPTANCE CRITERIA

- [ ] All 33 tasks completed in order
- [ ] `src/services/food_service.py` rewritten with new service functions, helpers, tool wrappers
- [ ] `resolve_amount_g` and `compute_servings` helpers exist and have unit tests
- [ ] `src/models.py`: `name` field removed from `FoodItem`
- [ ] Supabase migration `drop_legacy_food_items_name_column` applied successfully
- [ ] `food_items` schema no longer contains the `name` column
- [ ] Seed script reran after column drop; 93 canonical rows + 93 coach mappings persist
- [ ] All Pydantic schemas updated: `SingleFoodItem` has `count`+wider `unit`; `MacroEstimation` has name/category/unit fields
- [ ] All state TypedDicts updated: `PendingFoodItem`, `SearchResult`, `MacroResult`, `ProcessingResult`
- [ ] All 6 node files updated: input, food_search, selection, calculate_macros, confirmation, commit
- [ ] i18n TypedDict + both YAML files carry the new `confirmation_serving_line` + category-label keys; parity check passes
- [ ] `bot/gateway.py` `_format_interrupt_value` renders the servings line when present
- [ ] All unit tests pass (`uv run pytest tests/unit/ -v` — 130+ existing + new helper tests)
- [ ] All integration tests pass (`uv run pytest tests/integration/ -v` — updated fixtures + new bilingual tests)
- [ ] `ruff check` passes across `src/`, `bot/`, `tests/`
- [ ] No references to `FoodItem.name` / `food.name` / `food_item.name` remain in production code (only in historical commit logs and docs)
- [ ] Graph-api tests NOT run (intentional, resumes in Plan 3)

---

## COMPLETION CHECKLIST

- [ ] Tasks 1-3: schemas + state done
- [ ] Tasks 4-10: service layer rewritten
- [ ] Tasks 11-16: all nodes updated
- [ ] Tasks 17-19: i18n + bot gateway done
- [ ] Tasks 20-23: seed updated, migration applied, reseed verified
- [ ] Tasks 24-32: tests updated + new helper tests added
- [ ] Task 33: full test suite green
- [ ] All validation commands pass
- [ ] Successor work (Plan 3) summary reviewed — confirms what prompts remain to update

---

## SUCCESSOR WORK

Plan 3 is **prompts only** — no schema changes, no code signature changes. The contract between code and LLM is defined by the schemas Plan 2 ships. Plan 3 updates the prompts to produce data that fits those schemas.

### Plan 3 — LLM Prompts + HITL Copy Iteration + Evals

Files Plan 3 will touch (all in `prompts/` directory):

1. **`prompts/input_parser.md`** — drop "translate to English" instruction; teach LLM to emit `{count, unit}` and let downstream resolve via `default_unit_weight_g`
2. **`prompts/macro_estimation.md`** — ask for `name_en`, `name_he`, `category`, `tag` (optional), `default_unit`, `default_unit_weight_g`; teach the LLM about the category taxonomy
3. **`prompts/response_generator.md`** — coach voice with serving math; reason over `category`-grouped serving totals; reference `tag` (lean/fatty) in recommendations
4. **`prompts/agent_selection.md`** — teach the LLM to use `category` + `tag` for selection quality
5. **`prompts/confirmation_parser.md`** — likely minimal changes; maybe accept unit-based edits ("change chicken to 150g" already works via `new_amount_g`; "change eggs to 3" could be added via `new_count` + `new_unit` in `ItemEdit`)
6. **HITL copy iteration** — after testing `_format_interrupt_value` with Dolev on real messages, refine `confirmation_serving_line` wording in `en.yaml` + `he.yaml`
7. **Re-run evals** — `notebooks/evals/eval_input_parser.ipynb` (updated dataset with count/unit parsing), add new eval for estimation quality (does the LLM produce sensible categories?)

Schema sufficiency verification:
- ✅ `SingleFoodItem` has `count`/`unit` — parser prompt can target
- ✅ `MacroEstimation` has name_en/name_he/category/tag — estimation prompt can target
- ✅ `MacroResult` carries category/tag/servings — response prompt can reason over
- ✅ i18n has category labels — HITL can render any category in Hebrew

**Bottom line: Plan 2 delivers the data shape Plan 3 needs. Plan 3 is pure prompt engineering + eval work.**

---

## NOTES

### Why the bot breaks end-to-end between Plan 2 and Plan 3

After Plan 2 lands:
- Parser prompt (stale) still says "extract grams" → LLM might produce `{count: 100, unit: "g"}` for "2 eggs" — schema-valid but semantically wrong
- Search works (bilingual) → finds "Whole egg" row
- Selection works → picks the egg row
- `calculate_macros_node.resolve_amount_g` gets called with `unit="g"` and `count=100` → returns 100g → macros computed for 100g of egg (correct-ish, but not what user meant)
- HITL renders "ביצה — 100g (~0.67 protein servings)" — renders correctly with new format, but the amount is wrong

So unit tests pass (node/tool behavior is correct given valid inputs) but real bot conversations produce wrong amounts. This is accepted — Dolev confirmed.

### Why split helpers (resolve_amount_g, compute_servings) are useful even before Plan 3

- `resolve_amount_g` — once Plan 3 updates the parser to emit `{count: 2, unit: "piece"}`, the helper already works. Zero changes to calculate_macros_node needed in Plan 3.
- `compute_servings` — standalone helper usable by response_node (Plan 3) to say "you have 30g protein left = ~1.5 servings remaining" without having a specific food in hand.

### Why keep `name_en` required but `name_he` optional

- The 93 canonical catalog rows have name_he for all 93
- Estimated foods (legacy + new) may have only one language depending on what the user typed
- Making name_en optional complicates search fallback logic — pick one as canonical. English is the computer-friendlier language and always present.

### Double-query pattern (deferred to Backlog)

After Plan 2, a single food log produces two DB round-trips:
1. `search_food` in `food_search_node` — fetches many candidates, returns minimal dicts (id, names, category, tag)
2. `get_food_by_id` in `calculate_macros_node` — re-fetches the selected row to get per-100g macros + unit fields

For the POC (93 rows, low QPS) this is negligible. At scale or when token efficiency matters, we could:
- **Option A**: Return full per-100g macros from `search_food` and store the selected candidate in state; `calculate_macros_node` reads from state with no re-fetch.
- **Option B**: Cache the full candidate dict in `search_results[i]` and have selection_node produce not just `selected_food_id` but also `selected_food_data`.
- **Option C**: Keep as-is (simpler code, clearer separation of concerns).

Tracked as a `goal:learning` item in `brain/TASKS.md`. Revisit when either usage scales or LLM token costs become a concern.

### Safety: what rolls back cleanly if this plan blows up?

- Pydantic schema changes → revert via git
- SQLAlchemy model field removal → revert via git
- Supabase migration → manual rollback via `ALTER TABLE food_items ADD COLUMN name TEXT; UPDATE food_items SET name = name_en;` (rerun Plan 1's seed script first to repopulate name_en if wiped)
- The `data/canonical_food_catalog.csv` file is gitignored but preserved locally — if wiped by mistake, reconstruct from `data/canonical_food_catalog.csv.bak` or from the bulk plan
- Tests are git-tracked → full rollback via `git checkout`

### Confidence: 7/10 for one-pass success

Implementation risks:
- **Largest risk**: the LEFT JOIN tuple-return pattern is new to this codebase. If SQLAlchemy returns an empty `CoachFoodMapping()` instead of `None` when the LEFT JOIN has no match, downstream code crashes. Mitigation: explicit test in `test_food_service.py` for the no-mapping case (estimated food).
- **Second risk**: parameter order / naming drift between `create_food_item_record` (service) and `create_food_item` (@tool). Kept parallel to minimize drift.
- **Third risk**: `_apply_edits` in `confirmation_node` still references `item["food_name"]` in a few places (reject branch, logging) — Task 15 flags this but missing one line causes test failures. Mitigation: grep for `item["food_name"]` and `item['food_name']` after Task 15 completes.

What could go wrong that isn't covered:
- If `asyncpg` doesn't support the UUID filter on `coach_food_mappings.coach_id == coach_id` without an explicit cast — unlikely but if so, wrap coach_id as `str(coach_id)` or use `.cast(Uuid)`.
- If the bot gateway's `_format_interrupt_value` is called before `MESSAGES` reloads after i18n changes — restart required. Noted in gotcha.
