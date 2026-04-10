# Feature: Daily Log Persistence Layer

> [!IMPORTANT]
> **Pre-Implementation Checklist**
> - [ ] Read all files listed in "Relevant Codebase Files" section
> - [ ] Review SQLAlchemy 2.0 documentation links
> - [ ] Validate all import paths match actual project structure
> - [ ] Confirm pytest is configured correctly

## Feature Description

Implement a complete database persistence layer for tracking daily food intake logs. This feature creates the foundation for durable data storage, allowing users to log food entries that persist across sessions, query historical data, and maintain accurate daily nutritional totals. The implementation follows a **service layer pattern** with **write-through caching** to ensure data durability and consistency.

## User Story

**As a** FitPal user  
**I want** my food logs to be saved permanently to a database  
**So that** I can track my nutrition over time, resume conversations without data loss, and query historical eating patterns

## Problem Statement

Currently, the FitPal agent has no persistent storage for daily food logs. The `AgentState` holds temporary macro totals (`daily_calories`, `daily_protein`, etc.) in memory, which means:
- ❌ Data is lost if the conversation crashes
- ❌ No historical tracking across days
- ❌ Cannot query "What did I eat yesterday?"
- ❌ State accumulation is error-prone and doesn't reflect DB reality

## Solution Statement

Create a **DailyLog** SQLAlchemy model with comprehensive schema (timestamp, meal_type, audit fields), implement a service layer (`daily_log_service.py`) for CRUD operations, and refactor `AgentState` to use a **write-through pattern** where the database is the source of truth. All food entries are written immediately to the DB, then state is updated by querying fresh totals.

## Feature Metadata

**Feature Type**: New Capability  
**Estimated Complexity**: Medium  
**Primary Systems Affected**:  
- Database layer (`src/models.py`)
- Service layer (new: `src/services/daily_log_service.py`)
- State management (`src/agents/state.py`)
- Input schema (`src/schemas/input_schema.py`)
- Testing infrastructure (`tests/conftest.py`, new unit tests)

**Dependencies**:  
- SQLAlchemy 2.0.46+ (already installed)
- pytest 9.0.2+ (already installed)
- Python 3.13+ (already configured)

---

## CONTEXT REFERENCES

### Relevant Codebase Files - IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- [`src/models.py`](file:///c:/Users/User/Desktop/fit_pal/src/models.py) (lines 1-16)
  - **Why**: Contains `Base` and `FoodItem` model patterns to mirror for `DailyLog`
  - **Pattern**: SQLAlchemy declarative base, column definitions, indexing
  
