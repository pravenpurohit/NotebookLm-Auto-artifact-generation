# Lessons Learned — Common Pitfalls

Hard-won lessons from building the NotebookLM Dashboard. Follow these to avoid repeating past mistakes.

## Authentication & Playwright

1. **Playwright is synchronous** — always run it in a `threading.Thread`, never directly in an async handler. Use `queue.Queue` (stdlib) for cross-thread communication, NOT `asyncio.Queue` (not thread-safe across threads).

2. **`asyncio.get_event_loop()` is deprecated** — use `asyncio.get_running_loop()` instead. The old API raises DeprecationWarning in Python 3.12+ and will be removed.

3. **Cleanup Playwright on shutdown** — always call `cleanup_reauth()` in the FastAPI lifespan shutdown hook. Orphaned Chromium processes will consume memory and ports.

4. **Browser closure detection** — when the user closes the Playwright browser manually, `page.url` raises an exception. Catch it and emit a `cancelled` status, don't let it propagate as an unhandled error.

5. **Credential refresh requires `reinit_client()`** — after updating `SessionCredentials`, you MUST call `nlm_client.reinit_client()` to rebuild the SDK client. Otherwise the old (expired) client object is still used.

## notebooklm-py SDK

6. **Sub-API pattern** — the SDK uses `client.notebooks.list()`, `client.artifacts.generate_*()`, `client.sources.add_file()`. NEVER call methods directly on the client object (e.g., `client.list_notebooks()` does not exist).

7. **SDK return types are inconsistent** — some methods return objects with attributes (`.id`, `.title`), others return dicts. Always check with `isinstance(result, dict)` and fall back to `getattr(result, field, default)`.

8. **Verify sub-API attributes on init** — after constructing `NotebookLMClient`, check that `notebooks`, `artifacts`, and `sources` attributes exist. If they don't, the SDK version is incompatible.

9. **Audio format mapping** — the SDK uses its own `AudioFormat` enum. Map our string constants (`"DEEP_DIVE"`, `"BRIEF"`, etc.) to the SDK enum values. Import the enum inside the method to handle `ImportError` gracefully.

## Testing

10. **Mock return values for tuple unpacking** — when mocking `fetch_tokens()` which returns `(csrf_token, session_id)`, the mock MUST return a real tuple, not a `MagicMock`. A `MagicMock` will silently succeed on tuple unpacking but produce garbage values.

11. **Use `AsyncMock` for async methods** — `MagicMock` won't work for `await` calls. Always use `unittest.mock.AsyncMock` for async SDK methods.

12. **Don't use `--timeout` with pytest** — `pytest-timeout` is not installed. Use `@pytest.mark.asyncio` with `asyncio_mode = "auto"` (configured in `pyproject.toml`).

13. **Mock Playwright at the boundary** — never import or run real Playwright in tests. Mock at `_run_playwright_login` and push predetermined `ReauthStatus` objects into the queue.

## Data Integrity

14. **Preserve user-edited notebook names** — when re-uploading reports, check the `notebook_name_edited` flag. If `True`, do NOT overwrite the notebook name with the auto-generated one.

15. **Content hash for deduplication** — compute SHA-256 of file content on upload. Use it to detect duplicate reports and link notebooks to source files.

16. **Prompt hash for idempotency** — compute SHA-256 of template content before generation. Skip cells that already have a completed generation with the same prompt hash.

## Frontend

17. **WebSocket reconnection** — always implement exponential backoff (1s, 2s, 4s, 8s, max 30s) for WebSocket reconnection. Show a visible indicator when disconnected.

18. **Error sanitization** — never show raw Python tracebacks to users. Strip `Traceback (most recent call last):`, `File "..."` lines, module paths, and exception class names. Preserve actionable info like "run `playwright install chromium`".

19. **Server-side file size validation** — don't rely only on client-side checks. Enforce the 50MB limit in the FastAPI upload route and return HTTP 413 before writing to disk.

20. **Legacy URL redirects** — when removing old routes (`/files`, `/prompts`, `/processing`), add HTTP 301 redirects to the new locations so bookmarks and browser history still work.
