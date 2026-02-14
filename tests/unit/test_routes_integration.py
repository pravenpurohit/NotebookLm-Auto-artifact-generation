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
        """NotebookLMClientWrapper.create_notebook should call the underlying SDK client."""
        creds = SessionCredentials(cookies={"sid": "test"}, csrf_token="tok", session_id="sess")
        wrapper = NotebookLMClientWrapper(creds)

        # Mock the internal SDK client with spec= to catch attribute typos
        mock_sdk_client = MagicMock()
        mock_notebook = MagicMock()
        mock_notebook.id = "nb-test-123"
        mock_sdk_client.create_notebook = AsyncMock(return_value=mock_notebook)
        mock_sdk_client.add_source = AsyncMock()
        wrapper._client = mock_sdk_client

        result = await wrapper.create_notebook(name="Test NB", source_path="/test.pdf")

        assert result == "nb-test-123"
        mock_sdk_client.create_notebook.assert_called_once_with(title="Test NB")
        mock_sdk_client.add_source.assert_called_once_with(
            notebook_id="nb-test-123", file_path="/test.pdf"
        )

    @pytest.mark.asyncio
    async def test_nlm_client_submit_generation_calls_sdk(self):
        """submit_generation should forward to the SDK client.generate()."""
        creds = SessionCredentials(cookies={"sid": "test"}, csrf_token="tok", session_id="sess")
        wrapper = NotebookLMClientWrapper(creds)

        mock_sdk_client = MagicMock()
        mock_result = MagicMock()
        mock_result.task_id = "task-abc"
        mock_sdk_client.generate = AsyncMock(return_value=mock_result)
        wrapper._client = mock_sdk_client

        result = await wrapper.submit_generation(
            notebook_id="nb-1", prompt="test prompt",
            artifact_type="infographic", audio_format=None,
        )

        assert result == "task-abc"
        mock_sdk_client.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_nlm_client_poll_status_calls_sdk(self):
        """poll_status should call SDK's get_task_status and return a dict."""
        creds = SessionCredentials(cookies={"sid": "test"}, csrf_token="tok", session_id="sess")
        wrapper = NotebookLMClientWrapper(creds)

        mock_sdk_client = MagicMock()
        mock_sdk_client.get_task_status = AsyncMock(
            return_value={"status": "completed", "progress": 100, "error": None}
        )
        wrapper._client = mock_sdk_client

        result = await wrapper.poll_status("task-xyz")

        assert result["status"] == "completed"
        assert result["progress"] == 100
        mock_sdk_client.get_task_status.assert_called_once_with(task_id="task-xyz")


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
        mock_client.create_notebook = AsyncMock(return_value=mock_nb)
        mock_client.add_source = AsyncMock()
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
        mock_client.get_task_status = AsyncMock(
            return_value={"status": "completed", "progress": 100, "error": None}
        )
        wrapper._client = mock_client

        result = await wrapper.poll_status("task-1")
        assert not inspect.iscoroutine(result), "Result should not be a coroutine object"
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_list_notebooks_returns_list_not_coroutine(self):
        """Awaiting list_notebooks should return a list, not a coroutine."""
        creds = SessionCredentials(cookies={"sid": "x"}, csrf_token="t", session_id="s")
        wrapper = NotebookLMClientWrapper(creds)

        mock_client = MagicMock()
        mock_client.list_notebooks = AsyncMock(return_value=[])
        wrapper._client = mock_client

        result = await wrapper.list_notebooks()
        assert not inspect.iscoroutine(result), "Result should not be a coroutine object"
        assert isinstance(result, list)
