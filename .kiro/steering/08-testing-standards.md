---
inclusion: manual
---

# Testing Standards & Best Practices

Testing checklist for the NotebookLM Dashboard. Updated to reflect the current test suite (316 tests: unit + property-based, 6 correctness properties).

## 1. Test Organization

- [ ] Tests organized by type: `tests/unit/` for unit tests, `tests/property/` for PBT
- [ ] Test files mirror source: `app/foo.py` → `tests/unit/test_foo.py`
- [ ] Test classes group related scenarios with descriptive names
- [ ] Each test has a single clear assertion focus
- [ ] Test names describe scenario and expected outcome
- [ ] Shared fixtures in `tests/conftest.py`

## 2. Test Isolation & Determinism

- [ ] Tests do not depend on execution order
- [ ] Each test creates its own state (no shared mutable state)
- [ ] Temporary files and databases use `tmp_path`, never fixed paths
- [ ] No reliance on external services, network, or filesystem outside `tmp_path`
- [ ] Tests clean up resources in `finally` blocks or fixture teardown
- [ ] Module-level state mutations (`DB_PATH`, `_OUTPUT_BASE`, `PROMPTS_DIR`) wrapped in try/finally
- [ ] Module-level state kept patched through entire `TestClient` lifecycle — restore AFTER the context manager exits, not before (this was the root cause of the ZIP download test failure)
- [ ] No sleeping for arbitrary durations; use events, polling, or `TaskQueue.wait_for()`

## 3. Assertion Quality

- [ ] Assertions include descriptive failure messages for non-obvious checks
- [ ] Exact values asserted where possible (not just truthiness)
- [ ] Error paths assert specific exception type AND message content
- [ ] Collection assertions check both length and content
- [ ] No bare `assert obj` when `assert obj is not None` is meant
- [ ] Async return types verified: `assert not inspect.iscoroutine(result)`

## 4. Fixture Design

- [ ] Fixtures have narrowest possible scope (function > class > module > session)
- [ ] Database fixtures create isolated databases per test
- [ ] Async fixtures use `@pytest_asyncio.fixture`
- [ ] Factory fixtures preferred for parameterized tests
- [ ] Fixture teardown restores modified global state

## 5. Mocking & Faking

- [ ] Mocks use `spec=` to prevent attribute typos
- [ ] Mocks assert called with expected arguments
- [ ] No mocking of the system under test — only mock external dependencies
- [ ] `AsyncMock` for async methods, `MagicMock` for sync
- [ ] Mock return values match real return types
- [ ] SDK sub-API mocks match real structure: `mock_client.notebooks.create`, `mock_client.artifacts.generate_*`, `mock_client.sources.add_file`
- [ ] When mocking functions that unpack return values, return real tuples — not `MagicMock`

## 6. Property-Based Testing (PBT)

Current correctness properties (all passing):

| Property | Description | Test File | Validates |
|----------|-------------|-----------|-----------|
| P1 | SDK method dispatch by artifact type | test_prop_nlm_dispatch.py | Req 1.7, 1.9 |
| P2 | Template upload deduplication | test_prop_template_upload.py | Req 2.5 |
| P3 | Batch progress summary accuracy | test_prop_batch.py | Req 5.6 |
| P4 | Deduplication key determinism | test_prop_dedup.py | Req 7.2 |
| P5 | Batch generation skips completed cells | test_prop_batch.py | Req 7.1, 7.6 |
| P6 | Template exclusion toggle idempotency | test_prop_template_exclusion.py | Req 3.4 |

PBT rules:
- [ ] Each property test documents which requirement it validates (`**Validates: Requirements X.Y**`)
- [ ] Strategies constrain inputs to valid domain (no `assume()` overuse)
- [ ] Custom strategies reusable and defined at module level
- [ ] `max_examples` set explicitly (100-200 for fast, 50-100 for DB-bound)
- [ ] Property tests test pure logic, not I/O-bound code
- [ ] Counter-examples from failures documented and triaged

## 7. Async Test Patterns

- [ ] All async tests marked with `@pytest.mark.asyncio` (or use `asyncio_mode = "auto"`)
- [ ] Async tests do not use `asyncio.run()` or `loop.run_until_complete()` directly
- [ ] Background tasks awaited or cancelled before test teardown
- [ ] Tests verify async wrappers return values, not coroutine objects
- [ ] Integration tests for SDK wrappers include smoke check: assert result type is expected value, not `<coroutine>`

## 8. FastAPI & WebSocket Testing

- [ ] Dependency injection functions tested with correct parameter type (`Request` for HTTP, `WebSocket` for WS)
- [ ] WebSocket endpoints have connect/disconnect smoke test
- [ ] Route handlers that perform file I/O verified to use non-blocking patterns
- [ ] Tests for SDK wrapper endpoints verify full call chain (handler → wrapper → mock SDK)
- [ ] `TestClient` used for synchronous route tests; lifespan executes within the context manager

## 9. Test Data

- [ ] Sample testdata files in `tests/testdata/` used for real-world filename parsing tests
- [ ] Test data is minimal — only fields relevant to the assertion
- [ ] No magic numbers; use named constants or fixtures
- [ ] No commented-out tests or `@pytest.mark.skip` without linked issue

## 10. Coverage Targets

Current test suite: 316 tests passing

| Area | Tests | Notes |
|------|-------|-------|
| NLM Client | 33 unit + 4 PBT | SDK sub-API pattern, dispatch, error handling |
| State Manager | 27 unit | CRUD, cascade, dedup, content hashing |
| Task Queue | 17 unit | Enqueue, dedup, timeout, crash recovery |
| Template Detector | 35 unit | Filename parsing, classification, edge cases |
| Template Exclusion | 13 unit + 2 PBT | Toggle, upload dedup, .md validation |
| Routes Integration | 16 unit | DI types, WebSocket, file I/O, ZIP, pages |
| Artifact Namer | 18 unit | Name derivation, extension mapping |
| Auth | 7 unit | Login, logout, session validation |
| WebSocket Manager | 12 unit | Connect, disconnect, broadcast, dead cleanup |
| UX Improvements | 66 unit + 13 PBT | Remote artifacts, upload feedback, name preservation, deletion |
| Batch/Dedup | 3 unit + 12 PBT | Progress summary, skip completed, dedup keys |
| Main | 7 unit | App creation, lifespan, error handlers |

## 11. Anti-Patterns to Avoid

| Anti-Pattern | Correct Pattern |
|---|---|
| Restore `DB_PATH` before `TestClient` context | Keep patched through entire lifecycle, restore in `finally` |
| `asyncio.sleep(0.5)` in tests | `TaskQueue.wait_for()` or `asyncio.Event` |
| `MagicMock` for async SDK methods | `AsyncMock` |
| Testing with real `data/dashboard.db` | Always use `tmp_path` temp database |
| Skipping property tests because tasks are optional | All correctness properties must have PBT tests |
| Mocking the system under test | Only mock external dependencies |
| `assert obj` for None checks | `assert obj is not None` |
