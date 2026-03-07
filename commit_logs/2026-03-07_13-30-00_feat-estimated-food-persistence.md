# Commit: feat: persist estimated food items to DB with source tracking

**Date**: 2026-03-07
**Commit**: 3403cf3

## Changes Implemented

### Schema & Migration
- Added `source` column to `FoodItem` model (`String, NOT NULL, server_default="database"`)
- Generated Alembic migration (`add_source_column_to_food_items`)
- Added `source: str` field to `SearchResult` TypedDict in `state.py`

### Tool Layer
- **`create_food_item`** — new async `@tool` in `food_lookup.py` for persisting estimated foods
- **`search_food`** — two-tier search: DB foods first (`source="database"`), then estimated fallback (`source="estimated"`)
- **`calculate_food_macros`** — now returns `food.source` from DB (enables source transparency on reuse)

### Node Updates
- **`commit_node`** — creates `FoodItem` for estimated items before logging (back-calculated per-100g values), uses returned `food_id`
- **`calculate_macros_node`** — uses `macros.get("source", "database")` instead of hardcoded `"database"`

### Tests (71 passing)
- Added `mock_create_food_item` fixture to `conftest.py`
- Added `source="database"` to seed data
- New tests: `test_commit_estimated_item_creates_food_item`, `test_db_item_skips_food_item_creation`, `test_mixed_batch`, `test_db_path_preserves_estimated_source`
- Updated all search result dicts across test files to include `source` field

### Documentation
- Updated `CLAUDE.md` — project structure, architecture patterns, reference table
- Updated `PRD.md` — food database schema, Phase 2 off-menu marked complete

## Files Modified (14)
- `src/models.py`, `src/agents/state.py`, `src/tools/food_lookup.py`
- `src/agents/nodes/commit_node.py`, `src/agents/nodes/calculate_macros_node.py`
- `tests/conftest.py`, `tests/unit/test_commit_node.py`, `tests/unit/test_calculate_macros_node.py`
- `tests/unit/test_food_search_node.py`, `tests/unit/test_agent_selection.py`
- `tests/unit/test_feedback_logic.py`, `tests/unit/test_feedback_integration.py`
- `CLAUDE.md`, `PRD.md`

## Files Created (1)
- `alembic/versions/2026_03_07_4652804c7c7f_add_source_column_to_food_items.py`

## Next Steps
- User ID tracking (Phase 3)
- Deduplication of estimated foods (same name, different estimations)
- Consider adding `food_name` to `QueriedLog` via JOIN for richer stats reporting
