# Integration Testing (FastAPI)

## 1. Test Setup

```python
# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db

@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database for each test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)

@pytest.fixture(scope="function")
def client(db_session):
    """Create test client with overridden database."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
```

## 2. API Tests

```python
# tests/integration/test_api_habits.py

class TestHabitAPI:
    def test_create_habit_returns_201(self, client):
        response = client.post(
            "/api/habits",
            json={"name": "Exercise", "description": "Daily workout"}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Exercise"
        assert "id" in data

    def test_create_habit_without_name_returns_422(self, client):
        response = client.post("/api/habits", json={})

        assert response.status_code == 422

    def test_get_habit_returns_habit(self, client, db_session):
        # Setup: Create habit in database
        habit = Habit(name="Test", created_at=datetime.utcnow())
        db_session.add(habit)
        db_session.commit()

        # Test
        response = client.get(f"/api/habits/{habit.id}")

        assert response.status_code == 200
        assert response.json()["name"] == "Test"

    def test_get_nonexistent_habit_returns_404(self, client):
        response = client.get("/api/habits/99999")

        assert response.status_code == 404
```

## 3. Database Isolation with Transactions

Alternative approach using transaction rollbacks instead of fresh in-memory DBs for speed.

```python
@pytest.fixture
def db_session():
    """Rollback after each test for isolation."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()
```

## Running Integration Tests

```bash
pytest tests/integration
pytest -m integration
```
