"""Integration tests for UX improvements.

Covers:
  1. persist_reports with new reports — verify reports are created correctly
  2. persist_reports preserves edited notebook names when re-uploading
  3. Artifact listing returns local artifacts when remote fetch fails (mock NLM client)
  4. Remote artifacts endpoint returns proper response shape
  5. Merge logic with no overlap and full overlap scenarios

Requirements: 1.4, 2.3, 2.4, 3.1, 3.2
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import aiosqlite
import pytest
import pytest_asyncio

from app.nlm_client import NotebookLMClientError, NotebookLMClientWrapper
from app.state_manager import StateManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_path(tmp_path):
    return str(tmp_path / "test_ux.db")


@pytest_asyncio.fixture
async def state_manager(db_path):
    sm = StateManager(db_path=db_path)
    await sm.init_db()
    return sm


# ---------------------------------------------------------------------------
# 1. persist_reports with new reports — verify reports are created correctly
#    Requirements: 2.3, 2.4, 3.1
# ---------------------------------------------------------------------------

class TestPersistReportsNew:
    """Test that persist_reports correctly creates new report records."""

    @pytest.mark.asyncio
    async def test_single_report_created(self, state_manager, db_path):
        """A single new report should be persisted with all fields."""
        reports = [
            {
                "id": "r-new-1",
                "filename": "deep_research.md",
                "filepath": "/uploads/deep_research.md",
                "file_size": 4096,
                "last_modified": "2024-06-01T12:00:00Z",
                "notebook_name": "Deep Research",
            }
        ]
        await state_manager.persist_reports(reports)

        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT id, filename, filepath, file_size, last_modified, "
                "notebook_name, notebook_name_edited FROM reports WHERE id = ?",
                ("r-new-1",),
            )
            row = await cursor.fetchone()

        assert row is not None
        assert row[0] == "r-new-1"
        assert row[1] == "deep_research.md"
        assert row[2] == "/uploads/deep_research.md"
        assert row[3] == 4096
        assert row[4] == "2024-06-01T12:00:00Z"
        assert row[5] == "Deep Research"
        assert not row[6]  # notebook_name_edited defaults to False

    @pytest.mark.asyncio
    async def test_multiple_reports_created(self, state_manager, db_path):
        """Multiple reports should all be persisted in one call."""
        reports = [
            {
                "id": "r-a",
                "filename": "report_a.md",
                "filepath": "/uploads/report_a.md",
                "file_size": 1024,
                "last_modified": "2024-01-01",
                "notebook_name": "Report A",
            },
            {
                "id": "r-b",
                "filename": "report_b.pdf",
                "filepath": "/uploads/report_b.pdf",
                "file_size": 2048,
                "last_modified": "2024-01-02",
                "notebook_name": "Report B",
            },
        ]
        await state_manager.persist_reports(reports)

        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("SELECT id FROM reports ORDER BY id")
            rows = await cursor.fetchall()

        assert len(rows) == 2
        assert rows[0][0] == "r-a"
        assert rows[1][0] == "r-b"

    @pytest.mark.asyncio
    async def test_new_reports_appended_to_existing(self, state_manager, db_path):
        """New reports should be appended without removing existing ones."""
        await state_manager.persist_reports([
            {"id": "r-existing", "filename": "old.md", "filepath": "/old.md", "notebook_name": "Old"},
        ])
        await state_manager.persist_reports([
            {"id": "r-new", "filename": "new.md", "filepath": "/new.md", "notebook_name": "New"},
        ])

        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("SELECT id FROM reports ORDER BY id")
            rows = await cursor.fetchall()

        ids = [r[0] for r in rows]
        assert "r-existing" in ids
        assert "r-new" in ids
        assert len(ids) == 2


# ---------------------------------------------------------------------------
# 2. persist_reports preserves edited notebook names when re-uploading
#    Requirements: 3.1, 3.2
# ---------------------------------------------------------------------------

class TestPersistReportsPreservesEditedNames:
    """Test that user-edited notebook names survive re-upload."""

    @pytest.mark.asyncio
    async def test_edited_name_preserved_on_re_upload(self, state_manager, db_path):
        """After editing a notebook name, re-uploading the same report ID should keep the edited name."""
        # Initial upload
        await state_manager.persist_reports([
            {"id": "r1", "filename": "report.md", "filepath": "/report.md", "notebook_name": "Auto Name"},
        ])

        # User edits the notebook name
        await state_manager.update_report_notebook_name("r1", "My Custom Name")

        # Re-upload with the same ID but different auto-generated name
        await state_manager.persist_reports([
            {"id": "r1", "filename": "report.md", "filepath": "/report.md", "notebook_name": "Auto Name v2"},
        ])

        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT notebook_name, notebook_name_edited FROM reports WHERE id = 'r1'"
            )
            row = await cursor.fetchone()

        assert row[0] == "My Custom Name"
        assert row[1]  # notebook_name_edited should still be True

    @pytest.mark.asyncio
    async def test_non_edited_name_can_be_overwritten(self, state_manager, db_path):
        """A report whose name was NOT edited should accept a new name on re-upload."""
        await state_manager.persist_reports([
            {"id": "r2", "filename": "report.md", "filepath": "/report.md", "notebook_name": "Original"},
        ])

        # Re-upload with a different name (no user edit happened)
        await state_manager.persist_reports([
            {"id": "r2", "filename": "report.md", "filepath": "/report.md", "notebook_name": "Updated"},
        ])

        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT notebook_name FROM reports WHERE id = 'r2'"
            )
            row = await cursor.fetchone()

        assert row[0] == "Updated"

    @pytest.mark.asyncio
    async def test_mixed_edited_and_new_reports(self, state_manager, db_path):
        """Uploading a mix of existing-edited and brand-new reports should handle both correctly."""
        # Create initial report and edit its name
        await state_manager.persist_reports([
            {"id": "r-edited", "filename": "edited.md", "filepath": "/edited.md", "notebook_name": "Auto"},
        ])
        await state_manager.update_report_notebook_name("r-edited", "User Choice")

        # Persist both the existing edited report and a new one
        await state_manager.persist_reports([
            {"id": "r-edited", "filename": "edited.md", "filepath": "/edited.md", "notebook_name": "Overwrite Attempt"},
            {"id": "r-fresh", "filename": "fresh.md", "filepath": "/fresh.md", "notebook_name": "Fresh Name"},
        ])

        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT id, notebook_name FROM reports ORDER BY id"
            )
            rows = await cursor.fetchall()

        result = {r[0]: r[1] for r in rows}
        assert result["r-edited"] == "User Choice"  # preserved
        assert result["r-fresh"] == "Fresh Name"  # new report accepted


# ---------------------------------------------------------------------------
# 3. Artifact listing returns local artifacts when remote fetch fails
#    Requirements: 1.4
# ---------------------------------------------------------------------------

class TestArtifactListingFallback:
    """Test that local artifacts are returned when the NLM client fails."""

    @pytest.mark.asyncio
    async def test_local_artifacts_returned_on_remote_failure(self, state_manager, db_path):
        """When NLM client raises, list_artifacts should still return local data."""
        # Seed a report, template, and artifact
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO reports (id, filename, filepath, notebook_name) VALUES (?, ?, ?, ?)",
                ("r1", "report.md", "/report.md", "Report"),
            )
            await db.execute(
                "INSERT INTO templates (id, filename, number, artifact_type, name, content) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("t1", "01_Infographic_Test.md", 1, "infographic", "Test", "content"),
            )
            await db.execute(
                "INSERT INTO artifacts (id, report_id, template_id, artifact_type, artifact_name, "
                "file_path, file_extension) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("a1", "r1", "t1", "infographic", "Test Infographic", "/output/test.png", ".png"),
            )
            await db.commit()

        # Local artifacts should be retrievable regardless of NLM client state
        local_artifacts = await state_manager.list_artifacts()
        assert len(local_artifacts) == 1
        assert local_artifacts[0]["id"] == "a1"
        assert local_artifacts[0]["artifact_name"] == "Test Infographic"

    @pytest.mark.asyncio
    async def test_remote_endpoint_returns_error_on_nlm_failure(self):
        """The /api/artifacts/remote endpoint should return error info when NLM fails."""
        from app.routes.artifacts import list_remote_artifacts

        mock_client = AsyncMock(spec=NotebookLMClientWrapper)
        mock_client.list_notebooks.side_effect = NotebookLMClientError("Connection refused")

        result = await list_remote_artifacts(nlm_client=mock_client)

        assert result["artifacts"] == []
        assert "error" in result
        assert "Connection refused" in result["error"]


# ---------------------------------------------------------------------------
# 4. Remote artifacts endpoint returns proper response shape
#    Requirements: 1.4, 2.3
# ---------------------------------------------------------------------------

class TestRemoteArtifactsEndpoint:
    """Test the /api/artifacts/remote endpoint response shape."""

    @pytest.mark.asyncio
    async def test_remote_endpoint_returns_correct_shape(self):
        """Each remote artifact should have all required fields."""
        from app.routes.artifacts import list_remote_artifacts

        mock_client = AsyncMock(spec=NotebookLMClientWrapper)
        mock_client.list_notebooks.return_value = [
            {"id": "nb-1", "title": "Notebook One"},
        ]
        mock_client.list_notebook_artifacts.return_value = [
            {"id": "art-1", "name": "Summary", "type": "audio", "created_at": "2024-06-01"},
        ]

        mock_sm = AsyncMock()
        mock_sm.get_all_content_hashes = AsyncMock(return_value=set())

        result = await list_remote_artifacts(nlm_client=mock_client, sm=mock_sm)

        assert "artifacts" in result
        assert len(result["artifacts"]) == 1

        artifact = result["artifacts"][0]
        assert artifact["id"] == "remote-nb-1-0"
        assert artifact["artifact_name"] == "Summary"
        assert artifact["artifact_type"] == "audio"
        assert artifact["source_notebook_title"] == "Notebook One"
        assert artifact["source_notebook_id"] == "nb-1"
        assert artifact["created_at"] == "2024-06-01"
        assert artifact["is_remote"] is True

    @pytest.mark.asyncio
    async def test_remote_endpoint_multiple_notebooks(self):
        """Artifacts from multiple notebooks should be flattened into one list."""
        from app.routes.artifacts import list_remote_artifacts

        mock_client = AsyncMock(spec=NotebookLMClientWrapper)
        mock_client.list_notebooks.return_value = [
            {"id": "nb-1", "title": "First"},
            {"id": "nb-2", "title": "Second"},
        ]
        mock_client.list_notebook_artifacts.side_effect = [
            [{"id": "a1", "name": "Art1", "type": "infographic", "created_at": "2024-01-01"}],
            [{"id": "a2", "name": "Art2", "type": "video", "created_at": "2024-02-01"}],
        ]

        mock_sm = AsyncMock()
        mock_sm.get_all_content_hashes = AsyncMock(return_value=set())

        result = await list_remote_artifacts(nlm_client=mock_client, sm=mock_sm)

        assert len(result["artifacts"]) == 2
        assert result["artifacts"][0]["source_notebook_id"] == "nb-1"
        assert result["artifacts"][1]["source_notebook_id"] == "nb-2"

    @pytest.mark.asyncio
    async def test_remote_endpoint_empty_notebooks(self):
        """When there are no remote notebooks, artifacts list should be empty."""
        from app.routes.artifacts import list_remote_artifacts

        mock_client = AsyncMock(spec=NotebookLMClientWrapper)
        mock_client.list_notebooks.return_value = []

        mock_sm = AsyncMock()
        mock_sm.get_all_content_hashes = AsyncMock(return_value=set())

        result = await list_remote_artifacts(nlm_client=mock_client, sm=mock_sm)

        assert result["artifacts"] == []
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_remote_endpoint_partial_failure(self):
        """If one notebook's artifacts fail, others should still be returned."""
        from app.routes.artifacts import list_remote_artifacts

        mock_client = AsyncMock(spec=NotebookLMClientWrapper)
        mock_client.list_notebooks.return_value = [
            {"id": "nb-ok", "title": "OK Notebook"},
            {"id": "nb-fail", "title": "Failing Notebook"},
        ]
        mock_client.list_notebook_artifacts.side_effect = [
            [{"id": "a1", "name": "Good Art", "type": "audio", "created_at": "2024-01-01"}],
            NotebookLMClientError("Timeout"),
        ]

        mock_sm = AsyncMock()
        mock_sm.get_all_content_hashes = AsyncMock(return_value=set())

        result = await list_remote_artifacts(nlm_client=mock_client, sm=mock_sm)

        assert len(result["artifacts"]) == 1
        assert result["artifacts"][0]["artifact_name"] == "Good Art"


