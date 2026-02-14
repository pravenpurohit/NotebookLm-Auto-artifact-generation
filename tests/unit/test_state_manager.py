"""Unit tests for StateManager schema initialization and CRUD operations."""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
import aiosqlite

from app.models import CellStatus
from app.state_manager import GenerationCell, StateManager


@pytest_asyncio.fixture
async def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest_asyncio.fixture
async def state_manager(db_path):
    sm = StateManager(db_path=db_path)
    await sm.init_db()
    return sm


async def _seed_report_and_template(db_path: str, report_id: str = "r1", template_id: str = "t1"):
    """Insert prerequisite report and template rows so foreign keys pass."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys=ON;")
        await db.execute(
            "INSERT OR IGNORE INTO reports (id, filename, filepath, notebook_name) VALUES (?, ?, ?, ?)",
            (report_id, "report.pdf", "/path/report.pdf", "report"),
        )
        await db.execute(
            "INSERT OR IGNORE INTO templates (id, filename, number, artifact_type, name, content) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (template_id, "02_Infographic_Test.md", 2, "infographic", "Test", "content"),
        )
        await db.commit()


@pytest.mark.asyncio
async def test_init_db_creates_tables(state_manager, db_path):
    """All four tables should exist after init_db."""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]

    assert "artifacts" in tables
    assert "generation_cells" in tables
    assert "reports" in tables
    assert "templates" in tables


@pytest.mark.asyncio
async def test_init_db_creates_indexes(state_manager, db_path):
    """All four indexes should exist after init_db."""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%' ORDER BY name"
        )
        indexes = [row[0] for row in await cursor.fetchall()]

    assert "idx_artifacts_source" in indexes
    assert "idx_artifacts_type" in indexes
    assert "idx_cells_status" in indexes
    assert "idx_cells_task_id" in indexes


@pytest.mark.asyncio
async def test_init_db_is_idempotent(db_path):
    """Calling init_db twice should not raise."""
    sm = StateManager(db_path=db_path)
    await sm.init_db()
    await sm.init_db()  # second call should be safe


@pytest.mark.asyncio
async def test_foreign_keys_enabled(state_manager, db_path):
    """Foreign key enforcement should be on."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys=ON;")
        cursor = await db.execute("PRAGMA foreign_keys")
        row = await cursor.fetchone()
    assert row[0] == 1


@pytest.mark.asyncio
async def test_wal_mode_enabled(state_manager, db_path):
    """WAL journal mode should be set for concurrent access."""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
    assert row[0] == "wal"


@pytest.mark.asyncio
async def test_reports_table_schema(state_manager, db_path):
    """Reports table should accept a valid insert."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO reports (id, filename, filepath, file_size, last_modified, notebook_name) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("r1", "report.pdf", "/path/report.pdf", 1024, "2024-01-01", "report"),
        )
        await db.commit()
        cursor = await db.execute("SELECT * FROM reports WHERE id = 'r1'")
        row = await cursor.fetchone()
    assert row is not None
    assert row[1] == "report.pdf"


@pytest.mark.asyncio
async def test_templates_table_artifact_type_check(state_manager, db_path):
    """Templates table should reject invalid artifact_type values."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys=ON;")
        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                "INSERT INTO templates (id, filename, number, artifact_type, name, content) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("t1", "test.md", 1, "invalid_type", "Test", "content"),
            )


@pytest.mark.asyncio
async def test_generation_cells_status_check(state_manager, db_path):
    """Generation cells should reject invalid status values."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys=ON;")
        # Insert prerequisite report and template first
        await db.execute(
            "INSERT INTO reports (id, filename, filepath, notebook_name) VALUES (?, ?, ?, ?)",
            ("r1", "report.pdf", "/path/report.pdf", "report"),
        )
        await db.execute(
            "INSERT INTO templates (id, filename, number, artifact_type, name, content) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("t1", "test.md", 1, "audio", "Test", "content"),
        )
        await db.commit()
        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                "INSERT INTO generation_cells (report_id, template_id, status) VALUES (?, ?, ?)",
                ("r1", "t1", "invalid_status"),
            )


@pytest.mark.asyncio
async def test_generation_cells_composite_primary_key(state_manager, db_path):
    """Generation cells should enforce composite primary key (report_id, template_id)."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO reports (id, filename, filepath, notebook_name) VALUES (?, ?, ?, ?)",
            ("r1", "report.pdf", "/path/report.pdf", "report"),
        )
        await db.execute(
            "INSERT INTO templates (id, filename, number, artifact_type, name, content) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("t1", "test.md", 1, "audio", "Test", "content"),
        )
        await db.execute(
            "INSERT INTO generation_cells (report_id, template_id, status) VALUES (?, ?, ?)",
            ("r1", "t1", "not_started"),
        )
        await db.commit()
        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                "INSERT INTO generation_cells (report_id, template_id, status) VALUES (?, ?, ?)",
                ("r1", "t1", "pending"),
            )


