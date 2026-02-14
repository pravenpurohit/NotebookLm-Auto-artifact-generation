# Requirements Document

## Introduction

The NotebookLM Dashboard is a web application for generating NotebookLM artifacts (infographics, audio, video) from deep research report files. It provides a dashboard with real-time progress visibility, individual and batch artifact control, persistent state management, and Google account authentication. The application is designed for future porting to Android via WebView.

## Glossary

- **Report**: A source document (PDF/MD) uploaded to NotebookLM as a notebook source
- **Template**: A markdown prompt file that instructs NotebookLM to generate a specific artifact type (infographic, audio, or video)
- **Artifact**: A generated output (infographic PNG, audio MP3, or video MP4) produced by NotebookLM
- **Notebook**: A Google NotebookLM notebook containing one source document
- **Task_ID**: A UUID returned by NotebookLM when artifact generation starts, used for polling status and preventing duplicates
- **Batch**: A set of (Report, Template) pairs to process sequentially or in controlled concurrency
- **Status_Grid**: A matrix UI component displaying Reports as rows and Templates as columns, with each cell showing artifact generation status
- **Template_Detector**: The component responsible for parsing template filenames and classifying them by artifact type
- **Artifact_Namer**: The component responsible for deriving artifact names from template filenames
- **Dashboard**: The main web application interface providing authentication, file browsing, artifact generation, and status monitoring
- **NotebookLM_Client**: The unofficial Python SDK (notebooklm-py >= 0.3.2) used to interact with Google NotebookLM API

## Requirements

### Requirement 1: Google Account Authentication

**User Story:** As a user, I want to log in with my Google account so that I can access my NotebookLM notebooks and generate artifacts.

#### Acceptance Criteria

1. WHEN the Dashboard starts, THE Dashboard SHALL display a Google account login prompt before showing any other content
2. WHEN a user completes Google authentication, THE Dashboard SHALL store the session credentials and display the main dashboard view
3. IF authentication fails, THEN THE Dashboard SHALL display a descriptive error message and allow the user to retry
4. WHILE a user session is active, THE Dashboard SHALL maintain the authenticated state across page refreshes
5. WHEN a user clicks the logout button, THE Dashboard SHALL clear the session credentials and return to the login prompt

### Requirement 2: Report File Selection

**User Story:** As a user, I want to browse and select deep research report files so that I can generate NotebookLM artifacts from them.

#### Acceptance Criteria

1. WHEN a user navigates to the file browser, THE Dashboard SHALL display a file browser allowing selection of PDF and MD files
2. WHEN files are displayed in the file browser, THE Dashboard SHALL show the file name, file size, and last modified date for each file
3. WHEN a user selects one or more report files, THE Dashboard SHALL add the selected files to the active report list
4. WHEN a user removes a report from the active report list, THE Dashboard SHALL remove the report and update the Status_Grid accordingly
5. IF a user selects a file that is not a PDF or MD format, THEN THE Dashboard SHALL reject the selection and display a format validation error

### Requirement 3: Notebook Auto-Naming

**User Story:** As a user, I want notebooks to be automatically named based on the attached file so that I can identify them without manual naming effort.

#### Acceptance Criteria

1. WHEN a Report is added to the active report list, THE Dashboard SHALL generate a notebook name derived from the Report filename (without extension)
2. WHEN a user edits an auto-generated notebook name, THE Dashboard SHALL update the notebook name to the user-provided value
3. THE Artifact_Namer SHALL derive notebook names by stripping the file extension from the Report filename

### Requirement 4: Template Detection and Management

**User Story:** As a user, I want templates to be automatically loaded and classified so that I can generate the correct artifact types without manual configuration.

#### Acceptance Criteria

