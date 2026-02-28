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


@pytest.fixture
def mock_calculate_log_db_session():
    with patch("src.agents.nodes.calculate_log_node.get_async_db_session") as mock:
        session = AsyncMock()
        mock.return_value.__aenter__ = AsyncMock(return_value=session)
        mock.return_value.__aexit__ = AsyncMock(return_value=False)
        yield session


@pytest.fixture
def mock_daily_log_service_for_calc():
    with patch("src.agents.nodes.calculate_log_node.daily_log_service") as mock:
        mock.create_log_entry = AsyncMock()
        mock.get_logs_by_date = AsyncMock(return_value=[])
        mock.get_logs_by_date_range = AsyncMock(return_value=[])
        yield mock


@pytest.fixture
def mock_calculate_macros():
    with patch("src.agents.nodes.calculate_log_node.calculate_food_macros") as mock:
        yield mock


@pytest.fixture
def mock_stats_db_session():
    with patch("src.agents.nodes.stats_node.get_async_db_session") as mock:
        session = AsyncMock()
        mock.return_value.__aenter__ = AsyncMock(return_value=session)
        mock.return_value.__aexit__ = AsyncMock(return_value=False)
        yield session


@pytest.fixture
def mock_daily_log_service_for_stats():
    with patch("src.agents.nodes.stats_node.daily_log_service") as mock:
        mock.get_logs_by_date = AsyncMock(return_value=[])
        mock.get_logs_by_date_range = AsyncMock(return_value=[])
        yield mock
