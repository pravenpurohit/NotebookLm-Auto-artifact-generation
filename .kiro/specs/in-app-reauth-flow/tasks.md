# Implementation Plan: In-App Re-Authentication Flow

## Overview

Add an in-app re-authentication flow so users can complete Google login from the browser when session cookies expire. Implementation adds data models and URL detection to `app/auth.py`, a new `app/routes/reauth.py` router with SSE streaming, frontend JS on `login.html`, lifespan cleanup in `app/main.py`, and the `sse-starlette` dependency.

## Tasks

- [x] 1. Add `sse-starlette` dependency and reauth data models
  - [x] 1.1 Add `sse-starlette` to `requirements.txt`
    - Pin to exact version (e.g. `sse-starlette==2.1.3`) consistent with existing pinning strategy
    - _Requirements: 3.1_

  - [x] 1.2 Add `ReauthPhase`, `ReauthStatus`, and `ReauthSession` to `app/auth.py`
    - Add `ReauthPhase(str, Enum)` with values: `browser_launched`, `waiting_for_login`, `login_detected`, `authenticated`, `error`, `timeout`, `cancelled`
    - Add `ReauthStatus` dataclass with fields: `phase: ReauthPhase`, `message: str`, `error: str | None`
    - Add `ReauthSession` dataclass with fields: `session_id: str`, `active: bool = True`, `_cancel: bool = False`
    - _Requirements: 3.1, 5.3_

  - [x] 1.3 Add URL detection helper function to `app/auth.py`
    - Implement `is_login_complete(url: str) -> bool` as a module-level pure function
    - URLs containing `accounts.google.com` or Google sign-in paths → return `False`
    - URLs matching `notebooklm.google.com` without `/login` or `/signin` segments → return `True`
    - _Requirements: 2.1, 2.2_

  - [x] 1.4 Add error message sanitization utility to `app/auth.py`
    - Implement `sanitize_error_message(exc: Exception) -> str` as a module-level pure function
    - Strip Python traceback patterns (`Traceback (most recent call last):`, `File "..."`)
    - Remove internal module paths and raw exception class names
    - Preserve actionable information (e.g., "run `playwright install chromium`")
    - _Requirements: 6.5_

  - [x] 1.5 Add Playwright availability check to `AuthManager`
    - Add `playwright_available` property to `AuthManager`
    - Try `from playwright.sync_api import sync_playwright` and catch `ImportError`
    - Optionally verify Chromium is installed by attempting a quick headless launch or checking browser paths
    - Used by the reauth endpoint to return 503 before starting the flow
    - _Requirements: 5.1_

  - [ ]* 1.6 Write property test for URL detection (Property 6)
    - **Property 6: URL detection determinism**
    - **Validates: Requirements 2.1, 2.2**
    - Create `tests/property/test_prop_reauth.py`
    - Use Hypothesis `st.sampled_from` for known Google login paths and NotebookLM paths, combined with `st.text()` for path segments
    - Minimum 100 examples