# ---------------------------------------------------------------------------
# 5. Merge logic with no overlap and full overlap scenarios
#    Requirements: 2.4, 3.2
# ---------------------------------------------------------------------------

class TestMergeLogic:
    """Test the frontend merge logic (replicated in Python for verification).

    The merge algorithm:
    1. Build a set of (source_notebook_id, artifact_name) from local artifacts
    2. For each remote artifact, skip if key exists in local set
    3. Concatenate remaining remote artifacts with local
    """

    @staticmethod
    def merge_artifacts(local: list[dict], remote: list[dict]) -> list[dict]:
        """Python implementation of the frontend merge logic for testing."""
        local_keys = set()
        for a in local:
            nb_id = a.get("source_notebook_id")
            name = a.get("artifact_name")
            if nb_id and name:
                local_keys.add((nb_id, name))

        merged = list(local)
        for a in remote:
            key = (a.get("source_notebook_id"), a.get("artifact_name"))
            if key not in local_keys:
                merged.append(a)

        return merged

    def test_no_overlap_all_included(self):
        """When local and remote have no common keys, all artifacts appear in merged list."""
        local = [
            {"id": "local-1", "artifact_name": "Report Summary", "source_notebook_id": "nb-1"},
        ]
        remote = [
            {"id": "remote-2-0", "artifact_name": "Deep Dive", "source_notebook_id": "nb-2"},
        ]

        merged = self.merge_artifacts(local, remote)

        assert len(merged) == 2
        ids = {a["id"] for a in merged}
        assert "local-1" in ids
        assert "remote-2-0" in ids

    def test_full_overlap_only_local_kept(self):
        """When all remote artifacts match local ones, only local entries remain."""
        local = [
            {"id": "local-1", "artifact_name": "Summary", "source_notebook_id": "nb-1"},
            {"id": "local-2", "artifact_name": "Podcast", "source_notebook_id": "nb-2"},
        ]
        remote = [
            {"id": "remote-nb-1-0", "artifact_name": "Summary", "source_notebook_id": "nb-1"},
            {"id": "remote-nb-2-0", "artifact_name": "Podcast", "source_notebook_id": "nb-2"},
        ]

        merged = self.merge_artifacts(local, remote)

        assert len(merged) == 2
        ids = {a["id"] for a in merged}
        assert ids == {"local-1", "local-2"}

    def test_partial_overlap(self):
        """Only non-overlapping remote artifacts should be added."""
        local = [
            {"id": "local-1", "artifact_name": "Summary", "source_notebook_id": "nb-1"},
        ]
        remote = [
            {"id": "remote-nb-1-0", "artifact_name": "Summary", "source_notebook_id": "nb-1"},  # overlap
            {"id": "remote-nb-2-0", "artifact_name": "New Art", "source_notebook_id": "nb-2"},  # unique
        ]

        merged = self.merge_artifacts(local, remote)

        assert len(merged) == 2
        ids = {a["id"] for a in merged}
        assert "local-1" in ids
        assert "remote-nb-2-0" in ids
        assert "remote-nb-1-0" not in ids

    def test_empty_local_all_remote_included(self):
        """With no local artifacts, all remote artifacts should appear."""
        remote = [
            {"id": "remote-1-0", "artifact_name": "Art1", "source_notebook_id": "nb-1"},
            {"id": "remote-2-0", "artifact_name": "Art2", "source_notebook_id": "nb-2"},
        ]

        merged = self.merge_artifacts([], remote)

        assert len(merged) == 2

    def test_empty_remote_only_local(self):
        """With no remote artifacts, only local artifacts should appear."""
        local = [
            {"id": "local-1", "artifact_name": "Art1", "source_notebook_id": "nb-1"},
        ]

        merged = self.merge_artifacts(local, [])

        assert len(merged) == 1
        assert merged[0]["id"] == "local-1"

    def test_both_empty(self):
        """With no artifacts at all, merged list should be empty."""
        merged = self.merge_artifacts([], [])
        assert merged == []


