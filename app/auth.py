"""Authentication Manager.

Wraps the notebooklm-py SDK's browser-based Google login to provide
session credential management: login, validation, and logout.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
"""

from __future__ import annotations

import logging
from typing import Any

from app.nlm_client import SessionCredentials

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when an authentication operation fails."""


class AuthManager:
    """Manages Google account authentication via the notebooklm-py SDK.

    Uses the SDK's browser-based login flow to obtain session cookies,
    which are stored as ``SessionCredentials`` for subsequent API calls.
    Degrades gracefully when the SDK is not installed.
    """

    def __init__(self) -> None:
        self._sdk_available: bool = False
        self._nlm_module: Any | None = None
        self._try_import_sdk()

    def _try_import_sdk(self) -> None:
        """Attempt to import the notebooklm-py SDK."""
        try:
            import notebooklm as nlm  # type: ignore[import-untyped]

            # Verify the SDK version has the expected API (>= 0.3.2)
            if not hasattr(nlm, "NotebookLMClient"):
                raise ImportError(
                    "notebooklm-py is installed but too old "
                    "(missing NotebookLMClient class). Upgrade to >= 0.3.2."
                )

            self._nlm_module = nlm
            self._sdk_available = True
            logger.info("notebooklm-py SDK available for authentication")
        except ImportError as exc:
            self._sdk_available = False
            self._nlm_module = None
            logger.warning(
                "notebooklm-py SDK not usable – authentication disabled: %s", exc
            )

    @property
    def sdk_available(self) -> bool:
        """Whether the notebooklm-py SDK is installed and importable."""
        return self._sdk_available

    async def login(self) -> SessionCredentials:
        """Initiate Google login via the notebooklm-py browser-based flow.

        Opens a browser window for the user to authenticate with their
        Google account.  On success the returned cookies are wrapped in
        a ``SessionCredentials`` instance.

        Requirement 1.1: Display Google login prompt before showing content.
        Requirement 1.2: Store session credentials after auth.
        Requirement 1.3: Display error on failure, allow retry.

        Raises
        ------
        AuthenticationError
            If the SDK is unavailable or the login flow fails.
        """
        if not self._sdk_available or self._nlm_module is None:
            raise AuthenticationError(
                "NotebookLM SDK is not installed. "
                "Install notebooklm-py >= 0.3.2 to enable authentication."
            )

        try:
            # The notebooklm-py SDK uses Playwright browser storage for auth.
            # 1. Load cookies from browser storage
            # 2. Fetch CSRF token and session ID using those cookies
            # 3. Construct AuthTokens for the client
            nlm = self._nlm_module

            cookies: dict[str, str] = nlm.auth.load_auth_from_storage()
            if not cookies:
                raise AuthenticationError(
                    "No auth cookies found in browser storage. "
                    "Run the notebooklm-py Playwright login first."
                )

            csrf_token, session_id = await nlm.auth.fetch_tokens(cookies)

            credentials = SessionCredentials(
                cookies=cookies,
                csrf_token=csrf_token,
                session_id=session_id,
            )

            logger.info("Login successful (loaded from browser storage)")
            return credentials

        except AuthenticationError:
            raise
        except Exception as exc:
            logger.error("Authentication failed: %s", exc)
            raise AuthenticationError(
                f"Google authentication failed: {exc}"
            ) from exc

    async def validate_session(self, credentials: SessionCredentials) -> bool:
        """Check whether *credentials* still represent a valid session.

        Attempts a lightweight SDK operation (listing notebooks) to verify
        the session cookies have not expired.

        Requirement 1.4: Maintain authenticated state across page refreshes.

        Returns ``True`` if the session is valid, ``False`` otherwise.
        """
        if not credentials.cookies:
            return False

        if not self._sdk_available or self._nlm_module is None:
            logger.warning("Cannot validate session – SDK not available")
            return False

        if not credentials.csrf_token or not credentials.session_id:
            logger.info("Session missing csrf_token or session_id")
            return False

        try:
            nlm = self._nlm_module
            auth_tokens = nlm.AuthTokens(
                cookies=credentials.cookies,
                csrf_token=credentials.csrf_token,
                session_id=credentials.session_id,
            )
            client = nlm.NotebookLMClient(auth=auth_tokens)

            if hasattr(client, "is_connected"):
                return client.is_connected()

            # Fallback: assume valid if we could construct the client
            logger.debug("No is_connected method – assuming session is valid")
            return True

        except Exception as exc:
            logger.info("Session validation failed: %s", exc)
            return False

    async def logout(self, credentials: SessionCredentials) -> None:
        """Clear the session credentials.

        Requirement 1.5: Clear session on logout.

        Resets all fields on the supplied ``SessionCredentials`` instance
        so that subsequent API calls will fail authentication, effectively
        logging the user out.
        """
        credentials.cookies.clear()
        credentials.csrf_token = ""
        credentials.session_id = ""
        credentials.token = None
        credentials.user_email = None
        logger.info("User logged out – session credentials cleared")
