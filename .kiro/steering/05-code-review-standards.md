---
inclusion: manual
---

# Code Review Standards

Senior-level code review checklist for the NotebookLM Dashboard project. Updated to reflect the current codebase after all 3 specs (core dashboard, UX improvements, prompt management) are implemented.

## 1. Security

- [ ] No hardcoded secrets, tokens, or credentials
- [ ] User input validated and sanitized before use
- [ ] SQL queries use parameterized statements (no string interpolation)
- [ ] File paths validated with `pathlib.Path.resolve()` + `is_relative_to()` — never `startswith()`
- [ ] Error messages don't leak internal details to clients
- [ ] Dependencies pinned or version-constrained in `requirements.txt`
- [ ] Uploaded files validated (type: PDF/MD for reports, .md for templates; size: 50MB max)
- [ ] Filename sanitization applied before writing to disk (`_sanitize_filename` in reports.py)
- [ ] No CSS selector injection — use `dataset` property comparison, not `querySelectorAll` with user input
- [ ] No `innerHTML` with user-supplied text — use `textContent` or `escapeHtml()` from `utils.js`

## 2. Error Handling & Resilience

- [ ] All external calls (DB, SDK, network) wrapped in try/except
- [ ] Errors logged with sufficient context for debugging
- [ ] User-facing errors are clear and actionable
- [ ] Async tasks handle `CancelledError` properly
- [ ] Resource cleanup in finally blocks or context managers
- [ ] Graceful degradation when remote API fails (local operations continue)
- [ ] All errors return `{"detail": "message"}` via `HTTPException` (FastAPI convention)
- [ ] Exception: `/api/artifacts/remote` returns 200 with `{"error": "..."}` for frontend graceful degradation — this is intentional

## 3. Correctness

- [ ] No deprecated API usage
- [ ] Enum values compared correctly (use `.value` when comparing with strings)
- [ ] Database connections properly managed via `StateManager._get_db()` / `_release_db()`
- [ ] Race conditions addressed in concurrent code (semaphore in TaskQueue)
- [ ] Edge cases handled: empty inputs, None values, missing keys
- [ ] Type annotations accurate and consistent
- [ ] All async function calls use `await` — missing `await` returns a coroutine object, not the result
- [ ] SDK wrapper methods verified as async with `inspect.iscoroutinefunction()`
- [ ] Compound ID parsing uses `rsplit("-", 1)` from the right, not `split("-", N)` from the left
- [ ] Polling loops have maximum iteration counts to prevent infinite loops

## 4. Performance

- [ ] Database connections not held open unnecessarily (semaphore-based pool)
- [ ] N+1 query patterns avoided — use targeted query methods, not `load_state()` for single lookups
- [ ] Remote API fan-out uses `asyncio.gather()` with `Semaphore(5)`
- [ ] File I/O in async functions wrapped in `asyncio.to_thread()`
- [ ] WebSocket connections cleaned up on disconnect (dead connection removal)
- [ ] Background tasks don't leak (done callbacks, cancellation in `stop_all()`)

## 5. Code Quality

- [ ] Functions have single responsibility
- [ ] No dead code or unused imports
- [ ] Consistent naming conventions
- [ ] Docstrings on public APIs
- [ ] Magic numbers/strings are named constants
- [ ] DRY: no significant code duplication
- [ ] Shared regex `TEMPLATE_FILENAME_RE` used by both `ArtifactNamer` and `TemplateDetector`
- [ ] Cell serialization uses `cell_to_dict()` from `ws_manager.py` — no inline dict comprehensions

## 6. API Design

- [ ] REST endpoints follow conventions (proper HTTP methods, status codes)
- [ ] Request models validated with Pydantic (`UpdateReportRequest`, `UpdateTemplateRequest`, `UpdateTemplateExclusionRequest`)
- [ ] Endpoints return consistent response shapes
- [ ] WebSocket protocol documented (message types: `cell_update`, `batch_update`, `ack`)
- [ ] Route ordering: specific paths before parameterized paths (e.g., `/download-all` before `/{artifact_id}`)

## 7. Frontend

- [ ] HTML is semantic and accessible (ARIA labels, roles)
- [ ] XSS prevention: user content escaped via `escapeHtml()` or `textContent`
- [ ] Interactive elements meet 44px minimum touch target
- [ ] Responsive layout works at mobile and desktop breakpoints
- [ ] JavaScript errors caught and handled gracefully
- [ ] Loading text replaced with empty-state message after data fetch completes
- [ ] Destructive actions use custom `showConfirmModal()`, not `window.confirm()`
- [ ] Toast messages include both auto-dismiss timer and manual dismiss button

## 8. Testing

- [ ] Tests cover happy path and error cases
- [ ] Tests don't depend on external services or network
- [ ] Test fixtures clean up after themselves (try/finally for module-level state)
- [ ] Property-based tests use appropriate generators with documented requirement links
- [ ] SDK mocks use `AsyncMock` for async methods, `MagicMock` for sync
- [ ] Module-level state mutations (`DB_PATH`, `_OUTPUT_BASE`) kept active through entire test lifecycle
- [ ] Each test creates isolated temp database via `tmp_path`

## 9. SDK Integration

- [ ] All SDK calls go through `NotebookLMClientWrapper` — never call SDK directly from routes
- [ ] Wrapper uses sub-API pattern: `client.notebooks.list()`, `client.artifacts.generate_*()`, `client.sources.add_file()`
- [ ] Method dispatch by artifact type: `submit_generation` → `generate_infographic/audio/video`, `download_artifact` → `download_infographic/audio/video`
- [ ] SDK return types handled correctly: `Notebook.id`, `GenerationStatus.task_id`, `Artifact` fields
- [ ] `poll_status` requires both `notebook_id` and `task_id`
- [ ] SDK version pinned in `requirements.txt`
- [ ] Startup health check verifies sub-API attributes exist

## 10. Project-Specific Anti-Patterns

| Anti-Pattern | Correct Pattern |
|---|---|
| `innerHTML` with user text | `textContent` or `escapeHtml()` |
| `split("-", N)` on compound IDs | `rsplit("-", 1)` from the right |
| Unbounded polling loop | `max_polls` with documented timeout |
| CSS selector with user input | `row.dataset.id === id` comparison |
| File delete without path check | Validate with `is_relative_to()` against fixed base dir |
| `window.confirm()` | Custom `showConfirmModal()` |
| `load_state()` for single entity | Targeted query method (`get_report()`, `get_template()`) |
| Module-level `DB_PATH` restored before TestClient | Keep patched through entire TestClient context |
| Inline styles in JS-generated HTML | CSS classes (`.badge-remote`, `.btn-danger`) |
