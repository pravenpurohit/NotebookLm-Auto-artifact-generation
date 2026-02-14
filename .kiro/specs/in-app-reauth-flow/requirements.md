# Requirements Document

## Introduction

When Google session cookies expire, the NotebookLM Dashboard currently requires users to run `notebooklm login` in a terminal to re-authenticate. This feature adds an in-app re-authentication flow so users can complete the Playwright-based Google login directly from the browser, without leaving the dashboard.

## Glossary

- **Dashboard**: The FastAPI + Jinja2 web application served at `http://127.0.0.1:8000`
- **AuthManager**: The backend component (`app/auth.py`) responsible for session credential management
- **Reauth_Endpoint**: A new backend API endpoint that launches the Playwright browser login flow
- **Playwright_Browser**: A non-headless Chromium instance launched by Playwright for Google login
- **Storage_State**: The JSON file at `~/.notebooklm/storage_state.json` containing persisted browser cookies
- **SessionCredentials**: The dataclass (`app/nlm_client.py`) holding cookies, CSRF token, session ID, and user email
- **Login_Page**: The HTML page (`login.html`) where users initiate authentication
- **SSE_Stream**: A Server-Sent Events connection used to push reauth status updates from backend to frontend
- **Reauth_Session**: A backend-tracked state object representing an in-progress browser login attempt

## Requirements

### Requirement 1: Launch Browser Login from Dashboard

**User Story:** As a dashboard user, I want to click a button in the browser to launch the Google login flow, so that I can re-authenticate without switching to a terminal.

#### Acceptance Criteria

1. WHEN a user clicks the "Re-authenticate" button on the Login_Page, THE Reauth_Endpoint SHALL launch a non-headless Playwright_Browser navigated to `https://notebooklm.google.com/`
2. WHEN the Reauth_Endpoint receives a request while a Reauth_Session is already active, THE Reauth_Endpoint SHALL reject the request with a 409 Conflict status and a descriptive message
3. WHEN the Playwright_Browser is launched, THE Reauth_Endpoint SHALL return an immediate response containing a reauth session identifier so the frontend can begin polling for status

### Requirement 2: Detect Login Completion

**User Story:** As a dashboard user, I want the system to automatically detect when I have finished logging into Google, so that I do not need to manually signal completion.

#### Acceptance Criteria

1. WHILE the Playwright_Browser is open, THE AuthManager SHALL poll the browser page URL at a regular interval to detect navigation away from the Google login pages
2. WHEN the browser page URL matches a pattern indicating successful login (e.g. `notebooklm.google.com` without a sign-in path), THE AuthManager SHALL save the browser storage state to Storage_State and close the Playwright_Browser
3. WHEN login completion is detected, THE AuthManager SHALL read cookies from Storage_State and call `fetch_tokens` to obtain a new CSRF token and session ID

### Requirement 3: Stream Reauth Status to Frontend

**User Story:** As a dashboard user, I want to see real-time status updates during re-authentication, so that I know what is happening and when it completes.

#### Acceptance Criteria

1. WHEN a reauth session starts, THE Dashboard SHALL open an SSE_Stream from the frontend to a status endpoint that emits events for each phase: `browser_launched`, `waiting_for_login`, `login_detected`, `authenticated`, `error`
2. WHEN the SSE_Stream emits an `authenticated` event, THE Login_Page SHALL redirect the user to the dashboard page
3. WHEN the SSE_Stream emits an `error` event, THE Login_Page SHALL display the error message and re-enable the "Re-authenticate" button
4. IF the SSE_Stream connection drops before an `authenticated` or `error` event, THEN THE Login_Page SHALL display a connection-lost message and allow the user to retry

### Requirement 4: Update Session Credentials

**User Story:** As a dashboard user, I want my session to be fully restored after re-authentication, so that I can continue using the dashboard without restarting the server.

#### Acceptance Criteria

1. WHEN new credentials are obtained from the reauth flow, THE AuthManager SHALL update the in-memory SessionCredentials instance shared with the NotebookLMClientWrapper
2. WHEN SessionCredentials are updated, THE NotebookLMClientWrapper SHALL reinitialize its internal SDK client so subsequent API calls use the new credentials
3. WHEN the reauth flow completes successfully, THE Dashboard SHALL report the authentication status as valid on the `/api/auth/status` endpoint

### Requirement 5: Handle Reauth Errors Gracefully

**User Story:** As a dashboard user, I want clear error messages when re-authentication fails, so that I can understand the problem and take corrective action.

#### Acceptance Criteria

1. IF Playwright is not installed or Chromium is not available, THEN THE Reauth_Endpoint SHALL return a descriptive error indicating the missing dependency and suggest running `playwright install chromium`
2. IF the Playwright_Browser fails to launch, THEN THE AuthManager SHALL report the error through the SSE_Stream and clean up any partial state
3. IF the user does not complete login within a configurable timeout (default 120 seconds), THEN THE AuthManager SHALL close the Playwright_Browser, clean up the Reauth_Session, and emit a `timeout` error through the SSE_Stream
4. IF the browser is closed by the user before login completes, THEN THE AuthManager SHALL detect the closure, clean up the Reauth_Session, and emit a `cancelled` error through the SSE_Stream
5. IF cookie extraction or token fetching fails after login detection, THEN THE AuthManager SHALL emit an `error` event with a descriptive message through the SSE_Stream

### Requirement 6: Reauth UI on Login Page

**User Story:** As a dashboard user, I want a clear and accessible interface for re-authentication, so that I can easily initiate and monitor the process.

#### Acceptance Criteria

1. THE Login_Page SHALL display a "Re-authenticate with Google" button that is visually distinct from the existing "Sign in with Google" button
2. WHILE a reauth session is in progress, THE Login_Page SHALL display a status indicator showing the current phase (e.g. "Opening browser...", "Waiting for login...", "Completing authentication...")
3. WHILE a reauth session is in progress, THE Login_Page SHALL disable the "Re-authenticate" button to prevent duplicate sessions
4. WHEN the reauth flow completes or fails, THE Login_Page SHALL re-enable the "Re-authenticate" button
5. WHEN an error is displayed, THE Login_Page SHALL show a user-friendly message rather than raw technical exception text

### Requirement 7: Non-Blocking Backend Operation

**User Story:** As a dashboard user, I want the re-authentication flow to run without blocking other server operations, so that the dashboard remains responsive during the process.

#### Acceptance Criteria

1. WHILE the Playwright_Browser login flow is running, THE Dashboard SHALL continue to serve other HTTP requests and WebSocket connections without delay
2. WHEN the Playwright_Browser login flow is executed, THE AuthManager SHALL run the synchronous Playwright operations in a background thread to avoid blocking the async event loop
3. WHEN the reauth flow completes, THE AuthManager SHALL clean up the Playwright_Browser resources and the background thread