- [x] 2. Implement `AuthManager` reauth methods
  - [x] 2.1 Add reauth state fields to `AuthManager.__init__`
    - Add `_reauth_session: ReauthSession | None = None`
    - Add `_reauth_lock: threading.Lock = threading.Lock()`
    - Add `_reauth_thread: threading.Thread | None = None`
    - Add `reauth_active` property that reads `_reauth_session` under `_reauth_lock`
    - _Requirements: 1.2, 7.2_

  - [x] 2.2 Implement `_run_playwright_login` synchronous thread method
    - Runs in a background thread; receives a `queue.Queue[ReauthStatus]` for cross-thread communication
    - Launch non-headless Chromium via Playwright, navigate to `https://notebooklm.google.com/`
    - Push `browser_launched` and `waiting_for_login` statuses to the queue
    - Poll page URL at 1-second intervals using `is_login_complete()`; use a bounded loop (`for _ in range(timeout)`) rather than `while True` with time check; respect `_cancel` flag
    - On login detected: save storage state, push `login_detected`, close browser
    - On error/timeout/cancel: push appropriate status, close browser, clean up
    - Use `sanitize_error_message()` (from task 1.4) for all error messages passed to the queue
    - _Requirements: 1.1, 2.1, 2.2, 2.3, 5.2, 5.3, 5.4, 5.5, 6.5, 7.2_

  - [x] 2.3 Implement `browser_login` async method
    - Acquire `_reauth_lock`, reject if `reauth_active` (raise `AuthenticationError`)
    - Create `ReauthSession` with `session_id=uuid.uuid4().hex`, set `_reauth_session`
    - Start `_run_playwright_login` in a `threading.Thread`
    - Async poll loop: read from `queue.Queue` using `await asyncio.to_thread(status_queue.get, timeout=0.1)` in a polling loop; invoke `status_callback` for each status
    - Use `asyncio.get_running_loop()` (NOT deprecated `get_event_loop()`) for any loop references
    - On `login_detected`: load cookies from storage state, call `fetch_tokens`, build and return `SessionCredentials`
    - On terminal status (error/timeout/cancelled): raise `AuthenticationError`
    - Always clean up: mark session inactive, clear `_reauth_session` under lock
    - _Requirements: 1.1, 1.2, 1.3, 2.3, 4.1, 5.3, 7.2, 7.3_

  - [x] 2.4 Implement `cancel_reauth` and `cleanup_reauth` methods
    - `cancel_reauth()`: acquire lock, set `_cancel = True` on active session
    - `cleanup_reauth()`: call `cancel_reauth()`, then `await asyncio.to_thread(self._reauth_thread.join, timeout=10)` if thread exists
    - _Requirements: 5.3, 5.4, 7.3_

  - [ ]* 2.5 Write property test for concurrent reauth rejection (Property 1)
    - **Property 1: Concurrent reauth rejection**
    - **Validates: Requirements 1.2**
    - Add to `tests/property/test_prop_reauth.py`
    - Generate random `ReauthSession` states (active/inactive) with `st.booleans()` and `st.uuids()` for session IDs
    - Verify that when a session is active, starting a new one raises or returns 409
    - Minimum 100 examples

  - [ ]* 2.6 Write property test for session cleanup on termination (Property 4)
    - **Property 4: Session cleanup on termination**
    - **Validates: Requirements 5.3, 7.3**
    - Add to `tests/property/test_prop_reauth.py`
    - Generate random termination reasons (success, error, timeout, cancel) via `st.sampled_from`
    - Mock `_run_playwright_login` to push the chosen terminal status
    - Verify `reauth_active` returns `False` and `_reauth_session` is cleared after each termination
    - Minimum 100 examples

  - [ ]* 2.7 Write property test for user-friendly error messages (Property 5)
    - **Property 5: User-friendly error messages**
    - **Validates: Requirements 6.5**
    - Add to `tests/property/test_prop_reauth.py`
    - Generate various error conditions with `st.sampled_from(error_conditions)` and `st.text()` for exception messages
    - Verify emitted error messages contain no Python traceback text, raw exception class names, or internal module paths
    - Minimum 100 examples

- [x] 3. Checkpoint
  - Ensure all tests pass (`pytest tests/property/test_prop_reauth.py`), ask the user if questions arise.
  - Note: unit tests for AuthManager (`test_auth_reauth.py`) are created in task 7.2 and will be validated at the final checkpoint.


- [-] 4. Implement reauth routes and SSE streaming
  - [x] 4.1 Create `app/routes/reauth.py` with `POST /api/auth/reauth` endpoint
    - Return `{"session_id": ...}` on success
    - Return 409 if `auth_manager.reauth_active` is `True`
    - Return 503 if `auth_manager.playwright_available` is `False` (from task 1.5)
    - Use `Depends(get_auth_manager)` and `Depends(get_nlm_client)` for dependency injection
    - _Requirements: 1.1, 1.2, 1.3, 5.1_

  - [~] 4.2 Implement `GET /api/auth/reauth/status/{session_id}` SSE endpoint
    - Use `sse_starlette.sse.EventSourceResponse` to stream `ReauthStatus` events
    - Call `auth_manager.browser_login()` with a callback that yields SSE events
    - On `authenticated`: update `nlm_client.credentials`, call `nlm_client.reinit_client()`, emit final event
    - On terminal events (error/timeout/cancelled): emit event and close stream
    - _Requirements: 3.1, 3.2, 3.3, 4.1, 4.2_

  - [~] 4.3 Register reauth router in `app/routes/__init__.py`
    - Import `from app.routes.reauth import router as reauth_router`
    - Add `router.include_router(reauth_router)`
    - _Requirements: 1.1_

  - [ ]* 4.4 Write property test for SSE event ordering (Property 2)
    - **Property 2: SSE event ordering**
    - **Validates: Requirements 3.1**
    - Add to `tests/property/test_prop_reauth.py`
    - Generate random sequences of `ReauthStatus` objects using `st.lists(st.sampled_from(ReauthPhase))`
    - Test the queue-to-SSE conversion as a pure function (extract the generator that reads from queue and yields SSE events)
    - Verify events arrive in the same order they were enqueued, with no drops or reordering
    - Supplement with a single integration test using `TestClient` to verify the actual endpoint streams correctly
    - Minimum 100 examples

  - [ ]* 4.5 Write property test for credential update after reauth (Property 3)
    - **Property 3: Credential update after reauth**
    - **Validates: Requirements 4.1**
    - Add to `tests/property/test_prop_reauth.py`
    - Generate random cookie dicts (`st.dictionaries(st.text(min_size=1), st.text(min_size=1))`) and token strings (`st.text(min_size=1)`)
    - Mock `_run_playwright_login` to simulate a successful flow with the generated credentials
    - Verify `SessionCredentials` contains the exact generated cookies, CSRF token, and session ID
    - Minimum 100 examples

  - [ ]* 4.6 Write unit tests for reauth routes in `tests/unit/test_routes_reauth.py`
    - Test `POST /api/auth/reauth` returns 409 when reauth is active
    - Test `POST /api/auth/reauth` returns 503 when Playwright is not installed
    - Test SSE stream closes after `authenticated` event
    - Test SSE stream closes after `error` event
    - Test SSE stream emits connection-lost-safe events
    - Test that after `authenticated` event, `nlm_client.reinit_client()` is called (Req 4.2)
    - Test that after successful reauth, `GET /api/auth/status` returns `{"authenticated": true}` (Req 4.3)
    - Test backend cleanup when SSE client disconnects mid-stream (Req 3.4)
    - Mock Playwright at the `_run_playwright_login` boundary
    - _Requirements: 1.2, 3.2, 3.3, 3.4, 4.2, 4.3, 5.1_

