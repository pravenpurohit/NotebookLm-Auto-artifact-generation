# Requirements Document

## Introduction

A complete UX overhaul of the NotebookLM Dashboard application. The current app has a confusing multi-page layout with duplicated views (Dashboard and Processing show the same grid), no guided onboarding, no built-in prompts, and poor discoverability. This redesign replaces the disjointed page-based navigation with a guided wizard-style flow: **Login → Upload Reports → Configure Prompts → Generate Artifacts → Download Results**. The existing backend architecture (FastAPI, SQLite via aiosqlite, WebSocket, notebooklm-py SDK) is preserved and extended. All frontend templates, static CSS/JS, and page routes are rebuilt from scratch.

## Glossary

- **App**: The NotebookLM Dashboard FastAPI application
- **Wizard**: The four-step guided flow that is the primary user experience after login
- **Wizard_Step**: One discrete phase: Step 1 (Upload), Step 2 (Configure), Step 3 (Generate), Step 4 (Download)
- **Stepper**: The visual progress bar showing all four Wizard_Steps with completed/current/locked indicators
- **Report**: A user-uploaded PDF or Markdown research document stored in `data/uploads/`
- **Template**: A Markdown prompt file defining how NotebookLM generates a specific artifact type
- **Default_Template**: A built-in Template shipped in `.kiro/default files/NotebookLm Prompts to Learn stuff/` (13 files)
- **Generation_Cell**: A single (report_id, template_id) pair representing one artifact generation job in the database
- **Artifact**: An output file (infographic PNG, audio MP3/WAV, video MP4) produced by NotebookLM
- **Status_Grid**: The matrix table with reports as rows and non-excluded templates as columns, each cell showing Generation_Cell status
- **Cell_Status**: One of: `not_started`, `pending`, `in_progress`, `completed`, `failed`, `stopped`
- **Batch_Controls**: Toolbar with Start All, Stop All, Retry Failed buttons and a live progress summary
- **NLM_Sync**: Background two-way synchronization between the local SQLite database and the user's remote NotebookLM account
- **Session**: The authenticated state backed by Google credentials stored in the notebooklm-py SDK's `SessionCredentials`
- **Empty_State**: A placeholder UI component shown when a section has no data, with guidance text and a call-to-action button
- **Settings_Page**: A dedicated page for advanced operations outside the wizard flow
- **Card_Layout**: The mobile-friendly alternative to Status_Grid, showing one report card at a time with template statuses stacked vertically
- **Context_Menu**: A popover menu appearing on cell click with cell-specific actions (start, stop, retry, view artifact)
- **Sync_Indicator**: A non-blocking banner or badge showing NLM_Sync progress
- **Reconnection_Indicator**: A banner shown when the WebSocket connection drops, with auto-reconnect status

## Requirements

### Requirement 1: Guided Wizard Flow

**User Story:** As a new user, I want a step-by-step guided flow so that I understand what to do without prior knowledge of the app.

#### Acceptance Criteria

1. WHEN an authenticated user navigates to `/dashboard`, THE App SHALL render the Wizard with the Stepper showing all four Wizard_Steps and auto-select the earliest incomplete step
2. WHEN the user is on Step 1 (Upload) and no Reports exist in the database, THE Wizard SHALL display an Empty_State with an upload area accepting `.pdf` and `.md` files via drag-and-drop or file picker
3. WHEN the user uploads at least one Report successfully in Step 1, THE Wizard SHALL mark Step 1 as complete in the Stepper and enable the "Next" button to proceed to Step 2
4. WHEN the user is on Step 2 (Configure), THE Wizard SHALL display all Templates grouped under three collapsible sections (Infographic, Audio, Video) with a checkbox toggle per Template to include or exclude it
5. WHEN the user has at least one Template not excluded and clicks "Next" on Step 2, THE Wizard SHALL mark Step 2 as complete in the Stepper and navigate to Step 3 (Generate)
6. WHEN the user is on Step 3 (Generate), THE Wizard SHALL display the Status_Grid for all Reports × non-excluded Templates, plus the Batch_Controls toolbar above the grid
7. WHEN all Generation_Cells in the Status_Grid reach a terminal Cell_Status (completed, failed, or stopped), THE Wizard SHALL mark Step 3 as complete and enable navigation to Step 4
8. WHEN the user is on Step 4 (Download), THE Wizard SHALL display all generated Artifacts grouped by Report, with a download button per Artifact and a "Download All" button that triggers a ZIP download
9. THE Stepper SHALL render each Wizard_Step as a clickable element showing: step number, step label, and a status icon (checkmark for complete, circle-dot for current, lock for locked)
10. WHEN the user clicks a completed or current Wizard_Step in the Stepper, THE Wizard SHALL navigate to that step; WHEN the user clicks a locked step, THE Wizard SHALL show a tooltip explaining the prerequisite