1. WHEN the Dashboard loads templates from the prompts directory, THE Template_Detector SHALL parse each filename using the pattern `{number}_{Type}_{Name}.md`
2. WHEN a template filename contains "Infographic", THE Template_Detector SHALL classify the template as type "infographic"
3. WHEN a template filename contains "Audio", THE Template_Detector SHALL classify the template as type "audio"
4. WHEN a template filename contains "Video", THE Template_Detector SHALL classify the template as type "video"
5. WHEN a template filename contains "DeepDive", THE Template_Detector SHALL set the audio format to "DEEP_DIVE"
6. WHEN a template filename contains "TheBrief", THE Template_Detector SHALL set the audio format to "BRIEF"
7. WHEN a template filename contains "Critique", THE Template_Detector SHALL set the audio format to "CRITIQUE"
8. WHEN a template filename contains "Debate", THE Template_Detector SHALL set the audio format to "DEBATE"
9. WHEN the template filename is "01_Steering Prompt.md", THE Template_Detector SHALL exclude the template from the active template list
10. IF the Template_Detector cannot determine the type from the filename, THEN THE Template_Detector SHALL read the template file content and classify based on text analysis
11. WHEN a user adds a custom template file, THE Dashboard SHALL apply the same detection logic and add the template to the active template list
12. WHEN a user edits a template prompt, THE Dashboard SHALL store the edited version and use the edited prompt for artifact generation


### Requirement 5: Artifact Naming

**User Story:** As a user, I want generated artifacts to be named after the template prompt so that I can identify artifacts by their purpose.

#### Acceptance Criteria

1. WHEN an artifact is generated from a template, THE Artifact_Namer SHALL derive the artifact name from the template filename by extracting the `{Name}` portion after the `{number}_{Type}_` prefix
2. WHEN a template filename is "02_Infographic_One-page Map of a Complex Topic.md", THE Artifact_Namer SHALL produce the artifact name "One-page Map of a Complex Topic"
3. THE Artifact_Namer SHALL append the correct file extension based on artifact type: ".png" for infographic, ".mp3" for audio, ".mp4" for video

### Requirement 6: Artifact Generation and Task Tracking

**User Story:** As a user, I want to generate artifacts from report-template pairs and track their progress so that I know the status of each generation task.

#### Acceptance Criteria

1. WHEN a user starts artifact generation for a Report-Template pair, THE Dashboard SHALL create a NotebookLM notebook, attach the Report as a source, and submit the Template prompt for generation
2. WHEN artifact generation is submitted, THE Dashboard SHALL store the returned Task_ID and associate it with the Report-Template pair
3. WHILE an artifact generation task is in progress, THE Dashboard SHALL poll the NotebookLM_Client for status updates at regular intervals
4. WHEN a Task_ID already exists for a Report-Template pair, THE Dashboard SHALL use the existing Task_ID to poll status instead of submitting a duplicate generation request
5. IF artifact generation fails, THEN THE Dashboard SHALL mark the cell as failed and store the error message for display
6. WHEN artifact generation completes, THE Dashboard SHALL download the artifact and store it in the appropriate subdirectory (infographics/, audio/, video/) with the name derived by the Artifact_Namer

### Requirement 7: Status Grid Display

**User Story:** As a user, I want a real-time status grid showing all report-template combinations so that I can monitor generation progress at a glance.

#### Acceptance Criteria

1. THE Status_Grid SHALL display a matrix with Reports as rows and Templates as columns
2. WHEN artifact generation status changes, THE Status_Grid SHALL update the corresponding cell within 2 seconds
3. THE Status_Grid SHALL display one of the following statuses for each cell: "pending", "in_progress", "completed", "failed", or "not_started"
4. WHEN a user hovers over or taps a Status_Grid cell, THE Dashboard SHALL display detailed information including Task_ID, start time, elapsed time, and error message if applicable
5. WHEN a cell status is "completed", THE Status_Grid SHALL provide a link or button to view or download the generated artifact

### Requirement 8: Individual Artifact Control

