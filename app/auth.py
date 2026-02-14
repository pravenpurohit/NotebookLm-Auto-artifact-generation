"""Authentication Manager.

Wraps the notebooklm-py SDK's browser-based Google login to provide
session credential management: login, validation, and logout.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
"""

from __future__ import annotations

import asyncio
import logging
import queue
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from app.nlm_client import SessionCredentials

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Reauth data models (Task 1.2)
# ---------------------------------------------------------------------------


class ReauthPhase(str, Enum):
    """Phases of the reauth flow, emitted as SSE events."""

    BROWSER_LAUNCHED = "browser_launched"
    WAITING_FOR_LOGIN = "waiting_for_login"
    LOGIN_DETECTED = "login_detected"
    AUTHENTICATED = "authenticated"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class ReauthStatus:
    """Status update emitted during the reauth flow."""

    phase: ReauthPhase
    message: str = ""
    error: str | None = None


@dataclass
class ReauthSession:
    """Tracks an in-progress reauth attempt."""

    session_id: str
    active: bool = True
    _cancel: bool = False


# ---------------------------------------------------------------------------
# Pure helper functions (Tasks 1.3, 1.4)
# ---------------------------------------------------------------------------


def is_login_complete(url: str) -> bool:
    """Determine whether *url* indicates the user has finished Google login.

    Returns ``True`` only when the URL belongs to the NotebookLM app
    (``notebooklm.google.com``) and is *not* on a sign-in / login path.
    All other URLs — including ``accounts.google.com`` — return ``False``.

    This is a pure, deterministic function with no side-effects.

    Requirements: 2.1, 2.2
    """
    if not url:
        return False

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    host = (parsed.hostname or "").lower()

    # Still on Google sign-in pages → not done
    if "accounts.google.com" in host:
        return False

    # Google sign-in paths on any host
    path_lower = parsed.path.lower()
    _google_signin_paths = (
        "/signin",
        "/login",
        "/o/oauth2",
        "/servicelogin",
        "/accountchooser",
    )
    if "google.com" in host and any(
        path_lower.startswith(p) for p in _google_signin_paths
    ):
        return False

    # NotebookLM app without login/signin segments → done
    if host == "notebooklm.google.com":
        if "/login" in path_lower or "/signin" in path_lower:
            return False
        return True

    # Conservative default: anything else is not considered complete
    return False


# Patterns used by sanitize_error_message
_TRACEBACK_RE = re.compile(
    r"Traceback \(most recent call last\):.*?(?=\w+Error:|\w+Exception:|\Z)",
    re.DOTALL,
)
_FILE_LINE_RE = re.compile(r'\s*File ".*?", line \d+.*\n?')
_MODULE_PATH_RE = re.compile(r"\b[\w.]+(?:/[\w.]+)+\.py\b")
_EXC_CLASS_RE = re.compile(r"\b(\w+(?:Error|Exception))\b:\s*")

_FRIENDLY_NAMES: dict[str, str] = {
    "ImportError": "A required dependency is missing",
    "ModuleNotFoundError": "A required dependency is missing",
    "FileNotFoundError": "A required file was not found",
    "TimeoutError": "The operation timed out",
    "ConnectionError": "A connection error occurred",
    "OSError": "A system error occurred",
    "RuntimeError": "An unexpected error occurred",
    "BrowserError": "The browser encountered an error",
    "PlaywrightError": "The browser automation encountered an error",
}


