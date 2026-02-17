import os
import sys
from datetime import date

# Ensure project root is in python path - MUST be before src imports
sys.path.append(os.getcwd())

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models import Base, FoodItem

load_dotenv()


@pytest.fixture
def basic_state():
    """Returns a basic AgentState structure for testing."""
    return {
        "messages": [],
        "pending_food_items": [],
        "daily_totals": {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0},
        "current_date": date.today(),
        "last_action": "",
        "search_results": [],
        "selected_food_id": None,
    }


@pytest.fixture
def test_db_session():
    """Provides an in-memory SQLite session for testing.

    Creates all tables and seeds with a sample FoodItem (id=1).
    Session is automatically closed after each test.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()

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
    session.commit()

    yield session
    session.close()
