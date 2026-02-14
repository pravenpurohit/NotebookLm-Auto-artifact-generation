# Requirements Document

## Introduction

This feature addresses UX issues and adds new capabilities to the NotebookLM Dashboard application: (1) the Artifacts page now shows pre-existing notebooks/artifacts from the user's NotebookLM account, (2) the File Browser page has streamlined upload feedback, (3) the File Browser preserves user-customized notebook names, (4) users can delete individual artifacts, (5) users can delete entire notebooks, (6) integration tests clean up test-created notebooks, (7) duplicate notebook detection via content hashing, and (8) duplicate prompt detection for artifact generation.

## Glossary

- **Dashboard**: The NotebookLM Dashboard web application (FastAPI backend + vanilla JS frontend).
- **Artifacts_Page**: The `/artifacts` page that displays generated and pre-existing artifacts.
- **File_Browser**: The `/files` page where users upload report files and manage notebook names.
- **NLM_Client**: The `NotebookLMClientWrapper` that communicates with the NotebookLM API.
- **State_Manager**: The `StateManager` class responsible for SQLite persistence of reports, templates, cells, and artifacts.
- **Report**: A user-uploaded PDF or Markdown file tracked in the reports table.
- **Notebook_Name**: A user-editable label assigned to each Report, used when creating NotebookLM notebooks.
- **Remote_Notebook**: A notebook that exists in the user's NotebookLM account, retrieved via the NLM API.
- **Remote_Artifact**: An artifact associated with a Remote_Notebook, retrieved via the NLM API.
- **Content_Hash**: A SHA-256 hash of a file's content, used to detect duplicate uploads and link notebooks to source files.
- **Prompt_Hash**: A SHA-256 hash of a template prompt's content, used to detect duplicate generation requests.

## Requirements

### Requirement 1: Display Pre-Existing Notebooks and Artifacts

**User Story:** As a user, I want the Artifacts page to show all notebooks and artifacts from my NotebookLM account, so that I can browse everything in one place rather than only dashboard-generated items.

#### Acceptance Criteria

1. WHEN the Artifacts_Page loads, THE Artifacts_Page SHALL fetch Remote_Notebooks from the NLM_Client and display them alongside locally tracked artifacts.
2. WHEN Remote_Artifacts are retrieved, THE Artifacts_Page SHALL display each Remote_Artifact with its name, type, source notebook title, and creation date.
3. WHEN a Remote_Artifact has a matching local artifact record, THE Artifacts_Page SHALL display a single merged entry rather than duplicates.
4. IF the NLM_Client fails to retrieve Remote_Notebooks, THEN THE Artifacts_Page SHALL display locally tracked artifacts and show an error banner indicating the remote fetch failed.
5. WHEN the user applies filters on the Artifacts_Page, THE Artifacts_Page SHALL apply filters to both local and remote artifacts consistently.

### Requirement 2: Streamlined File Selection with Upload Feedback

**User Story:** As a user, I want immediate visual feedback when I select files in the File Browser, so that I know my selection was registered and I can proceed without a redundant Upload button click.

#### Acceptance Criteria

1. WHEN the user selects files via the file input, THE File_Browser SHALL automatically begin uploading the selected files without requiring a separate Upload button click.
2. WHEN file upload begins, THE File_Browser SHALL display a progress indicator showing that files are being processed.
3. WHEN file upload completes successfully, THE File_Browser SHALL display a success confirmation message listing the uploaded filenames.
4. IF file upload fails, THEN THE File_Browser SHALL display an error message identifying which files failed and the reason.
5. WHEN the upload is in progress, THE File_Browser SHALL disable the file input to prevent duplicate submissions.
6. WHEN the success confirmation message is displayed, THE File_Browser SHALL automatically dismiss the message after 5 seconds.
7. IF the user selects zero files (cancels the file dialog), THEN THE File_Browser SHALL not initiate an upload and SHALL leave the current state unchanged.
8. IF the user selects files with invalid formats (not PDF or MD), THEN THE File_Browser SHALL display an error identifying the invalid files and SHALL still upload any valid files in the selection.

### Requirement 4: Delete Notebook Artifacts

**User Story:** As a user, I want to delete individual artifacts from my NotebookLM notebooks, so that I can remove unwanted or failed generation outputs without deleting the entire notebook.

#### Acceptance Criteria