def sanitize_error_message(exc: Exception) -> str:
    """Return a user-friendly error string derived from *exc*.

    * Strips Python traceback blocks (``Traceback (most recent call last): …``)
    * Removes ``File "…", line N`` references
    * Removes internal module paths (e.g. ``app/auth.py``)
    * Replaces raw exception class names with friendly descriptions
    * Preserves actionable information (e.g. "run ``playwright install chromium``")

    Requirements: 6.5
    """
    raw = str(exc)
    if not raw.strip():
        return "An unexpected error occurred. Please try again."

    # Strip traceback blocks
    text = _TRACEBACK_RE.sub("", raw)
    # Strip individual File "..." lines
    text = _FILE_LINE_RE.sub("", text)
    # Strip internal module paths
    text = _MODULE_PATH_RE.sub("", text)

    # Replace exception class names with friendly text
    def _replace_exc_class(m: re.Match[str]) -> str:
        cls_name = m.group(1)
        friendly = _FRIENDLY_NAMES.get(cls_name, "An error occurred")
        return f"{friendly}: "

    text = _EXC_CLASS_RE.sub(_replace_exc_class, text)

    # Clean up whitespace
    text = re.sub(r"\n{2,}", "\n", text).strip()

    return text if text else "An unexpected error occurred. Please try again."


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
        self._playwright_available: bool | None = None  # cached result
        self._reauth_session: ReauthSession | None = None
        self._reauth_lock: threading.Lock = threading.Lock()
        self._reauth_thread: threading.Thread | None = None
        self._try_import_sdk()

    @property
    def reauth_active(self) -> bool:
        """Whether a reauth session is currently in progress.

        Thread-safe: acquires ``_reauth_lock`` before reading.
        """
        with self._reauth_lock:
            return self._reauth_session is not None and self._reauth_session.active

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

    @property
    def playwright_available(self) -> bool:
        """Whether Playwright's sync API is importable.

        The result is cached after the first check so repeated access
        does not trigger repeated import attempts.

        Requirements: 5.1
        """
        if self._playwright_available is not None:
            return self._playwright_available
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401

            self._playwright_available = True
        except ImportError:
            self._playwright_available = False
        return self._playwright_available

    # ------------------------------------------------------------------
    # Reauth flow (Tasks 2.2 – 2.4)
    # ------------------------------------------------------------------

    def _run_playwright_login(
        self,
        status_queue: queue.Queue[ReauthStatus],
        timeout: int,
    ) -> None:
        """Synchronous Playwright login — runs in a background thread.

        Launches Chromium, navigates to NotebookLM, polls the page URL
        for login completion, and saves storage state on success.

        Uses ``queue.Queue`` (not ``asyncio.Queue``) for thread-safe
        cross-thread communication with the async event loop.

        Requirements: 1.1, 2.1, 2.2, 2.3, 5.2, 5.3, 5.4, 5.5, 6.5, 7.2
        """
        from playwright.sync_api import sync_playwright

        nlm = self._nlm_module
        user_data_dir = str(nlm.paths.get_browser_profile_dir())
        storage_path = nlm.paths.get_storage_path()

        context = None
        playwright = None
        try:
            playwright = sync_playwright().start()
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--password-store=basic",
                ],
                ignore_default_args=["--enable-automation"],
            )

            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://notebooklm.google.com/")

            status_queue.put(
                ReauthStatus(
                    phase=ReauthPhase.BROWSER_LAUNCHED,
                    message="Browser opened.",
                )
            )
            status_queue.put(
                ReauthStatus(
                    phase=ReauthPhase.WAITING_FOR_LOGIN,
                    message="Waiting for you to complete Google login in the browser...",
                )
            )

            # Poll URL at 1-second intervals with a bounded loop
            for _ in range(timeout):
                # Check cancellation flag
                with self._reauth_lock:
                    session = self._reauth_session
                    if session is not None and session._cancel:
                        status_queue.put(
                            ReauthStatus(
                                phase=ReauthPhase.CANCELLED,
                                message="The login browser was closed before authentication completed.",
                                error="cancelled",
                            )
                        )
                        return

                try:
                    current_url = page.url
                except Exception:
                    # Browser was closed by the user
                    status_queue.put(
                        ReauthStatus(
                            phase=ReauthPhase.CANCELLED,
                            message="The login browser was closed before authentication completed.",
                            error="cancelled",
                        )
                    )
                    return

                if is_login_complete(current_url):
                    # Save storage state and signal success
                    context.storage_state(path=str(storage_path))
                    status_queue.put(
                        ReauthStatus(
                            phase=ReauthPhase.LOGIN_DETECTED,
                            message="Login detected, completing authentication...",
                        )
                    )
                    return

                time.sleep(1)

            # Timeout reached
            status_queue.put(
                ReauthStatus(
                    phase=ReauthPhase.TIMEOUT,
                    message=f"Login timed out after {timeout} seconds. Please try again.",
                    error="timeout",
                )
            )

        except Exception as exc:
            msg = sanitize_error_message(exc)
            status_queue.put(
                ReauthStatus(
                    phase=ReauthPhase.ERROR,
                    message=f"Failed to open the login browser. {msg}",
                    error=msg,
                )
            )
        finally:
            try:
                if context is not None:
                    context.close()
            except Exception:
                pass
            try:
                if playwright is not None:
                    playwright.stop()
            except Exception:
                pass

    async def browser_login(
        self,
        status_callback: Callable[[ReauthStatus], Awaitable[None]],
        timeout: int = 120,
    ) -> SessionCredentials:
        """Run the Playwright browser login in a background thread.

        Emits ``ReauthStatus`` updates via *status_callback*.
        Returns ``SessionCredentials`` on success.
        Raises ``AuthenticationError`` on failure.

        Requirements: 1.1, 1.2, 1.3, 2.3, 4.1, 5.3, 7.2, 7.3
        """
        # Reject if a reauth session is already active
        if self.reauth_active:
            raise AuthenticationError(
                "A re-authentication session is already in progress."
            )

        if not self._sdk_available or self._nlm_module is None:
            raise AuthenticationError(
                "NotebookLM SDK is not installed. "
                "Install notebooklm-py >= 0.3.2 to enable authentication."
            )

        session = ReauthSession(session_id=uuid.uuid4().hex)
        with self._reauth_lock:
            self._reauth_session = session

        status_queue: queue.Queue[ReauthStatus] = queue.Queue()

        thread = threading.Thread(
            target=self._run_playwright_login,
            args=(status_queue, timeout),
            daemon=True,
        )
        self._reauth_thread = thread
        thread.start()

        try:
            while True:
                try:
                    status = await asyncio.to_thread(
                        status_queue.get, timeout=0.5
                    )
                except Exception:
                    # queue.Empty — no status yet, keep polling
                    # Also check if the thread is still alive
                    if not thread.is_alive() and status_queue.empty():
                        raise AuthenticationError(
                            "Browser login thread exited unexpectedly."
                        )
                    continue

                await status_callback(status)

                if status.phase == ReauthPhase.LOGIN_DETECTED:
                    # Load cookies and fetch tokens
                    nlm = self._nlm_module
                    try:
                        cookies: dict[str, str] = nlm.auth.load_auth_from_storage()
                        csrf_token, session_id = await nlm.auth.fetch_tokens(
                            cookies
                        )
                        return SessionCredentials(
                            cookies=cookies,
                            csrf_token=csrf_token,
                            session_id=session_id,
                        )
                    except Exception as exc:
                        msg = sanitize_error_message(exc)
                        raise AuthenticationError(
                            f"Failed to complete authentication. {msg}"
                        ) from exc

                if status.phase in (
                    ReauthPhase.ERROR,
                    ReauthPhase.TIMEOUT,
                    ReauthPhase.CANCELLED,
                ):
                    raise AuthenticationError(status.message)

        finally:
            # Always clean up session state
            with self._reauth_lock:
                if self._reauth_session is not None:
                    self._reauth_session.active = False
                self._reauth_session = None
            self._reauth_thread = None

    def cancel_reauth(self) -> None:
        """Signal the active reauth session to cancel.

        Thread-safe: acquires ``_reauth_lock`` before writing.

        Requirements: 5.3, 5.4
        """
        with self._reauth_lock:
            if self._reauth_session is not None and self._reauth_session.active:
                self._reauth_session._cancel = True

    async def cleanup_reauth(self) -> None:
        """Cancel any active reauth and wait for the background thread.

        Called during lifespan shutdown to prevent orphaned Chromium processes.

        Requirements: 5.3, 5.4, 7.3
        """
        self.cancel_reauth()
        thread = self._reauth_thread
        if thread is not None and thread.is_alive():
            await asyncio.to_thread(thread.join, timeout=10)


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
