---
inclusion: manual
---

# Architecture & Efficient Code Guidelines

Refactoring playbook for the NotebookLM Dashboard. Each section identifies a structural problem, the target pattern, and the files affected.

## 1. Eliminate Raw SQL in Route Handlers

**Problem**: `routes.py` contains inline SQL for delete, update, and query operations (reports, templates, artifacts). This bypasses the `StateManager` abstraction, duplicates DB access patterns, and makes routes harder to test.

**Target**: All DB access goes through `StateManager`. Route handlers call `state_manager.method()` only.

**Affected files**: `app/routes.py`, `app/state_manager.py`

**Actions**:
- [x] Move `delete_report` SQL into `StateManager.delete_report(report_id)`
- [x] Move `update_report` SQL into `StateManager.update_report(report_id, notebook_name)`
- [x] Move `update_template` SQL into `StateManager.update_template(template_id, content)`
- [x] Move `list_artifacts` SQL into `StateManager.list_artifacts(filters)`
- [x] Move `get_artifact` SQL into `StateManager.get_artifact(artifact_id)`
- [x] Move `preview_artifact` SQL into `StateManager.get_artifact_file_info(artifact_id)`
- [x] Remove `import aiosqlite` from `routes.py`

## 2. Extract Route Handlers into Domain Modules

**Problem**: `routes.py` is a 400+ line monolith containing auth, reports, templates, generation, batch, grid, artifacts, recovery, and WebSocket routes. This violates single-responsibility and makes navigation difficult.

**Target**: One router file per domain, imported and included in `main.py`.

**Affected files**: `app/routes.py`, `app/main.py`

**Actions**:
- [x] Create `app/routes/auth.py` — login, logout, status
- [x] Create `app/routes/reports.py` — CRUD for reports
- [x] Create `app/routes/templates.py` — CRUD for templates
- [x] Create `app/routes/generation.py` — start, stop, retry single generation
- [x] Create `app/routes/batch.py` — batch start, pause, resume, stop, retry
- [x] Create `app/routes/grid.py` — grid endpoint
- [x] Create `app/routes/artifacts.py` — list, get, preview artifacts
- [x] Create `app/routes/recovery.py` — crash recovery sync
- [x] Create `app/routes/ws.py` — WebSocket endpoint
- [x] Create `app/routes/__init__.py` — re-export all routers
- [x] Move shared dependency helpers (`_get_state_manager`, etc.) into `app/dependencies.py`
- [x] Update `main.py` to include sub-routers

## 3. Use a Shared DB Connection Pool

**Problem**: Every `StateManager` method opens and closes its own `aiosqlite.connect()`. This creates connection churn and prevents transaction grouping.

**Target**: A single connection (or pool) created at startup, passed to `StateManager`, reused across calls.

**Affected files**: `app/state_manager.py`, `app/main.py`

**Actions**:
- [x] Add `async def open(self)` and `async def close(self)` to `StateManager` that manage a persistent `aiosqlite.Connection`
- [x] Replace per-method `async with aiosqlite.connect(...)` with `self._db` usage
- [x] Call `state_manager.open()` in lifespan startup, `state_manager.close()` in shutdown
- [x] Keep `init_db()` as a one-time schema migration that uses the persistent connection

## 4. Type the WebSocket Manager Dependency

**Problem**: `StateManager.__init__` accepts `ws_manager: object | None`. This loses type safety and requires `hasattr` checks at call sites.

**Target**: Use a protocol or the concrete `WebSocketManager` type.

**Affected files**: `app/state_manager.py`, `app/ws_manager.py`

**Actions**:
- [x] Define a `CellBroadcaster` Protocol in `app/ws_manager.py` with `async def broadcast_cell_update(self, cell: GenerationCell) -> None`
- [x] Type `StateManager.__init__` parameter as `ws_manager: CellBroadcaster | None = None`
- [x] Remove `hasattr` guard in `update_cell` — the protocol guarantees the method exists

## 5. Replace Dict-Based State with Typed Models

**Problem**: `load_state()` returns `dict` with string keys. `persist_reports()` and `persist_templates()` accept `list[dict | object]` with runtime `isinstance` checks. Route handlers build response dicts manually.

**Target**: Use the existing Pydantic models from `models.py` (which are currently unused) as the canonical data transfer objects.

**Affected files**: `app/state_manager.py`, `app/routes.py`, `app/main.py`, `app/task_queue.py`

