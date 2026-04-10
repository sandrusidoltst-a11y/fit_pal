# Daily Log Persistence - Planning Discussion & Recommendations

## Current Understanding

From the PRD and codebase analysis, here's what we need for **Phase 1: Daily Log Persistence**:

### What We Need
1. **Database Schema**: A `DailyLog` SQLAlchemy model to store food entries
2. **CRUD Operations**: Helper functions to write/read log entries
3. **Integration Points**: How nodes will interact with this persistence layer

---

## Architectural Decisions

### 1. Database Schema Design ✅

**USER INPUT**:
- ✅ `timestamp` - yes
- ✅ `meal_type` - yes, add to log
- ❓ `created_at` / `updated_at` - what's the difference from timestamp?

**RECOMMENDATION**:

Let me clarify the difference:
- **`timestamp`**: When the user actually ATE the food (e.g., "I had breakfast at 8:30 AM")
- **`created_at`**: When the log entry was CREATED in the database (e.g., user logged it at 10:00 PM)
- **`updated_at`**: When the entry was last modified (for correction flows)

**Decision**: Include all three for maximum flexibility:
- `timestamp` (DateTime) - When food was consumed (from `FoodIntakeEvent.date` + `time`)
- `meal_type` (String, nullable) - breakfast/lunch/dinner/snack
- `created_at` (DateTime) - Auto-set on insert
- `updated_at` (DateTime) - Auto-set on update

**About storing entire FoodIntakeEvent**: Good instinct! But we should **denormalize** it:
- Store the parsed fields directly in `DailyLog` (timestamp, meal_type, etc.)
- Optionally add `original_text` field to preserve user's exact input
- This makes querying much easier than storing JSON blobs

---

### 2. Date Handling ✅

**USER REQUEST**: "Give me your best practice recommendation"

**RECOMMENDATION**:

**Best Practice for LangGraph Agents**:

1. **Storage**: Always store as **UTC datetime** in the database
   - SQLAlchemy: Use `DateTime(timezone=True)` 
   - This prevents timezone bugs when querying

2. **Input Handling**:
   - If user provides date/time → use it
   - If missing → default to `datetime.now(timezone.utc)`
   - Store user's timezone in config (UTC+2 for you)

3. **Display**: Convert to user's local timezone when showing results

4. **Update `FoodIntakeEvent` schema**:
   ```python
   # Change from:
   date: Optional[date] = None
   time: Optional[time] = None
   
   # To:
   timestamp: Optional[datetime] = None  # Combined datetime
   ```

**Why**: Simpler to work with, avoids date/time mismatch bugs, standard practice.

---

### 3. CRUD Operations Location ✅

**USER REQUEST**: "What is your recommendation for this phase in the project?"

**RECOMMENDATION**: **Option B - Service Layer Pattern**

Create `src/services/daily_log_service.py`

**Why**:
- ✅ **Separation of Concerns**: Models define schema, services handle business logic
- ✅ **Testability**: Easy to mock services in node tests
- ✅ **Scalability**: As project grows, services can orchestrate multiple models
- ✅ **LangGraph Best Practice**: Nodes should be thin, calling services for data operations

**Structure**:
```python
# src/services/daily_log_service.py
def create_log_entry(session, food_id, amount_g, timestamp, meal_type, ...):
    """Create a new daily log entry"""
    
def get_daily_totals(session, date):
    """Get aggregated totals for a specific date"""
    
def get_logs_by_date_range(session, start_date, end_date):
    """Query logs within a date range"""
```

---

### 4. State Management ✅

**USER INPUT**: "In the first conversation of a day the user won't have anything inside his log. I was thinking holding it in the state then passing it to the DB but maybe it's not the best way."

**EXCELLENT QUESTION!** Let me clarify the options:

**Your Current Thinking** (State → DB):
```
User: "I ate 200g chicken"
→ Input Parser extracts data
→ Store in AgentState (daily_protein += 50g)
→ At end of conversation, write to DB
```

**Problem**: If conversation crashes, data is lost! ❌

**RECOMMENDATION**: **Write-Through Pattern** (DB is source of truth)

```
User: "I ate 200g chicken"
→ Input Parser extracts data
→ IMMEDIATELY write to DB
→ Query DB for updated totals
→ Update AgentState with fresh totals from DB
```

**Why**:
- ✅ **Durability**: Data persisted immediately
- ✅ **Consistency**: State always reflects DB reality
- ✅ **Crash Recovery**: Can resume conversation anytime
- ✅ **LangGraph Checkpointer**: Works seamlessly with state snapshots

**Decision**: 
- **Remove** `daily_calories`, `daily_protein`, etc. from `AgentState`
- **Keep** `daily_totals: dict` but populate it from DB on each turn
- **Add** `current_date: date` to track which day we're logging

**Flow**:
1. `food_lookup_node` → writes to DB immediately
2. `stats_lookup_node` → queries DB for totals
3. Both update `state["daily_totals"]` with fresh DB data

---

### 5. Testing Strategy ✅

**USER REQUEST**: "Use your testing skill to answer that"

**RECOMMENDATION** (Based on testing-and-logging skill):

**Use In-Memory SQLite (`:memory:`) for Unit Tests**

**Why**:
- ✅ **Fast**: No disk I/O, tests run in milliseconds
- ✅ **Isolated**: Each test gets fresh DB, no pollution
- ✅ **Simple**: No cleanup needed, automatic teardown
- ✅ **CI/CD Friendly**: Works everywhere without setup

**Implementation**:
```python
# tests/conftest.py
import pytest
from sqlalchemy import create_engine
from src.models import Base

@pytest.fixture
def test_db_session():
    """Provides an in-memory SQLite session for testing"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
```

**For Integration Tests**: Use a separate `data/test_nutrition.db` file that gets reset before each test run.

---

## Final Schema Design

```python
class DailyLog(Base):
    __tablename__ = "daily_logs"
    
    id = Column(Integer, primary_key=True)
    food_id = Column(Integer, ForeignKey("food_items.id"), nullable=False)
    amount_g = Column(Float, nullable=False)
    
    # Nutritional values (denormalized for query performance)
    calories = Column(Float, nullable=False)
    protein = Column(Float, nullable=False)
    carbs = Column(Float, nullable=False)
    fat = Column(Float, nullable=False)
    
    # Temporal data
    timestamp = Column(DateTime(timezone=True), nullable=False)  # When food was eaten
    meal_type = Column(String, nullable=True)  # breakfast/lunch/dinner/snack
    
    # Audit trail
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), onupdate=datetime.utcnow)
    
    # Optional: preserve original user input
    original_text = Column(String, nullable=True)
    
    # Relationship
    food_item = relationship("FoodItem", backref="logs")
```

---

## Updated AgentState

```python
class AgentState(TypedDict):
    messages: Annotated[List, add_messages]
    
    # Remove these (query from DB instead):
    # daily_calories: float
    # daily_protein: float
    # daily_carbs: float
    # daily_fat: float
    
    # Keep these:
    pending_food_items: List[dict]
    daily_totals: dict  # Populated from DB: {calories, protein, carbs, fat}
    current_date: date  # Track which day we're logging
    last_action: str
    search_results: List[dict]  # For agent selection node
```

---

## Next Steps

**Ready to proceed?** I'll now create the comprehensive implementation plan with:
- ✅ Database schema with all recommended fields
- ✅ Service layer for CRUD operations
- ✅ Write-through pattern for state management
- ✅ In-memory SQLite for testing
- ✅ Updated `FoodIntakeEvent` schema
- ✅ Migration strategy for `AgentState`

Let me know if you agree with these recommendations or want to adjust anything!
