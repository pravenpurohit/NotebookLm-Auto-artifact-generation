---
inclusion: manual
---

# Architecture & Efficient Code Guidelines

Architecture playbook for the NotebookLM Dashboard. Each section identifies a structural pattern, the target state, and the files affected. Sections marked ✅ are complete. Sections marked ⬜ are deferred tech debt.

## Current Architecture

```
app/
├── main.py              — App factory + async lifespan (component wiring, DB init, template loading, crash recovery)
├── routes/              — 10 domain routers: auth, reports, templates, generation, batch, grid, artifacts, recovery, pages, ws
│   └── __init__.py      — Re-exports all routers
├── dependencies.py      — FastAPI DI helpers (HTTP Request + WebSocket variants)
├── state_manager.py     — SQLite persistence (aiosqlite, connection pool, targeted queries)
├── task_queue.py        — Async generation orchestrator (concurrency semaphore, dedup, timeout, crash recovery)
├── nlm_client.py        — SDK wrapper (notebooklm-py sub-API pattern: notebooks, artifacts, sources)
├── ws_manager.py        — WebSocket manager + CellBroadcaster protocol
├── template_detector.py — Filename-based template classification
├── artifact_namer.py    — Template-to-artifact name derivation
├── models.py            — Pydantic models, enums, shared TEMPLATE_FILENAME_RE
├── validators.py        — Input validation helpers
└── auth.py              — Google auth session management
```

## Completed Refactorings

### ✅ 1. Eliminate Raw SQL in Route Handlers
All DB access goes through `StateManager`. No route imports `aiosqlite`.

### ✅ 2. Extract Route Handlers into Domain Modules
10 routers: `auth`, `reports`, `templates`, `generation`, `batch`, `grid`, `artifacts`, `recovery`, `pages`, `ws`. Plus `notebooks` for notebook deletion.

### ✅ 3. Shared DB Connection Pool
`StateManager.open()` / `close()` manage a persistent `aiosqlite.Connection`. Semaphore-based `_get_db()` / `_release_db()` for safe concurrent access.

### ✅ 4. Typed WebSocket Manager Dependency
`CellBroadcaster` protocol in `ws_manager.py`. `StateManager` typed as `ws_manager: CellBroadcaster | None`.

### ✅ 7. Page Routes Extracted
`app/routes/pages.py` handles all HTML page routes: `/`, `/dashboard`, `/files`, `/artifacts`, `/prompts`, `/processing`.

### ✅ 8. Consolidated Filename Pattern Regex
`TEMPLATE_FILENAME_RE` defined once in `app/models.py`, imported by both `ArtifactNamer` and `TemplateDetector`.

### ✅ 9. TaskQueue Testable Without Sleep
`TaskQueue.wait_for(report_id, template_id)` awaits the internal `asyncio.Task`.

### ✅ 10. Reduced `_run_generation` Complexity
Split into `_create_and_attach_notebook`, `_submit_and_poll`, `_download_and_complete`.

### ✅ 11. Pydantic Request Validation
`UpdateReportRequest`, `UpdateTemplateRequest`, `UpdateTemplateExclusionRequest` replace `Dict[str, Any]` in route signatures.

### ✅ 12. Frontend JS Modules
`utils.js` (shared helpers), `file-browser.js`, `artifacts.js`, `grid.js`, `prompts.js`, `processing.js`. All loaded via `<script>` tags.

### ✅ 14. Consistent Error Response Shape
All errors use `HTTPException(detail=str)`. Global handlers for `NotebookLMClientError` → 502, `ValueError` → 400. One intentional exception: `/api/artifacts/remote` returns 200 with `{"artifacts": [], "error": "..."}` for graceful frontend degradation.

### ✅ 15. Parallel Remote Fetching
`list_remote_artifacts()` uses `asyncio.gather()` with `Semaphore(5)`.

### ✅ 16. Targeted Query Methods
`get_template()`, `get_report()`, `get_all_reports()`, `get_all_templates()`, `find_template_by_filename()`. Routes use these instead of `load_state()`.

### ✅ 17. Async File I/O
All `os.*` calls in async functions wrapped in `asyncio.to_thread()`.

### ✅ 18. Path Traversal Protection
`pathlib.Path.resolve()` + `is_relative_to()` on all file-serving and file-deletion operations.

## Deferred Tech Debt

### ⬜ 5. Dict-Based State → Pydantic Models
`ReportModel`, `TemplateModel`, `GenerationCellModel` exist in `models.py` but are not used as canonical DTOs. Routes and StateManager pass raw dicts. `GenerationCell` dataclass in `state_manager.py` duplicates `GenerationCellModel`.

**Priority:** Medium. Targeted query methods reduce urgency. Blocked items: Section 6 cell serialization consolidation.