### Requirement 2: Built-in Default Templates

**User Story:** As a new user, I want the app to ship with useful prompt templates so that I can generate artifacts immediately without uploading prompt files.

#### Acceptance Criteria

1. WHEN the App starts and the templates table in the database is empty, THE App SHALL load all 13 Default_Templates from `.kiro/default files/NotebookLm Prompts to Learn stuff/`
2. WHEN loading Default_Templates, THE App SHALL parse each filename using the regex pattern `^(\d+)_([^_]+)_(.+)\.md$` to extract the template number, artifact type, and display name
3. WHEN Default_Templates are loaded, THE App SHALL store a boolean `is_default` flag set to `true` for each, so the UI can display a "Built-in" badge and prevent deletion of defaults
4. WHEN a user uploads a Template with the same filename as a Default_Template, THE App SHALL keep both but mark the user-uploaded version as the active one (is_excluded=false on user version, is_excluded=true on default)
5. THE App SHALL load exactly 13 Default_Templates: 5 Infographic (numbers 02-06), 4 Audio (numbers 07-09 with two 07s), and 4 Video (numbers 10-13)

### Requirement 3: Unified Generation View

**User Story:** As a user, I want a single view for monitoring and controlling artifact generation so that I do not switch between duplicate pages.

#### Acceptance Criteria

1. THE App SHALL serve a single `/dashboard` route that contains both the status overview and per-cell generation controls, replacing the old separate `/dashboard` and `/processing` routes
2. WHEN a user clicks a Generation_Cell in the Status_Grid, THE App SHALL display a Context_Menu with actions: "Start" (if not_started or failed), "Stop" (if pending or in_progress), "Retry" (if failed or stopped), "View Artifact" (if completed)
3. WHEN a Generation_Cell status changes via WebSocket, THE Status_Grid SHALL update only that cell's visual state (color and icon) without re-rendering the entire grid
4. THE Status_Grid SHALL display full report filenames (without path) as row headers and full template display names as column headers, using horizontal scroll on overflow rather than truncation
5. WHEN the viewport width is below 768px, THE Status_Grid SHALL be replaced by the Card_Layout showing one collapsible card per Report with template statuses listed vertically inside
6. THE Batch_Controls SHALL include: "Start All" button, "Stop All" button, "Retry Failed" button, and a progress summary text showing `"{completed}/{total} done, {failed} failed"` updated in real-time

### Requirement 4: Two-Way NLM Sync at Startup

**User Story:** As a returning user, I want the app to sync with my NotebookLM account at startup so that I see current notebook and artifact data.

#### Acceptance Criteria

1. WHEN an authenticated user loads `/dashboard`, THE App SHALL trigger NLM_Sync as a background task within 2 seconds of page load
2. WHEN NLM_Sync runs, THE App SHALL call the notebooklm-py SDK to list all notebooks in the user's account and match them to local Report records by content hash
3. WHEN NLM_Sync finds remote artifacts (audio, video, infographic sources) not present in the local artifacts table, THE App SHALL insert new Artifact records linked to the matching Report and Template
4. WHEN NLM_Sync finds local Generation_Cells with status `in_progress` whose corresponding remote notebook shows a completed artifact, THE App SHALL update the cell status to `completed` and set the artifact_path
5. WHILE NLM_Sync is running, THE App SHALL display a Sync_Indicator in the Stepper area showing "Syncing with NotebookLM..." with a spinner animation
6. IF NLM_Sync fails because the Session has expired (HTTP 401 or SDK auth error), THEN THE App SHALL display a re-authentication banner with a "Re-authenticate" button that opens the in-app reauth flow without navigating away from the current Wizard_Step

