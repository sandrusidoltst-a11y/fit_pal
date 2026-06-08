"""Unit tests for the coach dashboard FastAPI skeleton (Phase 1).

Mock boundary: the coach_service is mocked and the DB-session dependency is
overridden — the unit tier never touches a real database.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.config import DEFAULT_COACH_ID
from src.dashboard.app import app
from src.dashboard.dependencies import get_current_coach_id, get_db_session


@pytest.fixture
def client():
    """TestClient with the DB-session dependency stubbed out (service is mocked)."""
    app.dependency_overrides[get_db_session] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_get_current_coach_id_returns_default_coach():
    """
    Arrange: Phase 1 single-coach stub.
    Act: call get_current_coach_id.
    Assert: it returns the DEFAULT_COACH_ID as a string.
    """
    assert get_current_coach_id() == str(DEFAULT_COACH_ID)


def test_app_registers_health_and_trainees_routes():
    """
    Arrange: the dashboard app.
    Act: inspect registered route paths.
    Assert: /health and /api/dashboard/trainees are present.
    """
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/health" in paths
    assert "/api/dashboard/trainees" in paths


def test_health_endpoint_returns_ok(client):
    """
    Arrange: a test client.
    Act: GET /health.
    Assert: 200 with status ok.
    """
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_trainees_passes_coach_id_to_service(client):
    """
    Arrange: mock list_trainees_for_coach to return a single trainee.
    Act: GET /api/dashboard/trainees.
    Assert: response is the service result and the service was called with the
            default coach id.
    """
    fake_trainees = [{"user_id": "abc", "name": "Trainee One"}]
    with patch(
        "src.dashboard.routes.trainees.list_trainees_for_coach",
        new=AsyncMock(return_value=fake_trainees),
    ) as mock_list:
        response = client.get("/api/dashboard/trainees")

    assert response.status_code == 200
    assert response.json() == fake_trainees
    # coach_id (2nd positional / passed arg) is the single V1 coach
    called_coach_id = mock_list.await_args.args[1]
    assert called_coach_id == str(DEFAULT_COACH_ID)
