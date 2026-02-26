import os
import sys

# Ensure project root is in python path - MUST be before src imports
sys.path.append(os.getcwd())

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

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
