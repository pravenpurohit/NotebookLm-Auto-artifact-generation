# Common Mistakes to Avoid

Critical pitfalls for this project. Every coding agent must follow these rules.

## Async + Synchronous Libraries

- Playwright is synchronous. Run it in a `threading.Thread`, never directly in an async handler.
- Use `queue.Queue` (stdlib) for cross-thread communication. `asyncio.Queue` is NOT thread-safe across threads.
- Use `asyncio.get_running_loop()`, never `asyncio.get_event_loop()` (deprecated in Python 3.12+).
- When spawning background threads, always join them on shutdown. Orphaned threads leak resources (especially Chromium processes).

## notebooklm-py SDK

- The SDK uses a sub-API pattern: `client.notebooks.list()`, `client.artifacts.generate_*()`, `client.sources.add_file()`. Direct methods like `client.list_notebooks()` do NOT exist.
- SDK return types are inconsistent — some methods return objects with attributes (`.id`, `.title`), others return dicts. Always check `isinstance(result, dict)` first, then fall back to `getattr(result, field, default)`.
- After constructing `NotebookLMClient`, verify that `notebooks`, `artifacts`, and `sources` attributes exist. If missing, the SDK version is incompatible.
- The SDK has its own `AudioFormat` enum. Map string constants (`"DEEP_DIVE"`, `"BRIEF"`, etc.) to SDK enum values. Import the enum inside the method to handle `ImportError` gracefully.
- After updating `SessionCredentials`, you MUST call `nlm_client.reinit_client()` to rebuild the SDK client. The old client object retains expired credentials.

## Browser-Based Authentication

- Google login detection works by polling the Playwright page URL. URLs containing `accounts.google.com` mean still logging in. URLs matching `notebooklm.google.com` without `/login` or `/signin` mean login is complete.
- The user can close the Playwright browser at any time. Reading `page.url` will raise an exception — catch it and emit a `cancelled` status.
- Prevent concurrent re-authentication sessions with a `threading.Lock`. Two simultaneous Playwright instances will conflict.
- Sanitize all error messages before sending to the frontend. Strip Python tracebacks (`Traceback (most recent call last):`), `File "..."` lines, module paths, and exception class names. Keep actionable info like "run `playwright install chromium`".

## Testing

- When mocking `fetch_tokens()` which returns `(csrf_token, session_id)`, the mock MUST return a real tuple, not a `MagicMock`. A `MagicMock` silently succeeds on tuple unpacking but produces garbage values.
- Use `unittest.mock.AsyncMock` for async methods. `MagicMock` does not work with `await`.
- `pytest-timeout` is NOT installed. Do not use `--timeout`. Use `@pytest.mark.asyncio` with `asyncio_mode = "auto"` (configured in `pyproject.toml`).
- Never import or run real Playwright in tests. Mock at the `_run_playwright_login` boundary and push predetermined status objects into the queue.
- Property tests use Hypothesis. Minimum 100 examples per property.

## Data Integrity

- When re-uploading reports, check the `notebook_name_edited` flag. If `True`, do NOT overwrite the user's custom notebook name with the auto-generated one.
- Compute SHA-256 content hashes on file upload for deduplication. Use them to detect duplicate reports and link notebooks to source files.
- Compute SHA-256 prompt hashes before generation. Skip cells that already have a completed generation with the same prompt hash.
- When deleting reports, cascade-delete all associated generation cells and artifacts. Offer to delete the remote notebook too.

## Frontend

- Implement WebSocket reconnection with exponential backoff (1s, 2s, 4s, 8s, max 30s). Show a visible indicator when disconnected.
- Enforce file size limits server-side (FastAPI route, HTTP 413), not just client-side. Write nothing to disk before validation passes.
- All interactive elements need 44×44px minimum touch targets for mobile.
- Use `aria-live="polite"` regions to announce dynamic status changes to screen readers.
- Trap keyboard focus inside modal dialogs until dismissed. Return focus to the triggering element on close.