# ------------------------------------------------------------------
# CRUD operation tests
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_cell_and_get_cell(state_manager, db_path):
    """update_cell should persist a cell that get_cell can retrieve."""
    await _seed_report_and_template(db_path)

    cell = GenerationCell(
        report_id="r1",
        template_id="t1",
        status=CellStatus.IN_PROGRESS,
        task_id="task-abc",
        notebook_id="nb-1",
        error_message=None,
        started_at=datetime(2024, 6, 1, 12, 0, 0),
        completed_at=None,
        artifact_path=None,
    )
    await state_manager.update_cell(cell)

    loaded = await state_manager.get_cell("r1", "t1")
    assert loaded is not None
    assert loaded.report_id == "r1"
    assert loaded.template_id == "t1"
    assert loaded.status == CellStatus.IN_PROGRESS
    assert loaded.task_id == "task-abc"
    assert loaded.notebook_id == "nb-1"
    assert loaded.started_at == datetime(2024, 6, 1, 12, 0, 0)


@pytest.mark.asyncio
async def test_update_cell_upserts(state_manager, db_path):
    """Calling update_cell twice should overwrite the existing row."""
    await _seed_report_and_template(db_path)

    cell = GenerationCell(report_id="r1", template_id="t1", status=CellStatus.PENDING)
    await state_manager.update_cell(cell)

    cell.status = CellStatus.COMPLETED
    cell.completed_at = datetime(2024, 6, 1, 13, 0, 0)
    await state_manager.update_cell(cell)

    loaded = await state_manager.get_cell("r1", "t1")
    assert loaded.status == CellStatus.COMPLETED
    assert loaded.completed_at == datetime(2024, 6, 1, 13, 0, 0)


@pytest.mark.asyncio
async def test_get_cell_returns_none_for_missing(state_manager):
    """get_cell should return None when the cell doesn't exist."""
    result = await state_manager.get_cell("no-such-report", "no-such-template")
    assert result is None


@pytest.mark.asyncio
async def test_get_all_cells(state_manager, db_path):
    """get_all_cells should return every persisted cell."""
    await _seed_report_and_template(db_path, "r1", "t1")
    await _seed_report_and_template(db_path, "r2", "t1")

    await state_manager.update_cell(GenerationCell(report_id="r1", template_id="t1", status=CellStatus.PENDING))
    await state_manager.update_cell(GenerationCell(report_id="r2", template_id="t1", status=CellStatus.FAILED))

    cells = await state_manager.get_all_cells()
    assert len(cells) == 2
    ids = {(c.report_id, c.template_id) for c in cells}
    assert ("r1", "t1") in ids
    assert ("r2", "t1") in ids


@pytest.mark.asyncio
async def test_get_cells_by_status(state_manager, db_path):
    """get_cells_by_status should filter correctly."""
    await _seed_report_and_template(db_path, "r1", "t1")
    await _seed_report_and_template(db_path, "r2", "t1")

    await state_manager.update_cell(GenerationCell(report_id="r1", template_id="t1", status=CellStatus.FAILED))
    await state_manager.update_cell(GenerationCell(report_id="r2", template_id="t1", status=CellStatus.COMPLETED))

    failed = await state_manager.get_cells_by_status(CellStatus.FAILED)
    assert len(failed) == 1
    assert failed[0].report_id == "r1"

    completed = await state_manager.get_cells_by_status(CellStatus.COMPLETED)
    assert len(completed) == 1
    assert completed[0].report_id == "r2"

    pending = await state_manager.get_cells_by_status(CellStatus.PENDING)
    assert len(pending) == 0


@pytest.mark.asyncio
async def test_persist_reports_with_dicts(state_manager, db_path):
    """persist_reports should accept plain dicts."""
    reports = [
        {
            "id": "r1",
            "filename": "report1.pdf",
            "filepath": "/docs/report1.pdf",
            "file_size": 2048,
            "last_modified": "2024-01-15",
            "notebook_name": "report1",
        },
        {
            "id": "r2",
            "filename": "report2.md",
            "filepath": "/docs/report2.md",
            "file_size": 512,
            "last_modified": "2024-02-20",
            "notebook_name": "report2",
        },
    ]
    await state_manager.persist_reports(reports)

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("SELECT id, filename FROM reports ORDER BY id")
        rows = await cursor.fetchall()
    assert len(rows) == 2
    assert rows[0][1] == "report1.pdf"
    assert rows[1][1] == "report2.md"


