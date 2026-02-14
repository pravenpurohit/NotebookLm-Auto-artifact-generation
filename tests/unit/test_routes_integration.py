"""Integration tests for routes – FastAPI dependency injection, WebSocket, and SDK call chain.

Covers testing standards Sections 11 (FastAPI & WebSocket Testing),
5 (Mocking), and 7 (Async Test Patterns).
"""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocket
from fastapi.testclient import TestClient

from app.main import create_app
from app.nlm_client import NotebookLMClientWrapper, SessionCredentials
from app.dependencies import get_ws_manager_ws, get_ws_manager
from app.ws_manager import WebSocketManager


# ---------------------------------------------------------------------------
# Section 11.1: Dependency injection parameter types
# ---------------------------------------------------------------------------


class TestDependencyInjectionTypes:
    """Verify dependency functions accept the correct parameter type."""

    def test_get_ws_manager_ws_accepts_websocket_param(self):
        """get_ws_manager_ws should have a 'websocket' parameter typed as WebSocket."""
        sig = inspect.signature(get_ws_manager_ws)
        params = sig.parameters
        assert "websocket" in params, "Should accept 'websocket' parameter"
        annotation = params["websocket"].annotation
        # With `from __future__ import annotations`, annotation is a string
        expected = WebSocket if not isinstance(annotation, str) else "WebSocket"
        assert annotation == expected, (
            f"Parameter should be typed as WebSocket, got {annotation}"
        )

    def test_get_ws_manager_http_accepts_request_param(self):
        """get_ws_manager (HTTP) should have a 'request' parameter, not 'websocket'."""
        sig = inspect.signature(get_ws_manager)
        params = sig.parameters
        assert "request" in params, "HTTP dependency should accept 'request'"
        assert "websocket" not in params, "HTTP dependency should NOT accept 'websocket'"


# ---------------------------------------------------------------------------
# Section 11.2: WebSocket connect/disconnect smoke test
# ---------------------------------------------------------------------------


class TestWebSocketSmoke:
    """WebSocket /ws/grid endpoint smoke tests using TestClient."""

    def _create_test_app(self):
        """Create a test app with mocked lifespan components."""
        import app.main as main_mod

        original = main_mod.DB_PATH
        # Use in-memory DB for speed
        main_mod.DB_PATH = ":memory:"
        app = create_app()
        main_mod.DB_PATH = original
        return app

    def test_websocket_connect_and_disconnect(self, tmp_path):
        """Should be able to connect and disconnect from /ws/grid."""
        import app.main as main_mod

        db_path = str(tmp_path / "ws_test.db")
        original = main_mod.DB_PATH
        main_mod.DB_PATH = db_path

        try:
            app = create_app()
            with TestClient(app) as client:
                with client.websocket_connect("/ws/grid") as ws:
                    # Send a ping and expect an ack
                    ws.send_text("ping")
                    response = ws.receive_json()
                    assert response["type"] == "ack"
                    assert response["data"] == "ping"
        finally:
            main_mod.DB_PATH = original


# ---------------------------------------------------------------------------
# Section 11.3: Non-blocking file I/O in upload handler
# ---------------------------------------------------------------------------


