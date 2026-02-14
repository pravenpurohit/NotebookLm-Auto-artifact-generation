# Requirements Document

## Introduction

This feature overhauls the NotebookLM Dashboard to provide a complete end-to-end workflow: upload research files, upload and manage prompt templates, select which prompts run against which files, monitor parallel processing in a visual matrix, and download completed artifacts for offline use. It also fixes the NLM client SDK API mismatch that prevents all remote operations from working, and adds robust deduplication, deletion sync, and long-running task handling.

**Parent spec:** `.kiro/specs/notebooklm-dashboard/` — This feature extends the core dashboard spec. All requirements here build on the existing architecture, models, and infrastructure defined in the parent spec. Requirements 1–12 from the parent spec remain in effect; this document adds Requirements 1–11 in the prompt-management domain.

## Glossary

- **Prompt_Upload**: A UI component that lets the user upload `.md` prompt template files via drag/drop or file picker.
- **Prompt_Browser**: The page component that displays uploaded prompt templates, grouped and filterable by artifact type, with inline editing and selection controls.
- **Prompt_Editor**: An inline text editor for modifying a template's prompt content before running generation.
- **Processing_Matrix**: A visual grid where rows represent research files and columns represent selected prompt templates, showing real-time generation status for each cell.
- **Cell**: A single intersection of a report and a template in the Processing_Matrix, representing one generation task.
- **Selection_State**: The set of templates and reports the user has chosen to include in a batch generation run.
- **Offline_Marker**: A visual badge indicating an artifact has been downloaded locally and is available offline.
- **Deduplication_Key**: The combination of (report content_hash, template content_hash) that uniquely identifies a generation task to prevent duplicate processing.
- **NLM_Sub_API**: The `notebooklm-py` SDK pattern where methods are accessed via sub-objects (e.g., `client.notebooks.list()`) rather than directly on the client.

## Requirements

### Requirement 1: NLM Client SDK API Fix

**User Story:** As a developer, I want the NLM client wrapper to correctly call the notebooklm-py SDK sub-API methods so that all remote operations (list notebooks, create notebooks, generate artifacts, delete) actually work.

#### Acceptance Criteria

1. WHEN the wrapper calls `list_notebooks()`, IT SHALL use `client.notebooks.list()` instead of `client.list_notebooks()`.
2. WHEN the wrapper calls `create_notebook()`, IT SHALL use `client.notebooks.create(title=name)` instead of `client.create_notebook(title=name)`.
3. WHEN the wrapper calls `list_notebook_artifacts()`, IT SHALL use `client.artifacts.list(notebook_id=id)` instead of `client.list_artifacts(notebook_id=id)`.
4. WHEN the wrapper calls `delete_artifact()`, IT SHALL use `client.artifacts.delete(notebook_id=id, artifact_id=id)` instead of `client.delete_artifact(...)`.
5. WHEN the wrapper calls `delete_notebook()`, IT SHALL use `client.notebooks.delete(notebook_id=id)` instead of `client.delete_notebook(...)`.
6. WHEN the wrapper adds a source to a notebook, IT SHALL use `client.sources.add_file(notebook_id=id, file_path=path)` instead of `client.add_source(...)`.
7. WHEN the wrapper submits artifact generation, IT SHALL use the appropriate `client.artifacts.generate_*()` method based on artifact type (generate_infographic, generate_audio, generate_video) instead of `client.generate()`.
8. WHEN the wrapper polls generation status, IT SHALL use `client.artifacts.poll_status(notebook_id=id, task_id=id)` instead of `client.get_task_status(task_id=id)`.
9. WHEN the wrapper downloads an artifact, IT SHALL use the appropriate `client.artifacts.download_*()` method based on artifact type instead of `client.download_artifact(...)`.
10. ALL wrapper methods SHALL correctly handle the SDK's return types (`Notebook`, `Artifact`, `GenerationStatus`, `Source`) and extract the appropriate fields (id, title, task_id, status, etc.).

### Requirement 2: Prompt Template Upload

**User Story:** As a user, I want to upload prompt template files through the browser so that I can add my own prompts without needing server filesystem access.

#### Acceptance Criteria