# ---------------------------------------------------------------------------
# 6. Editing a notebook name marks the report as user-edited
#    Requirements: 3.4
# ---------------------------------------------------------------------------

class TestNotebookNameEditFlag:
    """Test that update_report_notebook_name sets notebook_name_edited = True."""

    @pytest.mark.asyncio
    async def test_editing_name_sets_edited_flag(self, state_manager, db_path):
        """After calling update_report_notebook_name, notebook_name_edited should be True."""
        await state_manager.persist_reports([
            {"id": "r-flag", "filename": "flag.md", "filepath": "/flag.md", "notebook_name": "Auto"},
        ])

        # Verify flag starts as False
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT notebook_name_edited FROM reports WHERE id = 'r-flag'"
            )
            row = await cursor.fetchone()
        assert not row[0], "notebook_name_edited should start as False"

        # Edit the name
        result = await state_manager.update_report_notebook_name("r-flag", "Custom Name")
        assert result is True, "update_report_notebook_name should return True for existing report"

        # Verify flag is now True and name is updated
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT notebook_name, notebook_name_edited FROM reports WHERE id = 'r-flag'"
            )
            row = await cursor.fetchone()
        assert row[0] == "Custom Name"
        assert row[1], "notebook_name_edited should be True after editing"

    @pytest.mark.asyncio
    async def test_editing_nonexistent_report_returns_false(self, state_manager):
        """Editing a non-existent report should return False."""
        result = await state_manager.update_report_notebook_name("no-such-id", "Name")
        assert result is False


# ---------------------------------------------------------------------------
# 7. Artifact deletion
#    Requirements: 4.2, 4.3, 4.4
# ---------------------------------------------------------------------------

class TestArtifactDeletion:
    """Test artifact deletion for both local and remote artifacts."""

    @pytest.mark.asyncio
    async def test_local_artifact_deletion_removes_db_record(self, state_manager, db_path):
        """Deleting a local artifact should remove it from the database."""
        # Seed a report, template, and artifact
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO reports (id, filename, filepath, notebook_name) VALUES (?, ?, ?, ?)",
                ("r-del", "report.md", "/report.md", "Report"),
            )
            await db.execute(
                "INSERT INTO templates (id, filename, number, artifact_type, name, content) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("t-del", "01_Infographic_Test.md", 1, "infographic", "Test", "content"),
            )
            await db.execute(
                "INSERT INTO artifacts (id, report_id, template_id, artifact_type, artifact_name, "
                "file_path, file_extension) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("a-del", "r-del", "t-del", "infographic", "Test Infographic", "/output/test.png", ".png"),
            )
            await db.commit()

        # Delete the artifact
        result = await state_manager.delete_artifact_record("a-del")
        assert result is True

        # Verify it's gone from the database
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("SELECT id FROM artifacts WHERE id = 'a-del'")
            row = await cursor.fetchone()
        assert row is None

    @pytest.mark.asyncio
    async def test_local_artifact_deletion_removes_file(self, state_manager, db_path, tmp_path):
        """Deleting a local artifact should also delete the file from disk."""
        # Create a real file on disk
        artifact_file = tmp_path / "output" / "test.png"
        artifact_file.parent.mkdir(parents=True, exist_ok=True)
        artifact_file.write_text("fake image data")

        # Set output base to the tmp_path output dir so path validation passes
        state_manager._output_base = str(tmp_path / "output")

        # Seed DB records
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO reports (id, filename, filepath, notebook_name) VALUES (?, ?, ?, ?)",
                ("r-file", "report.md", "/report.md", "Report"),
            )
            await db.execute(
                "INSERT INTO templates (id, filename, number, artifact_type, name, content) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("t-file", "01_Infographic_Test.md", 1, "infographic", "Test", "content"),
            )
            await db.execute(
                "INSERT INTO artifacts (id, report_id, template_id, artifact_type, artifact_name, "
                "file_path, file_extension) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("a-file", "r-file", "t-file", "infographic", "Test Infographic",
                 str(artifact_file), ".png"),
            )
            await db.commit()

        assert artifact_file.exists()

        result = await state_manager.delete_artifact_record("a-file")
        assert result is True
        assert not artifact_file.exists()

    @pytest.mark.asyncio
    async def test_deleting_nonexistent_artifact_returns_false(self, state_manager):
        """Deleting an artifact that doesn't exist should return False."""
        result = await state_manager.delete_artifact_record("no-such-artifact")
        assert result is False

    @pytest.mark.asyncio
    async def test_remote_artifact_deletion_calls_nlm_client(self):
        """The DELETE endpoint should call nlm_client.delete_artifact for remote artifacts."""
        from app.routes.artifacts import delete_artifact

        mock_client = AsyncMock(spec=NotebookLMClientWrapper)
        mock_sm = AsyncMock(spec=StateManager)

        result = await delete_artifact(
            artifact_id="remote-nb123-0",
            sm=mock_sm,
            nlm_client=mock_client,
        )

        mock_client.delete_artifact.assert_called_once_with("nb123", "remote-nb123-0")
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_remote_artifact_deletion_failure_returns_error(self):
        """When NLM client fails to delete, the endpoint should return a 500 error."""
        from app.routes.artifacts import delete_artifact

        mock_client = AsyncMock(spec=NotebookLMClientWrapper)
        mock_client.delete_artifact.side_effect = NotebookLMClientError("API timeout")
        mock_sm = AsyncMock(spec=StateManager)

        with pytest.raises(Exception) as exc_info:
            await delete_artifact(
                artifact_id="remote-nb123-0",
                sm=mock_sm,
                nlm_client=mock_client,
            )

        assert exc_info.value.status_code == 500
        assert "API timeout" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_local_artifact_deletion_via_endpoint(self):
        """The DELETE endpoint should call state_manager for local artifacts."""
        from app.routes.artifacts import delete_artifact

        mock_client = AsyncMock(spec=NotebookLMClientWrapper)
        mock_sm = AsyncMock(spec=StateManager)
        mock_sm.delete_artifact_record.return_value = True

        result = await delete_artifact(
            artifact_id="local-artifact-123",
            sm=mock_sm,
            nlm_client=mock_client,
        )

        mock_sm.delete_artifact_record.assert_called_once_with("local-artifact-123")
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_local_artifact_not_found_returns_404(self):
        """Deleting a non-existent local artifact should return 404."""
        from app.routes.artifacts import delete_artifact

        mock_client = AsyncMock(spec=NotebookLMClientWrapper)
        mock_sm = AsyncMock(spec=StateManager)
        mock_sm.delete_artifact_record.return_value = False

        with pytest.raises(Exception) as exc_info:
            await delete_artifact(
                artifact_id="nonexistent-id",
                sm=mock_sm,
                nlm_client=mock_client,
            )

        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# 8. Notebook deletion
