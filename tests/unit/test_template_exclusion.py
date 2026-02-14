"""Unit tests for template exclusion toggle endpoint and StateManager method.

Requirements: 3.4
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import aiosqlite

from fastapi.testclient import TestClient

from app.state_manager import StateManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def state_manager(tmp_path):
    sm = StateManager(db_path=str(tmp_path / "test.db"))
    await sm.init_db()
    return sm


async def _seed_template(sm: StateManager, template_id: str = "t1", is_excluded: bool = False):
    """Insert a template row for testing."""
    await sm.persist_templates([{
        "id": template_id,
        "filename": "02_Infographic_Test.md",
        "number": 2,
        "artifact_type": "infographic",
        "name": "Test",
        "audio_format": None,
        "content": "prompt content",
        "content_edited": False,
        "is_excluded": is_excluded,
    }])


# ---------------------------------------------------------------------------
# StateManager.update_template_exclusion
# ---------------------------------------------------------------------------


class TestUpdateTemplateExclusion:
    """Test the StateManager method directly."""

    @pytest.mark.asyncio
    async def test_exclude_template(self, state_manager):
        await _seed_template(state_manager, "t1", is_excluded=False)

        result = await state_manager.update_template_exclusion("t1", True)
        assert result is True

        t = await state_manager.get_template("t1")
        assert t["is_excluded"] is True

    @pytest.mark.asyncio
    async def test_include_template(self, state_manager):
        await _seed_template(state_manager, "t1", is_excluded=True)

        result = await state_manager.update_template_exclusion("t1", False)
        assert result is True

        t = await state_manager.get_template("t1")
        assert t["is_excluded"] is False

    @pytest.mark.asyncio
    async def test_nonexistent_template_returns_false(self, state_manager):
        result = await state_manager.update_template_exclusion("no-such-id", True)
        assert result is False

    @pytest.mark.asyncio
    async def test_idempotent_exclude(self, state_manager):
        """Setting is_excluded=True twice should leave it True."""
        await _seed_template(state_manager, "t1", is_excluded=True)

        await state_manager.update_template_exclusion("t1", True)
        t = await state_manager.get_template("t1")
        assert t["is_excluded"] is True

    @pytest.mark.asyncio
    async def test_idempotent_include(self, state_manager):
        """Setting is_excluded=False twice should leave it False."""
        await _seed_template(state_manager, "t1", is_excluded=False)

        await state_manager.update_template_exclusion("t1", False)
        t = await state_manager.get_template("t1")
        assert t["is_excluded"] is False


# ---------------------------------------------------------------------------
# PATCH /api/templates/{template_id}/exclude endpoint
# ---------------------------------------------------------------------------


class TestExcludeEndpoint:
    """Test the HTTP endpoint via TestClient."""

    def _create_app(self, db_path: str):
        import app.main as main_mod
        original = main_mod.DB_PATH
        main_mod.DB_PATH = db_path
        from app.main import create_app
        app = create_app()
        main_mod.DB_PATH = original
        return app

    def test_exclude_returns_200(self, tmp_path):
        import app.main as main_mod
        db_path = str(tmp_path / "test.db")
        original = main_mod.DB_PATH
        main_mod.DB_PATH = db_path
        try:
            from app.main import create_app
            app = create_app()
            with TestClient(app) as client:
                # Upload a template first
                resp = client.post(
                    "/api/templates",
                    files=[("file", ("02_Infographic_Test.md", b"# prompt", "text/markdown"))],
                )
                assert resp.status_code == 201
                tid = resp.json()["id"]

                # Exclude it
                resp = client.patch(
                    f"/api/templates/{tid}/exclude",
                    json={"is_excluded": True},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["is_excluded"] is True
                assert data["template_id"] == tid

                # Verify via list
                templates = client.get("/api/templates").json()
                match = [t for t in templates if t["id"] == tid]
                assert len(match) == 1
                assert match[0]["is_excluded"] is True
        finally:
            main_mod.DB_PATH = original

    def test_exclude_nonexistent_returns_404(self, tmp_path):
        import app.main as main_mod
        db_path = str(tmp_path / "test.db")
        original = main_mod.DB_PATH
        main_mod.DB_PATH = db_path
        try:
            from app.main import create_app
            app = create_app()
            with TestClient(app) as client:
                resp = client.patch(
                    "/api/templates/nonexistent/exclude",
                    json={"is_excluded": True},
                )
                assert resp.status_code == 404
        finally:
            main_mod.DB_PATH = original

    def test_exclude_invalid_body_returns_422(self, tmp_path):
        import app.main as main_mod
        db_path = str(tmp_path / "test.db")
        original = main_mod.DB_PATH
        main_mod.DB_PATH = db_path
        try:
            from app.main import create_app
            app = create_app()
            with TestClient(app) as client:
                resp = client.patch(
                    "/api/templates/some-id/exclude",
                    json={"wrong_field": True},
                )
                assert resp.status_code == 422
        finally:
            main_mod.DB_PATH = original


# ---------------------------------------------------------------------------
# Template upload tests with sample testdata (AC 2.2–2.8)
# ---------------------------------------------------------------------------

import os

TESTDATA_DIR = os.path.join(os.path.dirname(__file__), "..", "testdata")


class TestTemplateUpload:
    """Test POST /api/templates with real sample files."""

    def _create_app(self, db_path: str):
        import app.main as main_mod
        original = main_mod.DB_PATH
        main_mod.DB_PATH = db_path
        from app.main import create_app
        app = create_app()
        main_mod.DB_PATH = original
        return app

    def test_upload_infographic_template(self, tmp_path):
        """Upload 02_Infographic sample file — should parse type as infographic."""
        db_path = str(tmp_path / "test.db")
        app = self._create_app(db_path)
        fpath = os.path.join(TESTDATA_DIR, "02_Infographic_One-page Map of a Complex Topic.md")
        with open(fpath, "rb") as f:
            content = f.read()
        with TestClient(app) as client:
            resp = client.post(
                "/api/templates",
                files=[("file", ("02_Infographic_One-page Map of a Complex Topic.md", content, "text/markdown"))],
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["artifact_type"] == "infographic"
            assert data["number"] == 2

    def test_upload_audio_template(self, tmp_path):
        """Upload 07_Audio_DeepDive sample file — should parse type as audio."""
        db_path = str(tmp_path / "test.db")
        app = self._create_app(db_path)
        fpath = os.path.join(TESTDATA_DIR, "07_Audio_DeepDive.md")
        with open(fpath, "rb") as f:
            content = f.read()
        with TestClient(app) as client:
            resp = client.post(
                "/api/templates",
                files=[("file", ("07_Audio_DeepDive.md", content, "text/markdown"))],
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["artifact_type"] == "audio"
            assert data["number"] == 7

    def test_upload_video_template(self, tmp_path):
        """Upload 11_Video sample file — should parse type as video."""
        db_path = str(tmp_path / "test.db")
        app = self._create_app(db_path)
        fpath = os.path.join(TESTDATA_DIR, "11_Video_Teach a Beginner.md")
        with open(fpath, "rb") as f:
            content = f.read()
        with TestClient(app) as client:
            resp = client.post(
                "/api/templates",
                files=[("file", ("11_Video_Teach a Beginner.md", content, "text/markdown"))],
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["artifact_type"] == "video"
            assert data["number"] == 11

    def test_upload_duplicate_filename_updates(self, tmp_path):
        """Uploading same filename twice should update content, not create duplicate (AC 2.5)."""
        db_path = str(tmp_path / "test.db")
        app = self._create_app(db_path)
        with TestClient(app) as client:
            # First upload
            resp1 = client.post(
                "/api/templates",
                files=[("file", ("02_Infographic_Test.md", b"# original", "text/markdown"))],
            )
            assert resp1.status_code == 201
            id1 = resp1.json()["id"]

            # Second upload with same filename
            resp2 = client.post(
                "/api/templates",
                files=[("file", ("02_Infographic_Test.md", b"# updated", "text/markdown"))],
            )
            assert resp2.status_code == 201
            data2 = resp2.json()
            assert data2["id"] == id1  # same template updated
            assert data2["content"] == "# updated"

            # Only one template should exist
            templates = client.get("/api/templates").json()
            matches = [t for t in templates if t["filename"] == "02_Infographic_Test.md"]
            assert len(matches) == 1

    def test_upload_non_md_rejected(self, tmp_path):
        """Non-.md files should be rejected with 400 (AC 2.8)."""
        db_path = str(tmp_path / "test.db")
        app = self._create_app(db_path)
        with TestClient(app) as client:
            resp = client.post(
                "/api/templates",
                files=[("file", ("test.txt", b"content", "text/plain"))],
            )
            assert resp.status_code == 400
            assert ".md" in resp.json()["detail"]