**User Story:** As a user, I want to start, stop, and retry individual artifact generation tasks so that I have fine-grained control over the process.

#### Acceptance Criteria

1. WHEN a user clicks "start" on a Status_Grid cell with status "not_started" or "pending", THE Dashboard SHALL initiate artifact generation for that Report-Template pair
2. WHEN a user clicks "stop" on a Status_Grid cell with status "in_progress", THE Dashboard SHALL cancel the generation task and set the cell status to "stopped"
3. WHEN a user clicks "retry" on a Status_Grid cell with status "failed" or "stopped", THE Dashboard SHALL generate a new Task_ID and restart artifact generation for that Report-Template pair
4. IF a user attempts to start generation for a cell that already has status "in_progress", THEN THE Dashboard SHALL display a message indicating generation is already running

### Requirement 9: Batch Controls

**User Story:** As a user, I want batch controls to manage all artifact generation tasks at once so that I can efficiently control large generation runs.

#### Acceptance Criteria

1. WHEN a user clicks "Start All", THE Dashboard SHALL initiate artifact generation for all Report-Template pairs with status "not_started" or "pending"
2. WHEN a user clicks "Pause", THE Dashboard SHALL pause the submission of new generation tasks while allowing in-progress tasks to complete
3. WHEN a user clicks "Resume", THE Dashboard SHALL resume submitting paused generation tasks
4. WHEN a user clicks "Stop All", THE Dashboard SHALL cancel all in-progress generation tasks and set their status to "stopped"
5. WHEN a user clicks "Retry Failed", THE Dashboard SHALL restart artifact generation for all Report-Template pairs with status "failed"

### Requirement 10: State Persistence and Crash Recovery

**User Story:** As a user, I want the application to recover from crashes or shutdowns so that I do not lose progress on artifact generation.

#### Acceptance Criteria

1. WHEN the Dashboard starts after a crash or shutdown, THE Dashboard SHALL retrieve all NotebookLM notebooks from the linked Google account
2. WHEN recovering state, THE Dashboard SHALL match retrieved notebooks to previously tracked Report-Template pairs using stored Task_IDs
3. WHEN a previously in-progress task is found during recovery, THE Dashboard SHALL resume polling for that Task_ID status
4. THE Dashboard SHALL persist the current state (Report list, Template list, Task_IDs, statuses) to local storage after every state change
5. IF a notebook exists in the Google account but has no matching local state, THEN THE Dashboard SHALL display the notebook in a separate "untracked notebooks" section

### Requirement 11: Artifact Browsing and Filtering

**User Story:** As a user, I want to browse all generated artifacts with filters so that I can find specific artifacts quickly.

#### Acceptance Criteria

1. THE Dashboard SHALL provide an artifact browser view listing all generated artifacts
2. WHEN a user applies a source file location filter, THE Dashboard SHALL display only artifacts generated from reports in the specified location
3. WHEN a user applies a source file name filter, THE Dashboard SHALL display only artifacts generated from the specified report file
4. WHEN a user applies an artifact type filter, THE Dashboard SHALL display only artifacts of the selected type (infographic, audio, or video)
5. WHEN multiple filters are applied simultaneously, THE Dashboard SHALL display only artifacts matching all active filter criteria
6. WHEN a user selects an artifact from the browser, THE Dashboard SHALL display or play the artifact inline (image preview for PNG, audio player for MP3, video player for MP4)

### Requirement 12: Responsive Design

**User Story:** As a user, I want the application to work on both desktop and mobile devices so that I can manage artifact generation from any device.

#### Acceptance Criteria

1. THE Dashboard SHALL render correctly on viewport widths from 320px to 2560px
2. WHEN the viewport width is below 768px, THE Status_Grid SHALL switch to a vertically scrollable card layout instead of the matrix view
3. THE Dashboard SHALL support touch interactions for all controls on mobile devices
4. THE Dashboard SHALL maintain all functionality across desktop and mobile viewports
