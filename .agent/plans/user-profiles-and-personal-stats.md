# Feature: User Profiles & Personal Stats Logging

The following plan should be complete, but its important that you validate documentation and codebase patterns and task sanity before you start implementing.

Pay special attention to naming of existing utils types and models. Import from the right files etc.

## Feature Description

Add user profile management and personal stats logging to FitPal. Users set their profile (name, height, age, gender) during onboarding via the Telegram bot, and can log body measurements (weight, body fat %) through the graph agent via natural language. Profile data is injected into every graph run via config so the agent can personalize responses without extra DB queries.

## User Story

As a FitPal user
I want to store my personal profile and log body measurements over time
So that the agent knows my name, and I can track changes in weight and body composition

## Problem Statement

Currently FitPal has no concept of user identity beyond a UUID. The agent cannot greet users by name, and there is no way to track body measurements over time. Each new thread loses all personal context.

## Solution Statement

1. **`user_profiles` table** — stores identity data (name, height, age, gender), set once during bot onboarding
2. **`personal_stats_log` table** — stores time-series body measurements (weight, body fat %), logged via the graph agent
3. **Bot onboarding flow** — deterministic step-by-step Q&A after first registration, no LLM involved
4. **Profile injection** — bot loads profile from DB and passes it in `config["configurable"]` on every graph call
5. **New graph action `LOG_PERSONAL_STATS`** — input parser routes to new `personal_stats_node` which extracts stat type/value via its own LLM call and saves to DB

## Feature Metadata

**Feature Type**: New Capability
**Estimated Complexity**: Medium
**Primary Systems Affected**: Database models, bot gateway, graph agent (input parser + new node), service layer
**Dependencies**: No new external libraries required

---

## CONTEXT REFERENCES

### Relevant Codebase Files IMPORTANT: YOU MUST READ THESE FILES BEFORE IMPLEMENTING!

- `src/models.py` (lines 1-64) — Why: SQLAlchemy model patterns (Mapped columns, UUID PKs, relationships, audit fields). Mirror `DailyLog` for `PersonalStatsLog`.
- `src/database.py` — Why: Async session management (`get_async_db_session`, `AsyncSessionLocal`). New service/tools use same pattern.
- `src/services/daily_log_service.py` — Why: Service + tool dual layer pattern. Core functions accept `session: AsyncSession` (DI), `@tool` wrappers own their session and extract `user_id` from config.
- `src/tools/food_lookup.py` — Why: Async tool patterns (`@tool async def`, `get_user_id(config)`, return JSON dicts).
- `src/agents/nodes/stats_node.py` — Why: Simple async node pattern (read state, call tool with `await tool.ainvoke()`, return state dict). Mirror for `personal_stats_node`.
- `src/agents/nodes/input_node.py` — Why: Input parser pattern (load prompt, inject system time, structured output, return state updates). Needs `LOG_PERSONAL_STATS` action added.
- `src/agents/nodes/response_node.py` — Why: Context building pattern (`_build_context`). Needs new case for `LOG_PERSONAL_STATS`.
- `src/schemas/input_schema.py` — Why: `ActionType` enum and `FoodIntakeEvent` schema. Add `LOG_PERSONAL_STATS` to enum.
- `src/agents/state.py` (lines 51-63) — Why: `GraphAction` Literal type. Add `LOG_PERSONAL_STATS`.
- `src/agents/nutritionist.py` — Why: Graph wiring (nodes, edges, routing functions). Add new node and route.
- `src/config.py` (lines 25-49) — Why: `get_user_id()` pattern for extracting from config. Add `get_user_profile()` helper.
- `bot/gateway.py` — Why: Bot message handling, session management, `_call_langgraph()` config injection. Add onboarding flow and profile injection.
- `bot/supabase_admin.py` — Why: `get_or_create_user()` returns `is_new` flag. Onboarding triggers on `is_new: True`.
- `prompts/input_parser.md` — Why: Current prompt structure. Add `LOG_PERSONAL_STATS` action definition.
- `tests/unit/test_stats_node.py` — Why: Unit test pattern for async nodes with mocked tools.
- `tests/unit/test_commit_node.py` — Why: Unit test pattern for nodes that write to DB via tools.
- `tests/unit/test_input_parser.py` — Why: Unit test pattern for input parser action classification.
- `tests/unit/test_gateway.py` — Why: Bot gateway test patterns (mocked httpx, session management).
- `tests/integration/test_daily_log_service.py` — Why: Integration test pattern with real DB (transaction rollback fixture).
- `tests/conftest.py` — Why: Shared fixtures (`basic_state`, `TEST_CONFIG_A`, mock patterns).

### New Files to Create

- `src/services/personal_stats_service.py` — Service functions + @tool wrappers for personal stats CRUD
- `src/services/user_profile_service.py` — Service functions for user profile CRUD (no @tool wrappers — bot-only, not graph-accessible)
- `src/agents/nodes/personal_stats_node.py` — New graph node for stat extraction and logging
- `src/schemas/personal_stats_schema.py` — Pydantic schema for LLM stat extraction
- `prompts/personal_stats_extractor.md` — Prompt for extracting stat type/value from natural language
- `tests/unit/test_personal_stats_node.py` — Unit tests for the new node
- `tests/unit/test_onboarding.py` — Unit tests for bot onboarding flow
- `tests/integration/test_personal_stats_service.py` — Integration tests for stats service