1. WHEN a user navigates to the prompts page, THE Prompt_Upload SHALL display a drag-and-drop zone and a file picker button for uploading `.md` files.
2. WHEN a user uploads one or more `.md` files, THE Dashboard SHALL parse each filename using the template naming pattern `{number}_{Type}_{Name}.md` and classify them by artifact type.
3. IF an uploaded file does not match the naming pattern, THEN THE Dashboard SHALL reject that file with a descriptive error message while still processing valid files.
4. WHEN templates are successfully uploaded, THE Dashboard SHALL persist them to the database and display them in the Prompt_Browser.
5. WHEN a user uploads a template with the same filename as an existing template, THE Dashboard SHALL update the existing template's content rather than creating a duplicate.
6. THE Prompt_Upload SHALL show upload progress and a success/error message for each file.
7. IF a user selects zero files (cancels the file dialog), THEN THE Prompt_Upload SHALL not initiate any upload and SHALL not display an error.
8. IF a user uploads a non-`.md` file, THEN THE Dashboard SHALL reject it with a format validation error.

### Requirement 3: Prompt Template Browsing and Selection

**User Story:** As a user, I want to browse available prompt templates grouped by type and select which ones to run, so that I can control exactly what gets generated.

#### Acceptance Criteria

1. WHEN a user navigates to the prompts page, THE Prompt_Browser SHALL display all uploaded templates grouped by artifact type (Infographic, Audio, Video).
2. THE Prompt_Browser SHALL display each template's number, name, artifact type, and audio format (for Audio templates).
3. THE Prompt_Browser SHALL provide a checkbox next to each template to include or exclude it from the current batch run.
4. WHEN a user toggles a template's selection checkbox, THE Selection_State SHALL update immediately via API without a page reload.
5. THE Prompt_Browser SHALL provide "Select All" and "Deselect All" controls for batch template selection.
6. THE Prompt_Browser SHALL visually distinguish templates that have been user-edited from originals.
7. IF no templates are uploaded, THEN THE Prompt_Browser SHALL display an empty state message prompting the user to upload prompt files.

### Requirement 4: Prompt Content Editing

**User Story:** As a user, I want to edit prompt template content before running generation, so that I can customize prompts for specific research files.

#### Acceptance Criteria

1. WHEN a user clicks on a template in the Prompt_Browser, THE Prompt_Editor SHALL open with the full prompt content in an editable text area.
2. WHEN a user modifies prompt content and saves, THE Dashboard SHALL persist the updated content and mark the template as content_edited.
3. WHEN a user saves edited content, THE Prompt_Editor SHALL display a confirmation message indicating the save succeeded.
4. IF a user attempts to save empty or whitespace-only prompt content, THEN THE Prompt_Editor SHALL reject the save and display a validation error.
5. WHEN a user has unsaved changes and attempts to navigate away, THE Prompt_Editor SHALL warn the user about unsaved changes.

### Requirement 5: Processing Matrix View

**User Story:** As a user, I want to see a visual matrix of research files versus selected prompts showing processing status, so that I can monitor all generation tasks at a glance.

#### Acceptance Criteria

1. THE Processing_Matrix SHALL display research files as rows and selected (non-excluded) prompt templates as columns.
2. THE Processing_Matrix SHALL render each Cell with a color-coded status indicator matching the cell's current status (not_started, pending, in_progress, completed, failed, stopped).
3. WHEN a user hovers over or clicks a Cell, THE Processing_Matrix SHALL display a detail popover showing task ID, start time, elapsed time, and error message (if failed).
4. THE Processing_Matrix SHALL provide per-cell action buttons: start (for not_started/pending), stop (for in_progress), and retry (for failed/stopped).
5. WHEN the Processing_Matrix has more columns than fit in the viewport, IT SHALL enable horizontal scrolling with sticky row headers so report names remain visible.
6. THE Processing_Matrix SHALL display a batch progress summary (e.g., "12/18 complete, 3 in progress, 2 failed, 1 not started").

### Requirement 6: Real-Time Status Updates

**User Story:** As a user, I want to see generation status update in real time as processing happens in parallel, so that I do not need to manually refresh the page.

#### Acceptance Criteria

1. WHEN a generation cell's status changes on the server, THE Dashboard SHALL broadcast the update via WebSocket to all connected clients.
2. WHEN a WebSocket `cell_update` message is received, THE Processing_Matrix SHALL update the corresponding Cell's status indicator and action buttons immediately.
3. WHEN a WebSocket `batch_update` message is received, THE Processing_Matrix SHALL update all affected cells in a single render pass.
4. IF the WebSocket connection is lost, THEN THE Processing_Matrix SHALL display a disconnection indicator and attempt reconnection with exponential backoff.
5. WHEN the WebSocket connection is re-established, THE Processing_Matrix SHALL fetch the full grid state from the server to reconcile any missed updates.

### Requirement 7: Deduplication and Idempotent Processing

**User Story:** As a user, I want the system to detect when I've already processed a research file with a specific prompt, so that I don't waste time and API calls on duplicate generation.

#### Acceptance Criteria