**Actions** (deferred — high risk, moderate benefit; models kept for future adoption):
- [ ] Have `load_state()` return `GridStateModel` instead of a raw dict
- [ ] Have `persist_reports()` accept `list[ReportModel]`
- [ ] Have `persist_templates()` accept `list[TemplateModel]`
- [ ] Use `ReportModel`, `TemplateModel`, `GenerationCellModel` as FastAPI response models on route decorators
- [ ] Remove manual dict construction in route handlers — let Pydantic serialize
- [ ] Remove the `GenerationCell` dataclass from `state_manager.py` — use `GenerationCellModel` from `models.py` instead (eliminate the duplicate)

> **Review note (UX improvements, Section 9):** This remains the highest-priority deferred tech debt item. The targeted query methods added in Section 16 reduce the urgency (routes no longer call `load_state()` for single-entity lookups), but the dict-based data flow still makes the codebase harder to refactor safely. Blocked items: Section 6 cell serialization consolidation depends on this.

## 6. Centralize Cell Serialization

**Problem**: Cell-to-dict conversion is duplicated in `ws_manager._cell_to_dict()`, `routes.get_grid()`, and `main.dashboard()`. Each has slightly different field handling.

**Target**: One serialization path, ideally via Pydantic `.model_dump()`.

**Affected files**: `app/ws_manager.py`, `app/routes.py`, `app/main.py`

**Actions**:
- [ ] After adopting Pydantic models (Section 5), use `GenerationCellModel.model_dump()` everywhere
- [x] Remove `_cell_to_dict()` from `ws_manager.py` — replaced with public `cell_to_dict()` used by grid route and pages route
- [x] Remove inline dict comprehensions in `get_grid()` and `dashboard()` — both now use `cell_to_dict()`

> **Review note (UX improvements, Section 9):** Blocked by Section 5. The partial consolidation via `cell_to_dict()` is sufficient for now.

## 7. Move Page Routes Out of `create_app()`

**Problem**: `create_app()` defines `index()`, `dashboard()`, `files()`, and `artifacts()` as nested closures. This makes them untestable in isolation and bloats the factory function.

**Target**: Page routes live in a dedicated router (e.g. `app/routes/pages.py`).

**Affected files**: `app/main.py`

**Actions**:
- [x] Create `app/routes/pages.py` with a `pages_router`
- [x] Move `index`, `dashboard`, `files`, `artifacts` into it
- [x] Include `pages_router` in `create_app()`
- [x] Keep `create_app()` focused on wiring: lifespan, static mount, router inclusion

## 8. Consolidate Filename Pattern Regex

**Problem**: The regex `r"^(\d+)_([^_]+)_(.+)\.md$"` is defined independently in both `ArtifactNamer._FILENAME_PATTERN` and `TemplateDetector.FILENAME_PATTERN`. If one changes, the other silently diverges.

**Target**: Single source of truth for the template filename pattern.

**Affected files**: `app/artifact_namer.py`, `app/template_detector.py`

**Actions**:
- [x] Define `TEMPLATE_FILENAME_RE` once in `app/models.py` (or a shared `app/constants.py`)
- [x] Import and use it in both `ArtifactNamer` and `TemplateDetector`

## 9. Make TaskQueue Testable Without Sleep

**Problem**: Tests for `TaskQueue` rely on `await asyncio.sleep(0.1..0.5)` to wait for background tasks. This is flaky and slow.

**Target**: `TaskQueue` exposes an awaitable that resolves when a specific task completes.

**Affected files**: `app/task_queue.py`, `tests/unit/test_task_queue.py`

**Actions**:
- [x] Add `async def wait_for(self, report_id, template_id)` that awaits the internal `asyncio.Task`
- [x] Replace `await asyncio.sleep(0.1)` in tests with `await tq.wait_for("r1", "t1")`

## 10. Reduce `_run_generation` Complexity

**Problem**: `_run_generation` is a 60-line method with 4 sequential SDK calls, state lookups, error handling, and cell updates. Cyclomatic complexity is high.

**Target**: Break into named steps that each do one thing.

**Affected files**: `app/task_queue.py`

**Actions**:
- [x] Extract `_create_and_attach_notebook(cell, report, template) -> str`
- [x] Extract `_submit_and_poll(cell, notebook_id, template) -> str`
- [x] Extract `_download_and_complete(cell, template, nlm_task_id)`
- [x] Keep `_run_generation` as the orchestrator that calls these three steps

