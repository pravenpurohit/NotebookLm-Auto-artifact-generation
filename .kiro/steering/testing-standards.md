---
inclusion: manual
---

# Testing Standards & Best Practices

Senior-level test analysis and QA automation checklist for the NotebookLM Dashboard project.

## 1. Test Organization & Structure

- [ ] Tests are co-located by type: `tests/unit/` for unit tests, `tests/property/` for PBT
- [ ] Test files mirror source file names: `app/foo.py` → `tests/unit/test_foo.py`
- [ ] Test classes group related scenarios with descriptive names
- [ ] Each test has a single clear assertion focus (one logical concept per test)
- [ ] Test names describe the scenario and expected outcome, not the implementation
- [ ] Shared fixtures and helpers are defined at the appropriate scope (module, class, session)

## 2. Test Isolation & Determinism

- [ ] Tests do not depend on execution order
- [ ] Each test creates its own state (no shared mutable state between tests)
- [ ] Temporary files and databases use `tmp_path` or `tempfile`, never fixed paths
- [ ] Async fixtures use `pytest_asyncio.fixture`, not `pytest.fixture`
- [ ] No reliance on external services, network, or filesystem outside `tmp_path`
- [ ] Tests clean up resources in `finally` blocks or fixture teardown
- [ ] No sleeping for arbitrary durations; use events, polling, or mocked time
- [ ] Tests that assert state written by the function under test do so before yielding to the event loop (e.g. before `await asyncio.sleep()`), since background tasks may overwrite that state concurrently

## 3. Assertion Quality

- [ ] Assertions include descriptive failure messages for non-obvious checks
- [ ] Exact values are asserted where possible (not just truthiness)
- [ ] Error paths assert the specific exception type AND message content
- [ ] Collection assertions check both length and content (not just one)
- [ ] No bare `assert obj` when `assert obj is not None` or `assert len(obj) == N` is meant
- [ ] Floating-point comparisons use `pytest.approx()` where applicable

## 4. Fixture Design

- [ ] Fixtures have the narrowest possible scope (function > class > module > session)
- [ ] Database fixtures create isolated databases per test (no cross-contamination)
- [ ] Fixtures that perform I/O are async and use `@pytest_asyncio.fixture`
- [ ] Factory fixtures (functions that create objects) are preferred over static fixtures for parameterized tests
- [ ] Fixture teardown restores any modified global state (env vars, module-level vars)

## 5. Mocking & Faking

- [ ] Mocks use `spec=` to prevent attribute typos from silently passing
- [ ] Prefer fakes (lightweight implementations) over mocks for complex interfaces
- [ ] Mocks assert they were called with expected arguments (not just that they were called)
- [ ] No mocking of the system under test; only mock external dependencies
- [ ] `AsyncMock` is used for async methods, not `MagicMock`
- [ ] Mock return values match the real return type (no `MagicMock` where `str` is expected)
- [ ] When mocking SDK/third-party functions, verify the real function's sync/async nature first (`inspect.iscoroutinefunction()`), then use `AsyncMock` for async and `MagicMock` for sync — mismatching hides missing `await` bugs
- [ ] Mock-based tests for functions that unpack return values (e.g. `a, b = func()`) should return real tuples, not `MagicMock`, so missing `await` raises `TypeError` instead of silently passing

## 6. Property-Based Testing (PBT)

- [ ] Each property test documents which requirement it validates (`**Validates: Requirements X.Y**`)
- [ ] Strategies constrain inputs to the valid domain (no `assume()` overuse)
- [ ] Custom strategies are reusable and defined at module level
- [ ] `max_examples` is set explicitly (100-200 for fast properties, 50-100 for DB-bound)
- [ ] Property tests test pure logic functions, not I/O-bound code
- [ ] Generators avoid producing invalid inputs that would be filtered by `assume()`
- [ ] Counter-examples from failures are documented and triaged

## 7. Async Test Patterns

- [ ] All async tests are marked with `@pytest.mark.asyncio`
- [ ] Async tests do not use `asyncio.run()` or `loop.run_until_complete()` directly
- [ ] Background tasks are awaited or cancelled before test teardown
- [ ] `asyncio.sleep()` in tests uses minimal durations (0.05-0.2s, not seconds)
- [ ] Tests that spawn background tasks include cleanup to prevent resource leaks
- [ ] Tests verify that async wrapper functions actually `await` their SDK calls (assert return values are not coroutine objects using `inspect.iscoroutine()`)
- [ ] When mocking third-party async functions, use `AsyncMock` so that missing `await` in production code is caught as a type mismatch during tests
- [ ] Integration tests for SDK wrappers include a smoke check: call the wrapper and assert the result type is the expected value, not `<coroutine>`

## 8. Error & Edge Case Coverage

- [ ] Happy path is tested for every public function
- [ ] Error paths test specific exception types and messages
- [ ] Boundary values are tested (empty inputs, zero, max values, None)
- [ ] Idempotency is tested where the contract requires it (e.g., `init_db` twice)
- [ ] Concurrent access patterns are tested for shared-state components

