"""Unit tests for the LangGraph custom auth handler and get_user_id priority logic.

Scope:
    Tests the authentication handler (JWT validation via Supabase HTTP endpoint)
    and the updated get_user_id() function that checks langgraph_auth_user first.

LLM Usage:
    NONE — all external calls are mocked.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langgraph_sdk import Auth

from src.config import DEFAULT_DEV_USER_ID, get_user_id
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


class TestGetUserIdPriority:
    """Tests for get_user_id() priority: auth_user > manual user_id > default."""

    def test_prefers_auth_user_over_manual(self):
        """
        arrange: Config with both langgraph_auth_user and user_id keys.
        act:     Call get_user_id.
        assert:  Returns the auth_user identity, not user_id.
        """
        config = {
            "configurable": {
                "langgraph_auth_user": {"identity": "auth-user-uuid"},
                "user_id": "manual-user-uuid",
            }
        }
        assert get_user_id(config) == "auth-user-uuid"

    def test_falls_back_to_manual_user_id(self):
        """
        arrange: Config with only user_id (no langgraph_auth_user).
        act:     Call get_user_id.
        assert:  Returns the user_id value.
        """
        config = {"configurable": {"user_id": "manual-user-uuid"}}
        assert get_user_id(config) == "manual-user-uuid"

    def test_falls_back_to_default(self):
        """
        arrange: Config with empty configurable dict.
        act:     Call get_user_id.
        assert:  Returns DEFAULT_DEV_USER_ID.
        """
        config = {"configurable": {}}
        assert get_user_id(config) == DEFAULT_DEV_USER_ID

    def test_none_config_returns_default(self):
        """
        arrange: No config at all (None).
        act:     Call get_user_id.
        assert:  Returns DEFAULT_DEV_USER_ID.
        """
        assert get_user_id(None) == DEFAULT_DEV_USER_ID