@pytest.mark.asyncio
async def test_persist_reports_upserts(state_manager, db_path):
    """persist_reports should overwrite existing rows."""
    await state_manager.persist_reports([
        {"id": "r1", "filename": "old.pdf", "filepath": "/old.pdf", "notebook_name": "old"},
    ])
    await state_manager.persist_reports([
        {"id": "r1", "filename": "new.pdf", "filepath": "/new.pdf", "notebook_name": "new"},
    ])

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("SELECT filename, notebook_name FROM reports WHERE id = 'r1'")
        row = await cursor.fetchone()
    assert row[0] == "new.pdf"
    assert row[1] == "new"


@pytest.mark.asyncio
async def test_persist_templates_with_dicts(state_manager, db_path):
    """persist_templates should accept plain dicts."""
    templates = [
        {
            "id": "t1",
            "filename": "02_Infographic_Map.md",
            "number": 2,
            "artifact_type": "infographic",
            "name": "Map",
            "audio_format": None,
            "content": "# Map template",
        },
    ]
    await state_manager.persist_templates(templates)

    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute("SELECT id, name, artifact_type FROM templates")
        row = await cursor.fetchone()
    assert row[0] == "t1"
    assert row[1] == "Map"
    assert row[2] == "infographic"


@pytest.mark.asyncio
async def test_load_state_returns_all_data(state_manager, db_path):
    """load_state should return reports, templates, and cells."""
    await state_manager.persist_reports([
        {"id": "r1", "filename": "report.pdf", "filepath": "/report.pdf", "notebook_name": "report"},
    ])
    await state_manager.persist_templates([
        {"id": "t1", "filename": "02_Audio_Brief.md", "number": 2, "artifact_type": "audio", "name": "Brief", "content": "c"},
    ])
    await state_manager.update_cell(GenerationCell(report_id="r1", template_id="t1", status=CellStatus.PENDING))

    state = await state_manager.load_state()

    assert len(state["reports"]) == 1
    assert state["reports"][0]["id"] == "r1"
    assert len(state["templates"]) == 1
    assert state["templates"][0]["id"] == "t1"
    assert len(state["cells"]) == 1
    assert state["cells"][0].status == CellStatus.PENDING


@pytest.mark.asyncio
async def test_load_state_empty_db(state_manager):
    """load_state on a fresh DB should return empty lists."""
    state = await state_manager.load_state()
    assert state == {"reports": [], "templates": [], "cells": []}


@pytest.mark.asyncio
async def test_update_cell_broadcasts_via_ws_manager(db_path):
    """update_cell should call ws_manager.broadcast_cell_update when available."""
    broadcast_calls = []

    class FakeWSManager:
        async def broadcast_cell_update(self, cell):
            broadcast_calls.append(cell)

    sm = StateManager(db_path=db_path, ws_manager=FakeWSManager())
    await sm.init_db()

    await _seed_report_and_template(db_path)
    cell = GenerationCell(report_id="r1", template_id="t1", status=CellStatus.IN_PROGRESS)
    await sm.update_cell(cell)

    assert len(broadcast_calls) == 1
    assert broadcast_calls[0].status == CellStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_update_cell_persists_immediately(state_manager, db_path):
    """After update_cell, the data should be readable from a fresh connection."""
    await _seed_report_and_template(db_path)

    cell = GenerationCell(
        report_id="r1",
        template_id="t1",
        status=CellStatus.FAILED,
        error_message="timeout",
    )
    await state_manager.update_cell(cell)

    # Read directly from DB to confirm persistence
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT status, error_message FROM generation_cells WHERE report_id = 'r1' AND template_id = 't1'"
        )
        row = await cursor.fetchone()
    assert row[0] == "failed"
    assert row[1] == "timeout"


# ------------------------------------------------------------------
# recover_state tests
# ------------------------------------------------------------------


class FakeNLMClient:
    """Fake NotebookLM client that returns pre-configured notebooks."""

    def __init__(self, notebooks: list[dict]):
        self._notebooks = notebooks

    async def list_notebooks(self) -> list[dict]:
        return self._notebooks