## 9. Test Maintainability

- [ ] No magic numbers; use named constants or fixtures
- [ ] Helper functions are extracted for repeated setup patterns
- [ ] Test data is minimal (only fields relevant to the assertion)
- [ ] No commented-out tests or `@pytest.mark.skip` without a linked issue
- [ ] Unused imports are removed
- [ ] Tests do not duplicate production logic (test the interface, not the implementation)

## 10. Coverage & Completeness

- [ ] Every public function/method has at least one unit test
- [ ] Every Pydantic model has validation tests for required fields and constraints
- [ ] Every enum is tested for exhaustive membership
- [ ] Integration points (DB, WebSocket, SDK) have both success and failure tests
- [ ] Property tests cover all formally specified correctness properties

## 11. FastAPI & WebSocket Testing

- [ ] FastAPI dependency injection functions are tested with the correct parameter type (`Request` for HTTP routes, `WebSocket` for WebSocket routes) — a dependency that takes `Request` will fail silently at runtime when used in a WebSocket endpoint
- [ ] WebSocket endpoints have at least a connect/disconnect smoke test using `TestClient` or `httpx.AsyncClient` with WebSocket support
- [ ] Route handlers that perform file I/O use non-blocking patterns (`asyncio.to_thread`, `aiofiles`) — tests should verify the handler doesn't block the event loop for large payloads
- [ ] Tests for endpoints that call SDK wrappers verify the full call chain (handler → wrapper → mock SDK), not just the handler in isolation

## 12. Frontend Behavior Verification

- [ ] Pages that fetch data on load and display a "Loading…" placeholder have a test or manual check confirming the placeholder is replaced after fetch completes (both empty and non-empty result sets)
- [ ] JavaScript `render()` functions reset transient UI text (loading indicators, status messages) before rendering — never rely on the initial DOM state persisting after an async fetch
- [ ] Error states from failed API calls are surfaced to the user (not silently swallowed by `catch` blocks that only `console.error`)


## 13. Cross-Feature Property Test Coverage

- [ ] Every correctness property defined in a feature's design document has a corresponding property test in `tests/property/`
- [ ] Property tests for DB-bound operations (e.g., `persist_reports`, `update_report_notebook_name`) use `run_async()` with `tempfile.TemporaryDirectory` to create isolated databases per Hypothesis iteration
- [ ] Property tests for DB-bound operations use lower `max_examples` (50) to keep runtime reasonable while still providing meaningful coverage
- [ ] Pure-logic property tests (merge, filter, message building) use higher `max_examples` (100-200) since they're fast
- [ ] Feature-specific property tests are grouped in a single file per feature: `tests/property/test_prop_{feature_name}.py`
- [ ] Each property test file includes a module docstring listing all properties covered and their requirement traceability

## 14. Merge & Deduplication Testing

- [ ] Merge functions that combine data from multiple sources (e.g., local + remote artifacts) are tested with: no overlap, full overlap, partial overlap, empty left, empty right, both empty
- [ ] Deduplication keys are explicitly documented in test docstrings (e.g., `(source_notebook_id, artifact_name)`)
- [ ] Property tests for merge verify: no duplicate keys in output, output size ≤ sum of inputs, all "primary" items preserved (local artifacts take precedence over remote)

## 15. State Mutation Protection Testing

- [ ] Any function that protects user-edited state (e.g., `persist_reports` skipping edited notebook names) has both a unit test and a property test
- [ ] The protection test pattern: (1) create initial state, (2) mark as user-edited, (3) attempt overwrite, (4) verify original value preserved
- [ ] Tests verify the protection flag (`notebook_name_edited`) transitions correctly: starts False, becomes True on edit, stays True across re-uploads
- [ ] Tests cover the non-protected path too: non-edited values CAN be overwritten by re-upload

## 16. Anti-Patterns Discovered

- [ ] **Don't skip optional property tests**: All correctness properties in the design document should have property tests, even if the implementation task was marked optional. The audit found all 7 properties were untested because their tasks were optional.
- [ ] **Don't rely on unit tests alone for invariants**: Unit tests with specific examples don't catch edge cases that property tests with random inputs reveal. Always pair unit tests with property tests for core logic.
- [ ] **Test the flag, not just the effect**: When a function sets a boolean flag (e.g., `notebook_name_edited`), write a dedicated test that asserts the flag value directly, not just the downstream behavior the flag enables.
- [ ] **Frontend-untestable requirements need documentation**: Requirements that are purely frontend JS behavior (auto-dismiss, progress indicators, input disabling) should be explicitly marked as "manual verification only" in the test coverage matrix, not silently skipped.
- [ ] **Clean up imports after each review pass**: Unused imports accumulate across review cycles as tests are refactored. Each final review pass should verify no stale imports remain (e.g., `patch`, `SessionCredentials` imported but never used).