### Requirement 5: Navigation Redesign

**User Story:** As a user, I want navigation that reflects the wizard flow so that I always know where I am and what to do next.

#### Acceptance Criteria

1. THE App SHALL replace the old nav bar (Dashboard | File Browser | Prompts | Processing | Artifacts) with a new nav bar containing: the Stepper (showing the four Wizard_Steps), a Settings icon-link, and a Logout button
2. WHEN a Wizard_Step is locked (prerequisites not met), THE Navigation SHALL render that step with reduced opacity (0.5) and a lock icon, and clicking it SHALL show a tooltip with the prerequisite message
3. WHEN the user is on a Wizard_Step, THE Navigation SHALL highlight that step with an accent color underline and bold label
4. THE Logout button SHALL be visible on every page including the Settings_Page and SHALL POST to `/api/auth/logout` then redirect to `/`
5. THE Settings icon-link SHALL navigate to `/settings` and be accessible from every Wizard_Step

### Requirement 6: Empty States and Onboarding

**User Story:** As a new user, I want helpful empty states so that I know what action to take when a section has no data.

#### Acceptance Criteria

1. WHEN the Report list is empty on Step 1, THE Empty_State SHALL display a file-upload illustration (SVG), the text "No reports yet — upload your first research document to get started", and a prominent "Upload Files" button that opens the file picker
2. WHEN the Template list is empty on Step 2 and Default_Templates failed to load, THE Empty_State SHALL display the text "No prompt templates available" and two buttons: "Load Defaults" (triggers default template loading) and "Upload Custom" (opens file picker)
3. WHEN the Artifact list is empty on Step 4, THE Empty_State SHALL display the text "No artifacts generated yet" and a button "Go to Generate" that navigates to Step 3
4. WHEN the Status_Grid has zero rows (no Reports) or zero columns (all Templates excluded), THE Empty_State SHALL display a message identifying the missing prerequisite and a button linking to the relevant Wizard_Step (Step 1 for reports, Step 2 for templates)

### Requirement 7: Edge Case Handling

**User Story:** As a user, I want the app to handle mistakes, reloads, and session issues gracefully so that I do not lose progress or get stuck.

#### Acceptance Criteria

1. WHEN the user reloads the browser on any Wizard_Step, THE App SHALL determine the current step from database state (reports exist → step 1 done, non-excluded templates exist → step 2 done, etc.) and render the appropriate step
2. WHEN the Session expires during an active generation (WebSocket receives auth error or API returns 401), THE App SHALL pause the task queue, display a modal re-authentication prompt, and resume queued tasks after successful re-authentication
3. WHEN the user navigates directly to a URL for a locked Wizard_Step (e.g., `/dashboard?step=3` with no reports), THE App SHALL redirect to the earliest incomplete step and display a toast notification explaining why
4. WHEN a file upload fails due to network error, invalid format, or exceeding the 50MB size limit, THE App SHALL display an inline error message below the upload area specifying the failure reason, and preserve the file selection for retry
5. THE App SHALL enforce a 50MB maximum file size limit on the server side (FastAPI route), rejecting uploads that exceed the limit with HTTP 413 and a descriptive error message before writing to disk
6. WHEN a user uploads a non-`.md` file as a template in Step 2 or Settings, THE App SHALL reject the file with a format validation error specifying that only `.md` files are accepted
7. WHEN a user navigates to a removed legacy URL (`/files`, `/prompts`, `/processing`, `/artifacts`), THE App SHALL redirect (HTTP 301) to the appropriate Wizard_Step on `/dashboard` or to `/settings`
8. IF a Generation_Cell fails, THEN THE App SHALL display the error_message in the cell's tooltip on hover and show a retry icon button within the cell
9. WHEN the user clicks "Clear All Data" in Settings, THE App SHALL display a confirmation dialog listing: number of reports, templates, cells, and artifacts to be deleted, with "Cancel" and "Confirm Delete" buttons
10. WHEN the WebSocket connection drops, THE App SHALL display the Reconnection_Indicator banner ("Connection lost — reconnecting...") and attempt reconnection with exponential backoff (1s, 2s, 4s, 8s, max 30s), removing the banner on successful reconnect