### ⬜ 6. Centralize Cell Serialization
Partial consolidation via `cell_to_dict()` in `ws_manager.py`. Full consolidation blocked by Section 5.

### ⬜ 13. Pydantic Models as Response Models
Models kept as data shape documentation. Will be used as FastAPI response models when Section 5 is implemented.

### ⬜ 19. Remaining Minor Items

| Item | Priority | Notes |
|------|----------|-------|
| `persist_reports` N+1 within transaction | Low | Multiple INSERT/UPDATE in loop, already within single transaction |
| `delete_notebook_records` per-cell deletion | Low | Could optimize with DELETE JOIN, but volume is low |
| Make `DB_PATH` a parameter to `create_app()` | Medium | Eliminates module-level state mutation in tests |
| Pin `notebooklm-py` to exact version | High | Prevent silent breaking changes from `>=0.3.2` |
| SDK startup health check | High | Verify sub-API attributes exist before accepting requests |
| Remove HTMX or adopt broadly | Low | Currently only used for logout button |

## Active Architecture Rules

These rules apply to all new code:

### Database Access
- All DB access MUST go through `StateManager` methods. No raw SQL in routes.
- Routes MUST NOT call `load_state()` for single-entity lookups. Use targeted query methods.
- `load_state()` is reserved for the grid/dashboard view that needs full state.

### Async I/O
- Any synchronous file I/O in an `async def` function MUST be wrapped in `asyncio.to_thread()`.
- Any route that fans out to multiple remote API calls MUST use `asyncio.gather()` with a semaphore.

### Path Security
- Any endpoint or method that serves or deletes files MUST validate paths using `pathlib.Path.resolve()` + `is_relative_to()`.
- Never trust database-stored paths without validation.

### SDK Integration
- All SDK interactions go through `NotebookLMClientWrapper`. Never call SDK directly from routes.
- Wrapper must use the sub-API pattern (`client.notebooks.list()`, not `client.list_notebooks()`).
- Wrapper must verify SDK sub-API attributes exist at initialization time.
- Pin SDK version in `requirements.txt` to prevent silent breaking changes.
- Document expected SDK API surface in wrapper docstring.

### Error Handling
- All errors return `{"detail": "message"}` via `HTTPException`.
- External call failures (SDK, network) use try/except with specific error types.
- Graceful degradation: remote failures don't break local functionality.

### Testing
- Tests that mutate module-level state (`DB_PATH`, `_OUTPUT_BASE`) MUST keep the mutation active through the entire test lifecycle (including lifespan execution) and restore in `finally`.
- Each test creates its own isolated temp database.

## Third-Party SDK Integration

Rules for integrating third-party SDKs (e.g., `notebooklm-py`) to prevent API mismatches between wrapper assumptions and actual SDK surfaces.

### Startup-Time Validation
- Every SDK wrapper MUST verify that the expected sub-API attributes and methods exist on the client at initialization time, before the application accepts requests.
- Use `hasattr()` checks on the client object for required sub-APIs (e.g., `notebooks`, `artifacts`, `sources`) and log a clear, actionable error if any are missing.
- If a required sub-API is absent, the wrapper MUST raise an exception or set itself to a degraded state that prevents calls to the missing API from silently failing.

### Wrapper–SDK Contract
- Document the expected SDK API surface (method names, parameters, return types) in the wrapper's module-level or class-level docstring.
- When the SDK exposes methods via sub-objects (e.g., `client.notebooks.list()` instead of `client.list_notebooks()`), the wrapper MUST use the sub-object pattern. Never guess or fall back to flat method names.
- Pin the SDK to an exact version in `requirements.txt` (e.g., `notebooklm-py==0.3.2`, not `>=0.3.2`) to prevent silent breaking changes from upstream releases.

### Method Dispatch by Type
- When the SDK provides type-specific methods (e.g., `generate_infographic`, `generate_audio`, `generate_video`), the wrapper MUST dispatch to the correct method based on the artifact type parameter. A single generic call that ignores the type is not acceptable.
- The dispatch mapping MUST be explicit (dict or if/elif) rather than dynamic attribute lookup from user input, to prevent injection of arbitrary method names.

### Return Type Handling
- Wrapper methods MUST extract and return only the fields needed by the application from SDK return types (e.g., `.id`, `.title` from a `Notebook` object), rather than passing opaque SDK objects to callers.
- If the SDK changes its return type shape, the wrapper is the single place that breaks — routes and services MUST NOT depend on SDK-specific types.

### Testing SDK Wrappers
- Unit tests for SDK wrappers MUST mock the sub-API objects with `AsyncMock(spec=RealSubAPIClass)` so that calling a non-existent method raises `AttributeError` during testing.
- Include at least one test that verifies the startup validation logic rejects a client missing expected sub-API attributes.
- Property tests SHOULD cover dispatch correctness: for any valid artifact type, the correct SDK method is called.
