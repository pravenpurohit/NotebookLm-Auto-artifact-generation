---
inclusion: manual
---

# Technical Leader Review

Architecture and engineering quality review for the NotebookLM Dashboard. Evaluates the system from a scalability, maintainability, reliability, and technical debt perspective.

## Architecture Overview

```
FastAPI (async) + Jinja2 templates + vanilla JS frontend
├── app/
│   ├── main.py              — App factory, lifespan, component wiring
│   ├── routes/              — 10 domain-specific routers (auth, reports, templates, generation, batch, grid, artifacts, recovery, pages, ws)
│   ├── dependencies.py      — FastAPI dependency injection helpers
│   ├── state_manager.py     — SQLite persistence via aiosqlite (single connection pool)
│   ├── task_queue.py        — Async generation orchestrator with concurrency control
│   ├── nlm_client.py        — SDK wrapper (notebooklm-py sub-API pattern)
│   ├── ws_manager.py        — WebSocket connection manager + cell broadcast
│   ├── template_detector.py — Filename-based template classification
│   ├── artifact_namer.py    — Template-to-artifact name derivation
│   ├── models.py            — Pydantic models, enums, shared regex
│   ├── validators.py        — Input validation helpers
│   └── auth.py              — Google auth session management
├── static/js/               — Per-page JS modules + shared utils
├── data/                    — SQLite database + uploaded files
└── output/                  — Generated artifacts (infographics/, audio/, video/)
```

## Architecture Strengths

### Clean Separation of Concerns
- Routes are split into 10 domain-specific modules (was a single 400-line monolith)
- All DB access goes through `StateManager` — no raw SQL in routes
- SDK interactions isolated behind `NotebookLMClientWrapper`
- WebSocket management decoupled via `CellBroadcaster` protocol

### Async-First Design
- All I/O operations are async (aiosqlite, async SDK calls)
- File I/O wrapped in `asyncio.to_thread()` to avoid blocking the event loop
- WebSocket broadcasts are non-blocking with dead connection cleanup
- Task queue uses `asyncio.Semaphore` for concurrency control

### Resilience Patterns
- Crash recovery on startup: detects in-progress cells and resumes polling
- 2-hour polling timeout prevents infinite loops
- Graceful degradation: remote API failures don't break local functionality
- Path traversal protection on all file-serving endpoints

### Testing Infrastructure
- 316 tests (unit + property-based) all passing
- 6 correctness properties validated via Hypothesis PBT
- Isolated temp databases per test — no cross-contamination
- SDK mocks use AsyncMock matching real async signatures

## Architecture Concerns

### SQLite Scalability

The application uses a single SQLite database with WAL mode. This works well for single-user scenarios but has limitations:

- [ ] **Single-writer constraint** — SQLite allows only one writer at a time. Concurrent batch operations from multiple browser tabs could cause `SQLITE_BUSY` errors. The connection pool (`_get_db`/`_release_db`) mitigates this but doesn't eliminate it.
- [ ] **No connection pooling library** — The custom `_get_db`/`_release_db` pattern is a manual semaphore-based pool. Consider `aiosqlite` with a proper pool or migrate to PostgreSQL for multi-user scenarios.
- [ ] **Large state queries** — `load_state()` fetches ALL reports, templates, and cells in one call. This is fine for <1000 records but will degrade with scale. The targeted query methods (Section 16) reduce this for most routes, but the grid endpoint still loads everything.

### Module-Level State Mutation in Tests

- [ ] **`DB_PATH` patching** — Tests mutate `app.main.DB_PATH` at module level to use temp databases. This is fragile and was the root cause of the ZIP download test failure (DB_PATH restored before lifespan ran). Consider making `DB_PATH` a parameter to `create_app()` or using environment variables consistently.
- [ ] **`_OUTPUT_BASE` patching** — Similar pattern in artifact tests. The output base directory is a module-level constant that tests patch. Consider making it configurable via app state.

### Dict-Based Data Flow (Tech Debt)

- [ ] **Pydantic models defined but unused** — `ReportModel`, `TemplateModel`, `GenerationCellModel` exist in `models.py` but are not used as the canonical data transfer objects. Routes and StateManager pass raw dicts. This makes refactoring risky and prevents FastAPI's automatic response serialization.
- [ ] **Duplicate cell representation** — `GenerationCell` dataclass in `state_manager.py` duplicates `GenerationCellModel` in `models.py`. One should be the source of truth.
- [ ] **Manual dict construction** — Routes build response dicts by hand instead of using Pydantic `.model_dump()`. This is error-prone and inconsistent.

### Frontend Architecture

