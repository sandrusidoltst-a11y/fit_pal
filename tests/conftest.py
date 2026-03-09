import os
import sys
import uuid as uuid_mod

# Ensure project root is in python path - MUST be before src imports
sys.path.append(os.getcwd())

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from unittest.mock import AsyncMock, patch

from src.models import Base, FoodItem

load_dotenv()

TEST_USER_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TEST_USER_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
TEST_CONFIG_A: RunnableConfig = {"configurable": {"user_id": TEST_USER_A}}
TEST_CONFIG_B: RunnableConfig = {"configurable": {"user_id": TEST_USER_B}}

SEED_FOOD_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def basic_state():
    """Returns a basic AgentState structure for testing."""
    return {
        "messages": [],
        "pending_food_items": [],
        "daily_log_report": [],
        "consumed_at": None,
        "start_date": None,
        "end_date": None,
        "last_action": "",
        "search_results": [],
        "selected_food_id": None,
        "processing_results": [],
        "pending_confirmations": [],
    }


@pytest_asyncio.fixture
async def async_test_db_session():
    """Provides an async in-memory SQLite session for testing.

    Creates all tables and seeds with a sample FoodItem (UUID id).
    Session is automatically closed after each test.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    AsyncTestSession = async_sessionmaker(engine, expire_on_commit=False)
    async with AsyncTestSession() as session:
        # Seed with sample food item for testing
        sample_food = FoodItem(
            id=uuid_mod.UUID(SEED_FOOD_ID),
            name="Test Chicken",
            calories=165.0,
            protein=31.0,
            fat=3.6,
            carbs=0.0,
            source="database",
            user_id=None,  # shared database food
        )
        session.add(sample_food)
        await session.commit()

        yield session

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
def mock_query_food_logs_for_commit():
    """Mock query_food_logs tool on commit_node."""
    with patch("src.agents.nodes.commit_node.query_food_logs") as mock:
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