### Requirement 8: Responsive Design

**User Story:** As a user, I want the app to work well on different screen sizes so that I can use it on a tablet or phone.

#### Acceptance Criteria

1. WHEN the viewport width is below 768px, THE App SHALL switch to a single-column layout with the Stepper rendered vertically on the left side of the header
2. WHEN the viewport width is below 768px, THE Status_Grid SHALL switch to the Card_Layout as specified in Requirement 3.5
3. THE Stepper SHALL render horizontally on viewports 768px and above, and vertically (collapsed into a dropdown or sidebar) on viewports below 768px
4. WHEN the viewport width is below 768px, THE Navigation SHALL collapse the Stepper into a hamburger menu toggle that reveals the step list as a vertical dropdown
5. THE App SHALL ensure all interactive elements (buttons, links, checkboxes, cells) have a minimum touch target size of 44×44 CSS pixels on all viewport sizes

### Requirement 9: Accessibility

**User Story:** As a user with assistive technology, I want the app to be navigable and operable so that I can use all features.

#### Acceptance Criteria

1. THE App SHALL ensure all interactive elements are reachable via keyboard (Tab/Shift+Tab for navigation, Enter/Space for activation, Escape for dismissing modals and menus)
2. THE App SHALL render visible focus indicators (2px solid outline with 3:1 contrast ratio against adjacent colors) on all focusable elements
3. THE App SHALL use ARIA landmarks: `role="banner"` on the header, `role="navigation"` on the nav/stepper, `role="main"` on the wizard content area, `role="complementary"` on the settings sidebar if present
4. WHEN a Generation_Cell status changes via WebSocket, THE App SHALL announce the change via an `aria-live="polite"` region with text like "Report X, Template Y: status changed to completed"
5. THE App SHALL ensure all text has a minimum contrast ratio of 4.5:1 (normal text) and 3:1 (large text, 18px+ or 14px+ bold) against its background
6. THE App SHALL provide visible text labels or `aria-label` attributes on all icon-only buttons (hamburger menu, settings gear, cell action icons, close buttons)
7. WHEN a modal dialog (confirmation, re-auth prompt) is displayed, THE App SHALL trap keyboard focus within the dialog until dismissed, and return focus to the triggering element on close

### Requirement 10: Authentication and Session Management

**User Story:** As a user, I want reliable Google authentication that handles session expiry gracefully so that I can use the app without terminal access or manual cookie management.

#### Acceptance Criteria

