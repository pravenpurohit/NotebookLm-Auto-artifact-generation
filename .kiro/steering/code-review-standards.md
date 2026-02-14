---
inclusion: manual
---

# Code Review Standards

Senior-level code review checklist for the NotebookLM Dashboard project.

## 1. Security

- [ ] No hardcoded secrets, tokens, or credentials
- [ ] User input is validated and sanitized before use
- [ ] SQL queries use parameterized statements (no string interpolation)
- [ ] File paths are validated to prevent path traversal
- [ ] Error messages don't leak internal details to clients
- [ ] Dependencies are pinned or version-constrained
- [ ] CORS / auth middleware is applied where needed
- [ ] Uploaded files are validated (type, size) before processing

## 2. Error Handling & Resilience

- [ ] All external calls (DB, SDK, network) are wrapped in try/except
- [ ] Errors are logged with sufficient context for debugging
- [ ] User-facing errors are clear and actionable
- [ ] Async tasks handle CancelledError properly
- [ ] Resource cleanup happens in finally blocks or context managers
- [ ] Graceful degradation when optional dependencies are missing

## 3. Correctness

- [ ] No deprecated API usage (e.g. datetime.utcnow())
- [ ] Enum values are compared correctly (not string vs enum)
- [ ] Database connections are properly closed after use
- [ ] Race conditions are addressed in concurrent code
- [ ] Edge cases handled: empty inputs, None values, missing keys
- [ ] Type annotations are accurate and consistent
- [ ] All calls to async/coroutine functions use `await` (missing `await` returns a coroutine object, not the result)
- [ ] When integrating third-party SDKs, verify each function's sync/async nature with `inspect.iscoroutinefunction()` before calling
- [ ] Tuple unpacking targets match the return type (a coroutine is not iterable — missing `await` causes "cannot unpack non-iterable coroutine object")

## 4. Performance

- [ ] Database connections are not held open unnecessarily
- [ ] N+1 query patterns are avoided
- [ ] Large file uploads have size limits
- [ ] WebSocket connections are cleaned up on disconnect
- [ ] Background tasks don't leak (done callbacks, cancellation)

## 5. Code Quality

- [ ] Functions have single responsibility
- [ ] No dead code or unused imports
- [ ] Consistent naming conventions
- [ ] Docstrings on public APIs
- [ ] Magic numbers/strings are named constants
- [ ] DRY: no significant code duplication

## 6. API Design

- [ ] REST endpoints follow conventions (proper HTTP methods, status codes)
- [ ] Request/response models are validated with Pydantic
- [ ] Endpoints return consistent response shapes
- [ ] WebSocket protocol is documented

## 7. Frontend

- [ ] HTML is semantic and accessible (ARIA labels, roles)
- [ ] XSS prevention: user content is escaped before rendering
- [ ] Interactive elements meet 44px minimum touch target
- [ ] Responsive layout works at mobile and desktop breakpoints
- [ ] JavaScript errors are caught and handled gracefully
- [ ] Loading placeholder text (e.g. "Loading…") is reset to the empty-state message (e.g. "No items found.") inside the render function after data fetch completes — never leave stale loading text visible when the result set is empty

## 8. Testing

- [ ] Tests cover happy path and error cases
- [ ] Tests don't depend on external services or network
- [ ] Test fixtures clean up after themselves
- [ ] Property-based tests use appropriate generators
- [ ] No mocks that hide real bugs
- [ ] SDK integration points have runtime smoke tests that catch async/sync mismatches (e.g. assert the return is not a coroutine)

## 9. UI/UX Standards

- [ ] Review all frontend changes against `.kiro/steering/ui-ux-standards.md`
- [ ] Destructive actions have confirmation dialogs
- [ ] Touch targets meet 44px minimum
- [ ] Skip-to-content link present on all pages using base layout
- [ ] Loading indicators shown during async data fetches
- [ ] Focus is managed after dynamic content changes (deletions, modals)
- [ ] ARIA labels on all interactive elements
- [ ] Mobile table cells include `data-label` attributes for stacked layout
- [ ] Status messages are manually dismissable
- [ ] WebSocket disconnection state is visible to users

## 10. Testing Standards