1. WHEN the user clicks a delete button on an artifact in the Artifacts_Page, THE Dashboard SHALL prompt for confirmation before proceeding.
2. WHEN the user confirms deletion of a local artifact, THE State_Manager SHALL remove the artifact record from the database and delete the artifact file from disk.
3. WHEN the user confirms deletion of a Remote_Artifact, THE NLM_Client SHALL call the SDK to delete the artifact from the remote notebook.
4. IF artifact deletion fails, THEN THE Dashboard SHALL display an error message and leave the artifact in its current state.
5. WHEN an artifact is successfully deleted, THE Artifacts_Page SHALL remove the artifact from the displayed list without a full page reload.
6. IF a remote artifact ID has an invalid format, THEN THE Dashboard SHALL return a 400 error indicating the ID format is invalid.

### Requirement 5: Delete Notebooks

**User Story:** As a user, I want to delete entire notebooks from my NotebookLM account via the dashboard, so that I can clean up notebooks I no longer need.

#### Acceptance Criteria

1. WHEN the user clicks a delete button on a notebook entry, THE Dashboard SHALL prompt for confirmation before proceeding.
2. WHEN the user confirms deletion, THE NLM_Client SHALL call the SDK to delete the notebook from the remote account.
3. WHEN a notebook is deleted remotely, THE State_Manager SHALL remove all associated local records (generation cells, artifacts) for that notebook.
4. IF notebook deletion fails, THEN THE Dashboard SHALL display an error message and leave the notebook in its current state.
5. WHEN a notebook is successfully deleted, THE Dashboard SHALL remove it from the displayed list without a full page reload.

### Requirement 6: Test Cleanup — Delete Test Notebooks

**User Story:** As a developer, I want integration tests that create NotebookLM notebooks to clean up after themselves, so that test runs do not pollute the user's NotebookLM account.

#### Acceptance Criteria

1. WHEN an integration test creates a notebook via the NLM_Client, THE test teardown SHALL delete that notebook using the NLM_Client.
2. WHEN test cleanup fails to delete a notebook, THE test SHALL log a warning with the notebook ID for manual cleanup.
3. THE test cleanup SHALL be implemented as a pytest fixture that tracks created notebook IDs and deletes them in teardown.

### Requirement 7: Duplicate Notebook Detection

**User Story:** As a user, I want the dashboard to detect if a notebook has already been created from a specific deep research report, so that I avoid creating duplicate notebooks for the same source file.

#### Acceptance Criteria

1. WHEN a Report is uploaded, THE State_Manager SHALL compute a content hash (SHA-256) of the file and store it alongside the report record.
2. WHEN notebook creation is requested for a Report, THE Dashboard SHALL check if a notebook already exists with the same content hash.
3. IF a notebook with the same content hash already exists, THEN THE Dashboard SHALL warn the user and offer to reuse the existing notebook or create a new one.
4. THE content hash SHALL be included in the notebook name (as a short suffix) so that duplicates can be detected even from the remote notebook list.
5. WHEN listing remote notebooks, THE Dashboard SHALL flag any notebooks whose name suffix matches a local report's content hash as "already linked".
6. IF a Report has a content hash but no associated generation cell exists, THEN duplicate detection SHALL return no match (the report has not yet been used to create a notebook).
7. WHEN a Report is uploaded without a content_hash field (backward compatibility), THE State_Manager SHALL store the report with a NULL content_hash.

### Requirement 8: Duplicate Prompt Detection

**User Story:** As a user, I want the dashboard to detect if an artifact generation prompt has already been submitted for a notebook, so that I avoid generating duplicate artifacts.

#### Acceptance Criteria

1. WHEN a Template prompt is used for generation, THE State_Manager SHALL compute a content hash (SHA-256) of the prompt content and store it in the generation cell record.
2. WHEN generation is requested for a (Report, Template) pair, THE Dashboard SHALL check if a generation cell already exists with the same prompt hash and a completed status.
3. IF a completed generation with the same prompt hash exists, THEN THE Dashboard SHALL warn the user and offer to skip, regenerate, or view the existing artifact.
4. WHEN a Template's content is edited, THE Dashboard SHALL recompute the prompt hash so that edited prompts are treated as new.

### Requirement 3: Preserve User-Customized Notebook Names

**User Story:** As a user, I want my customized notebook names to be preserved when I load additional files, so that I do not lose my naming work before running generation.

#### Acceptance Criteria

1. WHEN new files are uploaded, THE File_Browser SHALL append the new Reports to the existing report list without modifying previously loaded Reports.
2. WHEN a Report has a user-edited Notebook_Name, THE State_Manager SHALL preserve that Notebook_Name across subsequent file uploads.
3. WHEN rendering the report list after new uploads, THE File_Browser SHALL retain the current Notebook_Name values for all previously loaded Reports.
4. WHEN the user edits a Notebook_Name, THE State_Manager SHALL mark that Report's Notebook_Name as user-edited.
5. WHEN a Report's Notebook_Name is marked as user-edited, THE State_Manager SHALL reject any automatic overwrite of that Notebook_Name.