class TestNonBlockingFileIO:
    """Verify that add_reports uses asyncio.to_thread for file writes."""

    @pytest.mark.asyncio
    async def test_add_reports_uses_to_thread(self, tmp_path):
        """The upload handler should call asyncio.to_thread for file I/O."""
        import app.main as main_mod

        db_path = str(tmp_path / "io_test.db")
        original = main_mod.DB_PATH
        main_mod.DB_PATH = db_path

        try:
            app = create_app()

            with TestClient(app) as client:
                with patch("app.routes.reports.asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
                    mock_to_thread.return_value = None
                    response = client.post(
                        "/api/reports",
                        files=[("files", ("test.pdf", b"fake pdf content", "application/pdf"))],
                    )
                    # The handler should have called asyncio.to_thread
                    assert mock_to_thread.called, (
                        "add_reports should use asyncio.to_thread for file writes"
                    )
        finally:
            main_mod.DB_PATH = original


# ---------------------------------------------------------------------------
# Section 11.4: SDK wrapper call chain verification
# ---------------------------------------------------------------------------


class TestSDKCallChain:
    """Verify the full call chain from handler → wrapper → mock SDK."""

    @pytest.mark.asyncio
    async def test_nlm_client_create_notebook_calls_sdk(self):
        """NotebookLMClientWrapper.create_notebook should call the underlying SDK sub-APIs."""
        creds = SessionCredentials(cookies={"sid": "test"}, csrf_token="tok", session_id="sess")
        wrapper = NotebookLMClientWrapper(creds)

        # Mock the internal SDK client with sub-API pattern
        mock_sdk_client = MagicMock()
        mock_notebook = MagicMock()
        mock_notebook.id = "nb-test-123"
        mock_sdk_client.notebooks = MagicMock()
        mock_sdk_client.notebooks.create = AsyncMock(return_value=mock_notebook)
        mock_sdk_client.sources = MagicMock()
        mock_sdk_client.sources.add_file = AsyncMock()
        mock_sdk_client.artifacts = MagicMock()
        wrapper._client = mock_sdk_client

        result = await wrapper.create_notebook(name="Test NB", source_path="/test.pdf")

        assert result == "nb-test-123"
        mock_sdk_client.notebooks.create.assert_called_once_with(title="Test NB")
        mock_sdk_client.sources.add_file.assert_called_once_with(
            notebook_id="nb-test-123", file_path="/test.pdf"
        )

    @pytest.mark.asyncio
    async def test_nlm_client_submit_generation_calls_sdk(self):
        """submit_generation should forward to the SDK client.artifacts.generate_*()."""
        creds = SessionCredentials(cookies={"sid": "test"}, csrf_token="tok", session_id="sess")
        wrapper = NotebookLMClientWrapper(creds)

        mock_sdk_client = MagicMock()
        mock_result = MagicMock()
        mock_result.task_id = "task-abc"
        mock_sdk_client.artifacts = MagicMock()
        mock_sdk_client.artifacts.generate_infographic = AsyncMock(return_value=mock_result)
        mock_sdk_client.notebooks = MagicMock()
        mock_sdk_client.sources = MagicMock()
        wrapper._client = mock_sdk_client

        result = await wrapper.submit_generation(
            notebook_id="nb-1", prompt="test prompt",
            artifact_type="infographic", audio_format=None,
        )

        assert result == "task-abc"
        mock_sdk_client.artifacts.generate_infographic.assert_called_once_with(
            notebook_id="nb-1", instructions="test prompt"
        )

    @pytest.mark.asyncio
    async def test_nlm_client_poll_status_calls_sdk(self):
        """poll_status should call SDK's artifacts.poll_status and return a dict."""
        creds = SessionCredentials(cookies={"sid": "test"}, csrf_token="tok", session_id="sess")
        wrapper = NotebookLMClientWrapper(creds)

        mock_sdk_client = MagicMock()
        mock_status = MagicMock()
        mock_status.status = "completed"
        mock_status.is_in_progress = False
        mock_status.error = None
        mock_status.is_complete = True
        mock_status.is_failed = False
        mock_sdk_client.artifacts = MagicMock()
        mock_sdk_client.artifacts.poll_status = AsyncMock(return_value=mock_status)
        mock_sdk_client.notebooks = MagicMock()
        mock_sdk_client.sources = MagicMock()
        wrapper._client = mock_sdk_client

        result = await wrapper.poll_status("nb-1", "task-xyz")

        assert result["status"] == "completed"
        mock_sdk_client.artifacts.poll_status.assert_called_once_with(
            notebook_id="nb-1", task_id="task-xyz"
        )


# ---------------------------------------------------------------------------
# Section 5.7: Verify mock types match real function sync/async nature
# ---------------------------------------------------------------------------


class TestMockTypeCorrectness:
    """Verify that SDK functions are mocked with the correct sync/async type."""

    def test_nlm_wrapper_methods_are_async(self):
        """All public NLM wrapper methods should be coroutine functions."""
        async_methods = [
            "create_notebook",
            "submit_generation",
            "poll_status",
            "download_artifact",
            "list_notebooks",
        ]
        creds = SessionCredentials()
        wrapper = NotebookLMClientWrapper(creds)

        for method_name in async_methods:
            method = getattr(wrapper, method_name)
            assert inspect.iscoroutinefunction(method), (
                f"NotebookLMClientWrapper.{method_name} should be async "
                f"(use AsyncMock when mocking)"
            )

    def test_auth_manager_methods_are_async(self):
        """AuthManager public methods should be async."""
        from app.auth import AuthManager

        mgr = AuthManager()
        for method_name in ["login", "validate_session", "logout"]:
            method = getattr(mgr, method_name)
            assert inspect.iscoroutinefunction(method), (
                f"AuthManager.{method_name} should be async"
            )


# ---------------------------------------------------------------------------
# Section 7.6/7.8: Verify async wrappers actually return values, not coroutines
# ---------------------------------------------------------------------------


class TestAsyncReturnTypes:
    """Verify that awaiting wrapper methods returns values, not coroutine objects."""

    @pytest.mark.asyncio
    async def test_create_notebook_returns_string_not_coroutine(self):
        """Awaiting create_notebook should return a str, not a coroutine."""
        creds = SessionCredentials(cookies={"sid": "x"}, csrf_token="t", session_id="s")
        wrapper = NotebookLMClientWrapper(creds)

        mock_client = MagicMock()
        mock_nb = MagicMock()
        mock_nb.id = "nb-42"
        mock_client.notebooks = MagicMock()
        mock_client.notebooks.create = AsyncMock(return_value=mock_nb)
        mock_client.sources = MagicMock()
        mock_client.sources.add_file = AsyncMock()
        mock_client.artifacts = MagicMock()
        wrapper._client = mock_client

        result = await wrapper.create_notebook("test", "/test.pdf")
        assert not inspect.iscoroutine(result), "Result should not be a coroutine object"
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_poll_status_returns_dict_not_coroutine(self):
        """Awaiting poll_status should return a dict, not a coroutine."""
        creds = SessionCredentials(cookies={"sid": "x"}, csrf_token="t", session_id="s")
        wrapper = NotebookLMClientWrapper(creds)

        mock_client = MagicMock()
        mock_status = MagicMock()
        mock_status.status = "completed"
        mock_status.is_in_progress = False
        mock_status.error = None
        mock_status.is_complete = True
        mock_status.is_failed = False
        mock_client.artifacts = MagicMock()
        mock_client.artifacts.poll_status = AsyncMock(return_value=mock_status)
        mock_client.notebooks = MagicMock()
        mock_client.sources = MagicMock()
        wrapper._client = mock_client

        result = await wrapper.poll_status("nb-1", "task-1")
        assert not inspect.iscoroutine(result), "Result should not be a coroutine object"
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_list_notebooks_returns_list_not_coroutine(self):
        """Awaiting list_notebooks should return a list, not a coroutine."""
        creds = SessionCredentials(cookies={"sid": "x"}, csrf_token="t", session_id="s")
        wrapper = NotebookLMClientWrapper(creds)

        mock_client = MagicMock()
        mock_client.notebooks = MagicMock()
        mock_client.notebooks.list = AsyncMock(return_value=[])
        mock_client.artifacts = MagicMock()
        mock_client.sources = MagicMock()
        wrapper._client = mock_client

        result = await wrapper.list_notebooks()
        assert not inspect.iscoroutine(result), "Result should not be a coroutine object"
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# ZIP download endpoint (AC 10.4)
# ---------------------------------------------------------------------------


class TestZipDownload:
    """Tests for GET /api/artifacts/download-all."""

    def test_download_all_returns_404_when_no_completed(self, tmp_path):
        """Should return 404 when no completed artifacts exist."""
        import app.main as main_mod

        db_path = str(tmp_path / "zip_test.db")
        original = main_mod.DB_PATH
        main_mod.DB_PATH = db_path
        try:
            app = create_app()
            with TestClient(app) as client:
                resp = client.get("/api/artifacts/download-all")
                assert resp.status_code == 404
        finally:
            main_mod.DB_PATH = original

    def test_download_all_returns_valid_zip(self, tmp_path):
        """Should return a valid ZIP with completed artifact files."""
        import zipfile as zf
        import io
        import app.main as main_mod

        db_path = str(tmp_path / "zip_test.db")

        # Create output dir with a fake artifact
        output_dir = tmp_path / "output" / "infographics"
        output_dir.mkdir(parents=True)
        artifact_file = output_dir / "test.png"
        artifact_file.write_bytes(b"fake png data")

        original = main_mod.DB_PATH
        main_mod.DB_PATH = db_path
        try:
            app = create_app()
            with TestClient(app) as client:
                # Seed data via the app's own state_manager (after lifespan init)
                sm = app.state.state_manager

                import asyncio
                from app.state_manager import GenerationCell, CellStatus

                async def seed():
                    await sm.persist_reports([{
                        "id": "r1", "filename": "report.pdf", "filepath": "/path/report.pdf",
                        "file_size": 100, "last_modified": None, "notebook_name": "report",
                        "notebook_name_edited": False, "created_at": None, "content_hash": None,
                    }])
                    await sm.persist_templates([{
                        "id": "t1", "filename": "02_Test.md", "number": 2,
                        "artifact_type": "infographic", "name": "Test",
                        "audio_format": None, "content": "content",
                        "content_edited": False, "is_excluded": False,
                    }])
                    cell = GenerationCell(
                        report_id="r1", template_id="t1",
                        status=CellStatus.COMPLETED, task_id="task-1",
                        artifact_path=str(artifact_file),
                    )
                    await sm.update_cell(cell)

                asyncio.run(seed())

                with patch("app.routes.artifacts._OUTPUT_BASE", str(tmp_path / "output")):
                    resp = client.get("/api/artifacts/download-all")

                assert resp.status_code == 200
                assert resp.headers["content-type"] == "application/zip"

                buf = io.BytesIO(resp.content)
                with zf.ZipFile(buf) as z:
                    names = z.namelist()
                    assert len(names) >= 1
                    assert any("test.png" in n for n in names)
        finally:
            main_mod.DB_PATH = original


# ---------------------------------------------------------------------------
# Page route tests (AC 11.2, 11.4)
# ---------------------------------------------------------------------------


class TestPageRoutes:
    """Tests for /prompts and /processing page routes."""

    def _create_test_app(self, db_path):
        import app.main as main_mod
        original = main_mod.DB_PATH
        main_mod.DB_PATH = db_path
        app = create_app()
        main_mod.DB_PATH = original
        return app

    def test_prompts_page_returns_200(self, tmp_path):
        """GET /prompts should return 200 with HTML content."""
        db_path = str(tmp_path / "page_test.db")
        app = self._create_test_app(db_path)
        with TestClient(app) as client:
            resp = client.get("/prompts")
            assert resp.status_code == 200
            assert "text/html" in resp.headers["content-type"]
            assert "Prompt Template" in resp.text

    def test_processing_page_returns_200(self, tmp_path):
        """GET /processing should return 200 with HTML content."""
        db_path = str(tmp_path / "page_test.db")
        app = self._create_test_app(db_path)
        with TestClient(app) as client:
            resp = client.get("/processing")
            assert resp.status_code == 200
            assert "text/html" in resp.headers["content-type"]
            assert "Processing" in resp.text