- [ ] 5. Checkpoint
  - Ensure all tests pass (`pytest tests/unit/test_routes_reauth.py tests/property/test_prop_reauth.py`), ask the user if questions arise.


- [-] 6. Update login page frontend
  - [~] 6.1 Add "Re-authenticate with Google" button and status area to `app/templates/login.html`
    - Add a secondary button below the existing "Sign in with Google" button, styled as outline/link
    - Add explanatory text: "Session expired? Open a browser to log in again."
    - Add a status indicator area with `aria-live="polite"` and `role="status"`
    - Add `aria-describedby` on the reauth button pointing to the status area
    - Ensure disabled button state uses a proper muted color (not just `opacity: 0.6`) to meet WCAG AA contrast ratio
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [~] 6.2 Implement reauth JavaScript on `app/templates/login.html`
    - `startReauth()`: POST to `/api/auth/reauth`, open `EventSource` to `/api/auth/reauth/status/{session_id}`
    - Update status indicator text for each phase (`browser_launched` → "Opening browser...", `waiting_for_login` → "Waiting for login... (Xs remaining)", etc.)
    - During `waiting_for_login` phase, display a countdown timer showing remaining seconds (start from known timeout value, decrement locally via `setInterval`)
    - On `authenticated`: close EventSource, redirect to `/dashboard`
    - On `error`/`timeout`/`cancelled`: close EventSource, show user-friendly error, re-enable button, return focus to the reauth button
    - On EventSource `onerror` (connection drop): show connection-lost message, allow retry
    - Disable reauth button while session is in progress
    - Manage focus: after error/cancel, focus returns to reauth button; after redirect, browser handles focus naturally
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 6.2, 6.3, 6.4, 6.5_

- [-] 7. Add lifespan cleanup and wire everything together
  - [~] 7.1 Update `app/main.py` lifespan shutdown to call `cleanup_reauth`
    - Add `await auth_manager.cleanup_reauth()` in the shutdown section, before `task_queue.stop_all()`
    - This prevents orphaned Chromium processes on server shutdown
    - _Requirements: 7.3_

  - [~] 7.2 Add shared reauth test fixtures to `tests/conftest.py`
    - Add a `mock_auth_manager` fixture that creates an `AuthManager` with Playwright stubbed out (SDK import mocked)
    - Add a `reauth_session_factory` fixture for creating `ReauthSession` instances with configurable state
    - Add a `mock_playwright_login` fixture that replaces `_run_playwright_login` with a function that pushes predetermined statuses to the queue
    - These fixtures are shared across `test_auth_reauth.py`, `test_routes_reauth.py`, and `test_prop_reauth.py`

  - [ ]* 7.3 Write unit tests for `AuthManager` reauth methods in `tests/unit/test_auth_reauth.py`
    - Test `cancel_reauth()` sets the cancel flag
    - Test `browser_login()` raises `AuthenticationError` when SDK unavailable
    - Test `reauth_active` property is thread-safe (concurrent reads)
    - Test `cleanup_reauth()` joins the background thread
    - Test timeout value is respected (mock time)
    - Test credentials are cleared on failed reauth (no partial state)
    - Test `sanitize_error_message()` strips tracebacks and class names
    - Test `playwright_available` property returns `False` when Playwright not installed
    - Mock Playwright at the `_run_playwright_login` boundary
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 6.5, 7.2, 7.3_

  - [ ]* 7.4 Write unit tests for URL detection in `tests/unit/test_reauth_url_detection.py`
    - Test known Google login URLs (`accounts.google.com/signin`, `accounts.google.com/o/oauth2/...`) → `False`
    - Test NotebookLM app URLs (`notebooklm.google.com/`, `notebooklm.google.com/notebook/...`) → `True`
    - Test edge cases: `notebooklm.google.com/login` → `False`, empty string, malformed URLs
    - _Requirements: 2.1, 2.2_

- [ ] 8. Final checkpoint
  - Run full test suite (`pytest`), ensure all 316+ existing tests still pass plus new tests. Ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties (P1–P6)
- Unit tests validate specific examples and edge cases
- All Playwright interactions are mocked at the `_run_playwright_login` boundary — no real browser in tests