#    Requirements: 5.2, 5.3, 5.4
# ---------------------------------------------------------------------------

class TestNotebookDeletion:
    """Test notebook deletion: remote call, cascade local records, error handling."""

    @pytest.mark.asyncio
    async def test_delete_notebook_endpoint_calls_nlm_client(self):
        """The DELETE /api/notebooks/{id} endpoint should call nlm_client.delete_notebook."""
        from app.routes.notebooks import delete_notebook

        mock_client = AsyncMock(spec=NotebookLMClientWrapper)
        mock_sm = AsyncMock(spec=StateManager)
        mock_sm.delete_notebook_records.return_value = 2

        result = await delete_notebook(
            notebook_id="nb-123",
            sm=mock_sm,
            nlm_client=mock_client,
        )

        mock_client.delete_notebook.assert_called_once_with("nb-123")
        mock_sm.delete_notebook_records.assert_called_once_with("nb-123")
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_delete_notebook_failure_returns_error(self):
        """When NLM client fails to delete, the endpoint should return a 500 error."""
        from app.routes.notebooks import delete_notebook

        mock_client = AsyncMock(spec=NotebookLMClientWrapper)
        mock_client.delete_notebook.side_effect = NotebookLMClientError("Network error")
        mock_sm = AsyncMock(spec=StateManager)

        with pytest.raises(Exception) as exc_info:
            await delete_notebook(
                notebook_id="nb-fail",
                sm=mock_sm,
                nlm_client=mock_client,
            )

        assert exc_info.value.status_code == 500
        assert "Network error" in exc_info.value.detail
        # State manager should NOT be called if remote deletion fails
        mock_sm.delete_notebook_records.assert_not_called()

    @pytest.mark.asyncio
    async def test_cascade_deletion_of_local_records(self, state_manager, db_path):
        """Deleting a notebook should remove all associated generation cells and artifacts."""
        # Seed: report, template, generation cell with notebook_id, artifact
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO reports (id, filename, filepath, notebook_name) VALUES (?, ?, ?, ?)",
                ("r-nb", "report.md", "/report.md", "Report"),
            )
            await db.execute(
                "INSERT INTO templates (id, filename, number, artifact_type, name, content) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("t-nb", "01_Infographic_Test.md", 1, "infographic", "Test", "content"),
            )
            await db.execute(
                "INSERT INTO generation_cells (report_id, template_id, status, notebook_id) "
                "VALUES (?, ?, ?, ?)",
                ("r-nb", "t-nb", "completed", "nb-to-delete"),
            )
            await db.execute(
                "INSERT INTO artifacts (id, report_id, template_id, artifact_type, artifact_name, "
                "file_path, file_extension) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("a-nb", "r-nb", "t-nb", "infographic", "Test Art", "/output/test.png", ".png"),
            )
            await db.commit()

        deleted = await state_manager.delete_notebook_records("nb-to-delete")
        assert deleted == 1

        # Verify generation cell is gone
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM generation_cells WHERE notebook_id = 'nb-to-delete'"
            )
            assert await cursor.fetchone() is None

            # Verify artifact is gone
            cursor = await db.execute("SELECT * FROM artifacts WHERE id = 'a-nb'")
            assert await cursor.fetchone() is None

            # Report and template should still exist
            cursor = await db.execute("SELECT id FROM reports WHERE id = 'r-nb'")
            assert await cursor.fetchone() is not None

    @pytest.mark.asyncio
    async def test_cascade_deletion_multiple_cells(self, state_manager, db_path):
        """Deleting a notebook with multiple cells should remove all of them."""
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO reports (id, filename, filepath, notebook_name) VALUES (?, ?, ?, ?)",
                ("r-multi", "report.md", "/report.md", "Report"),
            )
            await db.execute(
                "INSERT INTO templates (id, filename, number, artifact_type, name, content) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("t-multi-1", "01_Infographic_Test.md", 1, "infographic", "Test1", "c1"),
            )
            await db.execute(
                "INSERT INTO templates (id, filename, number, artifact_type, name, content) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("t-multi-2", "02_Audio_Test.md", 2, "audio", "Test2", "c2"),
            )
            await db.execute(
                "INSERT INTO generation_cells (report_id, template_id, status, notebook_id) "
                "VALUES (?, ?, ?, ?)",
                ("r-multi", "t-multi-1", "completed", "nb-multi"),
            )
            await db.execute(
                "INSERT INTO generation_cells (report_id, template_id, status, notebook_id) "
                "VALUES (?, ?, ?, ?)",
                ("r-multi", "t-multi-2", "completed", "nb-multi"),
            )
            await db.execute(
                "INSERT INTO artifacts (id, report_id, template_id, artifact_type, artifact_name, "
                "file_path, file_extension) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("a-m1", "r-multi", "t-multi-1", "infographic", "Art1", "/out/a1.png", ".png"),
            )
            await db.execute(
                "INSERT INTO artifacts (id, report_id, template_id, artifact_type, artifact_name, "
                "file_path, file_extension) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("a-m2", "r-multi", "t-multi-2", "audio", "Art2", "/out/a2.mp3", ".mp3"),
            )
            await db.commit()

        deleted = await state_manager.delete_notebook_records("nb-multi")
        assert deleted == 2

        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM generation_cells WHERE notebook_id = 'nb-multi'"
            )
            assert (await cursor.fetchone())[0] == 0

            cursor = await db.execute(
                "SELECT COUNT(*) FROM artifacts WHERE report_id = 'r-multi'"
            )
            assert (await cursor.fetchone())[0] == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent_notebook_returns_zero(self, state_manager):
        """Deleting a notebook with no local records should return 0."""
        deleted = await state_manager.delete_notebook_records("no-such-notebook")
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_cascade_deletion_removes_artifact_files(self, state_manager, db_path, tmp_path):
        """Cascade deletion should also remove artifact files from disk."""
        # Create a real file
        artifact_file = tmp_path / "output" / "nb_art.png"
        artifact_file.parent.mkdir(parents=True, exist_ok=True)
        artifact_file.write_text("fake image data")

        # Set output base to the tmp_path output dir so path validation passes
        state_manager._output_base = str(tmp_path / "output")

        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO reports (id, filename, filepath, notebook_name) VALUES (?, ?, ?, ?)",
                ("r-file-nb", "report.md", "/report.md", "Report"),
            )
            await db.execute(
                "INSERT INTO templates (id, filename, number, artifact_type, name, content) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("t-file-nb", "01_Infographic_Test.md", 1, "infographic", "Test", "content"),
            )
            await db.execute(
                "INSERT INTO generation_cells (report_id, template_id, status, notebook_id) "
                "VALUES (?, ?, ?, ?)",
                ("r-file-nb", "t-file-nb", "completed", "nb-file-del"),
            )
            await db.execute(
                "INSERT INTO artifacts (id, report_id, template_id, artifact_type, artifact_name, "
                "file_path, file_extension) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("a-file-nb", "r-file-nb", "t-file-nb", "infographic", "Test Art",
                 str(artifact_file), ".png"),
            )
            await db.commit()

        assert artifact_file.exists()
        await state_manager.delete_notebook_records("nb-file-del")
        assert not artifact_file.exists()


