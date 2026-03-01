# Feature: Refactor Mypy Type Errors

## Feature Description
Resolve robust typing errors reported by `mypy` natively by upgrading SQLAlchemy models to the 2.0 syntax (`Mapped[T]`) and securely handling Fallbacks for LangGraph Agent state dictionaries.

## User Story
As a developer
I want to run `uv run mypy src` without errors
So that I can trust our codebase's strict typing is sound and robust

## Problem Statement
Mypy is failing validation due to two distinct type mismatches:
1. **SQLAlchemy Legacy Columns**: In `src/agents/nodes/stats_node.py`, the query returns `Column` descriptor objects rather than primitives (int, float) according to mypy, resulting in `Incompatible types (expression has type "Column[int]", TypedDict item "id" has type "int")`.
2. **Invalid TypedDict Defaults**: In `src/agents/nodes/selection_node.py`, falling back to an empty dictionary `{}` for a strongly typed `PendingFoodItem` violates the schema requirements: `Missing keys ("food_name", "amount", "unit", "original_text")`.

## Solution Statement
1. **Model Upgrades**: Migrate `src/models.py` to leverage SQLAlchemy 2.0's `Mapped[T]` and `mapped_column()` syntax. This allows `mypy` to infer the correct primitive runtime types (e.g., `Mapped[int]` instead of `Column(Integer)`).
2. **Safe Optionals**: Refactor `selection_node.py` to fall back to `None` and explicitly handle the presence or absence of the target `current_item` before constructing `FAILED` records.

## Feature Metadata

**Feature Type**: Refactor & Bug Fix
**Estimated Complexity**: Low
**Primary Systems Affected**: `src/models.py`, `src/agents/nodes/selection_node.py`
**Dependencies**: `sqlalchemy` >= 2.0

---

## CONTEXT REFERENCES

### Relevant Codebase Files
- `src/models.py` (lines 11-59) - Why: Contains the raw SQLAlchemy ORM mappings using legacy `Column` syntax.
- `src/agents/nodes/stats_node.py` (lines 30-45) - Why: Assigns SQLAlchemy model fields to the `QueriedLog` TypedDict. Relies on the changes in `models.py`.
- `src/agents/nodes/selection_node.py` (lines 24-33) - Why: Contains the bad `{}` fallback that violates the TypedDict constraints.

### Relevant Documentation
- [SQLAlchemy 2.0 Declarative Mapping](https://docs.sqlalchemy.org/en/20/orm/declarative_styles.html#declarative-mapping-using-annotated-declarative)
  - Why: Defines the exact `Mapped[T]` syntax required to natively satisfy mypy typing without runtime casting.

---

## IMPLEMENTATION PLAN

### Phase 1: Core Implementation (Refactor)

**Tasks:**
- Refactor `src/models.py` attributes to utilize standard `Mapped` types.
- Update `src/agents/nodes/selection_node.py` to use `None`.

### Phase 2: Testing & Validation

**Tasks:**
- Revert any manual casting (e.g., `int()`, `float()`) inside `stats_node.py` if present.
- Run `uv run mypy src --explicit-package-bases` to confirm 0 errors.
- Run `uv run pytest tests/` to confirm no runtime behavioral regressions were introduced by type mapping refactoring.

---

## STEP-BY-STEP TASKS

### REFACTOR `src/agents/nodes/selection_node.py`

- **IMPLEMENT**: Change the fallback logic for `current_item`.
  - Line 24: `current_item = pending_items[0] if pending_items else None` (Change `{}` to `None`)

### REFACTOR `src/models.py`

- **IMPORTS**: Ensure `from sqlalchemy.orm import Mapped, mapped_column, relationship` is used.
- **IMPLEMENT**: `FoodItem` Model
  - `id: Mapped[int] = mapped_column(Integer, primary_key=True)`
  - `name: Mapped[str] = mapped_column(String, nullable=False, index=True)`
  - `calories: Mapped[Optional[float]] = mapped_column(Float)`
  - `protein: Mapped[Optional[float]] = mapped_column(Float)`
  - `fat: Mapped[Optional[float]] = mapped_column(Float)`
  - `carbs: Mapped[Optional[float]] = mapped_column(Float)`
  - `logs: Mapped[list["DailyLog"]] = relationship("DailyLog", back_populates="food_item")`
- **IMPLEMENT**: `DailyLog` Model
  - `id: Mapped[int] = mapped_column(Integer, primary_key=True)`
  - `food_id: Mapped[int] = mapped_column(Integer, ForeignKey("food_items.id"), nullable=False)`
  - `amount_g: Mapped[float] = mapped_column(Float, nullable=False)`
  - `calories: Mapped[float] = mapped_column(Float, nullable=False)`
  - `protein: Mapped[float] = mapped_column(Float, nullable=False)`
  - `carbs: Mapped[float] = mapped_column(Float, nullable=False)`
  - `fat: Mapped[float] = mapped_column(Float, nullable=False)`
  - `timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)`
  - `meal_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)`
  - `created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))`
  - `updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc))`
  - `original_text: Mapped[Optional[str]] = mapped_column(String, nullable=True)`
  - `food_item: Mapped["FoodItem"] = relationship("FoodItem", back_populates="logs")`

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style

`uv run ruff check .`

### Level 2: Strict Typing

`uv run mypy src --explicit-package-bases`

### Level 3: Runtime Tests

`uv run pytest tests/ -v`

---

## ACCEPTANCE CRITERIA

- [ ] All standard Mypy validation commands pass with zero errors related to Database columns or Selection node dictionaries.
- [ ] Pytest suite remains perfectly green.
- [ ] No behavioral regressions in DB saves/loads.

---

## NOTES
- Wrapping SQLAlchemy relationships in quotes stringifies them to prevent circular dependency type-validation errors (`Mapped[list["DailyLog"]]`).
- `Mapped[Optional[T]]` is required for columns that do not enforce `nullable=False`.