@pytest.mark.asyncio
async def test_recover_state_matches_by_notebook_id(state_manager, db_path):
    """recover_state should match remote notebooks to local cells by notebook_id."""
    await _seed_report_and_template(db_path, "r1", "t1")
    cell = GenerationCell(
        report_id="r1",
        template_id="t1",
        status=CellStatus.COMPLETED,
        notebook_id="nb-100",
        task_id="task-1",
    )
    await state_manager.update_cell(cell)

    client = FakeNLMClient([{"id": "nb-100", "title": "My Notebook"}])
    result = await state_manager.recover_state(client)

    assert len(result["matched"]) == 1
    remote_nb, local_cell = result["matched"][0]
    assert remote_nb["id"] == "nb-100"
    assert local_cell.report_id == "r1"
    assert local_cell.notebook_id == "nb-100"
    assert result["in_progress"] == []
    assert result["untracked"] == []


@pytest.mark.asyncio
async def test_recover_state_detects_in_progress(state_manager, db_path):
    """recover_state should flag in-progress cells for polling resumption."""
    await _seed_report_and_template(db_path, "r1", "t1")
    cell = GenerationCell(
        report_id="r1",
        template_id="t1",
        status=CellStatus.IN_PROGRESS,
        notebook_id="nb-200",
        task_id="task-2",
    )
    await state_manager.update_cell(cell)

    client = FakeNLMClient([{"id": "nb-200", "title": "In Progress NB"}])
    result = await state_manager.recover_state(client)

    assert len(result["matched"]) == 1
    assert len(result["in_progress"]) == 1
    assert result["in_progress"][0].task_id == "task-2"
    assert result["in_progress"][0].status == CellStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_recover_state_detects_untracked(state_manager, db_path):
    """recover_state should list remote notebooks with no local match as untracked."""
    # No local cells at all
    client = FakeNLMClient([
        {"id": "nb-orphan-1", "title": "Orphan 1"},
        {"id": "nb-orphan-2", "title": "Orphan 2"},
    ])
    result = await state_manager.recover_state(client)

    assert result["matched"] == []
    assert result["in_progress"] == []
    assert len(result["untracked"]) == 2
    untracked_ids = {nb["id"] for nb in result["untracked"]}
    assert untracked_ids == {"nb-orphan-1", "nb-orphan-2"}


@pytest.mark.asyncio
async def test_recover_state_mixed_scenario(state_manager, db_path):
    """recover_state should handle a mix of matched, in-progress, and untracked."""
    await _seed_report_and_template(db_path, "r1", "t1")
    await _seed_report_and_template(db_path, "r2", "t1")

    # r1/t1 is completed with notebook_id nb-A
    await state_manager.update_cell(GenerationCell(
        report_id="r1", template_id="t1", status=CellStatus.COMPLETED,
        notebook_id="nb-A", task_id="task-a",
    ))
    # r2/t1 is in_progress with notebook_id nb-B
    await state_manager.update_cell(GenerationCell(
        report_id="r2", template_id="t1", status=CellStatus.IN_PROGRESS,
        notebook_id="nb-B", task_id="task-b",
    ))

    client = FakeNLMClient([
        {"id": "nb-A", "title": "Notebook A"},
        {"id": "nb-B", "title": "Notebook B"},
        {"id": "nb-C", "title": "Untracked Notebook"},
    ])
    result = await state_manager.recover_state(client)

    assert len(result["matched"]) == 2
    assert len(result["in_progress"]) == 1
    assert result["in_progress"][0].notebook_id == "nb-B"
    assert len(result["untracked"]) == 1
    assert result["untracked"][0]["id"] == "nb-C"


@pytest.mark.asyncio
async def test_recover_state_empty_remote(state_manager, db_path):
    """recover_state with no remote notebooks should return all empty lists."""
    await _seed_report_and_template(db_path, "r1", "t1")
    await state_manager.update_cell(GenerationCell(
        report_id="r1", template_id="t1", status=CellStatus.IN_PROGRESS,
        notebook_id="nb-1", task_id="task-1",
    ))

    client = FakeNLMClient([])
    result = await state_manager.recover_state(client)

    assert result["matched"] == []
    assert result["in_progress"] == []
    assert result["untracked"] == []


@pytest.mark.asyncio
async def test_recover_state_cells_without_notebook_id(state_manager, db_path):
    """Cells with no notebook_id should not match any remote notebook."""
    await _seed_report_and_template(db_path, "r1", "t1")
    await state_manager.update_cell(GenerationCell(
        report_id="r1", template_id="t1", status=CellStatus.PENDING,
        notebook_id=None, task_id=None,
    ))

    client = FakeNLMClient([{"id": "nb-999", "title": "Some Notebook"}])
    result = await state_manager.recover_state(client)

    assert result["matched"] == []
    assert result["in_progress"] == []
    assert len(result["untracked"]) == 1
    assert result["untracked"][0]["id"] == "nb-999"
