# Feature: Implement Food Lookup Tools (Search & Calculate)

## Feature Description
Implement a **Two-Stage Retrieval & Calculation** system using SQLAlchemy.
1.  **Search Tool**: Returns a strict list of `{id, name}` candidates (No calories/noise).
2.  **Calculator Tool**: Takes `id` and `amount_grams`, retrieves 100g data from DB, performs the math, and returns final totals.

## User Story
**As a** system optimizer
**I want** the agent to search for simple names and then offload the math to a tool
**So that** I minimize token usage and guarantee mathematical accuracy for user logs.

## Problem Statement
-   Search returns too much data (calories/macros were noise).
-   LLM is bad at floating point multiplication (e.g., "165kcal * 235g").

## Solution Statement
1.  **Tool 1: `search_food(query)`**:
    -   SELECT `id`, `name` FROM `food_items` WHERE `name` ILIKE `%query%`.
    -   Return: `[{"id": 1, "name": "Chicken Breast"}, ...]` (Strictly minimal).
2.  **Tool 2: `calculate_food_macros(food_id, amount_g)`**:
    -   Fetch 100g values for `food_id`.
    -   Compute: `(value_100g * amount_g) / 100`.
    -   Return: `{"name": "Chicken Breast", "calories": 330.0, "protein": 62.0, ...}`.

## Feature Metadata
**Feature Type**: New Capability
**Estimated Complexity**: Medium
**Dependencies**: `sqlalchemy`

---

## CONTEXT REFERENCES

- `src/tools/food_lookup.py` (Target)
- `data/nutrition.db` (DB)

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation
**Tasks:**
1.  Add `SQLAlchemy`.
2.  Define `FoodItem` model (`src/models.py`).
3.  Setup `get_db_session` (`src/database.py`).

### Phase 2: Core Implementation
**Tasks:**
1.  Refactor `src/tools/food_lookup.py`:
    -   `@tool search_food(query: str)`: Returns IDs/Names.
    -   `@tool calculate_food_macros(food_id: int, amount: float)`: Does the math.

### Phase 3: Testing
**Tasks:**
1.  `tests/test_food_lookup.py`:
    -   Verify `search_food` returns NO macros, just ID/Name.
    -   Verify `calculate_food_macros(id=1, amount=200)` returns exactly double the 100g values.

---

## STEP-BY-STEP TASKS

### 1. INSTALL DEPENDENCY
- **RUN**: `uv add sqlalchemy`

### 2. CREATE `src/models.py`
- **IMPLEMENT**: `FoodItem` class.

### 3. CREATE `src/database.py`
- **IMPLEMENT**: Session factory.

### 4. UPDATE `src/tools/food_lookup.py`
- **IMPLEMENT**:
    -   `search_food`: Return `list[dict(id, name)]`.
    -   `calculate_food_macros`: `val = (db_val * amount) / 100`.

### 5. CREATE `tests/test_food_lookup.py`
- **IMPLEMENT**: Unit tests for both tools.

---

## VALIDATION COMMANDS

### Level 1: Syntax
`uv run ruff check src`

### Level 2: Integration
`uv run pytest tests/test_food_lookup.py -v`
