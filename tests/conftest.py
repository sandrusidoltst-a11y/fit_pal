import os
import ssl as _ssl
import sys
import uuid as uuid_mod

# Ensure project root is in python path - MUST be before src imports
sys.path.append(os.getcwd())

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from unittest.mock import AsyncMock, MagicMock, patch

from src.config import DATABASE_URL, DEFAULT_COACH_ID
from src.context import ContextSchema, DEFAULT_DEV_PROFILE
from src.models import CoachFoodMapping, FoodItem

load_dotenv()

TEST_USER_A = "fbeeb45f-d728-4c7c-9e6d-7b9b41685da7"  # dev@dev.fitpal.bot (auth.users)
TEST_USER_B = "72c10336-9d61-4357-9851-20cbb4d32b1a"  # e2e@test.fitpal.bot (auth.users)


def _make_mock_runtime(user_id: str, user_profile: dict | None = None) -> MagicMock:
    """Create a mock Runtime[ContextSchema] for unit tests."""
    runtime = MagicMock()
    runtime.context = ContextSchema(
        user_id=user_id,
        user_profile=user_profile or DEFAULT_DEV_PROFILE.copy(),
    )
    return runtime


TEST_RUNTIME_A = _make_mock_runtime(TEST_USER_A)
TEST_RUNTIME_B = _make_mock_runtime(TEST_USER_B)

SEED_FOOD_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def basic_state():
    """Returns a basic AgentState structure for testing."""
    return {
        "messages": [],
        "pending_food_items": [],
        "query_logs": [],
        "log_food": {},
        "query_stats": {},
        "user_intent": "",
        "pipeline_stage": "",
        "search_results": [],
        "selected_food_id": None,
        "processing_results": [],
        "pending_confirmations": [],
        "daily_log_today": [],
    }


@pytest_asyncio.fixture
async def async_test_db_session():
    """Provides an async Supabase Postgres session for testing.

    Uses transaction rollback for isolation — all test data (including seed)
    is visible during the test but rolled back at the end, leaving the real
    DB untouched.
    """
    # Build engine with SSL context for asyncpg (mirrors src/database.py)
    engine_kwargs: dict = {}
    if "asyncpg" in DATABASE_URL:
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        engine_kwargs["connect_args"] = {"ssl": ctx}

    engine = create_async_engine(DATABASE_URL, **engine_kwargs)
    async with engine.connect() as connection:
        # Outer transaction — will be rolled back at the end
        transaction = await connection.begin()
        # Nested savepoint so session.commit() releases savepoint, not outer TX
        await connection.begin_nested()

        session = AsyncSession(bind=connection, expire_on_commit=False)

        # Re-create savepoint after each commit so multiple commits work
        @event.listens_for(session.sync_session, "after_transaction_end")
        def restart_savepoint(sync_session, trans):
            if trans.nested and not trans._parent.nested:
                sync_session.begin_nested()

        # Seed with sample food item + coach mapping for testing
        sample_food = FoodItem(
            id=uuid_mod.UUID(SEED_FOOD_ID),
            name_en="Test Chicken",
            name_he="עוף לבדיקה",
            calories=165.0,
            protein=31.0,
            fat=3.6,
            carbs=0.0,
            unit_weights={},
            unit_synonyms={},
            source="database",
            user_id=None,  # shared database food
        )
        session.add(sample_food)
        await session.flush()  # make visible within TX, don't commit outer

        sample_mapping = CoachFoodMapping(
            food_id=sample_food.id,
            coach_id=DEFAULT_COACH_ID,
            category="protein",
            tag="lean",
            serving_amount_g=100.0,
            active=True,
        )
        session.add(sample_mapping)
        await session.flush()

        yield session

        # Cleanup
        await session.close()
        await transaction.rollback()

    await engine.dispose()


# ---------------------------------------------------------------------------
# Tool mock fixtures — mock .ainvoke() on tool objects used by nodes
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_search_food():
    """Mock search_food tool on food_search_node."""
    with patch("src.agents.nodes.food_search_node.search_food") as mock:
        mock.ainvoke = AsyncMock()
        yield mock


@pytest.fixture
def mock_calculate_macros():
    """Mock calculate_food_macros tool on calculate_macros_node."""
    with patch("src.agents.nodes.calculate_macros_node.calculate_food_macros") as mock:
        mock.ainvoke = AsyncMock()
        yield mock


@pytest.fixture
def mock_log_food_entry():
    """Mock log_food_entry tool on commit_node."""
    with patch("src.agents.nodes.commit_node.log_food_entry") as mock:
        mock.ainvoke = AsyncMock()
        yield mock


@pytest.fixture
def mock_create_food_item():
    """Mock create_food_item tool on commit_node."""
    with patch("src.agents.nodes.commit_node.create_food_item") as mock:
        mock.ainvoke = AsyncMock()
        yield mock


@pytest.fixture
def mock_query_food_logs_for_stats():
    """Mock query_food_logs tool on stats_node."""
    with patch("src.agents.nodes.stats_node.query_food_logs") as mock:
        mock.ainvoke = AsyncMock()
        yield mock


@pytest.fixture
def mock_log_personal_stat():
    """Mock log_personal_stat tool on personal_stats_node."""
    with patch("src.agents.nodes.personal_stats_node.log_personal_stat") as mock:
        mock.ainvoke = AsyncMock()
        yield mock