- [`src/database.py`](file:///c:/Users/User/Desktop/fit_pal/src/database.py) (lines 1-13)
  - **Why**: Shows session management pattern and `get_db_session()` helper
  - **Pattern**: Engine creation, SessionLocal factory, session helper function

- [`src/agents/state.py`](file:///c:/Users/User/Desktop/fit_pal/src/agents/state.py) (lines 1-23)
  - **Why**: Current `AgentState` schema that needs refactoring
  - **Action**: Remove `daily_calories`, `daily_protein`, `daily_carbs`, `daily_fat`; add `current_date`

- [`src/schemas/input_schema.py`](file:///c:/Users/User/Desktop/fit_pal/src/schemas/input_schema.py) (lines 1-24)
  - **Why**: Contains `FoodIntakeEvent` with `date` and `time` fields to refactor
  - **Action**: Replace separate `date`/`time` with single `timestamp: Optional[datetime]`

- [`src/tools/food_lookup.py`](file:///c:/Users/User/Desktop/fit_pal/src/tools/food_lookup.py) (lines 1-47)
  - **Why**: Shows session management pattern in tools (open, use, close in finally)
  - **Pattern**: `session = get_db_session()` → try/finally → `session.close()`

- [`tests/conftest.py`](file:///c:/Users/User/Desktop/fit_pal/tests/conftest.py) (lines 1-17)
  - **Why**: Existing pytest fixtures to extend with DB fixtures
  - **Pattern**: `@pytest.fixture` decorator, basic_state fixture

- [`tests/test_food_lookup.py`](file:///c:/Users/User/Desktop/fit_pal/tests/test_food_lookup.py) (lines 1-41)
  - **Why**: Example of tool testing pattern with assertions
  - **Pattern**: Tool invocation, pytest.approx for floats, skip conditions

- [`.agent/plans/daily-log-persistence.md`](file:///c:/Users/User/Desktop/fit_pal/.agent/plans/daily-log-persistence.md)
  - **Why**: Architectural decisions and schema design rationale
  - **Contains**: Final schema, state management strategy, testing approach

### New Files to Create

- `src/services/__init__.py` - Empty init file for services package
- `src/services/daily_log_service.py` - CRUD operations for DailyLog
- `tests/unit/test_daily_log_service.py` - Unit tests for service layer
- `tests/unit/test_daily_log_model.py` - Unit tests for DailyLog model

### Relevant Documentation - YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [SQLAlchemy 2.0 - Declaring Models](https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html)
  - **Section**: Declarative Mapping
  - **Why**: Shows proper Column definitions, relationships, and indexes

- [SQLAlchemy 2.0 - DateTime with Timezone](https://docs.sqlalchemy.org/en/20/core/type_basics.html#sqlalchemy.types.DateTime)
  - **Section**: DateTime type with timezone=True
  - **Why**: Critical for proper UTC datetime storage

- [SQLAlchemy 2.0 - Relationships](https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html#one-to-many)
  - **Section**: One-to-Many relationships
  - **Why**: `FoodItem` → `DailyLog` relationship pattern

- [Pydantic V2 - Datetime Fields](https://docs.pydantic.dev/latest/concepts/types/#datetime-types)
  - **Section**: datetime, date, time types
  - **Why**: Proper datetime handling in FoodIntakeEvent schema

- [pytest - Fixtures](https://docs.pytest.org/en/stable/how-to/fixtures.html)
  - **Section**: Fixture scopes and teardown
  - **Why**: Creating in-memory DB fixtures for testing

### Patterns to Follow

**Naming Conventions:**
```python
# Models: PascalCase
class DailyLog(Base):
    pass

# Tables: snake_case plural
__tablename__ = "daily_logs"

# Functions: snake_case
def create_log_entry(...):
    pass

# Columns: snake_case
created_at = Column(DateTime(timezone=True))
```

**SQLAlchemy Model Pattern** (from `src/models.py`):
```python
from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class FoodItem(Base):
    __tablename__ = "food_items"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, index=True)  # Index for searches
    calories = Column(Float)
```

**Session Management Pattern** (from `src/tools/food_lookup.py`):
```python
from src.database import get_db_session

def some_operation():
    session = get_db_session()
    try:
        # Do database work
        result = session.query(...)
        return result
    finally:
        session.close()  # Always close!
```

**Test Pattern** (from `tests/test_food_lookup.py`):
```python
import pytest

def test_something():
    result = function_to_test()
    assert isinstance(result, expected_type)
    assert result["field"] == expected_value
    # Use pytest.approx for floats
    assert result["number"] == pytest.approx(expected, abs=0.1)
```

**Pytest Fixture Pattern** (from `tests/conftest.py`):
```python
import pytest

@pytest.fixture
def fixture_name():
    """Docstring explaining what fixture provides."""
    # Setup
    value = create_test_resource()
    yield value
    # Teardown (optional)
    cleanup(value)
```

---

## IMPLEMENTATION PLAN

### Phase 1: Database Schema Foundation

Create the `DailyLog` model and update `FoodItem` with relationship.

**Tasks:**
- Add `DailyLog` model to `src/models.py`
- Add relationship to `FoodItem` model
- Create database migration (manual table creation for SQLite)

### Phase 2: Schema Updates

Update `FoodIntakeEvent` to use combined datetime and refactor `AgentState`.

**Tasks:**
- Refactor `FoodIntakeEvent` schema to use `timestamp` instead of `date`/`time`
- Update `AgentState` to remove individual macro fields
- Add `current_date` field to `AgentState`

### Phase 3: Service Layer Implementation

Create the service layer for CRUD operations.

**Tasks:**
- Create `src/services/` directory and `__init__.py`
- Implement `daily_log_service.py` with CRUD functions
- Add comprehensive docstrings and type hints

### Phase 4: Testing Infrastructure

Set up testing fixtures and write comprehensive tests.

**Tasks:**
- Add in-memory DB fixture to `tests/conftest.py`
- Create unit tests for `DailyLog` model
- Create unit tests for service layer functions
- Ensure all tests use fixtures properly

---

## STEP-BY-STEP TASKS

> [!IMPORTANT]
> Execute every task in order, top to bottom. Each task is atomic and independently testable.

### Task 1: CREATE `src/services/__init__.py`

- **IMPLEMENT**: Empty `__init__.py` file to make `services` a Python package
- **VALIDATE**: `python -c "import src.services"`

### Task 2: UPDATE `src/models.py` - Add DailyLog Model

- **IMPLEMENT**: Add `DailyLog` class after `FoodItem` class
- **PATTERN**: Mirror `FoodItem` structure (lines 7-15 of `src/models.py`)
- **IMPORTS**: Add `DateTime, ForeignKey` from sqlalchemy, `relationship` from sqlalchemy.orm, `datetime` from datetime
- **SCHEMA**:
  ```python
  class DailyLog(Base):
      __tablename__ = "daily_logs"
      
      id = Column(Integer, primary_key=True)
      food_id = Column(Integer, ForeignKey("food_items.id"), nullable=False)
      amount_g = Column(Float, nullable=False)
      
      # Nutritional values (denormalized)
      calories = Column(Float, nullable=False)
      protein = Column(Float, nullable=False)
      carbs = Column(Float, nullable=False)
      fat = Column(Float, nullable=False)
      
      # Temporal data
      timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
      meal_type = Column(String, nullable=True)
      
      # Audit trail
      created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
      updated_at = Column(DateTime(timezone=True), onupdate=datetime.utcnow)
      
      # Optional: preserve user input
      original_text = Column(String, nullable=True)
      
      # Relationship
      food_item = relationship("FoodItem", back_populates="logs")
  ```
- **GOTCHA**: Must use `DateTime(timezone=True)` for proper UTC storage
- **GOTCHA**: `default=datetime.utcnow` (no parentheses - pass function, not result)
- **VALIDATE**: `python -c "from src.models import DailyLog; print(DailyLog.__tablename__)"`

### Task 3: UPDATE `src/models.py` - Add Relationship to FoodItem

- **IMPLEMENT**: Add `logs = relationship("DailyLog", back_populates="food_item")` to `FoodItem` class
- **LOCATION**: After line 15 in `FoodItem` class
- **VALIDATE**: `python -c "from src.models import FoodItem, DailyLog; print(hasattr(FoodItem, 'logs'))"`

### Task 4: CREATE Database Tables

- **IMPLEMENT**: Create tables in database using SQLAlchemy
- **PATTERN**: Use `Base.metadata.create_all(engine)` from `src/database.py`
- **COMMAND**: Create a migration script or run:
  ```python
  from src.database import engine
  from src.models import Base
  Base.metadata.create_all(engine)
  ```
- **VALIDATE**: `python -c "from src.database import engine; from sqlalchemy import inspect; print('daily_logs' in inspect(engine).get_table_names())"`

### Task 5: UPDATE `src/schemas/input_schema.py` - Refactor FoodIntakeEvent

- **IMPLEMENT**: Replace `date` and `time` fields with single `timestamp` field
- **PATTERN**: Use `Optional[datetime]` from datetime module
- **CHANGE**:
  ```python
  # Remove lines 22-23:
  # date: Optional[date] = None
  # time: Optional[time] = None
  
  # Add instead:
  timestamp: Optional[datetime] = Field(None, description="When the food was consumed (UTC)")
  ```
- **IMPORTS**: Change line 3 from `from datetime import date, time` to `from datetime import datetime`
- **VALIDATE**: `python -c "from src.schemas.input_schema import FoodIntakeEvent; print(FoodIntakeEvent.model_fields.keys())"`

### Task 6: UPDATE `src/agents/state.py` - Refactor AgentState

- **IMPLEMENT**: Remove individual macro fields, add `current_date`, update docstring
- **REMOVE**: Lines 16-19 (`daily_calories`, `daily_protein`, `daily_carbs`, `daily_fat`)
- **ADD**: `current_date: date` after `daily_totals`
- **IMPORTS**: Add `from datetime import date`
- **UPDATE DOCSTRING**: Remove mentions of individual macro fields, add description of `current_date`
- **FINAL SCHEMA**:
  ```python
  class AgentState(TypedDict):
      """
      State definition for the FitPal agent.
      
      Attributes:
          messages: List of messages in the conversation history.
          pending_food_items: Food items extracted from user input, pending processing.
          daily_totals: Aggregated nutritional totals from DB {calories, protein, carbs, fat}.
          current_date: The date being tracked (for multi-day conversations).
          last_action: The last action type determined by input parser.
      """
      messages: Annotated[List, add_messages]
      pending_food_items: List[dict]
      daily_totals: dict
      current_date: date
      last_action: str
  ```
- **VALIDATE**: `python -c "from src.agents.state import AgentState; print('current_date' in AgentState.__annotations__)"`

### Task 7: CREATE `src/services/daily_log_service.py`

- **IMPLEMENT**: Service layer with CRUD functions
- **PATTERN**: Session management from `src/tools/food_lookup.py` (lines 13-20)
- **IMPORTS**:
  ```python
  from datetime import datetime, date
  from typing import List, Dict, Optional
  from sqlalchemy import select, func
  from sqlalchemy.orm import Session
  from src.models import DailyLog, FoodItem
  ```
- **FUNCTIONS TO IMPLEMENT**:

  1. `create_log_entry(session: Session, food_id: int, amount_g: float, calories: float, protein: float, carbs: float, fat: float, timestamp: datetime, meal_type: Optional[str] = None, original_text: Optional[str] = None) -> DailyLog`
     - Create and commit new DailyLog entry
     - Return the created object
  
  2. `get_daily_totals(session: Session, target_date: date) -> Dict[str, float]`
     - Query all logs for target_date (filter by timestamp.date())
     - Use `func.sum()` to aggregate calories, protein, carbs, fat
     - Return dict: `{"calories": X, "protein": Y, "carbs": Z, "fat": W}`
  
  3. `get_logs_by_date(session: Session, target_date: date) -> List[DailyLog]`
     - Query all logs for specific date
     - Return list of DailyLog objects
  
  4. `get_logs_by_date_range(session: Session, start_date: date, end_date: date) -> List[DailyLog]`
     - Query logs between start_date and end_date (inclusive)
     - Return list of DailyLog objects

- **GOTCHA**: When filtering by date from datetime column, use `func.date(DailyLog.timestamp) == target_date`
- **GOTCHA**: Always commit after creating entries: `session.add(log); session.commit(); session.refresh(log)`
- **VALIDATE**: `python -c "from src.services.daily_log_service import create_log_entry, get_daily_totals; print('Functions imported successfully')"`

### Task 8: UPDATE `tests/conftest.py` - Add DB Fixtures

- **IMPLEMENT**: Add in-memory SQLite DB fixture
- **PATTERN**: Existing `basic_state` fixture (lines 10-16)
- **ADD FIXTURE**:
  ```python
  from sqlalchemy import create_engine
  from sqlalchemy.orm import sessionmaker
  from src.models import Base, FoodItem
  
  @pytest.fixture
  def test_db_session():
      """Provides an in-memory SQLite session for testing."""
      engine = create_engine("sqlite:///:memory:")
      Base.metadata.create_all(engine)
      SessionLocal = sessionmaker(bind=engine)
      session = SessionLocal()
      
      # Seed with sample food item for testing
      sample_food = FoodItem(
          id=1,
          name="Test Chicken",
          calories=165.0,
          protein=31.0,
          fat=3.6,
          carbs=0.0
      )
      session.add(sample_food)
      session.commit()
      
      yield session
      session.close()
  ```
- **VALIDATE**: `uv run pytest tests/conftest.py::test_db_session -v` (will show fixture is available)

### Task 9: CREATE `tests/unit/test_daily_log_model.py`

- **IMPLEMENT**: Unit tests for DailyLog model
- **PATTERN**: Test pattern from `tests/test_food_lookup.py`
- **TESTS TO WRITE**:
  
  1. `test_daily_log_creation(test_db_session)` - Create DailyLog, verify all fields
  2. `test_daily_log_relationship(test_db_session)` - Verify FoodItem relationship works
  3. `test_daily_log_timestamps(test_db_session)` - Verify created_at is auto-set
  
- **EXAMPLE TEST**:
  ```python
  from datetime import datetime, timezone
  from src.models import DailyLog
  
  def test_daily_log_creation(test_db_session):
      log = DailyLog(
          food_id=1,
          amount_g=100.0,
          calories=165.0,
          protein=31.0,
          carbs=0.0,
          fat=3.6,
          timestamp=datetime.now(timezone.utc),
          meal_type="lunch"
      )
      test_db_session.add(log)
      test_db_session.commit()
      
      assert log.id is not None
      assert log.food_id == 1
      assert log.created_at is not None
  ```
- **VALIDATE**: `uv run pytest tests/unit/test_daily_log_model.py -v`

### Task 10: CREATE `tests/unit/test_daily_log_service.py`

- **IMPLEMENT**: Unit tests for service layer functions
- **PATTERN**: Test pattern from `tests/test_food_lookup.py` (lines 10-40)
- **TESTS TO WRITE**:
  
  1. `test_create_log_entry(test_db_session)` - Create entry, verify return value
  2. `test_get_daily_totals_empty(test_db_session)` - Query empty day, verify zeros
  3. `test_get_daily_totals_with_entries(test_db_session)` - Create entries, verify aggregation
  4. `test_get_logs_by_date(test_db_session)` - Create entries, filter by date
  5. `test_get_logs_by_date_range(test_db_session)` - Create multi-day entries, verify range query
  
- **EXAMPLE TEST**:
  ```python
  from datetime import datetime, date, timezone
  from src.services.daily_log_service import create_log_entry, get_daily_totals
  
  def test_get_daily_totals_with_entries(test_db_session):
      today = date.today()
      now = datetime.now(timezone.utc)
      
      # Create two log entries
      create_log_entry(
          test_db_session, 
          food_id=1, 
          amount_g=100.0,
          calories=165.0, 
          protein=31.0, 
          carbs=0.0, 
          fat=3.6,
          timestamp=now
      )
      create_log_entry(
          test_db_session, 
          food_id=1, 
          amount_g=50.0,
          calories=82.5, 
          protein=15.5, 
          carbs=0.0, 
          fat=1.8,
          timestamp=now
      )
      
      totals = get_daily_totals(test_db_session, today)
      
      assert totals["calories"] == pytest.approx(247.5, abs=0.1)
      assert totals["protein"] == pytest.approx(46.5, abs=0.1)
  ```
- **VALIDATE**: `uv run pytest tests/unit/test_daily_log_service.py -v`

---

## TESTING STRATEGY

### Unit Tests

**Framework**: pytest 9.0.2+  
**Scope**: Isolated testing of models and service functions  
**Fixtures**: In-memory SQLite database (`test_db_session`)

**Test Coverage Requirements**:
- ✅ DailyLog model creation and field validation
- ✅ Relationship between FoodItem and DailyLog
- ✅ Automatic timestamp generation (created_at)
- ✅ Service layer CRUD operations
- ✅ Date filtering and aggregation logic
- ✅ Edge cases (empty results, date boundaries)

**Fixture Strategy**:
- Use `:memory:` SQLite for speed and isolation
- Seed each test with sample FoodItem (id=1)
- Automatic teardown (session.close() in fixture)

### Integration Tests

**Scope**: Not required for this phase (no node integration yet)  
**Future**: Will test full flow when `food_lookup_node` is implemented

### Edge Cases

**Must Test**:
1. **Empty day query**: `get_daily_totals()` on date with no entries → return zeros
2. **Timezone handling**: Entries with different timezones → correct date filtering
3. **Null meal_type**: Create entry without meal_type → should succeed
4. **Date boundary**: Entries at 23:59 vs 00:01 → correct date assignment
5. **Multiple entries same food**: Aggregation works correctly

---

## VALIDATION COMMANDS

Execute every command to ensure zero regressions and 100% feature correctness.

### Level 1: Syntax & Style

```bash
# Lint with ruff
uv run ruff check src/models.py src/services/ src/agents/state.py src/schemas/input_schema.py

# Format check
uv run ruff format --check src/models.py src/services/ src/agents/state.py src/schemas/input_schema.py
```

### Level 2: Unit Tests

```bash
# Run all new unit tests
uv run pytest tests/unit/test_daily_log_model.py -v
uv run pytest tests/unit/test_daily_log_service.py -v

# Run with coverage
uv run pytest tests/unit/test_daily_log_model.py tests/unit/test_daily_log_service.py --cov=src.models --cov=src.services --cov-report=term-missing
```

### Level 3: Integration Tests

```bash
# Ensure existing tests still pass (no regressions)
uv run pytest tests/test_food_lookup.py -v
uv run pytest tests/unit/test_input_parser.py -v
```

### Level 4: Manual Validation

**Test 1: Verify Database Schema**
```python
# Run in Python REPL
from src.database import engine
from sqlalchemy import inspect

inspector = inspect(engine)
print("Tables:", inspector.get_table_names())
print("DailyLog columns:", [c['name'] for c in inspector.get_columns('daily_logs')])

# Expected: daily_logs table exists with all columns
```

**Test 2: Create and Query Log Entry**
```python
# Run in Python REPL
from src.database import get_db_session
from src.services.daily_log_service import create_log_entry, get_daily_totals
from datetime import datetime, date, timezone

session = get_db_session()
today = date.today()
now = datetime.now(timezone.utc)

# Create entry
log = create_log_entry(
    session, 
    food_id=1,  # Assumes FoodItem with id=1 exists
    amount_g=100.0,
    calories=165.0,
    protein=31.0,
    carbs=0.0,
    fat=3.6,
    timestamp=now,
    meal_type="lunch"
)
print(f"Created log: {log.id}")

# Query totals
totals = get_daily_totals(session, today)
print(f"Daily totals: {totals}")

session.close()

# Expected: Log created with ID, totals show 165 cal, 31g protein
```

### Level 5: Additional Validation

**Import Validation**:
```bash
# Verify all new modules import without errors
python -c "from src.models import DailyLog; from src.services.daily_log_service import create_log_entry, get_daily_totals; from src.agents.state import AgentState; print('All imports successful')"
```

**Type Checking** (if mypy is added later):
```bash
uv add --dev mypy
uv run mypy src/models.py src/services/daily_log_service.py
```

---

## ACCEPTANCE CRITERIA

- [x] `DailyLog` model created with all required fields (11 columns)
- [x] Relationship between `FoodItem` and `DailyLog` established
- [x] `FoodIntakeEvent` schema updated to use `timestamp` instead of `date`/`time`
- [x] `AgentState` refactored (removed 4 fields, added `current_date`)
- [x] Service layer created with 4 CRUD functions
- [x] In-memory DB fixture added to `conftest.py`
- [x] Unit tests for `DailyLog` model (3+ tests)
- [x] Unit tests for service layer (5+ tests)
- [x] All validation commands pass with zero errors
- [x] No regressions in existing tests
- [x] Code follows project conventions (snake_case, docstrings, type hints)
- [x] Database tables created successfully
- [x] Manual validation confirms CRUD operations work

---

## COMPLETION CHECKLIST

- [ ] All 10 tasks completed in order
- [ ] Each task validation passed immediately after implementation
- [ ] All Level 1-5 validation commands executed successfully
- [ ] Full test suite passes (new + existing tests)
- [ ] No linting or formatting errors
- [ ] Manual testing confirms feature works end-to-end
- [ ] All acceptance criteria met
- [ ] Code reviewed for quality and maintainability
- [ ] Documentation updated (this plan serves as documentation)

---

## NOTES

### Design Decisions

**1. Why Denormalize Nutritional Values?**
- Store calculated macros in `DailyLog` instead of computing on-the-fly
- **Trade-off**: Slight data duplication vs. query performance
- **Rationale**: Aggregation queries (`SUM(calories)`) are much faster on indexed columns

**2. Why Write-Through Pattern?**
- Write to DB immediately, then query for state updates
- **Alternative**: Accumulate in state, write at end of conversation
- **Rationale**: Durability > Performance. Prevents data loss on crashes.

**3. Why Service Layer?**
- Separate business logic from models and nodes
- **Alternative**: Put logic in models (Active Record) or directly in nodes
- **Rationale**: Testability, separation of concerns, scalability

**4. Why UTC Datetime?**
- Store all timestamps in UTC, convert for display
- **Alternative**: Store in user's local timezone
- **Rationale**: Avoids DST bugs, standard practice for distributed systems

### Known Limitations

- **No migration system**: Using `Base.metadata.create_all()` for simplicity
  - For production, consider Alembic for schema migrations
- **No soft deletes**: Entries are permanently deleted
  - Future: Add `deleted_at` column for soft deletes
- **No user isolation**: Single-user system (no user_id foreign key)
  - Future: Add multi-user support with user_id column

### Future Enhancements

- Add `update_log_entry()` and `delete_log_entry()` for correction flows (Phase 3)
- Add indexes on `meal_type` if filtering by meal becomes common
- Add `user_id` foreign key for multi-user support
- Implement Alembic migrations for schema versioning
- Add caching layer (Redis) if query performance becomes issue

---

## Confidence Score: 9/10

**Rationale**:
- ✅ All patterns extracted from existing codebase
- ✅ Clear, atomic tasks with validation commands
- ✅ Comprehensive test strategy with fixtures
- ✅ No external dependencies (all libraries already installed)
- ⚠️ Minor risk: Manual table creation step (Task 4) - could fail if DB is locked

**Expected Implementation Time**: 2-3 hours for experienced developer, 4-5 hours for someone new to SQLAlchemy.