1. WHEN a user starts generation for a report-template pair that already has a completed cell with a matching content hash, THE Dashboard SHALL skip generation and display the cell as "completed" with a message "Already processed — no action needed."
2. THE Dashboard SHALL compute a Deduplication_Key from (report content_hash, template content_hash) to uniquely identify each generation task.
3. WHEN a user re-uploads the same research file, THE Dashboard SHALL detect the duplicate via content_hash and reuse the existing report record and its associated generation cells.
4. WHEN a user edits a template's content, THE Dashboard SHALL compute a new content hash so that re-running with the edited prompt is treated as a new generation task.
5. WHEN a Task_ID already exists for a report-template pair with status "in_progress", THE Dashboard SHALL use the existing Task_ID to poll status instead of submitting a duplicate generation request.
6. WHEN batch generation starts, THE Dashboard SHALL skip all cells that are already "completed" and only enqueue cells with status "not_started", "pending", or "failed".
7. WHEN a completed cell is skipped during batch generation, THE Dashboard SHALL display a count of skipped cells in the batch status message (e.g., "Started 12 tasks, skipped 6 already completed").

### Requirement 8: Long-Running Task Handling

**User Story:** As a user, I want the application to handle long-running generation tasks (up to 1 hour for videos) without losing track of progress or creating duplicates.

#### Acceptance Criteria

1. WHILE a generation task is in progress, THE Dashboard SHALL continue polling at regular intervals (every 5 seconds) and display elapsed time in the cell.
2. WHEN the user refreshes the browser during a long-running task, THE Dashboard SHALL reconnect to the WebSocket and restore the current state from the server, showing all in-progress tasks with their current status.
3. WHEN the application restarts while tasks are in progress, THE Dashboard SHALL detect in-progress cells during startup and resume polling for their Task_IDs.
4. THE Dashboard SHALL set a maximum polling timeout of 2 hours, after which it marks the cell as "failed" with a timeout error message.
5. WHEN a user attempts to start generation for a cell that is already "in_progress", THE Dashboard SHALL display a message indicating generation is already running and show the elapsed time.

### Requirement 9: Deletion Sync

**User Story:** As a user, I want deletions in this application to be reflected in NotebookLM online, so that I don't have orphaned notebooks or artifacts in my Google account.

#### Acceptance Criteria

1. WHEN a user deletes an artifact from the Dashboard, THE Dashboard SHALL also delete the artifact from the remote NotebookLM notebook via the SDK.
2. WHEN a user deletes a notebook from the Dashboard, THE Dashboard SHALL also delete the notebook from the remote NotebookLM account via the SDK.
3. IF the remote deletion fails, THEN THE Dashboard SHALL still delete the local record but display a warning that the remote deletion failed.
4. WHEN a user deletes a report from the Dashboard, THE Dashboard SHALL delete all associated generation cells and offer to delete the corresponding remote notebook.
5. WHEN a user initiates a deletion, THE Dashboard SHALL display a confirmation dialog before proceeding with the destructive action.

### Requirement 10: Artifact Offline Availability

**User Story:** As a user, I want to download completed artifacts to my browser so that I can view them without internet access.

#### Acceptance Criteria

1. WHEN a Cell's status is "completed" and an artifact path exists, THE Processing_Matrix SHALL display a download button on that Cell.
2. WHEN a user clicks the download button, THE Dashboard SHALL serve the artifact file as a downloadable browser attachment.
3. WHEN an artifact has been downloaded, THE Processing_Matrix SHALL display an Offline_Marker badge on that Cell.
4. THE Processing_Matrix SHALL provide a "Download All Completed" button that downloads all completed artifacts as a ZIP archive.
5. WHEN a user clicks a completed Cell, THE Dashboard SHALL render the artifact inline (image for infographics, audio player for audio, video player for video).
6. IF an artifact file is missing from disk when download is requested, THEN THE Dashboard SHALL return a 404 error with a descriptive message.

### Requirement 11: Navigation and Page Integration

**User Story:** As a user, I want the prompt management and processing views to integrate with the existing dashboard navigation, so that I can move between pages seamlessly.

#### Acceptance Criteria

1. THE Dashboard SHALL add a "Prompts" navigation link to the existing navigation bar.
2. WHEN a user clicks the "Prompts" link, THE Dashboard SHALL render the Prompt_Browser page at the `/prompts` URL path.
3. THE Prompt_Browser page SHALL include a "Start Processing" button that navigates to the Processing_Matrix view.
4. THE Processing_Matrix page SHALL be accessible at the `/processing` URL path.
5. THE Dashboard SHALL highlight the active page in the navigation to indicate the user's current location.