- [ ] **No build system** — Vanilla JS with `<script>` tags. No bundling, no tree-shaking, no TypeScript. This is intentional for simplicity and Android WebView compatibility, but limits code sharing and type safety.
- [ ] **No component framework** — Each page has its own JS module with manual DOM manipulation. Shared patterns (modals, toasts, tables) are implemented via utility functions in `utils.js`, which works but doesn't scale well.
- [ ] **HTMX dependency** — `base.html` loads HTMX but it's only used for the logout button. Consider removing it or using it more broadly.
- [ ] **No client-side routing** — Full page reloads between `/prompts` and `/processing`. The WebSocket reconnection handles this gracefully, but it's not ideal for perceived performance.

### SDK Dependency Risk

- [ ] **Unofficial SDK** — `notebooklm-py` is an unofficial Python SDK for Google NotebookLM. It could break at any time if Google changes their API. The wrapper pattern isolates this risk, but there's no automated compatibility check.
- [ ] **No SDK version lock** — `requirements.txt` specifies `notebooklm-py>=0.3.2` (minimum version). A new release could introduce breaking changes. Pin to an exact version.
- [ ] **No startup health check** — The design calls for verifying SDK sub-API attributes at startup, but this is listed as a TODO in the architecture guidelines. Implement it.

## Component Quality Assessment

| Component | Quality | Notes |
|-----------|---------|-------|
| `state_manager.py` | Good | Clean async interface, proper connection management, targeted queries |
| `nlm_client.py` | Good | Sub-API pattern correctly implemented, comprehensive error handling |
| `task_queue.py` | Good | Concurrency control, dedup, timeout, crash recovery |
| `ws_manager.py` | Good | Protocol-based typing, dead connection cleanup |
| `routes/` | Good | Domain-split, Pydantic request validation, consistent error shapes |
| `template_detector.py` | Good | Shared regex, content-based fallback classification |
| `models.py` | Mixed | Well-defined but underutilized — most code passes raw dicts |
| `dependencies.py` | Good | Clean DI pattern, separate HTTP/WS helpers |
| Frontend JS | Adequate | Functional but manual DOM manipulation, no type safety |
| Test suite | Strong | 316 tests, 6 PBT properties, good isolation |

## Security Assessment

| Area | Status | Notes |
|------|--------|-------|
| Path traversal | ✅ Protected | `pathlib.Path.resolve()` + `is_relative_to()` on all file operations |
| SQL injection | ✅ Protected | Parameterized queries throughout StateManager |
| XSS | ✅ Protected | `escapeHtml()` utility, `textContent` for user data |
| File upload validation | ✅ Protected | Type checking (PDF/MD), size limits, filename sanitization |
| Auth | ⚠️ Basic | Google session cookies, no CSRF token on API routes, no rate limiting |
| CORS | ⚠️ Not configured | No CORS middleware — fine for same-origin but blocks external API consumers |
| Secrets | ✅ Clean | No hardcoded credentials, session-based auth |

## Reliability Assessment

| Scenario | Handling | Notes |
|----------|----------|-------|
| App crash during generation | ✅ Recovery | Startup detects in-progress cells, resumes polling |
| Browser refresh during processing | ✅ Handled | WebSocket reconnects, fetches full grid state |
| SDK API failure | ✅ Graceful | Local operations continue, error banner shown |
| Database corruption | ⚠️ Partial | WAL mode helps, but no backup/restore mechanism |
| Concurrent browser tabs | ⚠️ Limited | WebSocket broadcasts to all, but SQLite single-writer may conflict |
| Network disconnection | ✅ Handled | WebSocket reconnection with exponential backoff |

## Technical Debt Summary

| Item | Priority | Effort | Impact |
|------|----------|--------|--------|
| Dict → Pydantic model adoption | Medium | High | Safer refactoring, auto-serialization |
| Pin SDK version exactly | High | Low | Prevent silent breaking changes |
| SDK startup health check | High | Low | Fail fast on incompatible SDK |
| Make DB_PATH configurable via create_app() | Medium | Low | Eliminate test fragility |
| Remove unused HTMX dependency | Low | Low | Reduce page load size |
| Add CSRF protection on mutation endpoints | Medium | Medium | Security hardening |
| Add database backup/restore | Low | Medium | Data safety |

## Recommendations

### Immediate (This Sprint)

1. Pin `notebooklm-py` to exact version in `requirements.txt`
2. Implement SDK startup health check (verify sub-API attributes exist)
3. Make `DB_PATH` a parameter to `create_app()` instead of module-level global

### Next Sprint

1. Add CSRF token validation on all POST/PATCH/DELETE endpoints
2. Start migrating routes to use Pydantic response models (begin with `/api/grid`)
3. Remove HTMX or adopt it for more interactions

### Future

1. Evaluate PostgreSQL migration for multi-user support
2. Consider TypeScript for frontend if complexity grows
3. Add structured logging (JSON format) for production observability
4. Add health check endpoint (`/health`) for monitoring