## 11. Add Request Validation with Pydantic Body Models

**Problem**: `update_report` and `update_template` accept `body: Dict[str, Any]` and manually check for required keys. This skips FastAPI's automatic validation.

**Target**: Define Pydantic request models and let FastAPI validate.

**Affected files**: `app/routes.py` (or the split route files), `app/models.py`

**Actions**:
- [x] Create `UpdateReportRequest(BaseModel)` with `notebook_name: str`
- [x] Create `UpdateTemplateRequest(BaseModel)` with `content: str`
- [x] Replace `body: Dict[str, Any]` with the typed models in route signatures
- [x] Remove manual `body.get()` + HTTPException(400) checks

## 12. Extract Frontend JS into Modules

**Problem**: `file_browser.html` and `artifacts.html` contain 100+ line inline `<script>` blocks. `grid.js` is a 350-line IIFE. No code sharing between pages (e.g. `escapeHtml`, `formatDate` are duplicated).

**Target**: Shared utility module + per-page modules.

**Affected files**: `static/js/grid.js`, `app/templates/file_browser.html`, `app/templates/artifacts.html`

**Actions**:
- [x] Create `static/js/utils.js` with shared helpers: `escapeHtml`, `formatDate`, `formatSize`, `apiPost`, `apiDelete`
- [x] Create `static/js/file-browser.js` — extract inline script from `file_browser.html`
- [x] Create `static/js/artifacts.js` — extract inline script from `artifacts.html`
- [x] Reduce `grid.js` to dashboard-specific logic, importing from `utils.js`
- [x] Add `<script src="/static/js/utils.js">` to `base.html`

## 13. Remove Unused Pydantic Models

**Problem**: `models.py` defines `ReportModel`, `TemplateModel`, `GenerationCellModel`, `ArtifactModel`, `GridStateModel`, `ArtifactFilterModel` — but none are imported or used anywhere in the application code. They exist only as dead code.

**Target**: Either use them (per Section 5) or remove them. No dead model definitions.

**Affected files**: `app/models.py`

**Actions**:
- [x] If implementing Section 5, keep and use them
- [x] Models kept as data shape documentation and for future Section 5 adoption

## 14. Consistent Error Response Shape

**Problem**: Error responses vary — some use `HTTPException(detail=str)`, some return `{"status": "error", ...}`. No standard error envelope.

**Target**: All errors return `{"detail": "message"}` via HTTPException, matching FastAPI convention.

**Affected files**: `app/routes.py`

**Actions**:
- [x] Audit all error paths for consistent `HTTPException` usage
- [x] Add a global exception handler for `NotebookLMClientError` → 502
- [x] Add a global exception handler for `ValueError` → 400

> **Review note (UX improvements, Section 9):** One accepted exception: `/api/artifacts/remote` returns 200 with `{"artifacts": [], "error": "..."}` instead of raising HTTPException when the NLM API fails. This enables frontend graceful degradation — the artifacts page shows local artifacts and an error banner rather than a full error page. This pattern is intentional and should NOT be "fixed" to use HTTPException.


## 15. Parallel Remote Fetching with Semaphore

**Problem**: `list_remote_artifacts()` in `app/routes/artifacts.py` originally fetched notebook artifacts sequentially — one `await` per notebook. This created an N+1 remote call pattern where listing N notebooks required N+1 HTTP round-trips in series.

**Pattern**: Use `asyncio.gather()` with `asyncio.Semaphore(5)` to fetch artifacts from all notebooks in parallel, bounded to avoid overwhelming the upstream API.

**Affected files**: `app/routes/artifacts.py`

**Actions**:
- [x] Replace sequential `for notebook in notebooks: await fetch(notebook)` with `asyncio.gather(*tasks)`
- [x] Wrap each task in a semaphore acquire to limit concurrency to 5

**Rule**: Any route that fans out to multiple remote API calls MUST use `asyncio.gather()` with a semaphore. Sequential awaits in a loop are not acceptable for remote I/O.

## 16. Targeted Query Methods on StateManager

**Problem**: Routes that needed a single report, template, or artifact were calling `load_state()` which fetches ALL reports, templates, cells, and artifacts from the database. This is wasteful for single-entity lookups.

**Pattern**: Add focused query methods to `StateManager` that fetch exactly what's needed: `get_template()`, `get_report()`, `get_all_reports()`, `get_all_templates()`.

