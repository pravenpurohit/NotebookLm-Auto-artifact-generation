# Implementation Plan: NotebookLM Dashboard

## Overview

Incremental implementation of the NotebookLM Dashboard, starting with core data models and pure logic components (template detection, artifact naming), then building up through state management, task queue, API routes, and finally the frontend. Each step builds on the previous and wires into the growing application.

## Tasks

- [x] 1. Set up project structure and dependencies
  - Create directory structure: `app/`, `app/templates/`, `static/css/`, `static/js/`, `data/`, `output/infographics/`, `output/audio/`, `output/video/`, `tests/unit/`, `tests/property/`
  - Create `requirements.txt` with: fastapi, uvicorn, jinja2, python-multipart, aiosqlite, websockets, notebooklm-py>=0.3.2, pydantic, hypothesis, pytest, pytest-asyncio, pytest-mock
  - Create `app/models.py` with all Pydantic models and enums (ArtifactType, AudioFormat, CellStatus, ReportModel, TemplateModel, GenerationCellModel, ArtifactModel, GridStateModel, ArtifactFilterModel)
  - Create `app/__init__.py`
  - _Requirements: 7.3, 10.4_

- [x] 2. Implement Template Detector and Artifact Namer
  - [x] 2.1 Implement `app/template_detector.py`
    - TemplateDetector class with FILENAME_PATTERN, EXCLUDED_FILES, TYPE_MAP, AUDIO_FORMAT_MAP
    - `parse_filename(filename) -> TemplateInfo | None`
    - `detect_type_from_content(content) -> str | None`
    - `load_templates(directory) -> list[TemplateInfo]`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10_

  - [x] 2.2 Implement `app/artifact_namer.py`
    - ArtifactNamer class with EXTENSION_MAP
    - `derive_artifact_name(template_filename) -> str`
    - `derive_notebook_name(report_filename) -> str`
    - `get_artifact_filename(template_filename, artifact_type) -> str`
    - _Requirements: 3.1, 3.3, 5.1, 5.2, 5.3_

  - [x] 2.3 Write unit tests for TemplateDetector (`tests/unit/test_template_detector.py`)
    - Test all 13 active templates parse correctly
    - Test steering prompt exclusion (4.9)
    - Test content-based fallback detection (4.10)
    - _Requirements: 4.1, 4.9, 4.10_

  - [x] 2.4 Write unit tests for ArtifactNamer (`tests/unit/test_artifact_namer.py`)
    - Test specific example: "02_Infographic_One-page Map of a Complex Topic.md" → "One-page Map of a Complex Topic"
    - Test notebook name derivation from report filenames
    - _Requirements: 5.2, 3.1_

  - [x] 2.5 Write property test for template filename parsing round trip (`tests/property/test_prop_template_detector.py`)
    - **Property 4: Template filename parsing round trip**
    - **Validates: Requirements 4.1**

  - [x] 2.6 Write property test for template type classification (`tests/property/test_prop_template_detector.py`)
    - **Property 2: Template type classification from filename**
    - **Validates: Requirements 4.2, 4.3, 4.4**

  - [x] 2.7 Write property test for audio format detection (`tests/property/test_prop_template_detector.py`)
    - **Property 3: Audio format detection from filename**
    - **Validates: Requirements 4.5, 4.6, 4.7, 4.8**

  - [x] 2.8 Write property test for notebook name derivation (`tests/property/test_prop_artifact_namer.py`)
    - **Property 1: Notebook name derivation**
    - **Validates: Requirements 3.1, 3.3**

  - [x] 2.9 Write property test for artifact filename derivation (`tests/property/test_prop_artifact_namer.py`)
    - **Property 5: Artifact filename derivation**
    - **Validates: Requirements 5.1, 5.3**

  - [x] 2.10 Write property test for file format validation (`tests/property/test_prop_file_validation.py`)
    - **Property 6: File format validation**
    - **Validates: Requirements 2.5**

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement State Manager and Database
  - [x] 4.1 Create SQLite schema initialization in `app/state_manager.py`
    - Create tables: reports, templates, generation_cells, artifacts
    - Create indexes for status and task_id lookups
    - Use aiosqlite for async database access
    - _Requirements: 10.4_

  - [x] 4.2 Implement StateManager CRUD operations
    - `get_cell`, `update_cell`, `get_all_cells`, `get_cells_by_status`
    - `persist_reports`, `persist_templates`, `load_state`
    - Ensure every `update_cell` call persists immediately
    - _Requirements: 10.4, 7.1, 7.3_

  - [x] 4.3 Implement WebSocket Manager (`app/ws_manager.py`)
    - Connection tracking, connect/disconnect handlers
    - `broadcast_cell_update` and `broadcast_batch_update`
    - Wire into StateManager so cell updates trigger broadcasts
    - _Requirements: 7.2_

  - [x] 4.4 Write property test for state persistence round trip (`tests/property/test_prop_state.py`)
    - **Property 19: State persistence round trip**
    - **Validates: Requirements 10.4**

  - [x] 4.5 Write property test for grid dimensions (`tests/property/test_prop_cell_status.py`)
    - **Property 11: Grid dimensions**
    - **Validates: Requirements 7.1**

  - [x] 4.6 Write property test for cell status invariant (`tests/property/test_prop_cell_status.py`)
    - **Property 10: Cell status invariant**
    - **Validates: Requirements 7.3**