1. WHEN the App starts with no stored credentials, THE Login page SHALL display a "Sign in with Google" button that loads cookies from the notebooklm-py SDK's browser storage state (`~/.notebooklm/storage_state.json`) and fetches CSRF token and session ID
2. WHEN the stored browser cookies are valid, THE App SHALL construct a `SessionCredentials` instance (cookies, csrf_token, session_id) and redirect to `/dashboard`
3. IF no browser storage state exists or cookies are expired, THEN THE Login page SHALL display a "Re-authenticate with Google" button that launches a non-headless Playwright Chromium browser navigated to `https://notebooklm.google.com/`
4. WHEN the Playwright browser is launched for re-authentication, THE App SHALL run the synchronous Playwright operations in a background thread using `threading.Thread` and communicate status via `queue.Queue` (not `asyncio.Queue`) to avoid blocking the FastAPI async event loop
5. WHILE the Playwright browser is open, THE App SHALL poll the browser page URL at 1-second intervals using the `is_login_complete()` function to detect when the user has finished Google login (URL is `notebooklm.google.com` without `/login` or `/signin` paths)
6. WHEN login completion is detected, THE App SHALL save the Playwright browser storage state, extract cookies, call `fetch_tokens()` to obtain CSRF token and session ID, and update the shared `SessionCredentials` instance
7. WHEN credentials are updated after re-authentication, THE App SHALL call `nlm_client.reinit_client()` to re-initialize the SDK client with the new credentials so all subsequent API calls use the fresh session
8. THE App SHALL stream re-authentication status to the frontend via Server-Sent Events (SSE) with phases: `browser_launched`, `waiting_for_login`, `login_detected`, `authenticated`, `error`, `timeout`, `cancelled`
9. IF the user does not complete login within 120 seconds, THEN THE App SHALL close the Playwright browser, clean up the reauth session, and emit a `timeout` error via SSE
10. IF the Playwright browser is closed by the user before login completes, THEN THE App SHALL detect the closure (via exception when reading `page.url`), clean up the session, and emit a `cancelled` error via SSE
11. THE App SHALL prevent concurrent re-authentication sessions by rejecting new reauth requests with HTTP 409 while one is active, using a `threading.Lock` to guard the session state
12. IF Playwright is not installed or Chromium is not available, THEN THE App SHALL return HTTP 503 with a message suggesting `playwright install chromium`
13. WHEN the App shuts down (lifespan shutdown), THE App SHALL call `cleanup_reauth()` to cancel any active reauth session and join the background thread, preventing orphaned Chromium processes
14. THE App SHALL sanitize all error messages before sending to the frontend, stripping Python tracebacks, `File "..."` references, internal module paths, and raw exception class names while preserving actionable information
15. WHEN the user clicks Logout, THE App SHALL clear all fields on the `SessionCredentials` instance (cookies, csrf_token, session_id, token, user_email) and redirect to the login page
16. THE App SHALL use the `sse-starlette` library (pinned in `requirements.txt`) for Server-Sent Events streaming in the reauth flow

### Requirement 11: NLM Client SDK Sub-API Compatibility

**User Story:** As a developer, I want the NLM client wrapper to correctly call the notebooklm-py SDK sub-API methods so that all remote operations work.

#### Acceptance Criteria

1. WHEN the wrapper calls notebook operations, IT SHALL use the sub-API pattern: `client.notebooks.list()`, `client.notebooks.create(title=name)`, `client.notebooks.delete(notebook_id=id)`
2. WHEN the wrapper calls artifact operations, IT SHALL use: `client.artifacts.list(notebook_id=id)`, `client.artifacts.delete(notebook_id=id, artifact_id=id)`, and the type-specific `client.artifacts.generate_infographic()`, `client.artifacts.generate_audio()`, `client.artifacts.generate_video()` methods
3. WHEN the wrapper adds a source to a notebook, IT SHALL use `client.sources.add_file(notebook_id=id, file_path=path)`
4. WHEN the wrapper polls generation status, IT SHALL use `client.artifacts.poll_status(notebook_id=id, task_id=id)`
5. WHEN the wrapper downloads an artifact, IT SHALL use the type-specific `client.artifacts.download_infographic()`, `client.artifacts.download_audio()`, `client.artifacts.download_video()` methods
6. ALL wrapper methods SHALL correctly handle the SDK's return types (`Notebook`, `Artifact`, `GenerationStatus`, `Source`) and extract the appropriate fields
7. WHEN initializing the SDK client, THE wrapper SHALL verify that the `notebooks`, `artifacts`, and `sources` sub-API attributes exist on the client object, and log an error and set client to None if any are missing

### Requirement 12: Deduplication and Idempotent Processing

### Requirement 12: Deduplication and Idempotent Processing

**User Story:** As a user, I want the system to detect duplicate uploads and duplicate generation requests so that I do not waste time and API calls.

#### Acceptance Criteria

1. WHEN a Report is uploaded, THE App SHALL compute a SHA-256 content hash of the file and store it in the report record
2. WHEN a Report with the same content hash already exists in the database, THE App SHALL warn the user and offer to reuse the existing report or create a new one
3. WHEN generation is requested for a (Report, Template) pair that already has a completed Generation_Cell with a matching prompt content hash, THE App SHALL skip generation and display the cell as "completed" with a "Already processed" indicator
4. WHEN a Template's content is edited, THE App SHALL recompute the prompt content hash so that re-running with the edited prompt is treated as a new generation task
5. WHEN batch generation starts, THE App SHALL skip all cells with status "completed" and only enqueue cells with status "not_started", "pending", or "failed", displaying a count of skipped cells