**Affected files**: `app/state_manager.py`, `app/routes/reports.py`, `app/routes/templates.py`, `app/routes/artifacts.py`

**Actions**:
- [x] Add `get_template(template_id)` — single row fetch by ID
- [x] Add `get_report(report_id)` — single row fetch by ID
- [x] Add `get_all_reports()` — fetch all reports without cells/artifacts
- [x] Add `get_all_templates()` — fetch all templates without cells/artifacts
- [x] Update routes to use targeted methods instead of `load_state()`

**Rule**: Routes MUST NOT call `load_state()` when they only need a single entity or a single table's data. Use the targeted query methods instead. `load_state()` is reserved for the grid/dashboard view that genuinely needs the full state.

## 17. Async File I/O via `asyncio.to_thread()`

**Problem**: `delete_artifact_record()` and `delete_notebook_records()` performed synchronous `os.path.exists()` and `os.remove()` calls inside async route handlers. This blocks the event loop during disk I/O.

**Pattern**: Wrap all synchronous file system operations in `asyncio.to_thread()` to offload them to the thread pool.

**Affected files**: `app/state_manager.py`, `app/routes/artifacts.py`, `app/routes/reports.py`, `app/nlm_client.py`

**Actions**:
- [x] Wrap `os.path.exists()` and `os.remove()` in `delete_artifact_record()` with `asyncio.to_thread()`
- [x] Wrap file operations in `delete_notebook_records()` with `asyncio.to_thread()`
- [x] Wrap `os.path.isfile()` in `get_artifact()` and `preview_artifact()` with `asyncio.to_thread()` (fixed in second-pass review, task 12.2)
- [x] Wrap `os.makedirs()` in `nlm_client.download_artifact()` with `asyncio.to_thread()` (fixed in second-pass review, task 12.2)
- [x] Wrap `os.makedirs()` in `reports.add_reports()` with `asyncio.to_thread()` (fixed in second-pass review, task 12.2)

**Rule**: Any synchronous file I/O (read, write, delete, stat, mkdir) inside an `async def` function MUST be wrapped in `asyncio.to_thread()`. Direct `os.*` calls in async handlers are not acceptable.

## 18. Path Traversal Protection for File Serving

**Problem**: `get_artifact()` and `preview_artifact()` served files from disk based on a database-stored file path without validating that the resolved path stayed within the expected `output/` directory. A crafted path could escape the output directory.

**Pattern**: After resolving the file path, validate that it is relative to (contained within) the expected base directory using `pathlib.Path.resolve()` and `pathlib.Path.is_relative_to()`.

**Affected files**: `app/routes/artifacts.py`

**Actions**:
- [x] Add path validation in `get_artifact()` — resolve path and check `is_relative_to(output_dir)`
- [x] Add path validation in `preview_artifact()` — same check
- [x] Return 403 if path escapes the allowed directory
- [x] Migrated from string-based `os.path.realpath()` + `startswith()` to `pathlib.Path.resolve()` + `is_relative_to()` for safer path comparison (fixed in second-pass review, task 12.2)
- [x] Migrated `delete_artifact_record()` and `delete_notebook_records()` in `state_manager.py` from string-based `startswith()` to `pathlib.Path.is_relative_to()` (fixed in final steering review, task 15.2)

**Rule**: Any endpoint or method that validates file paths MUST use `pathlib.Path.resolve()` + `pathlib.Path.is_relative_to()`. Never trust database-stored paths without validation. Prefer `pathlib.Path.is_relative_to()` over string-based `startswith()` checks — the latter can be tricked by paths like `/output-evil/`. This applies to both route handlers AND internal StateManager methods that delete files.

## 19. Remaining Tech Debt (Post UX Improvements)

Items identified during the Section 9 architect review that were deferred:

| Item | Priority | Blocked By | Notes |
|------|----------|------------|-------|
| Section 5: Dict-based state → Pydantic models | Medium | — | Highest-priority deferred item. Targeted query methods (Section 16) reduce urgency. |
| Section 6: Cell serialization consolidation | Low | Section 5 | Partial consolidation via `cell_to_dict()` is sufficient for now. |
| `persist_reports` N+1 within transaction | Low | — | Multiple INSERT/UPDATE statements in a loop, but already within a single transaction. Performance impact is minimal. |
| `delete_notebook_records` per-cell artifact deletion | Low | — | Deletes artifacts one-by-one per cell. Could be optimized with a single DELETE JOIN, but volume is low. |
