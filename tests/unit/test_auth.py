"""Unit tests for AuthManager – login flow, session validation, logout.

Covers testing standards Section 5 (mock return values for tuple unpacking)
and Section 7 (async patterns).
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.auth import AuthManager, AuthenticationError
from app.nlm_client import SessionCredentials


# ---------------------------------------------------------------------------
# Section 5.8: Mock return values for tuple unpacking use real tuples
# ---------------------------------------------------------------------------


class TestLoginTupleUnpacking:
    """Verify that fetch_tokens mock returns a real tuple for unpacking."""

    @pytest.mark.asyncio
    async def test_login_unpacks_fetch_tokens_tuple(self):
        """login() does `csrf_token, session_id = await fetch_tokens(cookies)`.
        The mock must return a real tuple so missing await raises TypeError."""
        mgr = AuthManager()

        mock_nlm = MagicMock()
        mock_nlm.auth.load_auth_from_storage = MagicMock(
            return_value={"cookie_key": "cookie_val"}
        )
        # Return a real tuple — not a MagicMock — so tuple unpacking works correctly
        mock_nlm.auth.fetch_tokens = AsyncMock(return_value=("csrf-tok-123", "sess-id-456"))
        mock_nlm.NotebookLMClient = MagicMock()
        mock_nlm.AuthTokens = MagicMock()

        mgr._sdk_available = True
        mgr._nlm_module = mock_nlm

        credentials = await mgr.login()

        assert credentials.csrf_token == "csrf-tok-123"
        assert credentials.session_id == "sess-id-456"
        assert credentials.cookies == {"cookie_key": "cookie_val"}

    @pytest.mark.asyncio
    async def test_login_raises_when_no_cookies(self):
        """login() should raise AuthenticationError when no cookies found."""
        mgr = AuthManager()

        mock_nlm = MagicMock()
        mock_nlm.auth.load_auth_from_storage = MagicMock(return_value={})

        mgr._sdk_available = True
        mgr._nlm_module = mock_nlm

        with pytest.raises(AuthenticationError, match="No auth cookies found"):
            await mgr.login()

    @pytest.mark.asyncio
    async def test_login_raises_when_sdk_unavailable(self):
        """login() should raise AuthenticationError when SDK is not available."""
        mgr = AuthManager()
        mgr._sdk_available = False

        with pytest.raises(AuthenticationError, match="SDK is not installed"):
            await mgr.login()


# ---------------------------------------------------------------------------
# Session validation
# ---------------------------------------------------------------------------


class TestValidateSession:
    @pytest.mark.asyncio
    async def test_validate_returns_false_for_empty_cookies(self):
        mgr = AuthManager()
        creds = SessionCredentials(cookies={})
        result = await mgr.validate_session(creds)
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_returns_false_when_sdk_unavailable(self):
        mgr = AuthManager()
        mgr._sdk_available = False
        creds = SessionCredentials(
            cookies={"sid": "val"}, csrf_token="tok", session_id="sess"
        )
        result = await mgr.validate_session(creds)
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_returns_false_for_missing_tokens(self):
        mgr = AuthManager()
        mgr._sdk_available = True
        mgr._nlm_module = MagicMock()
        creds = SessionCredentials(cookies={"sid": "val"}, csrf_token="", session_id="")
        result = await mgr.validate_session(creds)
        assert result is False


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


class TestLogout:
    @pytest.mark.asyncio
    async def test_logout_clears_credentials(self):
        mgr = AuthManager()
        creds = SessionCredentials(
            cookies={"sid": "val"},
            csrf_token="tok",
            session_id="sess",
            token="bearer-token",
            user_email="user@example.com",
        )

        await mgr.logout(creds)

        assert creds.cookies == {}
        assert creds.csrf_token == ""
        assert creds.session_id == ""
        assert creds.token is None
        assert creds.user_email is None
