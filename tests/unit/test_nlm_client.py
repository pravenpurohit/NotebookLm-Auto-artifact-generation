"""Unit tests for NotebookLMClientWrapper.

Covers SDK wrapper error handling, _ensure_client guard,
and async method behavior (Section 7, 11.4).
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.nlm_client import NotebookLMClientError, NotebookLMClientWrapper, SessionCredentials


@pytest.fixture
def wrapper():
    """Create a wrapper with no real SDK client."""
    creds = SessionCredentials()
    w = NotebookLMClientWrapper(creds)
    w._client = None  # Ensure no SDK
    return w


@pytest.fixture
def wrapper_with_mock_client():
    """Create a wrapper with a mocked SDK client."""
    creds = SessionCredentials(cookies={"sid": "x"}, csrf_token="t", session_id="s")
    w = NotebookLMClientWrapper(creds)
    mock_client = MagicMock()
    w._client = mock_client
    return w, mock_client


class TestEnsureClient:
    """_ensure_client should raise NotebookLMClientError when SDK is unavailable."""

    @pytest.mark.asyncio
    async def test_create_notebook_raises_without_client(self, wrapper):
        with pytest.raises(NotebookLMClientError, match="not available"):
            await wrapper.create_notebook("test", "/test.pdf")

    @pytest.mark.asyncio
    async def test_submit_generation_raises_without_client(self, wrapper):
        with pytest.raises(NotebookLMClientError, match="not available"):
            await wrapper.submit_generation("nb-1", "prompt", "infographic")

    @pytest.mark.asyncio
    async def test_poll_status_raises_without_client(self, wrapper):
        with pytest.raises(NotebookLMClientError, match="not available"):
            await wrapper.poll_status("task-1")

    @pytest.mark.asyncio
    async def test_download_artifact_raises_without_client(self, wrapper):
        with pytest.raises(NotebookLMClientError, match="not available"):
            await wrapper.download_artifact("task-1", "/out/file.png")

    @pytest.mark.asyncio
    async def test_list_notebooks_raises_without_client(self, wrapper):
        with pytest.raises(NotebookLMClientError, match="not available"):
            await wrapper.list_notebooks()


class TestDownloadArtifact:
    """Test download_artifact creates directories and returns abs path."""

    @pytest.mark.asyncio
    async def test_download_creates_dirs_and_returns_path(self, tmp_path):
        creds = SessionCredentials(cookies={"sid": "x"}, csrf_token="t", session_id="s")
        wrapper = NotebookLMClientWrapper(creds)

        mock_client = MagicMock()
        mock_client.download_artifact = AsyncMock()
        wrapper._client = mock_client

        output = str(tmp_path / "sub" / "artifact.png")
        result = await wrapper.download_artifact("task-1", output)

        mock_client.download_artifact.assert_called_once_with(
            task_id="task-1", output_path=output
        )
        assert result.endswith("artifact.png")


class TestSDKExceptionWrapping:
    """SDK exceptions should be wrapped in NotebookLMClientError."""

    @pytest.mark.asyncio
    async def test_create_notebook_wraps_sdk_error(self):
        creds = SessionCredentials(cookies={"sid": "x"}, csrf_token="t", session_id="s")
        wrapper = NotebookLMClientWrapper(creds)

        mock_client = MagicMock()
        mock_client.create_notebook = AsyncMock(side_effect=RuntimeError("SDK boom"))
        wrapper._client = mock_client

        with pytest.raises(NotebookLMClientError, match="Failed to create notebook"):
            await wrapper.create_notebook("test", "/test.pdf")

    @pytest.mark.asyncio
    async def test_list_notebooks_wraps_sdk_error(self):
        creds = SessionCredentials(cookies={"sid": "x"}, csrf_token="t", session_id="s")
        wrapper = NotebookLMClientWrapper(creds)

        mock_client = MagicMock()
        mock_client.list_notebooks = AsyncMock(side_effect=RuntimeError("network"))
        wrapper._client = mock_client

        with pytest.raises(NotebookLMClientError, match="Failed to list notebooks"):
            await wrapper.list_notebooks()