- [x] 5. Implement NotebookLM Client Wrapper and Task Queue
  - [x] 5.1 Implement `app/nlm_client.py`
    - NotebookLMClientWrapper wrapping notebooklm-py SDK
    - `create_notebook`, `submit_generation`, `poll_status`, `download_artifact`, `list_notebooks`
    - _Requirements: 6.1, 6.2, 6.3, 6.6_

  - [x] 5.2 Implement `app/task_queue.py`
    - Asyncio-based task queue with configurable max_concurrent
    - `enqueue` with duplicate detection (check existing Task_ID + in_progress status)
    - `start_all`, `pause`, `resume`, `stop_all`, `retry_failed`, `stop_task`
    - Generation workflow: create notebook → attach source → submit prompt → poll → download
    - _Requirements: 6.1, 6.2, 6.4, 8.1, 8.2, 8.3, 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 5.3 Write property test for duplicate prevention (`tests/property/test_prop_cell_status.py`)
    - **Property 9: Duplicate prevention**
    - **Validates: Requirements 6.4, 8.4**

  - [x] 5.4 Write property tests for individual cell state transitions (`tests/property/test_prop_cell_status.py`)
    - **Property 12: Start transitions cell status correctly**
    - **Property 13: Stop transitions cell status correctly**
    - **Property 14: Retry transitions cell status with new Task_ID**
    - **Validates: Requirements 8.1, 8.2, 8.3**

  - [x] 5.5 Write property tests for batch operations (`tests/property/test_prop_batch.py`)
    - **Property 15: Start All transitions all eligible cells**
    - **Property 16: Pause/Resume round trip**
    - **Property 17: Stop All transitions all in-progress cells**
    - **Property 18: Retry Failed transitions all failed cells**
    - **Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5**

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement Authentication and Recovery
  - [x] 7.1 Implement `app/auth.py`
    - AuthManager using notebooklm-py browser-based login
    - `login`, `validate_session`, `logout`
    - Session credential storage and validation
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 7.2 Implement crash recovery logic in StateManager
    - `recover_state` method: call `nlm_client.list_notebooks()`, match to local cells by notebook_id
    - Resume polling for in-progress tasks found during recovery
    - Detect untracked notebooks (remote notebooks with no local match)
    - _Requirements: 10.1, 10.2, 10.3, 10.5_

  - [x] 7.3 Write property test for recovery matching (`tests/property/test_prop_state.py`)
    - **Property 20: Recovery matching**
    - **Validates: Requirements 10.2**

  - [x] 7.4 Write property test for untracked notebook detection (`tests/property/test_prop_state.py`)
    - **Property 21: Untracked notebook detection**
    - **Validates: Requirements 10.5**