- [ ] Review all test changes against `.kiro/steering/testing-standards.md`
- [ ] Tests clean up background tasks and async resources (no task leaks)
- [ ] Module-level state mutations are wrapped in try/finally for restoration
- [ ] Unused fixtures and imports are removed
- [ ] Property-based tests document which requirement they validate
- [ ] Mocks use `spec=` to prevent silent attribute typos
- [ ] Database fixtures create isolated databases per test
- [ ] Assertions include descriptive failure messages
- [ ] Assertions on state written by the function under test happen before yielding to the event loop (race condition prevention)
- [ ] SDK mocks match the real function's sync/async nature (AsyncMock for async, MagicMock for sync)
- [ ] FastAPI dependency functions are tested with the correct injection type (Request vs WebSocket)
- [ ] Frontend loading states are verified to clear after data fetch completes

## 11. Project-Specific Patterns (from Code Review)

The following checklist items were discovered during the task 10.1–10.2 code review of the UX improvements feature. They capture recurring patterns and anti-patterns specific to this project.

### XSS Prevention (S1, S2)

- [ ] Never use `innerHTML` with user-supplied text — use `textContent` or DOM API methods (`createElement`, `appendChild`) instead
- [ ] When `innerHTML` is unavoidable (e.g. building complex markup), escape all user-supplied values through `escapeHtml()` from `utils.js`
- [ ] Batch status messages and dynamic feedback must be built with DOM API, not string concatenation into `innerHTML`

### Path Traversal (S3)

- [ ] All file deletion and file access methods must validate that the resolved path (`os.path.realpath`) stays within the expected base directory
- [ ] Path validation must happen before any filesystem operation (delete, read, write)
- [ ] Use a shared validation helper rather than inline checks to avoid inconsistency

### CSS Selector Injection (S5)

- [ ] Never interpolate user-supplied values into `querySelectorAll` or `querySelector` selectors
- [ ] Use `dataset` property comparison (e.g. `row.dataset.notebookId === id`) instead of CSS attribute selectors with user input
- [ ] When removing DOM elements by data attribute, iterate all matching elements and compare via `dataset` rather than building a selector string

### Compound ID Parsing (C1)

- [ ] When parsing compound IDs that contain UUIDs or other hyphenated values (e.g. `remote-{notebook_id}-{index}`), use `rsplit("-", 1)` to split from the right, not `split("-", 2)` from the left
- [ ] Always validate the number of parts after splitting and return a clear error for malformed IDs

### Polling & Timeout Safety (C3)

- [ ] All polling loops must have a maximum iteration count to prevent infinite loops
- [ ] Document the timeout calculation in a comment (e.g. `max 360 polls × 5s = 30 min`)
- [ ] After exhausting max polls, raise a clear timeout error rather than silently returning

### Dead Code (Q1)

- [ ] Remove unused methods, functions, and imports during each review cycle
- [ ] Check for methods that were superseded by refactoring but never deleted (e.g. `_find_report`, `_find_template` in `TaskQueue`)

## 12. Anti-Patterns to Watch For

| Anti-Pattern | Example Found | Correct Pattern |
|---|---|---|
| `innerHTML` with user text | `renderGrid()` used `innerHTML` with report names | Use `textContent` or `escapeHtml()` |
| `split("-", N)` on compound IDs | `split("-", 2)` broke UUID-containing IDs | `rsplit("-", 1)` from the right |
| Unbounded polling | `_poll_until_done` had no max iterations | Add `max_polls` with documented timeout |
| CSS selector with user input | `querySelectorAll('[data-id="' + id + '"]')` | `row.dataset.id === id` comparison |
| File delete without path check | `delete_artifact_record` deleted any path | Validate resolved path is within output dir |
| Leftover helper methods | `_find_report`/`_find_template` unused after refactor | Remove dead code promptly |
| `confirm()` in JS | `showDuplicatePromptDialog` and `bindBatchControls` used `confirm()` | Use custom `showConfirmModal()` for consistent UX |
| Circular path validation | `delete_artifact_record` derived expected dir from stored path itself | Validate against a fixed `_output_base` directory |

## 13. Findings from Second-Pass Code Review (Task 12.3)

### Confirm Dialog Consistency (UX/S)

- [ ] Never use `window.confirm()` or `window.alert()` in production JS — always use the custom `showConfirmModal()` pattern for consistent UX and accessibility
- [ ] All destructive or significant actions must use the same modal pattern (overlay, role=dialog, aria-modal, Escape key support)

### Path Validation Robustness (S)

- [ ] File deletion path validation must compare against a fixed, known base directory (e.g. `_OUTPUT_BASE`), not a directory derived from the stored path itself
- [ ] The base directory should be configurable on the class instance (e.g. `self._output_base`) so tests can override it while production uses the real output directory
- [ ] Both `delete_artifact_record` and `delete_notebook_records` must use the same validation logic