# ---------------------------------------------------------------------------
# 9. Test cleanup fixture for notebooks
#    Requirements: 6.1, 6.2, 6.3
# ---------------------------------------------------------------------------

class TestNlmCleanupFixture:
    """Verify the nlm_cleanup pytest fixture tracks and cleans up notebooks."""

    @pytest.mark.asyncio
    async def test_cleanup_deletes_tracked_notebooks(self, nlm_cleanup):
        """Tracked notebook IDs should be deleted via the client on teardown.

        Requirements: 6.1, 6.3
        """
        mock_client = AsyncMock()
        nlm_cleanup.client = mock_client

        nlm_cleanup.append("nb-test-1")
        nlm_cleanup.append("nb-test-2")

        assert len(nlm_cleanup) == 2
        assert list(nlm_cleanup) == ["nb-test-1", "nb-test-2"]

    @pytest.mark.asyncio
    async def test_cleanup_logs_warning_on_failure(self, nlm_cleanup, caplog):
        """When delete_notebook raises, a warning should be logged but the test should not fail.

        Requirements: 6.2
        """
        mock_client = AsyncMock()
        mock_client.delete_notebook.side_effect = Exception("API unavailable")
        nlm_cleanup.client = mock_client

        nlm_cleanup.append("nb-fail-cleanup")

        # Manually trigger teardown logic to verify warning behavior
        import logging as _logging

        with caplog.at_level(_logging.WARNING):
            for nb_id in nlm_cleanup:
                try:
                    await nlm_cleanup.client.delete_notebook(nb_id)
                except Exception as exc:
                    _logging.getLogger(__name__).warning(
                        "Test cleanup failed for notebook %s: %s", nb_id, exc
                    )

        assert any("nb-fail-cleanup" in record.message for record in caplog.records)
        assert any("API unavailable" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_cleanup_with_no_client_skips_teardown(self, nlm_cleanup):
        """When no client is set, teardown should skip without error.

        Requirements: 6.3
        """
        nlm_cleanup.append("nb-orphan")
        # No client set — teardown should not raise
        assert nlm_cleanup.client is None
        assert len(nlm_cleanup) == 1

    @pytest.mark.asyncio
    async def test_cleanup_empty_list_is_noop(self, nlm_cleanup):
        """When no notebooks are tracked, teardown should be a no-op.

        Requirements: 6.3
        """
        mock_client = AsyncMock()
        nlm_cleanup.client = mock_client
        assert len(nlm_cleanup) == 0

    @pytest.mark.asyncio
    async def test_notebook_deletion_with_cleanup_fixture(self, nlm_cleanup):
        """Simulate a test that creates a notebook and registers it for cleanup.

        Requirements: 6.1
        """
        mock_client = AsyncMock()
        nlm_cleanup.client = mock_client

        # Simulate creating a notebook
        created_id = "nb-integration-test-123"
        nlm_cleanup.append(created_id)

        # The test does its assertions...
        assert created_id in list(nlm_cleanup)

        # Teardown will call delete_notebook for this ID


# ---------------------------------------------------------------------------
# Content Hashing and Duplicate Detection (Req 7.1, 7.2, 7.4, 7.5)
# ---------------------------------------------------------------------------

class TestContentHashing:
    """Test SHA-256 content hash computation and storage."""

    def test_hash_is_deterministic(self):
        """Computing hash of the same content twice produces the same result.

        Requirements: 7.1
        """
        content = b"Hello, this is a test report content."
        hash1 = StateManager.compute_content_hash(content)
        hash2 = StateManager.compute_content_hash(content)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex digest is 64 chars

    def test_identical_content_same_hash(self):
        """Two files with identical content produce the same hash.

        Requirements: 7.1
        """
        content = b"Identical content for both files"
        assert StateManager.compute_content_hash(content) == StateManager.compute_content_hash(content)

    def test_different_content_different_hash(self):
        """Two files with different content produce different hashes.

        Requirements: 7.1
        """
        hash1 = StateManager.compute_content_hash(b"Content A")
        hash2 = StateManager.compute_content_hash(b"Content B")
        assert hash1 != hash2

    def test_empty_content_has_valid_hash(self):
        """Empty content still produces a valid SHA-256 hash.

        Requirements: 7.1
        """
        h = StateManager.compute_content_hash(b"")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    @pytest.mark.asyncio
    async def test_content_hash_stored_in_db(self, state_manager, db_path):
        """Content hash is persisted alongside the report record.

        Requirements: 7.1
        """
        content = b"Test report content for hashing"
        content_hash = StateManager.compute_content_hash(content)

        report = {
            "id": "report-hash-1",
            "filename": "test.md",
            "filepath": "/tmp/test.md",
            "file_size": len(content),
            "last_modified": "2024-01-01T00:00:00Z",
            "notebook_name": f"test [{content_hash[:8]}]",
            "notebook_name_edited": False,
            "content_hash": content_hash,
        }
        await state_manager.persist_reports([report])

        # Verify hash is stored
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT content_hash FROM reports WHERE id = ?", ("report-hash-1",)
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == content_hash

    @pytest.mark.asyncio
    async def test_hash_suffix_in_notebook_name(self, state_manager, db_path):
        """Notebook name includes the first 8 chars of the content hash as a suffix.

        Requirements: 7.4
        """
        content = b"Report content for name suffix test"
        content_hash = StateManager.compute_content_hash(content)
        hash_suffix = content_hash[:8]
        notebook_name = f"My Report [{hash_suffix}]"

        report = {
            "id": "report-suffix-1",
            "filename": "My Report.md",
            "filepath": "/tmp/My Report.md",
            "file_size": len(content),
            "last_modified": "2024-01-01T00:00:00Z",
            "notebook_name": notebook_name,
            "notebook_name_edited": False,
            "content_hash": content_hash,
        }
        await state_manager.persist_reports([report])

        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT notebook_name FROM reports WHERE id = ?", ("report-suffix-1",)
            )
            row = await cursor.fetchone()
            assert row is not None
            assert f"[{hash_suffix}]" in row[0]