- [x] 8. Implement REST API Routes
  - [x] 8.1 Create `app/routes.py` with all API endpoints
    - Auth routes: POST /api/auth/login, POST /api/auth/logout, GET /api/auth/status
    - Report routes: GET/POST/DELETE/PATCH /api/reports
    - Template routes: GET/POST/PATCH /api/templates
    - Generation routes: POST/DELETE /api/generate/{report_id}/{template_id}, POST retry
    - Batch routes: POST /api/batch/start, pause, resume, stop, retry-failed
    - Grid route: GET /api/grid
    - Artifact routes: GET /api/artifacts (with filter query params), GET /api/artifacts/{id}, GET /api/artifacts/{id}/preview
    - Recovery route: POST /api/recovery/sync
    - WebSocket endpoint: WS /ws/grid
    - _Requirements: 2.1, 2.3, 2.4, 2.5, 3.2, 4.11, 4.12, 6.1, 8.1, 8.2, 8.3, 8.4, 9.1, 9.2, 9.3, 9.4, 9.5, 11.1, 11.2, 11.3, 11.4, 11.5_

  - [x] 8.2 Create `app/main.py` FastAPI application entry point
    - Wire all components: AuthManager, TemplateDetector, ArtifactNamer, StateManager, TaskQueue, NLMClientWrapper, WebSocketManager
    - Mount static files, configure Jinja2 templates
    - Startup event: initialize DB, load templates, run recovery
    - _Requirements: 1.1, 10.1_

  - [x] 8.3 Write property test for report list operations (`tests/property/test_prop_report_list.py`)
    - **Property 7: Report selection grows active list**
    - **Property 8: Report removal shrinks active list and grid**
    - **Validates: Requirements 2.3, 2.4**

  - [x] 8.4 Write property test for artifact filtering (`tests/property/test_prop_filters.py`)
    - **Property 22: Artifact filtering**
    - **Validates: Requirements 11.2, 11.3, 11.4, 11.5**

- [x] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement Frontend
  - [x] 10.1 Create base HTML template (`app/templates/base.html`)
    - Responsive layout with meta viewport tag
    - Include HTMX library, WebSocket JS, and app CSS/JS
    - Navigation between dashboard, artifact browser, and file browser views
    - _Requirements: 12.1, 12.3, 12.4_

  - [x] 10.2 Create login page (`app/templates/login.html`)
    - Google login button, error message display area, retry capability
    - _Requirements: 1.1, 1.3_

  - [x] 10.3 Create dashboard page with Status Grid (`app/templates/dashboard.html`, `static/js/grid.js`)
    - Status_Grid: matrix layout with reports as rows, templates as columns
    - Cell rendering with color-coded status indicators
    - Cell hover/tap tooltip showing Task_ID, start time, elapsed time, error message
    - Completed cell: download/view link
    - Individual cell controls: start, stop, retry buttons based on current status
    - Batch control bar: Start All, Pause, Resume, Stop All, Retry Failed buttons
    - WebSocket connection for live cell updates
    - Responsive: card layout below 768px viewport width
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 8.1, 8.2, 8.3, 8.4, 9.1, 9.2, 9.3, 9.4, 9.5, 12.2_

  - [x] 10.4 Create file browser page (`app/templates/file_browser.html`)
    - File listing with name, size, last modified date
    - PDF/MD file filtering
    - Multi-select capability
    - Editable notebook name field per selected report
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 3.1, 3.2_

  - [x] 10.5 Create artifact browser page (`app/templates/artifacts.html`)
    - Artifact list with filter controls: source location, source filename, artifact type
    - Inline preview: image for PNG, audio player for MP3, video player for MP4
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

  - [x] 10.6 Create CSS styles (`static/css/styles.css`)
    - Responsive grid layout with breakpoint at 768px
    - Status color coding for cell states
    - Touch-friendly button sizes for mobile
    - _Requirements: 12.1, 12.2, 12.3, 12.4_

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis
- Unit tests validate specific examples and edge cases
- The notebooklm-py SDK handles Google auth complexity — no manual Google Cloud setup needed
- All NotebookLM API interactions are wrapped for easy mocking in tests
