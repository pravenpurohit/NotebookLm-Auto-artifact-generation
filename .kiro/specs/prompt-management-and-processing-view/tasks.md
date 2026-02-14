# Implementation Tasks

## Task 1: Fix NLM Client SDK API Mismatch
- [x] 1.1 Update `create_notebook()` to use `client.notebooks.create(title=name)` and `client.sources.add_file(notebook_id, file_path)` instead of `client.create_notebook()` and `client.add_source()`
- [x] 1.2 Update `submit_generation()` to dispatch to `client.artifacts.generate_infographic()`, `generate_audio()`, or `generate_video()` based on artifact_type, passing `instructions=prompt` and appropriate format params
- [x] 1.3 Update `poll_status()` to use `client.artifacts.poll_status(notebook_id, task_id)` — add `notebook_id` parameter to the wrapper method signature
- [x] 1.4 Update `download_artifact()` to dispatch to `client.artifacts.download_infographic()`, `download_audio()`, or `download_video()` based on artifact_type — add `notebook_id` and `artifact_type` parameters
- [x] 1.5 Update `list_notebooks()` to use `client.notebooks.list()` and extract `Notebook.id`, `Notebook.title`
- [x] 1.6 Update `list_notebook_artifacts()` to use `client.artifacts.list(notebook_id)` and extract `Artifact.id`, `Artifact.title`, `Artifact.artifact_type`, `Artifact.created_at`
- [x] 1.7 Update `delete_artifact()` to use `client.artifacts.delete(notebook_id, artifact_id)`
- [x] 1.8 Update `delete_notebook()` to use `client.notebooks.delete(notebook_id)`
- [x] 1.9 Update all callers of modified wrapper methods (task_queue.py, routes) to pass the new required parameters (notebook_id, artifact_type)
- [x] 1.10 Add startup SDK verification in `_init_client()` — check that client has `notebooks`, `artifacts`, `sources` sub-API attributes, log clear error if missing
- [x] 1.11 Write unit tests for all updated wrapper methods using mocked SDK sub-APIs with `spec=` matching real sub-API classes, using sample testdata files
- [x] 1.12 Write property test for SDK method dispatch by artifact type (Property 1)

## Task 2: Template Exclusion API
- [x] 2.1 Add `update_template_exclusion(template_id, is_excluded)` method to StateManager
- [x] 2.2 Add `PATCH /api/templates/{template_id}/exclude` endpoint to `app/routes/templates.py`
- [x] 2.3 Add `UpdateTemplateExclusionRequest` model to `app/models.py`
- [x] 2.4 Write unit tests for exclusion toggle endpoint
- [x] 2.5 Write property test for template exclusion idempotency (Property 6)

## Task 3: Prompt Browser Page (Frontend)
- [x] 3.1 Create `app/templates/prompts.html` extending `base.html` with upload zone, template list, and editor sections
- [x] 3.2 Create `static/js/prompts.js` with template list rendering grouped by artifact type, selection checkboxes, and Select All/Deselect All controls
- [x] 3.3 Add inline prompt editor with save/cancel, validation for empty content, and unsaved changes warning
- [x] 3.4 Add drag-and-drop upload zone with file picker fallback, progress indicators, and success/error messages
- [x] 3.5 Add "Start Processing" button that navigates to `/processing`

## Task 4: Processing Matrix Page (Frontend)
- [x] 4.1 Create `app/templates/processing.html` extending `base.html` with matrix table, batch controls bar, and progress summary
- [x] 4.2 Create `static/js/processing.js` with matrix rendering (rows=reports, columns=selected templates), color-coded status cells, and per-cell action buttons
- [x] 4.3 Add WebSocket connection for real-time cell updates with reconnection logic and disconnection indicator
- [x] 4.4 Add batch controls (Start All, Pause, Resume, Stop All, Retry Failed) with status banner
- [x] 4.5 Add batch progress summary bar computing counts from cell statuses
- [x] 4.6 Add horizontal scrolling with sticky row headers for wide matrices
- [x] 4.7 Add cell detail popover showing task ID, start time, elapsed time, error message

## Task 5: Deduplication Logic
- [x] 5.1 Add deduplication check in `TaskQueue.enqueue()` — skip generation if completed cell exists with matching content hashes, return "already completed" status
- [x] 5.2 Update `batch/start` endpoint to skip completed cells and return count of skipped vs enqueued (AC 7.7)
- [x] 5.3 Write unit tests for deduplication scenarios (same file+prompt, edited prompt, re-uploaded file)
- [x] 5.4 Write property test for deduplication key determinism (Property 4)
- [x] 5.5 Write property test for batch generation skipping completed cells (Property 5)

## Task 6: Long-Running Task Handling
- [x] 6.1 Add 2-hour maximum polling timeout to `_poll_until_done` in task_queue.py — mark cell as failed with timeout message after limit
- [x] 6.2 Add elapsed time tracking to cell updates broadcast via WebSocket
- [x] 6.3 Ensure crash recovery resumes polling for in-progress cells on application restart
- [x] 6.4 Write unit test for polling timeout behavior

## Task 7: Artifact Offline Download
- [x] 7.1 Add `GET /api/artifacts/download-all` endpoint that streams a ZIP of all completed artifacts using `zipfile` + `StreamingResponse`
- [x] 7.2 Add download button rendering in processing.js for completed cells
- [x] 7.3 Add localStorage-based offline marker tracking in processing.js
- [x] 7.4 Add inline artifact preview (image/audio/video) on cell click
- [x] 7.5 Write unit test for ZIP download endpoint (valid ZIP, correct files, 404 for missing)
- [x] 7.6 Write property test for batch progress summary accuracy (Property 3)

## Task 8: Navigation and Page Routes
- [x] 8.1 Add `GET /prompts` and `GET /processing` page routes to `app/routes/pages.py`
- [x] 8.2 Update `app/templates/base.html` to add "Prompts" and "Processing" nav links with active page highlighting
- [x] 8.3 Write unit tests for new page routes returning 200

## Task 9: Template Upload Enhancement
- [x] 9.1 Update `POST /api/templates` endpoint to handle duplicate filename uploads by updating existing template content instead of creating duplicates
- [x] 9.2 Add validation to reject non-`.md` files with format error (AC 2.8)
- [x] 9.3 Handle zero-file upload gracefully as no-op (AC 2.7)
- [x] 9.4 Write unit tests for upload with sample testdata files (02_Infographic, 07_Audio_DeepDive, 11_Video)
- [x] 9.5 Write property test for template upload deduplication (Property 2)

## Task 10: Steering File Enhancements
- [x] 10.1 Update `ba-product-owner-review.md` — add "End-to-End Workflow Validation" section requiring every user journey to be walkable start-to-finish, and "Entity Management UI Audit" requiring every data entity to have a management page
- [x] 10.2 Update `code-review-standards.md` — add "SDK API Verification" section requiring runtime verification of third-party SDK method signatures before first use, and "API Mismatch Detection" checklist
- [x] 10.3 Update `ui-ux-standards.md` — add "Feature Completeness" section requiring every data entity (reports, templates, artifacts) to have browse/create/edit/delete UI, not just API endpoints
- [x] 10.4 Update `testing-standards.md` — add "End-to-End Smoke Tests" section requiring at least one test per user journey that exercises the full stack, and "SDK Integration Verification" requiring tests that verify SDK method existence
- [x] 10.5 Update `architecture-guidelines.md` — add "Third-Party SDK Integration" section with rules for verifying SDK APIs match wrapper assumptions, including startup-time validation