### Requirement 13: Deletion Sync with NotebookLM

**User Story:** As a user, I want deletions in this app to be reflected in my NotebookLM account so that I do not have orphaned notebooks or artifacts.

#### Acceptance Criteria

1. WHEN a user deletes an artifact from the App, THE App SHALL also delete the artifact from the remote NotebookLM notebook via the SDK
2. WHEN a user deletes a report from the App, THE App SHALL delete all associated Generation_Cells and offer to delete the corresponding remote notebook
3. IF a remote deletion fails, THEN THE App SHALL still delete the local record but display a warning that the remote deletion failed
4. WHEN a user initiates any deletion, THE App SHALL display a confirmation dialog before proceeding

### Requirement 14: Template Detection and Artifact Naming

**User Story:** As a user, I want templates to be automatically classified by type and artifacts to be named meaningfully so that I can identify everything without manual configuration.

#### Acceptance Criteria

1. WHEN loading templates, THE App SHALL parse each filename using the regex `^(\d+)_([^_]+)_(.+)\.md$` to extract number, type, and name
2. WHEN a template filename type portion matches "Infographic", "Audio", or "Video", THE App SHALL classify the template accordingly
3. WHEN a template filename contains "DeepDive", "TheBrief", "Critique", or "Debate" in the name portion, THE App SHALL set the corresponding audio format (DEEP_DIVE, BRIEF, CRITIQUE, DEBATE)
4. IF the template type cannot be determined from the filename, THEN THE App SHALL fall back to content-based detection by scanning for type keywords in the file content
5. WHEN an artifact is generated, THE App SHALL derive the artifact name from the template's `{Name}` portion and append the correct file extension (.png for infographic, .mp3 for audio, .mp4 for video)
6. WHEN the template filename is "01_Steering Prompt.md", THE App SHALL exclude it from the active template list

### Requirement 15: Settings and Advanced Operations

**User Story:** As an experienced user, I want access to advanced operations so that I can manage templates, reports, and cached data outside the wizard flow.

#### Acceptance Criteria

1. THE App SHALL serve a `/settings` route with sections: Template Management, Report Management, Data Management, and Sync
2. THE Settings_Page Template Management section SHALL allow: uploading new templates, editing template content inline, deleting user-uploaded templates, and a "Restore Defaults" button that reloads Default_Templates from disk
3. THE Settings_Page Report Management section SHALL allow: uploading new reports, editing the notebook name mapping for each report, and deleting reports (with confirmation showing affected Generation_Cells and option to delete remote notebook per Requirement 12.2)
4. THE Settings_Page Data Management section SHALL provide a "Clear All Data" button that, after confirmation per Requirement 7.6, deletes all rows from reports, templates, generation_cells, and artifacts tables and removes files from `data/uploads/` and `output/`
5. THE Settings_Page Sync section SHALL provide a "Sync Now" button that triggers NLM_Sync on demand with a progress indicator, and display the timestamp of the last successful sync

### Requirement 16: Long-Running Task Handling

**User Story:** As a user, I want the app to handle long-running generation tasks (up to 1 hour for videos) without losing track of progress.

#### Acceptance Criteria

1. WHILE a generation task is in progress, THE App SHALL poll the NLM SDK for status updates every 5 seconds and display elapsed time in the Generation_Cell
2. WHEN the user refreshes the browser during a long-running task, THE App SHALL reconnect to the WebSocket and restore the current state from the server, showing all in-progress tasks with their current status
3. WHEN the App restarts while tasks are in progress, THE App SHALL detect in-progress Generation_Cells during startup and resume polling for their Task_IDs
4. THE App SHALL set a maximum polling timeout of 2 hours, after which it marks the Generation_Cell as "failed" with a timeout error message
5. WHEN a user attempts to start generation for a cell that is already "in_progress", THE App SHALL display a message indicating generation is already running and show the elapsed time
