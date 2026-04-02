"""Unit tests for the LangGraph custom auth handler and ContextSchema defaults.

Scope:
    Tests the authentication handler (JWT validation via Supabase HTTP endpoint)
    and the ContextSchema default values used for LangGraph Studio fallback.

LLM Usage:
    NONE — all external calls are mocked.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langgraph_sdk import Auth

from src.context import ContextSchema, DEFAULT_DEV_USER_ID, DEFAULT_DEV_PROFILE
from src.security.auth import get_current_user


class TestAuthenticateHandler:
    """Tests for the @auth.authenticate handler (get_current_user)."""

    async def test_valid_token_returns_user_identity(self):
        """
        arrange: Mock httpx to return 200 with a valid user payload.
        act:     Call get_current_user with a valid Bearer token.
        assert:  Returns MinimalUserDict with correct identity.
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "user-uuid-123",
            "email": "test@example.com",
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.security.auth.httpx.AsyncClient", return_value=mock_client):
            result = await get_current_user(authorization="Bearer valid-token")

        assert result == {"identity": "user-uuid-123", "is_authenticated": True}

    async def test_missing_authorization_raises_401(self):
        """
        arrange: No authorization header.
        act:     Call get_current_user with None.
        assert:  Raises HTTPException with status 401.
        """
        with pytest.raises(Auth.exceptions.HTTPException) as exc_info:
            await get_current_user(authorization=None)
        assert exc_info.value.status_code == 401

    async def test_invalid_token_raises_401(self):
        """
        arrange: Mock httpx to return 401 (invalid/expired token).
        act:     Call get_current_user with an invalid token.
        assert:  Raises HTTPException with status 401.
        """
        mock_response = MagicMock()
        mock_response.status_code = 401

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.security.auth.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(Auth.exceptions.HTTPException) as exc_info:
                await get_current_user(authorization="Bearer invalid-token")
        assert exc_info.value.status_code == 401

    async def test_malformed_authorization_raises_401(self):
        """
        arrange: Authorization header with wrong scheme (not Bearer).
        act:     Call get_current_user with malformed header.
        assert:  Raises HTTPException with status 401.
        """
        with pytest.raises(Auth.exceptions.HTTPException) as exc_info:
            await get_current_user(authorization="NotBearer some-token")
        assert exc_info.value.status_code == 401

    async def test_no_scheme_raises_401(self):
        """
        arrange: Authorization header with no space (just a bare token).
        act:     Call get_current_user with bare token.
        assert:  Raises HTTPException with status 401.
        """
        with pytest.raises(Auth.exceptions.HTTPException) as exc_info:
            await get_current_user(authorization="justabaretoken")
        assert exc_info.value.status_code == 401

    async def test_network_error_raises_401(self):
        """
        arrange: Mock httpx to raise a connection error.
        act:     Call get_current_user with a valid-looking token.
        assert:  Raises HTTPException with status 401.
        """
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("network down"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.security.auth.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(Auth.exceptions.HTTPException) as exc_info:
                await get_current_user(authorization="Bearer some-token")
        assert exc_info.value.status_code == 401


class TestContextSchemaDefaults:
    """Tests for ContextSchema default values (Studio fallback behavior)."""

    def test_default_user_id(self):
        """
        arrange: Create ContextSchema with no arguments.
        act:     Access user_id.
        assert:  Returns DEFAULT_DEV_USER_ID.
        """
        ctx = ContextSchema()
        assert ctx.user_id == DEFAULT_DEV_USER_ID

    def test_default_user_profile(self):
        """
        arrange: Create ContextSchema with no arguments.
        act:     Access user_profile.
        assert:  Returns DEFAULT_DEV_PROFILE values.
        """
        ctx = ContextSchema()
        assert ctx.user_profile["name"] == DEFAULT_DEV_PROFILE["name"]
        assert ctx.user_profile["age"] == DEFAULT_DEV_PROFILE["age"]

    def test_custom_user_id(self):
        """
        arrange: Create ContextSchema with explicit user_id.
        act:     Access user_id.
        assert:  Returns the provided value.
        """
        ctx = ContextSchema(user_id="11111111-1111-1111-1111-111111111111")
        assert ctx.user_id == "11111111-1111-1111-1111-111111111111"

    def test_custom_user_profile(self):
        """
        arrange: Create ContextSchema with explicit user_profile.
        act:     Access user_profile.
        assert:  Returns the provided profile.
        """
        profile = {"name": "Dolev", "height_cm": 180, "age": 30, "gender": "male"}
        ctx = ContextSchema(user_id="test-uuid", user_profile=profile)
        assert ctx.user_profile["name"] == "Dolev"
        assert ctx.user_profile["height_cm"] == 180

    def test_invalid_uuid_falls_back_to_default(self):
        """
        arrange: Create ContextSchema with invalid UUID string.
        act:     Access user_id.
        assert:  Falls back to DEFAULT_DEV_USER_ID.
        """
        ctx = ContextSchema(user_id="not-a-valid-uuid")
        assert ctx.user_id == DEFAULT_DEV_USER_ID

    def test_default_profile_is_independent_copy(self):
        """
        arrange: Create two ContextSchema instances with defaults.
        act:     Modify one's profile.
        assert:  The other is unaffected (no shared mutable default).
        """
        ctx1 = ContextSchema()
        ctx2 = ContextSchema()
        ctx1.user_profile["name"] = "Modified"
        assert ctx2.user_profile["name"] == DEFAULT_DEV_PROFILE["name"]