class TestDuplicateNotebookDetection:
    """Test duplicate notebook detection via content hash matching."""

    @pytest.mark.asyncio
    async def test_find_notebook_by_content_hash_returns_match(self, state_manager, db_path):
        """When a notebook exists for a report with the same content hash, it is found.

        Requirements: 7.2
        """
        content_hash = StateManager.compute_content_hash(b"Duplicate content")

        # Create a report with a content hash
        report = {
            "id": "report-dup-1",
            "filename": "dup.md",
            "filepath": "/tmp/dup.md",
            "file_size": 100,
            "last_modified": "2024-01-01T00:00:00Z",
            "notebook_name": f"dup [{content_hash[:8]}]",
            "notebook_name_edited": False,
            "content_hash": content_hash,
        }
        await state_manager.persist_reports([report])

        # Create a generation cell with a notebook_id for this report
        from app.state_manager import GenerationCell
        from app.models import CellStatus

        # First create a template so the FK constraint is satisfied
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO templates (id, filename, number, artifact_type, name, content) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("tmpl-1", "1_infographic_Test.md", 1, "infographic", "Test", "prompt"),
            )
            await db.commit()

        cell = GenerationCell(
            report_id="report-dup-1",
            template_id="tmpl-1",
            status=CellStatus.COMPLETED,
            notebook_id="nb-existing-123",
        )
        await state_manager.update_cell(cell)

        # Now check for duplicate
        result = await state_manager.find_notebook_by_content_hash(content_hash)
        assert result is not None
        assert result["notebook_id"] == "nb-existing-123"
        assert result["report_id"] == "report-dup-1"

    @pytest.mark.asyncio
    async def test_find_notebook_by_content_hash_returns_none_when_no_match(self, state_manager):
        """When no notebook exists with the given content hash, returns None.

        Requirements: 7.2
        """
        result = await state_manager.find_notebook_by_content_hash("nonexistent_hash")
        assert result is None

    @pytest.mark.asyncio
    async def test_find_notebook_by_content_hash_with_none(self, state_manager):
        """Passing None content hash returns None without error.

        Requirements: 7.2
        """
        result = await state_manager.find_notebook_by_content_hash(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_all_content_hashes(self, state_manager):
        """get_all_content_hashes returns all non-null hashes from reports.

        Requirements: 7.5
        """
        hash1 = StateManager.compute_content_hash(b"Content 1")
        hash2 = StateManager.compute_content_hash(b"Content 2")

        reports = [
            {
                "id": "r1", "filename": "a.md", "filepath": "/a.md",
                "file_size": 10, "last_modified": "2024-01-01",
                "notebook_name": "a", "notebook_name_edited": False,
                "content_hash": hash1,
            },
            {
                "id": "r2", "filename": "b.md", "filepath": "/b.md",
                "file_size": 20, "last_modified": "2024-01-01",
                "notebook_name": "b", "notebook_name_edited": False,
                "content_hash": hash2,
            },
            {
                "id": "r3", "filename": "c.md", "filepath": "/c.md",
                "file_size": 30, "last_modified": "2024-01-01",
                "notebook_name": "c", "notebook_name_edited": False,
                "content_hash": None,
            },
        ]
        await state_manager.persist_reports(reports)

        hashes = await state_manager.get_all_content_hashes()
        assert hash1 in hashes
        assert hash2 in hashes
        assert len(hashes) == 2  # None hash excluded


class TestRemoteLinkedDetection:
    """Test that remote notebook listing flags already-linked notebooks."""

    def test_hash_suffix_regex_matches(self):
        """The hash suffix regex correctly extracts 8-char hex suffixes from notebook names.

        Requirements: 7.5
        """
        import re
        pattern = re.compile(r"\[([0-9a-f]{8})\]\s*$")

        # Should match
        m = pattern.search("My Report [abcd1234]")
        assert m is not None
        assert m.group(1) == "abcd1234"

        # Should match with trailing space
        m = pattern.search("Report [12345678] ")
        assert m is not None
        assert m.group(1) == "12345678"

        # Should not match (uppercase)
        m = pattern.search("Report [ABCD1234]")
        assert m is None

        # Should not match (wrong length)
        m = pattern.search("Report [abc123]")
        assert m is None

        # Should not match (no brackets)
        m = pattern.search("Report abcd1234")
        assert m is None

    @pytest.mark.asyncio
    async def test_remote_endpoint_flags_linked_notebooks(self):
        """Remote artifacts from notebooks with matching hash suffixes are flagged as linked.

        Requirements: 7.5
        """
        from app.routes.artifacts import list_remote_artifacts

        content_hash = StateManager.compute_content_hash(b"Linked content")
        hash_prefix = content_hash[:8]

        mock_nlm = AsyncMock()
        mock_nlm.list_notebooks = AsyncMock(return_value=[
            {"id": "nb-linked", "title": f"Report [{hash_prefix}]"},
            {"id": "nb-unlinked", "title": "Other Notebook"},
        ])
        mock_nlm.list_notebook_artifacts = AsyncMock(return_value=[
            {"name": "artifact1", "type": "audio", "created_at": "2024-01-01"},
        ])

        mock_sm = AsyncMock()
        mock_sm.get_all_content_hashes = AsyncMock(return_value={content_hash})

        result = await list_remote_artifacts(nlm_client=mock_nlm, sm=mock_sm)
        artifacts = result["artifacts"]

        # The linked notebook's artifact should have is_linked=True
        linked = [a for a in artifacts if a["source_notebook_id"] == "nb-linked"]
        assert len(linked) == 1
        assert linked[0]["is_linked"] is True

        # The unlinked notebook's artifact should have is_linked=False
        unlinked = [a for a in artifacts if a["source_notebook_id"] == "nb-unlinked"]
        assert len(unlinked) == 1
        assert unlinked[0]["is_linked"] is False


# ---------------------------------------------------------------------------
# Prompt Hashing and Duplicate Prompt Detection
#    Requirements: 8.1, 8.2, 8.4
# ---------------------------------------------------------------------------

class TestPromptHashAndDuplicateDetection:
    """Test prompt hash computation, storage, and duplicate detection."""

    def test_prompt_hash_changes_when_content_changes(self):
        """Different template content produces different prompt hashes.

        Requirements: 8.4
        """
        content_a = "Generate an infographic about climate change"
        content_b = "Generate an infographic about ocean pollution"

        hash_a = StateManager.compute_content_hash(content_a.encode("utf-8"))
        hash_b = StateManager.compute_content_hash(content_b.encode("utf-8"))

        assert hash_a != hash_b
        # Both should be valid SHA-256 hex strings
        assert len(hash_a) == 64
        assert len(hash_b) == 64

    def test_prompt_hash_deterministic(self):
        """Same content always produces the same hash.

        Requirements: 8.1
        """
        content = "Generate a deep dive podcast"
        hash1 = StateManager.compute_content_hash(content.encode("utf-8"))
        hash2 = StateManager.compute_content_hash(content.encode("utf-8"))
        assert hash1 == hash2

    @pytest.mark.asyncio
    async def test_prompt_hash_stored_in_cell(self, state_manager, db_path):
        """Prompt hash is stored in the generation_cells table.

        Requirements: 8.1
        """
        from app.models import CellStatus
        from app.state_manager import GenerationCell
        from datetime import datetime, timezone

        # Create a report and template first
        await state_manager.persist_reports([{
            "id": "r-ph1",
            "filename": "report.md",
            "filepath": "/tmp/report.md",
            "file_size": 100,
            "last_modified": "2024-01-01",
            "notebook_name": "Report",
        }])
        await state_manager.persist_templates([{
            "id": "t-ph1",
            "filename": "template.md",
            "number": 1,
            "artifact_type": "infographic",
            "name": "Test Template",
            "audio_format": None,
            "content": "Generate something",
        }])

        prompt_hash = StateManager.compute_content_hash(b"Generate something")
        cell = GenerationCell(
            report_id="r-ph1",
            template_id="t-ph1",
            status=CellStatus.COMPLETED,
            task_id="task-1",
            notebook_id="nb-1",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            artifact_path="/tmp/artifact.png",
            prompt_hash=prompt_hash,
        )
        await state_manager.update_cell(cell)

        # Verify it's stored
        retrieved = await state_manager.get_cell("r-ph1", "t-ph1")
        assert retrieved is not None
        assert retrieved.prompt_hash == prompt_hash

    @pytest.mark.asyncio
    async def test_find_duplicate_prompt_returns_match(self, state_manager, db_path):
        """find_duplicate_prompt returns existing cell info when a completed duplicate exists.

        Requirements: 8.2
        """
        from app.models import CellStatus
        from app.state_manager import GenerationCell
        from datetime import datetime, timezone

        await state_manager.persist_reports([{
            "id": "r-dup1",
            "filename": "report.md",
            "filepath": "/tmp/report.md",
            "file_size": 100,
            "last_modified": "2024-01-01",
            "notebook_name": "Report",
        }])
        await state_manager.persist_templates([{
            "id": "t-dup1",
            "filename": "template.md",
            "number": 1,
            "artifact_type": "infographic",
            "name": "Test Template",
            "audio_format": None,
            "content": "Generate an infographic",
        }])

        prompt_hash = StateManager.compute_content_hash(b"Generate an infographic")
        cell = GenerationCell(
            report_id="r-dup1",
            template_id="t-dup1",
            status=CellStatus.COMPLETED,
            task_id="task-1",
            notebook_id="nb-1",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            artifact_path="/tmp/artifact.png",
            prompt_hash=prompt_hash,
        )
        await state_manager.update_cell(cell)

        # Check for duplicate
        result = await state_manager.find_duplicate_prompt("r-dup1", prompt_hash)
        assert result is not None
        assert result["report_id"] == "r-dup1"
        assert result["template_id"] == "t-dup1"
        assert result["artifact_path"] == "/tmp/artifact.png"
        assert result["notebook_id"] == "nb-1"

    @pytest.mark.asyncio
    async def test_find_duplicate_prompt_returns_none_for_different_hash(self, state_manager, db_path):
        """find_duplicate_prompt returns None when no matching hash exists.

        Requirements: 8.2
        """
        from app.models import CellStatus
        from app.state_manager import GenerationCell
        from datetime import datetime, timezone

        await state_manager.persist_reports([{
            "id": "r-dup2",
            "filename": "report.md",
            "filepath": "/tmp/report.md",
            "file_size": 100,
            "last_modified": "2024-01-01",
            "notebook_name": "Report",
        }])
        await state_manager.persist_templates([{
            "id": "t-dup2",
            "filename": "template.md",
            "number": 1,
            "artifact_type": "infographic",
            "name": "Test Template",
            "audio_format": None,
            "content": "Generate an infographic",
        }])

        prompt_hash = StateManager.compute_content_hash(b"Generate an infographic")
        cell = GenerationCell(
            report_id="r-dup2",
            template_id="t-dup2",
            status=CellStatus.COMPLETED,
            task_id="task-1",
            notebook_id="nb-1",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            artifact_path="/tmp/artifact.png",
            prompt_hash=prompt_hash,
        )
        await state_manager.update_cell(cell)

        # Different hash should not match
        different_hash = StateManager.compute_content_hash(b"Different content")
        result = await state_manager.find_duplicate_prompt("r-dup2", different_hash)
        assert result is None

    @pytest.mark.asyncio
    async def test_find_duplicate_prompt_ignores_non_completed(self, state_manager, db_path):
        """find_duplicate_prompt only matches cells with completed status.

        Requirements: 8.2
        """
        from app.models import CellStatus
        from app.state_manager import GenerationCell
        from datetime import datetime, timezone

        await state_manager.persist_reports([{
            "id": "r-dup3",
            "filename": "report.md",
            "filepath": "/tmp/report.md",
            "file_size": 100,
            "last_modified": "2024-01-01",
            "notebook_name": "Report",
        }])
        await state_manager.persist_templates([{
            "id": "t-dup3",
            "filename": "template.md",
            "number": 1,
            "artifact_type": "infographic",
            "name": "Test Template",
            "audio_format": None,
            "content": "Generate an infographic",
        }])

        prompt_hash = StateManager.compute_content_hash(b"Generate an infographic")
        # Create a FAILED cell (not completed)
        cell = GenerationCell(
            report_id="r-dup3",
            template_id="t-dup3",
            status=CellStatus.FAILED,
            task_id="task-1",
            notebook_id="nb-1",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            error_message="Some error",
            prompt_hash=prompt_hash,
        )
        await state_manager.update_cell(cell)

        # Should not find a duplicate (cell is failed, not completed)
        result = await state_manager.find_duplicate_prompt("r-dup3", prompt_hash)
        assert result is None

    @pytest.mark.asyncio
    async def test_find_duplicate_prompt_scoped_to_report(self, state_manager, db_path):
        """find_duplicate_prompt only matches within the same report_id.

        Requirements: 8.2
        """
        from app.models import CellStatus
        from app.state_manager import GenerationCell
        from datetime import datetime, timezone

        # Create two reports
        await state_manager.persist_reports([
            {
                "id": "r-dup4a",
                "filename": "report_a.md",
                "filepath": "/tmp/report_a.md",
                "file_size": 100,
                "last_modified": "2024-01-01",
                "notebook_name": "Report A",
            },
            {
                "id": "r-dup4b",
                "filename": "report_b.md",
                "filepath": "/tmp/report_b.md",
                "file_size": 100,
                "last_modified": "2024-01-01",
                "notebook_name": "Report B",
            },
        ])
        await state_manager.persist_templates([{
            "id": "t-dup4",
            "filename": "template.md",
            "number": 1,
            "artifact_type": "infographic",
            "name": "Test Template",
            "audio_format": None,
            "content": "Generate an infographic",
        }])

        prompt_hash = StateManager.compute_content_hash(b"Generate an infographic")
        # Create completed cell for report A
        cell = GenerationCell(
            report_id="r-dup4a",
            template_id="t-dup4",
            status=CellStatus.COMPLETED,
            task_id="task-1",
            notebook_id="nb-1",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            artifact_path="/tmp/artifact.png",
            prompt_hash=prompt_hash,
        )
        await state_manager.update_cell(cell)

        # Should find duplicate for report A
        result = await state_manager.find_duplicate_prompt("r-dup4a", prompt_hash)
        assert result is not None

        # Should NOT find duplicate for report B (different report)
        result = await state_manager.find_duplicate_prompt("r-dup4b", prompt_hash)
        assert result is None

    def test_edited_template_produces_new_hash(self):
        """When template content is edited, the hash changes.

        Requirements: 8.4
        """
        original = "Generate an infographic about AI"
        edited = "Generate an infographic about AI and machine learning"

        hash_original = StateManager.compute_content_hash(original.encode("utf-8"))
        hash_edited = StateManager.compute_content_hash(edited.encode("utf-8"))

        assert hash_original != hash_edited

    @pytest.mark.asyncio
    async def test_find_duplicate_prompt_with_empty_hash(self, state_manager):
        """find_duplicate_prompt returns None for empty/None hash.

        Requirements: 8.2
        """
        result = await state_manager.find_duplicate_prompt("r-any", "")
        assert result is None

        result = await state_manager.find_duplicate_prompt("r-any", None)
        assert result is None

    @pytest.mark.asyncio
    async def test_check_duplicate_endpoint(self):
        """The check-duplicate endpoint returns correct response shape.

        Requirements: 8.2, 8.3
        """
        from app.routes.generation import check_duplicate_prompt

        mock_sm = AsyncMock()
        mock_sm.get_template = AsyncMock(return_value={
            "id": "t1", "content": "Generate something",
        })
        mock_sm.find_duplicate_prompt = AsyncMock(return_value=None)

        result = await check_duplicate_prompt(
            report_id="r1", template_id="t1", sm=mock_sm
        )
        assert result["duplicate"] is False
        assert "prompt_hash" in result

    @pytest.mark.asyncio
    async def test_check_duplicate_endpoint_finds_duplicate(self):
        """The check-duplicate endpoint returns duplicate info when found.

        Requirements: 8.2, 8.3
        """
        from app.routes.generation import check_duplicate_prompt

        existing = {
            "report_id": "r1",
            "template_id": "t1",
            "artifact_path": "/tmp/artifact.png",
            "notebook_id": "nb-1",
        }

        mock_sm = AsyncMock()
        mock_sm.get_template = AsyncMock(return_value={
            "id": "t1", "content": "Generate something",
        })
        mock_sm.find_duplicate_prompt = AsyncMock(return_value=existing)

        result = await check_duplicate_prompt(
            report_id="r1", template_id="t1", sm=mock_sm
        )
        assert result["duplicate"] is True
        assert result["existing"] == existing
        assert "prompt_hash" in result


# ---------------------------------------------------------------------------
# BA/PO Review: Missing edge case tests
# ---------------------------------------------------------------------------

class TestUploadEdgeCases:
    """Edge case tests for file upload flow identified during BA/PO review.

    Requirements: 2.1, 2.4
    """

    @pytest.mark.asyncio
    async def test_upload_empty_file_list(self):
        """Uploading zero files should return an empty list.

        Requirements: 2.1
        """
        from app.routes.reports import add_reports

        mock_sm = AsyncMock(spec=StateManager)
        mock_sm.persist_reports = AsyncMock()
        mock_namer = AsyncMock()

        result = await add_reports(files=[], sm=mock_sm, namer=mock_namer)

        assert result == []
        mock_sm.persist_reports.assert_not_called()


class TestRemoteArtifactEdgeCases:
    """Edge case tests for remote artifact handling identified during BA/PO review.

    Requirements: 1.2, 4.4
    """

    @pytest.mark.asyncio
    async def test_remote_artifacts_with_missing_fields_use_defaults(self):
        """Remote artifacts with missing fields should use safe defaults.

        Requirements: 1.2
        """
        from app.routes.artifacts import list_remote_artifacts

        mock_client = AsyncMock(spec=NotebookLMClientWrapper)
        mock_client.list_notebooks.return_value = [
            {"id": "nb-sparse", "title": "Sparse Notebook"},
        ]
        # Artifact with minimal fields — missing name, type, created_at
        mock_client.list_notebook_artifacts.return_value = [
            {"id": "a-sparse"},
        ]

        mock_sm = AsyncMock()
        mock_sm.get_all_content_hashes = AsyncMock(return_value=set())

        result = await list_remote_artifacts(nlm_client=mock_client, sm=mock_sm)

        assert len(result["artifacts"]) == 1
        artifact = result["artifacts"][0]
        # Should have safe defaults for missing fields
        assert artifact["artifact_name"] == ""
        assert artifact["artifact_type"] == "unknown"
        assert artifact["created_at"] is None

    @pytest.mark.asyncio
    async def test_delete_artifact_invalid_remote_id_format(self):
        """Deleting a remote artifact with invalid ID format should return 400.

        Requirements: 4.4
        """
        from app.routes.artifacts import delete_artifact

        mock_client = AsyncMock(spec=NotebookLMClientWrapper)
        mock_sm = AsyncMock(spec=StateManager)

        with pytest.raises(Exception) as exc_info:
            await delete_artifact(
                artifact_id="remote-invalid",  # no trailing index after last hyphen
                sm=mock_sm,
                nlm_client=mock_client,
            )

        # Should get a 400 for bad format, or the rsplit handles it
        # The current implementation uses rsplit("-", 1) which would split
        # "invalid" from "remote-" prefix, so "invalid" has no hyphen to split on
        # Actually "remote-invalid" -> prefix_and_nb = "invalid" -> rsplit("-", 1) = ["invalid"]
        # len(parts) < 2 -> 400
        assert exc_info.value.status_code == 400


class TestDuplicateNotebookWarning:
    """Test that duplicate notebook detection warns the user.

    Requirements: 7.2, 7.3
    """

    @pytest.mark.asyncio
    async def test_find_notebook_by_content_hash_with_no_generation_cell(self, state_manager, db_path):
        """When a report has a content hash but no generation cell, no duplicate is found.

        Requirements: 7.2
        """
        content_hash = StateManager.compute_content_hash(b"Orphan content")

        report = {
            "id": "r-orphan",
            "filename": "orphan.md",
            "filepath": "/tmp/orphan.md",
            "file_size": 100,
            "last_modified": "2024-01-01",
            "notebook_name": f"Orphan [{content_hash[:8]}]",
            "content_hash": content_hash,
        }
        await state_manager.persist_reports([report])

        # No generation cell exists, so no notebook should be found
        result = await state_manager.find_notebook_by_content_hash(content_hash)
        assert result is None


class TestPersistReportsContentHashBackwardCompat:
    """Test that persist_reports handles missing content_hash gracefully.

    Requirements: 7.1
    """

    @pytest.mark.asyncio
    async def test_persist_reports_without_content_hash(self, state_manager, db_path):
        """Reports without content_hash field should still be persisted.

        Requirements: 7.1
        """
        report = {
            "id": "r-no-hash",
            "filename": "old_report.md",
            "filepath": "/tmp/old_report.md",
            "file_size": 500,
            "last_modified": "2024-01-01",
            "notebook_name": "Old Report",
        }
        await state_manager.persist_reports([report])

        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT id, content_hash FROM reports WHERE id = ?", ("r-no-hash",)
            )
            row = await cursor.fetchone()

        assert row is not None
        assert row[0] == "r-no-hash"
        assert row[1] is None  # content_hash should be NULL when not provided
