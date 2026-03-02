import os
import sys

# Ensure project root is in python path - MUST be before src imports
sys.path.append(os.getcwd())

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from unittest.mock import AsyncMock, patch

from src.models import Base, FoodItem

load_dotenv()


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
    }


@pytest_asyncio.fixture
async def async_test_db_session():
    """Provides an async in-memory SQLite session for testing.

    Creates all tables and seeds with a sample FoodItem (id=1).
    Session is automatically closed after each test.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    AsyncTestSession = async_sessionmaker(engine, expire_on_commit=False)
    async with AsyncTestSession() as session:
        # Seed with sample food item for testing
        sample_food = FoodItem(
            id=1,
            name="Test Chicken",
            calories=165.0,
            protein=31.0,
            fat=3.6,
            carbs=0.0,
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
    """Mock calculate_food_macros tool on calculate_log_node."""
    with patch("src.agents.nodes.calculate_log_node.calculate_food_macros") as mock:
        mock.ainvoke = AsyncMock()
        yield mock


@pytest.fixture
def mock_log_food_entry():
    """Mock log_food_entry tool on calculate_log_node."""
    with patch("src.agents.nodes.calculate_log_node.log_food_entry") as mock:
        mock.ainvoke = AsyncMock()
        yield mock


@pytest.fixture
def mock_query_food_logs_for_calc():
    """Mock query_food_logs tool on calculate_log_node."""
    with patch("src.agents.nodes.calculate_log_node.query_food_logs") as mock:
        mock.ainvoke = AsyncMock()
        yield mock


@pytest.fixture
def mock_query_food_logs_for_stats():
    """Mock query_food_logs tool on stats_node."""
    with patch("src.agents.nodes.stats_node.query_food_logs") as mock:
        mock.ainvoke = AsyncMock()
        yield mock
