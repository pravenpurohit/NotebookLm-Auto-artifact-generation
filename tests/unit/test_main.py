"""Unit tests for app/main.py – FastAPI application entry point."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.main import create_app, DB_PATH


class TestCreateApp:
    """Tests for the create_app factory and application structure."""

    def test_create_app_returns_fastapi_instance(self):
        app = create_app()
        assert app.title == "NotebookLM Dashboard"
        assert app.version == "0.1.0"

    def test_router_included(self):
        app = create_app()
        paths = [route.path for route in app.routes]
        assert "/api/auth/login" in paths
        assert "/api/grid" in paths
        assert "/api/reports" in paths

    def test_index_route_registered(self):
        app = create_app()
        paths = [route.path for route in app.routes]
        assert "/" in paths

    def test_files_route_registered(self):
        app = create_app()
        paths = [route.path for route in app.routes]
        assert "/files" in paths

    def test_static_mount_present(self):
        """Static files should be mounted when the static/ directory exists."""
        app = create_app()
        route_paths = [route.path for route in app.routes]
        # StaticFiles mount shows up as "/static" path prefix
        assert any("/static" in p for p in route_paths)


@pytest.mark.asyncio
class TestLifespan:
    """Tests for the application lifespan (startup/shutdown)."""

    async def test_startup_initializes_db(self, tmp_path):
        """The lifespan should create the SQLite database on startup."""
        import app.main as main_mod

        db_path = str(tmp_path / "test.db")
        original = main_mod.DB_PATH

        try:
            main_mod.DB_PATH = db_path
            app = create_app()

            async with app.router.lifespan_context(app):
                assert os.path.isfile(db_path), "Database file should exist after startup"
                # Verify components are wired on app.state
                assert hasattr(app.state, "state_manager")
                assert hasattr(app.state, "auth_manager")
                assert hasattr(app.state, "template_detector")
                assert hasattr(app.state, "artifact_namer")
                assert hasattr(app.state, "nlm_client")
                assert hasattr(app.state, "task_queue")
                assert hasattr(app.state, "ws_manager")
        finally:
            main_mod.DB_PATH = original

    async def test_startup_components_are_correct_types(self, tmp_path):
        """Verify each component on app.state is the expected type."""
        import app.main as main_mod

        db_path = str(tmp_path / "test2.db")
        original = main_mod.DB_PATH

        try:
            main_mod.DB_PATH = db_path

            from app.artifact_namer import ArtifactNamer
            from app.auth import AuthManager
            from app.nlm_client import NotebookLMClientWrapper
            from app.state_manager import StateManager
            from app.task_queue import TaskQueue
            from app.template_detector import TemplateDetector
            from app.ws_manager import WebSocketManager

            app = create_app()
            async with app.router.lifespan_context(app):
                assert isinstance(app.state.state_manager, StateManager)
                assert isinstance(app.state.auth_manager, AuthManager)
                assert isinstance(app.state.template_detector, TemplateDetector)
                assert isinstance(app.state.artifact_namer, ArtifactNamer)
                assert isinstance(app.state.nlm_client, NotebookLMClientWrapper)
                assert isinstance(app.state.task_queue, TaskQueue)
                assert isinstance(app.state.ws_manager, WebSocketManager)
        finally:
            main_mod.DB_PATH = original
