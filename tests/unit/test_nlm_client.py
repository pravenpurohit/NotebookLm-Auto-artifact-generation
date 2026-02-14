"""Unit tests for NotebookLMClientWrapper.

Covers SDK wrapper error handling, _ensure_client guard, sub-API dispatch,
and async method behavior. Tests use mocked SDK sub-APIs (notebooks,
artifacts, sources) matching the real SDK pattern.

Requirements: 6.1, 6.2, 6.3, 6.6, 1.1, 1.2, 4.3, 5.2
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.nlm_client import (
    NotebookLMClientError,
    NotebookLMClientWrapper,
    SessionCredentials,
    _DOWNLOAD_METHOD_MAP,
    _GENERATE_METHOD_MAP,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_sdk_client() -> MagicMock:
    """Create a mock SDK client with notebooks/artifacts/sources sub-APIs."""
    client = MagicMock()
    client.notebooks = MagicMock()
    client.artifacts = MagicMock()
    client.sources = MagicMock()
    return client


def _make_wrapper(mock_client: MagicMock | None = None) -> NotebookLMClientWrapper:
    """Create a wrapper with an optional mock SDK client injected."""
    creds = SessionCredentials(cookies={"sid": "x"}, csrf_token="t", session_id="s")
    w = NotebookLMClientWrapper(creds)
    w._client = mock_client
    return w


# ---------------------------------------------------------------------------
# _ensure_client guard
# ---------------------------------------------------------------------------


class TestEnsureClient:
    """All public methods should raise NotebookLMClientError when SDK is unavailable."""

    @pytest.mark.asyncio
    async def test_create_notebook_raises(self):
        w = _make_wrapper(None)
        with pytest.raises(NotebookLMClientError, match="not available"):
            await w.create_notebook("test", "/test.pdf")

    @pytest.mark.asyncio
    async def test_submit_generation_raises(self):
        w = _make_wrapper(None)
        with pytest.raises(NotebookLMClientError, match="not available"):
            await w.submit_generation("nb-1", "prompt", "infographic")

    @pytest.mark.asyncio
    async def test_poll_status_raises(self):
        w = _make_wrapper(None)
        with pytest.raises(NotebookLMClientError, match="not available"):
            await w.poll_status("nb-1", "task-1")

    @pytest.mark.asyncio
    async def test_download_artifact_raises(self):
        w = _make_wrapper(None)
        with pytest.raises(NotebookLMClientError, match="not available"):
            await w.download_artifact("nb-1", "infographic", "/out/file.png")

    @pytest.mark.asyncio
    async def test_list_notebooks_raises(self):
        w = _make_wrapper(None)
        with pytest.raises(NotebookLMClientError, match="not available"):
            await w.list_notebooks()

    @pytest.mark.asyncio
    async def test_list_notebook_artifacts_raises(self):
        w = _make_wrapper(None)
        with pytest.raises(NotebookLMClientError, match="not available"):
            await w.list_notebook_artifacts("nb-1")

    @pytest.mark.asyncio
    async def test_delete_artifact_raises(self):
        w = _make_wrapper(None)
        with pytest.raises(NotebookLMClientError, match="not available"):
            await w.delete_artifact("nb-1", "art-1")

    @pytest.mark.asyncio
    async def test_delete_notebook_raises(self):
        w = _make_wrapper(None)
        with pytest.raises(NotebookLMClientError, match="not available"):
            await w.delete_notebook("nb-1")


# ---------------------------------------------------------------------------
# create_notebook
# ---------------------------------------------------------------------------


class TestCreateNotebook:
    """Req 6.1: create notebook + attach source via sub-APIs."""

    @pytest.mark.asyncio
    async def test_creates_and_attaches_source(self):
        mock = _make_mock_sdk_client()
        nb = MagicMock()
        nb.id = "nb-42"
        mock.notebooks.create = AsyncMock(return_value=nb)
        mock.sources.add_file = AsyncMock()
        w = _make_wrapper(mock)

        result = await w.create_notebook("My NB", "/data/report.pdf")

        assert result == "nb-42"
        mock.notebooks.create.assert_called_once_with(title="My NB")
        mock.sources.add_file.assert_called_once_with(
            notebook_id="nb-42", file_path="/data/report.pdf"
        )

    @pytest.mark.asyncio
    async def test_wraps_sdk_error(self):
        mock = _make_mock_sdk_client()
        mock.notebooks.create = AsyncMock(side_effect=RuntimeError("boom"))
        w = _make_wrapper(mock)

        with pytest.raises(NotebookLMClientError, match="Failed to create notebook"):
            await w.create_notebook("test", "/test.pdf")


# ---------------------------------------------------------------------------
# submit_generation — dispatch by artifact_type
# ---------------------------------------------------------------------------


class TestSubmitGeneration:
    """Req 6.1, 6.2: dispatch to correct generate_* method."""

    @pytest.mark.asyncio
    async def test_infographic_dispatch(self):
        mock = _make_mock_sdk_client()
        result_obj = MagicMock()
        result_obj.task_id = "task-info"
        mock.artifacts.generate_infographic = AsyncMock(return_value=result_obj)
        w = _make_wrapper(mock)

        tid = await w.submit_generation("nb-1", "make infographic", "infographic")

        assert tid == "task-info"
        mock.artifacts.generate_infographic.assert_called_once_with(
            notebook_id="nb-1", instructions="make infographic"
        )

    @pytest.mark.asyncio
    async def test_audio_dispatch(self):
        mock = _make_mock_sdk_client()
        result_obj = MagicMock()
        result_obj.task_id = "task-audio"
        mock.artifacts.generate_audio = AsyncMock(return_value=result_obj)
        w = _make_wrapper(mock)

        tid = await w.submit_generation("nb-1", "deep dive", "audio")

        assert tid == "task-audio"
        mock.artifacts.generate_audio.assert_called_once_with(
            notebook_id="nb-1", instructions="deep dive"
        )

    @pytest.mark.asyncio
    async def test_video_dispatch(self):
        mock = _make_mock_sdk_client()
        result_obj = MagicMock()
        result_obj.task_id = "task-vid"
        mock.artifacts.generate_video = AsyncMock(return_value=result_obj)
        w = _make_wrapper(mock)

        tid = await w.submit_generation("nb-1", "teach beginner", "video")

        assert tid == "task-vid"
        mock.artifacts.generate_video.assert_called_once_with(
            notebook_id="nb-1", instructions="teach beginner"
        )

    @pytest.mark.asyncio
    async def test_unsupported_type_raises(self):
        mock = _make_mock_sdk_client()
        w = _make_wrapper(mock)

        with pytest.raises(NotebookLMClientError, match="Unsupported artifact type"):
            await w.submit_generation("nb-1", "prompt", "hologram")

    @pytest.mark.asyncio
    async def test_wraps_sdk_error(self):
        mock = _make_mock_sdk_client()
        mock.artifacts.generate_infographic = AsyncMock(
            side_effect=RuntimeError("API error")
        )
        w = _make_wrapper(mock)

        with pytest.raises(NotebookLMClientError, match="Failed to submit"):
            await w.submit_generation("nb-1", "prompt", "infographic")


# ---------------------------------------------------------------------------
# poll_status
# ---------------------------------------------------------------------------


class TestPollStatus:
    """Req 6.3: poll via artifacts.poll_status(notebook_id, task_id)."""

    @pytest.mark.asyncio
    async def test_returns_status_dict_from_object(self):
        mock = _make_mock_sdk_client()
        status = MagicMock()
        status.status = "completed"
        status.is_in_progress = False
        status.error = None
        status.is_complete = True
        status.is_failed = False
        mock.artifacts.poll_status = AsyncMock(return_value=status)
        w = _make_wrapper(mock)

        result = await w.poll_status("nb-1", "task-1")

        assert result["status"] == "completed"
        assert result["is_complete"] is True
        assert result["is_failed"] is False
        mock.artifacts.poll_status.assert_called_once_with(
            notebook_id="nb-1", task_id="task-1"
        )

    @pytest.mark.asyncio
    async def test_returns_status_dict_from_dict(self):
        mock = _make_mock_sdk_client()
        mock.artifacts.poll_status = AsyncMock(
            return_value={"status": "in_progress", "progress": 50, "error": None}
        )
        w = _make_wrapper(mock)

        result = await w.poll_status("nb-1", "task-1")

        assert result["status"] == "in_progress"
        assert result["progress"] == 50

    @pytest.mark.asyncio
    async def test_wraps_sdk_error(self):
        mock = _make_mock_sdk_client()
        mock.artifacts.poll_status = AsyncMock(side_effect=RuntimeError("timeout"))
        w = _make_wrapper(mock)

        with pytest.raises(NotebookLMClientError, match="Failed to poll"):
            await w.poll_status("nb-1", "task-1")


# ---------------------------------------------------------------------------
# download_artifact — dispatch by artifact_type
# ---------------------------------------------------------------------------


class TestDownloadArtifact:
    """Req 6.6: dispatch to correct download_* method."""

    @pytest.mark.asyncio
    async def test_infographic_download(self, tmp_path):
        mock = _make_mock_sdk_client()
        mock.artifacts.download_infographic = AsyncMock()
        w = _make_wrapper(mock)

        out = str(tmp_path / "sub" / "art.png")
        result = await w.download_artifact("nb-1", "infographic", out)

        mock.artifacts.download_infographic.assert_called_once_with(
            notebook_id="nb-1", output_path=out
        )
        assert result.endswith("art.png")

    @pytest.mark.asyncio
    async def test_audio_download(self, tmp_path):
        mock = _make_mock_sdk_client()
        mock.artifacts.download_audio = AsyncMock()
        w = _make_wrapper(mock)

        out = str(tmp_path / "audio.mp3")
        result = await w.download_artifact("nb-1", "audio", out)

        mock.artifacts.download_audio.assert_called_once_with(
            notebook_id="nb-1", output_path=out
        )
        assert result.endswith("audio.mp3")

    @pytest.mark.asyncio
    async def test_video_download(self, tmp_path):
        mock = _make_mock_sdk_client()
        mock.artifacts.download_video = AsyncMock()
        w = _make_wrapper(mock)

        out = str(tmp_path / "vid.mp4")
        result = await w.download_artifact("nb-1", "video", out)

        mock.artifacts.download_video.assert_called_once_with(
            notebook_id="nb-1", output_path=out
        )
        assert result.endswith("vid.mp4")

    @pytest.mark.asyncio
    async def test_unsupported_type_raises(self, tmp_path):
        mock = _make_mock_sdk_client()
        w = _make_wrapper(mock)

        with pytest.raises(NotebookLMClientError, match="Unsupported artifact type"):
            await w.download_artifact("nb-1", "hologram", str(tmp_path / "x"))

    @pytest.mark.asyncio
    async def test_wraps_sdk_error(self, tmp_path):
        mock = _make_mock_sdk_client()
        mock.artifacts.download_infographic = AsyncMock(
            side_effect=RuntimeError("disk full")
        )
        w = _make_wrapper(mock)

        with pytest.raises(NotebookLMClientError, match="Failed to download"):
            await w.download_artifact("nb-1", "infographic", str(tmp_path / "x.png"))


# ---------------------------------------------------------------------------
# list_notebooks
# ---------------------------------------------------------------------------


class TestListNotebooks:
    """Req 10.1: list notebooks via notebooks.list()."""

    @pytest.mark.asyncio
    async def test_returns_list_of_dicts(self):
        mock = _make_mock_sdk_client()
        nb1 = MagicMock()
        nb1.id = "nb-1"
        nb1.title = "Report A"
        nb2 = MagicMock()
        nb2.id = "nb-2"
        nb2.title = "Report B"
        mock.notebooks.list = AsyncMock(return_value=[nb1, nb2])
        w = _make_wrapper(mock)

        result = await w.list_notebooks()

        assert len(result) == 2
        assert result[0] == {"id": "nb-1", "title": "Report A"}
        assert result[1] == {"id": "nb-2", "title": "Report B"}

    @pytest.mark.asyncio
    async def test_handles_dict_items(self):
        mock = _make_mock_sdk_client()
        mock.notebooks.list = AsyncMock(
            return_value=[{"id": "nb-1", "title": "X"}]
        )
        w = _make_wrapper(mock)

        result = await w.list_notebooks()
        assert result == [{"id": "nb-1", "title": "X"}]

    @pytest.mark.asyncio
    async def test_wraps_sdk_error(self):
        mock = _make_mock_sdk_client()
        mock.notebooks.list = AsyncMock(side_effect=RuntimeError("network"))
        w = _make_wrapper(mock)

        with pytest.raises(NotebookLMClientError, match="Failed to list notebooks"):
            await w.list_notebooks()


# ---------------------------------------------------------------------------
# list_notebook_artifacts
# ---------------------------------------------------------------------------


class TestListNotebookArtifacts:
    """Req 1.1, 1.2: list artifacts via artifacts.list(notebook_id)."""

    @pytest.mark.asyncio
    async def test_returns_list_of_dicts(self):
        mock = _make_mock_sdk_client()
        a1 = MagicMock()
        a1.id = "art-1"
        a1.title = "Infographic"
        a1.artifact_type = "infographic"
        a1.created_at = "2026-01-01"
        mock.artifacts.list = AsyncMock(return_value=[a1])
        w = _make_wrapper(mock)

        result = await w.list_notebook_artifacts("nb-1")

        assert len(result) == 1
        assert result[0]["id"] == "art-1"
        assert result[0]["name"] == "Infographic"
        assert result[0]["type"] == "infographic"
        mock.artifacts.list.assert_called_once_with(notebook_id="nb-1")

    @pytest.mark.asyncio
    async def test_wraps_sdk_error(self):
        mock = _make_mock_sdk_client()
        mock.artifacts.list = AsyncMock(side_effect=RuntimeError("fail"))
        w = _make_wrapper(mock)

        with pytest.raises(NotebookLMClientError, match="Failed to list artifacts"):
            await w.list_notebook_artifacts("nb-1")


# ---------------------------------------------------------------------------
# delete_artifact / delete_notebook
# ---------------------------------------------------------------------------


class TestDeleteArtifact:
    """Req 4.3: delete via artifacts.delete(notebook_id, artifact_id)."""

    @pytest.mark.asyncio
    async def test_calls_sdk(self):
        mock = _make_mock_sdk_client()
        mock.artifacts.delete = AsyncMock()
        w = _make_wrapper(mock)

        await w.delete_artifact("nb-1", "art-1")

        mock.artifacts.delete.assert_called_once_with(
            notebook_id="nb-1", artifact_id="art-1"
        )

    @pytest.mark.asyncio
    async def test_wraps_sdk_error(self):
        mock = _make_mock_sdk_client()
        mock.artifacts.delete = AsyncMock(side_effect=RuntimeError("denied"))
        w = _make_wrapper(mock)

        with pytest.raises(NotebookLMClientError, match="Failed to delete artifact"):
            await w.delete_artifact("nb-1", "art-1")


class TestDeleteNotebook:
    """Req 5.2: delete via notebooks.delete(notebook_id)."""

    @pytest.mark.asyncio
    async def test_calls_sdk(self):
        mock = _make_mock_sdk_client()
        mock.notebooks.delete = AsyncMock()
        w = _make_wrapper(mock)

        await w.delete_notebook("nb-1")

        mock.notebooks.delete.assert_called_once_with(notebook_id="nb-1")

    @pytest.mark.asyncio
    async def test_wraps_sdk_error(self):
        mock = _make_mock_sdk_client()
        mock.notebooks.delete = AsyncMock(side_effect=RuntimeError("nope"))
        w = _make_wrapper(mock)

        with pytest.raises(NotebookLMClientError, match="Failed to delete notebook"):
            await w.delete_notebook("nb-1")


# ---------------------------------------------------------------------------
# reinit_client
# ---------------------------------------------------------------------------


class TestReinitClient:
    """reinit_client should re-run _init_client."""

    def test_reinit_sets_client_to_none_without_creds(self):
        creds = SessionCredentials()  # no cookies
        w = NotebookLMClientWrapper(creds)
        assert w._client is None

        w.reinit_client()
        assert w._client is None  # still None, no creds