### Relevant Documentation YOU SHOULD READ THESE BEFORE IMPLEMENTING!

- [Supabase Migrations](https://supabase.com/docs/guides/cli/managing-environments)
  - How to create and apply migrations
  - Why: Need migrations for both new tables
- [Supabase RLS Policies](https://supabase.com/docs/guides/database/postgres/row-level-security)
  - User-scoped row level security patterns
  - Why: Both tables need RLS policies matching existing `food_items`/`daily_logs` pattern
- [LangGraph RunnableConfig](https://python.langchain.com/docs/concepts/runnables/#runnableconfig)
  - How to pass custom data via config["configurable"]
  - Why: Profile injection pattern

### Patterns to Follow

**Service + Tool Dual Layer** (from `src/services/daily_log_service.py`):
```python
# Core function: explicit session DI, pure async
async def create_stat_entry(session: AsyncSession, user_id: str, ...) -> PersonalStatsLog:
    entry = PersonalStatsLog(...)
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry

# @tool wrapper: owns session, extracts user_id from config
@tool
async def log_personal_stat(stat_type: str, value: float, ..., config: RunnableConfig = None) -> dict:
    user_id = get_user_id(config)
    async with get_async_db_session() as session:
        entry = await create_stat_entry(session, user_id, ...)
        return {"id": str(entry.id), "status": "logged"}
```

**Async Node Pattern** (from `src/agents/nodes/stats_node.py`):
```python
async def personal_stats_node(state: AgentState, config: RunnableConfig) -> dict:
    # 1. Extract user message
    # 2. LLM structured output to get stat_type + value
    # 3. Call tool with await tool.ainvoke({...}, config=config)
    # 4. Return state dict
```

**Structured Output Pattern** (from `src/agents/nodes/input_node.py`):
```python
llm = get_llm_for_node("personal_stats_node")
structured_llm = llm.with_structured_output(PersonalStatExtraction)
result = structured_llm.invoke([SystemMessage(...), user_message])
```

**Mock Pattern for Unit Tests** (from `tests/conftest.py`):
```python
@pytest.fixture
def mock_log_personal_stat():
    with patch("src.agents.nodes.personal_stats_node.log_personal_stat") as mock:
        mock.ainvoke = AsyncMock()
        yield mock
```

**Naming Conventions:**
- Models: PascalCase (`PersonalStatsLog`, `UserProfile`)
- Tables: snake_case (`personal_stats_log`, `user_profiles`)
- Services: snake_case functions (`create_stat_entry`, `get_stat_history`)
- Tools: snake_case with descriptive names (`log_personal_stat`, `get_stat_history`)
- Nodes: snake_case with `_node` suffix (`personal_stats_node`)
- Schemas: PascalCase Pydantic models (`PersonalStatExtraction`)

**Error Handling:**
- Services: raise exceptions (caller handles)
- Tools: return `{"error": "message"}` dict
- Nodes: log warnings, return safe defaults

**Logging Pattern:**
```python
logger = structlog.get_logger(__name__)
logger.info("Stat logged", stat_type=stat_type, value=value, user_id=user_id)
```

---

## IMPLEMENTATION PLAN

### Phase 1: Foundation (Database + Models)

Create the two new database tables and SQLAlchemy models. Apply Supabase migrations with RLS policies.

**Tasks:**
- Add `UserProfile` and `PersonalStatsLog` SQLAlchemy models to `src/models.py`
- Create Supabase migration for both tables with indexes and RLS

### Phase 2: Service Layer

Create service functions and tools for personal stats. Create profile service for bot-level CRUD (no tools — bot accesses directly).

**Tasks:**
- Create `src/services/user_profile_service.py` with profile CRUD
- Create `src/services/personal_stats_service.py` with stat CRUD + @tool wrappers

### Phase 3: Graph Changes

Add `LOG_PERSONAL_STATS` action, create the new node with its own schema/prompt, wire into the graph.

**Tasks:**
- Add `LOG_PERSONAL_STATS` to `ActionType` enum and `GraphAction` literal
- Create `PersonalStatExtraction` Pydantic schema
- Create extraction prompt
- Create `personal_stats_node`
- Add node config for LLM
- Update input parser prompt
- Wire node into graph
- Update response node context building

### Phase 4: Bot Changes

Add deterministic onboarding flow and profile injection into graph config.

**Tasks:**
- Add onboarding state machine to bot gateway
- Load and inject profile into config on every message

### Phase 5: Testing & Validation

Unit tests, integration tests, and eval dataset updates.

**Tasks:**
- Unit tests for personal_stats_node
- Unit tests for onboarding flow
- Integration tests for personal stats service
- Update eval datasets with LOG_PERSONAL_STATS examples

---

## STEP-BY-STEP TASKS

IMPORTANT: Execute every task in order, top to bottom. Each task is atomic and independently testable.

### Task 1: UPDATE `src/models.py` — Add UserProfile and PersonalStatsLog models

- **IMPLEMENT**: Add two new SQLAlchemy models following existing `DailyLog` pattern:

```python
class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, primary_key=True, default=uuid_mod.uuid4)
    user_id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    height_cm: Mapped[float] = mapped_column(Float, nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    gender: Mapped[str] = mapped_column(String, nullable=False)  # "male", "female", "other"
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc)
    )

class PersonalStatsLog(Base):
    __tablename__ = "personal_stats_log"

    id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, primary_key=True, default=uuid_mod.uuid4)
    user_id: Mapped[uuid_mod.UUID] = mapped_column(Uuid, nullable=False, index=True)
    weight_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    body_fat_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
```

- **PATTERN**: Mirror `DailyLog` in `src/models.py` (lines 29-63) for column style, UUID PKs, audit fields
- **IMPORTS**: Add `Integer` to the SQLAlchemy imports on line 5
- **GOTCHA**: `user_id` on `UserProfile` must be `unique=True` (one profile per user). `PersonalStatsLog` does NOT have unique constraint (time-series).
- **GOTCHA**: `PersonalStatsLog` uses `recorded_at` (not `timestamp`) to distinguish from `DailyLog.timestamp`. Include time, not just date.
- **VALIDATE**: `uv run python -c "from src.models import UserProfile, PersonalStatsLog; print('Models imported OK')"`

### Task 2: CREATE Supabase migration — Both tables + RLS

- **IMPLEMENT**: Create migration file via Supabase MCP or manually at `supabase/migrations/<timestamp>_add_user_profiles_and_personal_stats.sql`:

```sql
-- User Profiles table
CREATE TABLE IF NOT EXISTS public.user_profiles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL UNIQUE,
    name text NOT NULL,
    height_cm double precision NOT NULL,
    age integer NOT NULL,
    gender text NOT NULL,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz
);

CREATE INDEX idx_user_profiles_user_id ON public.user_profiles USING btree (user_id);

-- RLS for user_profiles
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own profile" ON public.user_profiles
    FOR SELECT USING ((SELECT auth.uid()) = user_id);
CREATE POLICY "Users can insert own profile" ON public.user_profiles
    FOR INSERT WITH CHECK ((SELECT auth.uid()) = user_id);
CREATE POLICY "Users can update own profile" ON public.user_profiles
    FOR UPDATE USING ((SELECT auth.uid()) = user_id)
    WITH CHECK ((SELECT auth.uid()) = user_id);

-- Service role bypass (for bot writes)
CREATE POLICY "Service role full access to user_profiles" ON public.user_profiles
    FOR ALL USING (auth.role() = 'service_role');

-- Personal Stats Log table
CREATE TABLE IF NOT EXISTS public.personal_stats_log (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL,
    weight_kg double precision,
    body_fat_pct double precision,
    recorded_at timestamptz NOT NULL,
    created_at timestamptz DEFAULT now()
);

CREATE INDEX idx_personal_stats_log_user_id ON public.personal_stats_log USING btree (user_id);
CREATE INDEX idx_personal_stats_log_recorded_at ON public.personal_stats_log USING btree (recorded_at);

-- RLS for personal_stats_log
ALTER TABLE public.personal_stats_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own stats" ON public.personal_stats_log
    FOR SELECT USING ((SELECT auth.uid()) = user_id);
CREATE POLICY "Users can insert own stats" ON public.personal_stats_log
    FOR INSERT WITH CHECK ((SELECT auth.uid()) = user_id);

-- Service role bypass (for graph writes)
CREATE POLICY "Service role full access to personal_stats_log" ON public.personal_stats_log
    FOR ALL USING (auth.role() = 'service_role');
```

- **PATTERN**: Mirror existing RLS policies on `food_items` and `daily_logs` (service role bypass for bot/graph writes)
- **GOTCHA**: Use `(SELECT auth.uid())` (with subquery) for RLS performance per Supabase docs
- **GOTCHA**: FitPal uses service role key which bypasses RLS. The policies are defense-in-depth.
- **VALIDATE**: Apply migration via Supabase MCP `mcp__supabase__apply_migration` or `supabase db push`

### Task 3: CREATE `src/services/user_profile_service.py` — Profile CRUD (bot-only)

- **IMPLEMENT**: Service functions for profile CRUD. NO @tool wrappers — this is accessed by the bot, not the graph.

```python
"""User profile service for bot-level CRUD operations.

Handles creation and retrieval of user profiles during onboarding
and for config injection. Not exposed as LangGraph tools — the bot
accesses these directly.
"""

import uuid as uuid_mod
from typing import Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import UserProfile

logger = structlog.get_logger(__name__)


async def create_user_profile(
    session: AsyncSession,
    user_id: str,
    name: str,
    height_cm: float,
    age: int,
    gender: str,
) -> UserProfile:
    """Create a new user profile."""
    profile = UserProfile(
        user_id=uuid_mod.UUID(user_id),
        name=name,
        height_cm=height_cm,
        age=age,
        gender=gender,
    )
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    logger.info("User profile created", user_id=user_id, name=name)
    return profile


async def get_user_profile(
    session: AsyncSession,
    user_id: str,
) -> Optional[dict]:
    """Get user profile as a dict, or None if not found."""
    stmt = select(UserProfile).where(
        UserProfile.user_id == uuid_mod.UUID(user_id)
    )
    result = await session.execute(stmt)
    profile = result.scalar_one_or_none()
    if profile is None:
        return None
    return {
        "name": profile.name,
        "height_cm": profile.height_cm,
        "age": profile.age,
        "gender": profile.gender,
    }
```

- **PATTERN**: Mirror `src/services/daily_log_service.py` core functions (explicit `session` param, async, structlog)
- **GOTCHA**: No @tool wrappers here. The bot imports these directly. The graph never needs profile CRUD.
- **VALIDATE**: `uv run python -c "from src.services.user_profile_service import create_user_profile, get_user_profile; print('OK')"`

### Task 4: CREATE `src/services/personal_stats_service.py` — Stats service + tools

- **IMPLEMENT**: Service functions with @tool wrappers following the dual-layer pattern.

Core functions needed:
- `create_stat_entry(session, user_id, weight_kg, body_fat_pct, recorded_at) -> PersonalStatsLog`
- `get_latest_stats(session, user_id) -> Optional[dict]`
- `get_stat_history(session, user_id, stat_type, limit) -> list[dict]`

Tool wrappers needed:
- `@tool async def log_personal_stat(stat_type, value, config) -> dict` — creates a stat entry
- `@tool async def get_personal_stat_history(stat_type, limit, config) -> list[dict]` — retrieves history (for future chart features)

- **PATTERN**: Mirror `src/services/daily_log_service.py` exactly — core functions accept `session`, tools own their session via `get_async_db_session()`, tools extract user_id via `get_user_id(config)`
- **IMPORTS**: `from src.database import get_async_db_session`, `from src.config import get_user_id`, `from src.models import PersonalStatsLog`
- **GOTCHA**: `log_personal_stat` tool receives `stat_type: str` ("weight" or "body_fat") and `value: float`. Map to correct column: weight → `weight_kg`, body_fat → `body_fat_pct`. The other column stays None.
- **GOTCHA**: `recorded_at` should default to `datetime.now(timezone.utc)` if not provided by the user. The node will handle relative time parsing if needed.
- **VALIDATE**: `uv run python -c "from src.services.personal_stats_service import log_personal_stat, get_personal_stat_history; print('OK')"`

### Task 5: CREATE `src/schemas/personal_stats_schema.py` — Extraction schema

- **IMPLEMENT**: Pydantic model for LLM structured output in personal_stats_node:

```python
"""Schema for personal stats extraction from natural language."""

from typing import Literal, Optional
from pydantic import BaseModel, Field


class PersonalStatExtraction(BaseModel):
    """Extracted personal stat from user message."""

    stat_type: Literal["weight", "body_fat"] = Field(
        ...,
        description="The type of body measurement. 'weight' for body weight, 'body_fat' for body fat percentage."
    )
    value: float = Field(
        ...,
        description="The numeric value of the measurement. For weight: kilograms. For body fat: percentage (0-100)."
    )
    unit: Optional[str] = Field(
        None,
        description="The unit provided by the user, e.g. 'kg', 'lbs', '%'. Used for conversion if needed."
    )
```

- **PATTERN**: Mirror `src/schemas/estimation_schema.py` — simple flat Pydantic model with Field descriptions
- **VALIDATE**: `uv run python -c "from src.schemas.personal_stats_schema import PersonalStatExtraction; print('OK')"`

### Task 6: CREATE `prompts/personal_stats_extractor.md` — Extraction prompt

- **IMPLEMENT**: Prompt for extracting stat type and value from natural language:

```markdown
You are extracting body measurement data from user messages.

Identify which type of measurement the user is reporting and extract the numeric value.

### Supported Measurements:
- **weight**: Body weight in kilograms. If the user provides pounds (lbs), convert to kg (divide by 2.205).
  - Examples: "I weigh 74kg", "74 kilos", "שוקל 74", "163 lbs"
- **body_fat**: Body fat percentage (0-100).
  - Examples: "My body fat is 15%", "BF is 14.5", "אחוז שומן 15"

### Rules:
- Always output the value in the standard unit (kg for weight, % for body fat)
- If the user provides lbs, convert to kg
- Extract only the first measurement if multiple are mentioned
- The user message may be in English or Hebrew
```

- **PATTERN**: Mirror `prompts/macro_estimation.md` structure — clear rules, examples, multilingual support
- **VALIDATE**: File exists: `ls prompts/personal_stats_extractor.md`

### Task 7: UPDATE `src/schemas/input_schema.py` — Add LOG_PERSONAL_STATS action

- **IMPLEMENT**: Add `LOG_PERSONAL_STATS = "LOG_PERSONAL_STATS"` to `ActionType` enum
- **PATTERN**: Follows existing enum values on lines 5-10
- **GOTCHA**: Must match exactly the string used in `GraphAction` literal (Task 8)
- **VALIDATE**: `uv run python -c "from src.schemas.input_schema import ActionType; print(ActionType.LOG_PERSONAL_STATS)"`

### Task 8: UPDATE `src/agents/state.py` — Add LOG_PERSONAL_STATS to GraphAction

- **IMPLEMENT**: Add `"LOG_PERSONAL_STATS"` to the `GraphAction` Literal type on lines 51-63
- **PATTERN**: Follows existing action strings in the Literal
- **VALIDATE**: `uv run python -c "from src.agents.state import GraphAction; print('OK')"`

### Task 9: UPDATE `prompts/input_parser.md` — Add LOG_PERSONAL_STATS action definition

- **IMPLEMENT**: Add new action to Step 1 in the prompt, between QUERY_DAILY_STATS and QUERY_FOOD_INFO:

```markdown
- **LOG_PERSONAL_STATS**: The user is reporting a body measurement (weight, body fat).
  - Examples: "I weigh 74kg", "My weight is 74 kilos", "Body fat is 15%", "שוקל 74", "אחוז שומן 15"
  - Do NOT confuse with food logging — this is about the user's body, not food.
  - Return an **empty list** for `items` (`[]`).
```

- **PATTERN**: Mirror existing action definitions with examples and clear disambiguation
- **GOTCHA**: Must explicitly state "empty list for items" to prevent parser from extracting "74kg" as food
- **VALIDATE**: `grep "LOG_PERSONAL_STATS" prompts/input_parser.md`

### Task 10: UPDATE `src/config.py` — Add personal_stats_node config and get_user_profile helper

- **IMPLEMENT**:
  1. Add `"personal_stats_node": {"temperature": 0.0}` to `NODE_CONFIGS` dict
  2. Add dev default profile (mirrors `DEFAULT_DEV_USER_ID` pattern):
     ```python
     DEFAULT_DEV_PROFILE = {
         "name": "Dev User",
         "height_cm": 175.0,
         "age": 25,
         "gender": "male",
     }
     ```

  3. Add helper function to extract user profile from config:

```python
def get_user_profile(config: RunnableConfig | None) -> dict:
    """Extract user_profile from config, falling back to dev default.

    Priority chain:
    1. Production: bot injects real profile from DB into config.
    2. Dev/Studio: falls back to DEFAULT_DEV_PROFILE.

    Always returns a profile dict so nodes never need None-checks.
    """
    if config:
        profile = config["configurable"].get("user_profile")
        if profile:
            return profile
    logger.warning("No user_profile in config, falling back to DEFAULT_DEV_PROFILE")
    return DEFAULT_DEV_PROFILE
```

- **PATTERN**: Mirror `get_user_id()` on lines 25-49 — same fallback chain concept
- **GOTCHA**: Returns `dict` (not `Optional[dict]`) — nodes never need to handle None. Dev always gets a profile.
- **VALIDATE**: `uv run python -c "from src.config import get_user_profile, DEFAULT_DEV_PROFILE; print(DEFAULT_DEV_PROFILE)"`

### Task 11: CREATE `src/agents/nodes/personal_stats_node.py` — New graph node

- **IMPLEMENT**: Async node that:
  1. Gets the last user message
  2. Loads prompt from `prompts/personal_stats_extractor.md`
  3. Uses `get_llm_for_node("personal_stats_node")` with structured output (`PersonalStatExtraction`)
  4. Calls `log_personal_stat` tool with extracted data
  5. Returns state dict with `last_action` and `processing_results`

```python
async def personal_stats_node(state: AgentState, config: RunnableConfig) -> dict:
    messages = state.get("messages", [])
    last_message = messages[-1]

    # Load prompt
    prompt_path = os.path.join(BASE_DIR, "prompts", "personal_stats_extractor.md")
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read()
    except FileNotFoundError:
        system_prompt = "Extract the body measurement type and value from the user message."

    # Extract stat via LLM
    llm = get_llm_for_node("personal_stats_node")
    structured_llm = llm.with_structured_output(PersonalStatExtraction)
    result = structured_llm.invoke([
        SystemMessage(content=system_prompt),
        last_message,
    ])

    # Log stat via tool
    tool_result = await log_personal_stat.ainvoke(
        {"stat_type": result.stat_type, "value": result.value},
        config=config,
    )

    # Build processing result for response node
    stat_label = "weight" if result.stat_type == "weight" else "body fat"
    unit = "kg" if result.stat_type == "weight" else "%"
    processing_results = list(state.get("processing_results", []))
    processing_results.append({
        "food_name": f"{stat_label}: {result.value}{unit}",
        "amount": result.value,
        "unit": unit,
        "original_text": last_message.content if hasattr(last_message, 'content') else str(last_message),
        "status": "LOGGED",
        "message": f"Logged {stat_label}: {result.value}{unit}",
        "source": None,
    })

    return {
        "last_action": "LOGGED",
        "processing_results": processing_results,
    }
```

- **PATTERN**: Mirror `src/agents/nodes/stats_node.py` for async node structure. Mirror `src/agents/nodes/input_node.py` for prompt loading + structured output.
- **IMPORTS**: `os`, `structlog`, `SystemMessage` from langchain_core, `AgentState` from state, `RunnableConfig`, `get_llm_for_node` and `BASE_DIR` from config, `PersonalStatExtraction` from schemas, `log_personal_stat` from services
- **GOTCHA**: Use `structlog.get_logger(__name__)` not `logging.getLogger`
- **GOTCHA**: Reuse `ProcessingResult`-like dict shape so response_node can handle it with existing `_build_context` logic for `LOGGED` action
- **VALIDATE**: `uv run python -c "from src.agents.nodes.personal_stats_node import personal_stats_node; print('OK')"`

### Task 12: UPDATE `src/agents/nutritionist.py` — Wire new node into graph

- **IMPLEMENT**:
  1. Import `personal_stats_node` from new module
  2. Add node: `workflow.add_node("personal_stats", personal_stats_node)`
  3. Add `LOG_PERSONAL_STATS` route in `route_parser`:
     ```python
     elif action == "LOG_PERSONAL_STATS":
         return "personal_stats"
     ```
  4. Update conditional edges map to include `"personal_stats": "personal_stats"`
  5. Add edge: `workflow.add_edge("personal_stats", "response")`

- **PATTERN**: Mirror `stats_lookup` wiring — simple path: `input_parser → personal_stats → response`
- **GOTCHA**: The route string in `route_parser` must match the key in the conditional edges dict AND the node name
- **VALIDATE**: `uv run python -c "from src.agents.nutritionist import define_graph; import asyncio; g = asyncio.run(define_graph()); print('Graph compiled OK')"`

### Task 13: UPDATE `src/agents/nodes/response_node.py` — Add LOG_PERSONAL_STATS context

- **IMPLEMENT**: In `_build_context()` function, add a case for when `last_action` is `"LOGGED"` and processing_results contain stat entries. The existing `LOGGED` case should already handle this since we use the same `processing_results` shape. Verify this is the case.
- **PATTERN**: Check the existing `_build_context` function — if it already includes `processing_results` for `LOGGED` action, no change is needed
- **GOTCHA**: Only modify if the existing `LOGGED` path doesn't cover our case
- **VALIDATE**: `uv run pytest tests/unit/test_response_node.py -v`

### Task 14: UPDATE `bot/gateway.py` — Add onboarding flow

- **IMPLEMENT**:
  1. Add onboarding state to `SessionData`:
     ```python
     class SessionData(TypedDict):
         user_id: str
         thread_id: str
         last_activity: datetime
         interrupted: bool
         onboarding_step: Optional[str]  # None, "name", "height", "age", "gender"
         onboarding_data: dict           # accumulates answers
     ```

  2. Add onboarding constants:
     ```python
     ONBOARDING_QUESTIONS = {
         "name": "What's your name?",
         "height": "What's your height in cm?",
         "age": "How old are you?",
         "gender": "What's your gender? (male/female/other)",
     }
     ONBOARDING_ORDER = ["name", "height", "age", "gender"]
     ```

  3. After passphrase accepted (line 251-260), if `result["is_new"]` is True, start onboarding:
     ```python
     user_sessions[chat_id] = {
         ...existing fields...,
         "onboarding_step": "name",
         "onboarding_data": {},
     }
     await message.answer("Welcome to FitPal! Let's set up your profile.")
     await message.answer(ONBOARDING_QUESTIONS["name"])
     return
     ```

  4. Add onboarding handler before authenticated message relay. When `session.get("onboarding_step")` is not None, process the answer:
     ```python
     async def _handle_onboarding(message: Message, session: dict) -> bool:
         """Process onboarding step. Returns True if still onboarding."""
         step = session.get("onboarding_step")
         if step is None:
             return False

         text = message.text.strip()
         # Validate and store answer
         if step == "name":
             session["onboarding_data"]["name"] = text
         elif step == "height":
             try:
                 session["onboarding_data"]["height_cm"] = float(text)
             except ValueError:
                 await message.answer("Please enter a number for height (cm).")
                 return True
         elif step == "age":
             try:
                 session["onboarding_data"]["age"] = int(text)
             except ValueError:
                 await message.answer("Please enter a number for age.")
                 return True
         elif step == "gender":
             if text.lower() not in ("male", "female", "other"):
                 await message.answer("Please enter male, female, or other.")
                 return True
             session["onboarding_data"]["gender"] = text.lower()

         # Advance to next step
         current_idx = ONBOARDING_ORDER.index(step)
         if current_idx + 1 < len(ONBOARDING_ORDER):
             next_step = ONBOARDING_ORDER[current_idx + 1]
             session["onboarding_step"] = next_step
             await message.answer(ONBOARDING_QUESTIONS[next_step])
             return True

         # Onboarding complete — save profile to DB
         session["onboarding_step"] = None
         await _save_user_profile(session["user_id"], session["onboarding_data"])
         name = session["onboarding_data"]["name"]
         await message.answer(
             f"Great, {name}! Your profile is set up. You can start logging food now."
         )
         return True
     ```

  5. Add `_save_user_profile` helper:
     ```python
     async def _save_user_profile(user_id: str, data: dict) -> None:
         """Save onboarding data to user_profiles table."""
         from src.database import get_async_db_session
         from src.services.user_profile_service import create_user_profile

         async with get_async_db_session() as session:
             await create_user_profile(
                 session=session,
                 user_id=user_id,
                 name=data["name"],
                 height_cm=data["height_cm"],
                 age=data["age"],
                 gender=data["gender"],
             )
     ```

  6. In `_handle_authenticated_message`, add onboarding check at the top:
     ```python
     if await _handle_onboarding(message, session):
         return
     ```

- **PATTERN**: Simple state machine. Each step validates input, stores answer, advances to next step.
- **GOTCHA**: Import `get_async_db_session` and service inside the function (not at top-level) to avoid circular imports between bot and src modules
- **GOTCHA**: For existing users (`is_new: False`), `onboarding_step` should be `None` — they skip onboarding. Initialize it in the existing session creation on passphrase acceptance.
- **VALIDATE**: `uv run pytest tests/unit/test_gateway.py -v`

### Task 15: UPDATE `bot/gateway.py` — Inject profile into graph config

- **IMPLEMENT**:
  1. Add profile loading helper:
     ```python
     async def _load_user_profile(user_id: str) -> dict | None:
         """Load user profile from DB for config injection."""
         from src.database import get_async_db_session
         from src.services.user_profile_service import get_user_profile

         async with get_async_db_session() as session:
             return await get_user_profile(session, user_id)
     ```

  2. In `_handle_authenticated_message`, before calling `_call_langgraph`, load profile and cache it on the session:
     ```python
     # Load profile if not cached
     if "user_profile" not in session:
         session["user_profile"] = await _load_user_profile(user_id)
     ```

  3. Update `_call_langgraph` to accept and pass profile:
     ```python
     async def _call_langgraph(
         thread_id: str,
         user_id: str,
         *,
         input: dict | None = None,
         command: dict | None = None,
         user_profile: dict | None = None,
     ) -> dict:
         body: dict = {
             "assistant_id": ASSISTANT_ID,
             "config": {"configurable": {"user_id": user_id}},
         }
         if user_profile:
             body["config"]["configurable"]["user_profile"] = user_profile
         ...
     ```

- **PATTERN**: Mirror how `user_id` is already passed in config (line 78)
- **GOTCHA**: Cache profile on session dict to avoid DB query on every message. Profile changes only during onboarding.
- **GOTCHA**: `SessionData` TypedDict needs `user_profile: Optional[dict]` added
- **VALIDATE**: `uv run pytest tests/unit/test_gateway.py -v`

### Task 16: CREATE `tests/unit/test_personal_stats_node.py` — Unit tests

- **IMPLEMENT**: Unit tests for `personal_stats_node` following AAA docstring pattern. Test cases:

  1. **test_weight_logging** — Mock LLM returns weight extraction, mock tool logs it, verify state updates
  2. **test_body_fat_logging** — Same for body fat
  3. **test_processing_results_accumulated** — Verify results append to existing processing_results

- **PATTERN**: Mirror `tests/unit/test_stats_node.py` for async node testing and `tests/unit/test_commit_node.py` for tool mocking
- **IMPORTS**: `pytest`, `AsyncMock`, `patch`, `HumanMessage`, `TEST_CONFIG_A` from conftest
- **GOTCHA**: Mock at import location: `patch("src.agents.nodes.personal_stats_node.log_personal_stat")`
- **GOTCHA**: Also mock the LLM: `patch("src.agents.nodes.personal_stats_node.get_llm_for_node")`
- **VALIDATE**: `uv run pytest tests/unit/test_personal_stats_node.py -v`

### Task 17: CREATE `tests/unit/test_onboarding.py` — Onboarding unit tests

- **IMPLEMENT**: Unit tests for bot onboarding flow. Test cases:

  1. **test_new_user_starts_onboarding** — After passphrase, is_new=True triggers onboarding
  2. **test_onboarding_collects_name** — First answer stored as name, advances to height
  3. **test_onboarding_validates_height** — Non-numeric input rejected, re-prompted
  4. **test_onboarding_validates_age** — Non-integer input rejected
  5. **test_onboarding_validates_gender** — Invalid gender rejected
  6. **test_onboarding_completes_saves_profile** — After all 4 steps, profile saved to DB
  7. **test_existing_user_skips_onboarding** — is_new=False skips onboarding

- **PATTERN**: Mirror `tests/unit/test_gateway.py` for bot testing patterns (mock httpx, message objects)
- **GOTCHA**: Mock `_save_user_profile` to avoid real DB calls in unit tests
- **VALIDATE**: `uv run pytest tests/unit/test_onboarding.py -v`

### Task 18: CREATE `tests/integration/test_personal_stats_service.py` — Integration tests

- **IMPLEMENT**: Integration tests hitting real Supabase DB. Test cases:

  1. **test_create_weight_entry** — Create weight log, verify returned object
  2. **test_create_body_fat_entry** — Create body fat log, verify returned object
  3. **test_get_latest_stats** — Create multiple entries, verify latest returned
  4. **test_get_stat_history** — Create entries with different timestamps, verify ordered
  5. **test_user_isolation** — Stats for user A not visible to user B

- **PATTERN**: Mirror `tests/integration/test_daily_log_service.py` exactly — use `async_test_db_session` fixture with transaction rollback
- **GOTCHA**: Ensure `PersonalStatsLog` table exists in test DB. May need `Base.metadata.create_all()` update in conftest.
- **VALIDATE**: `uv run pytest tests/integration/test_personal_stats_service.py -v`

### Task 19: UPDATE eval datasets — Add LOG_PERSONAL_STATS examples

- **IMPLEMENT**: Add 2-3 examples to both eval notebooks. Since datasets are already uploaded to LangSmith, the user will need to delete and recreate them. Add examples like:

  English (`eval_input_parser.ipynb`):
  ```python
  {"question": "I weigh 74kg", "action": "LOG_PERSONAL_STATS", "items": [], "item_count": 0, ...},
  {"question": "My body fat is 15%", "action": "LOG_PERSONAL_STATS", "items": [], "item_count": 0, ...},
  ```

  Hebrew (`eval_input_parser_hebrew.ipynb`):
  ```python
  {"question": "אני שוקל 74 קילו", "action": "LOG_PERSONAL_STATS", "items": [], "item_count": 0, ...},
  {"question": "אחוז שומן 15", "action": "LOG_PERSONAL_STATS", "items": [], "item_count": 0, ...},
  ```

- **GOTCHA**: Hebrew notebook must be edited via Python script (not Write tool) to preserve UTF-8 Hebrew characters. See the `_build_hebrew_nb.py` pattern used previously.
- **GOTCHA**: Delete existing LangSmith datasets and re-run notebooks to upload updated examples
- **VALIDATE**: Run both eval notebooks, verify LOG_PERSONAL_STATS examples pass action classification

---

## TESTING STRATEGY

### Unit Tests

| Test File | Tests | Mocks |
|-----------|-------|-------|
| `test_personal_stats_node.py` | Weight logging, body fat logging, result accumulation | LLM (get_llm_for_node), tool (log_personal_stat) |
| `test_onboarding.py` | Full onboarding flow, validation, skip for existing users | httpx, _save_user_profile |
| `test_input_parser.py` | Add LOG_PERSONAL_STATS cases to existing test | LLM (existing mock) |

### Integration Tests

| Test File | Tests | DB Required |
|-----------|-------|-------------|
| `test_personal_stats_service.py` | CRUD operations, user isolation, ordering | Yes (Supabase) |

### Edge Cases

- User says "I weigh 74" without unit — LLM should assume kg
- User says "163 lbs" — prompt instructs conversion to kg
- User says "I had 200g of protein" — input parser must route to LOG_FOOD, not LOG_PERSONAL_STATS
- User says "body fat is down to 14.5" — decimal values
- Onboarding: user sends non-numeric height, gets re-prompted
- Onboarding: user sends invalid gender, gets re-prompted
- Bot restart during onboarding — session lost, user can re-trigger via passphrase

---

## VALIDATION COMMANDS

### Level 1: Syntax & Style

```bash
uv run ruff check .
```

### Level 2: Unit Tests

```bash
uv run pytest tests/unit/ -v
```

### Level 3: Integration Tests

```bash
uv run pytest tests/integration/ -v
```

### Level 4: Manual Validation

1. Start `langgraph dev` and test in Studio:
   - Send "I weigh 74kg" → should route to personal_stats_node → log stat → response
   - Send "Body fat is 15%" → same flow for body fat
   - Send "I had 200g chicken" → should still route to LOG_FOOD (no regression)

2. Test bot onboarding (if Telegram bot is running):
   - New user sends passphrase → bot asks name → height → age → gender → profile saved
   - Existing user reconnects → no onboarding prompt

---

## ACCEPTANCE CRITERIA

- [ ] `UserProfile` and `PersonalStatsLog` models exist and migrations applied
- [ ] User profiles created during bot onboarding (deterministic, no LLM)
- [ ] Onboarding asks each field in a separate message with validation
- [ ] Profile injected into graph config on every message
- [ ] "I weigh 74kg" routes to LOG_PERSONAL_STATS and logs to personal_stats_log
- [ ] "Body fat is 15%" routes to LOG_PERSONAL_STATS and logs to personal_stats_log
- [ ] "I had 200g chicken" still routes to LOG_FOOD (no regression)
- [ ] All existing unit tests pass (85 tests)
- [ ] New unit tests pass for personal_stats_node and onboarding
- [ ] Integration tests pass for personal stats service
- [ ] Ruff lint passes
- [ ] Response node personalizes with user name when available

---

## COMPLETION CHECKLIST

- [ ] All tasks completed in order (1-19)
- [ ] Each task validation passed immediately
- [ ] All validation commands executed successfully
- [ ] Full test suite passes (unit + integration)
- [ ] No linting errors
- [ ] Manual testing confirms feature works in Studio
- [ ] Acceptance criteria all met
- [ ] No regressions in existing 85 unit tests

---

## NOTES

### Design Decisions

1. **Option B for stat extraction** — Separate LLM call in personal_stats_node rather than extending input parser schema. Cleaner separation, independently evaluable. Adds ~200ms latency (acceptable for gpt-4.1-nano).

2. **Option C (regex extraction) noted as future optimization** — Could replace the LLM call for simple cases like "74kg" or "15%". Would eliminate the extra LLM call entirely. Track in PRD as a performance improvement.

3. **No tools for user_profiles** — Bot handles profile CRUD directly. The graph only needs read access via config injection. Keeps the tool surface small.

4. **Wide table for personal_stats_log** — Explicit `weight_kg` and `body_fat_pct` columns instead of EAV (stat_type + value). More queryable, better for future charts/dashboards, type-safe. New stat types require migration but this is infrequent.

5. **Profile cached on session** — Loaded once after authentication, cached on session dict. Avoids DB query on every message. Invalidated on bot restart (acceptable since profile rarely changes).

### Risks

- **Input parser confusion**: "I weigh 74kg" vs "I had 74g of protein" — the prompt must clearly distinguish body stats from food. Eval datasets will catch regressions.
- **Bot restart loses onboarding state** — If bot restarts mid-onboarding, user must send passphrase again and restart onboarding. Acceptable for MVP. Fix in future with persistent sessions.
- **Hebrew stat extraction** — The personal_stats_extractor prompt includes Hebrew examples but gpt-4.1-nano may struggle with Hebrew number parsing. Monitor via evals.
