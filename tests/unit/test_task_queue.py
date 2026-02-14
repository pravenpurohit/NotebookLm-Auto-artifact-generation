"""Unit tests for TaskQueue – enqueue, batch ops, and generation workflow."""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import aiosqlite

from app.models import CellStatus
from app.nlm_client import NotebookLMClientError, NotebookLMClientWrapper, SessionCredentials
from app.state_manager import GenerationCell, StateManager
from app.task_queue import DuplicateTaskError, TaskQueue


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest_asyncio.fixture
async def state_manager(db_path):
    sm = StateManager(db_path=db_path)
    await sm.init_db()
    return sm


async def _seed(db_path: str, report_id: str = "r1", template_id: str = "t1"):
    """Insert prerequisite report and template rows."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys=ON;")
        await db.execute(
            "INSERT OR IGNORE INTO reports (id, filename, filepath, notebook_name) "
            "VALUES (?, ?, ?, ?)",
            (report_id, "report.pdf", "/path/report.pdf", "report"),
        )
        await db.execute(
            "INSERT OR IGNORE INTO templates "
            "(id, filename, number, artifact_type, name, content) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (template_id, "02_Infographic_Test.md", 2, "infographic", "Test", "prompt content"),
        )
        await db.commit()


def _mock_nlm_client() -> NotebookLMClientWrapper:
    """Create a mock NLM client with all async methods stubbed."""
    client = MagicMock(spec=NotebookLMClientWrapper)
    client.create_notebook = AsyncMock(return_value="nb-123")
    client.submit_generation = AsyncMock(return_value="nlm-task-456")
    client.poll_status = AsyncMock(return_value={"status": "completed", "progress": 100, "error": None})
    client.download_artifact = AsyncMock(return_value="/abs/output/infographics/Test.png")
    return client


# ---------------------------------------------------------------------------
# Enqueue & duplicate detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_returns_task_id(state_manager, db_path):
    """enqueue should return a UUID task_id and set cell to in_progress."""
    await _seed(db_path)
    client = _mock_nlm_client()
    tq = TaskQueue(state_manager, client, max_concurrent=2)

    task_id = await tq.enqueue("r1", "t1")

    assert task_id  # non-empty string
    # Wait for background task to finish
    await tq.wait_for("r1", "t1")

    cell = await state_manager.get_cell("r1", "t1")
    assert cell is not None
    assert cell.status in (CellStatus.IN_PROGRESS, CellStatus.COMPLETED)
    # task_id may be updated by the background generation task before we read it
    assert cell.task_id is not None

    await tq.stop_all()


@pytest.mark.asyncio
async def test_enqueue_duplicate_raises(state_manager, db_path):
    """enqueue should raise DuplicateTaskError for an in-progress cell."""
    await _seed(db_path)
    client = _mock_nlm_client()
    # Make poll_status hang so the task stays in_progress
    client.poll_status = AsyncMock(side_effect=asyncio.CancelledError)
    tq = TaskQueue(state_manager, client, max_concurrent=2)

    # First enqueue succeeds
    await tq.enqueue("r1", "t1")

    # Second enqueue should raise
    with pytest.raises(DuplicateTaskError):
        await tq.enqueue("r1", "t1")

    # Cleanup
    await tq.stop_all()


@pytest.mark.asyncio
async def test_enqueue_after_failed_is_allowed(state_manager, db_path):
    """enqueue should succeed for a cell that previously failed."""
    await _seed(db_path)
    client = _mock_nlm_client()
    tq = TaskQueue(state_manager, client, max_concurrent=2)

    # Manually set cell to failed
    cell = GenerationCell(
        report_id="r1", template_id="t1",
        status=CellStatus.FAILED, task_id="old-task",
        error_message="previous error",
    )
    await state_manager.update_cell(cell)

    # Should succeed with a new task_id
    new_task_id = await tq.enqueue("r1", "t1")
    assert new_task_id != "old-task"

    await tq.wait_for("r1", "t1")
    await tq.stop_all()


# ---------------------------------------------------------------------------
# stop_task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_task_sets_stopped(state_manager, db_path):
    """stop_task should cancel the running task and set status to stopped."""
    await _seed(db_path)
    client = _mock_nlm_client()

    # Make poll_status block forever by awaiting a never-resolved future
    async def _hang(*args, **kwargs):
        await asyncio.Future()  # blocks until cancelled

    client.poll_status = AsyncMock(side_effect=_hang)
    tq = TaskQueue(state_manager, client, max_concurrent=2)

    await tq.enqueue("r1", "t1")
    # Give the background task a moment to reach poll
    await asyncio.sleep(0.05)

    await tq.stop_task("r1", "t1")

    cell = await state_manager.get_cell("r1", "t1")
    assert cell is not None
    assert cell.status == CellStatus.STOPPED


# ---------------------------------------------------------------------------
# stop_all
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_all_stops_all_running(state_manager, db_path):
    """stop_all should stop every running task."""
    await _seed(db_path, "r1", "t1")
    await _seed(db_path, "r2", "t2")
    client = _mock_nlm_client()

    async def _hang(*args, **kwargs):
        await asyncio.Future()

    client.poll_status = AsyncMock(side_effect=_hang)
    tq = TaskQueue(state_manager, client, max_concurrent=4)

    await tq.enqueue("r1", "t1")
    await tq.enqueue("r2", "t2")
    await asyncio.sleep(0.05)

    await tq.stop_all()

    for rid, tid in [("r1", "t1"), ("r2", "t2")]:
        cell = await state_manager.get_cell(rid, tid)
        assert cell is not None
        assert cell.status == CellStatus.STOPPED


# ---------------------------------------------------------------------------
# pause / resume
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pause_and_resume(state_manager, db_path):
    """pause should block new tasks from proceeding; resume unblocks."""
    await _seed(db_path)
    client = _mock_nlm_client()
    tq = TaskQueue(state_manager, client, max_concurrent=2)

    # Pause the queue
    await tq.pause()
    assert not tq._resume_event.is_set()

    # Resume the queue
    await tq.resume()
    assert tq._resume_event.is_set()


# ---------------------------------------------------------------------------
# start_all
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_all_enqueues_eligible_cells(state_manager, db_path):
    """start_all should enqueue cells with not_started or pending status."""
    await _seed(db_path, "r1", "t1")
    await _seed(db_path, "r2", "t2")
    client = _mock_nlm_client()
    tq = TaskQueue(state_manager, client, max_concurrent=4)

    cells = [
        GenerationCell(report_id="r1", template_id="t1", status=CellStatus.NOT_STARTED),
        GenerationCell(report_id="r2", template_id="t2", status=CellStatus.PENDING),
    ]
    # Persist initial cells
    for c in cells:
        await state_manager.update_cell(c)

    await tq.start_all(cells)

    # Wait for all tasks to complete
    await tq.wait_for("r1", "t1")
    await tq.wait_for("r2", "t2")

    for rid, tid in [("r1", "t1"), ("r2", "t2")]:
        cell = await state_manager.get_cell(rid, tid)
        assert cell is not None
        # Should be in_progress or completed (since mock completes instantly)
        assert cell.status in (CellStatus.IN_PROGRESS, CellStatus.COMPLETED)

    await tq.stop_all()


@pytest.mark.asyncio
async def test_start_all_skips_non_eligible(state_manager, db_path):
    """start_all should not enqueue cells that are already completed or failed."""
    await _seed(db_path, "r1", "t1")
    client = _mock_nlm_client()
    tq = TaskQueue(state_manager, client, max_concurrent=2)

    cell = GenerationCell(
        report_id="r1", template_id="t1",
        status=CellStatus.COMPLETED, task_id="done-task",
    )
    await state_manager.update_cell(cell)

    await tq.start_all([cell])
    await tq.wait_for("r1", "t1")

    # Status should remain completed
    result = await state_manager.get_cell("r1", "t1")
    assert result is not None
    assert result.status == CellStatus.COMPLETED

    await tq.stop_all()


# ---------------------------------------------------------------------------
# retry_failed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_failed_re_enqueues_failed_cells(state_manager, db_path):
    """retry_failed should re-enqueue all failed cells with new task IDs."""
    await _seed(db_path, "r1", "t1")
    client = _mock_nlm_client()
    tq = TaskQueue(state_manager, client, max_concurrent=2)

    # Set cell to failed
    cell = GenerationCell(
        report_id="r1", template_id="t1",
        status=CellStatus.FAILED, task_id="old-id",
        error_message="some error",
    )
    await state_manager.update_cell(cell)

    await tq.retry_failed()
    await tq.wait_for("r1", "t1")

    result = await state_manager.get_cell("r1", "t1")
    assert result is not None
    assert result.task_id != "old-id"
    assert result.status in (CellStatus.IN_PROGRESS, CellStatus.COMPLETED)

    await tq.stop_all()


# ---------------------------------------------------------------------------
# Generation workflow – error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generation_failure_marks_cell_failed(state_manager, db_path):
    """If NLM client raises, the cell should be marked as failed."""
    await _seed(db_path)
    client = _mock_nlm_client()
    client.create_notebook = AsyncMock(side_effect=NotebookLMClientError("API down"))
    tq = TaskQueue(state_manager, client, max_concurrent=2)

    await tq.enqueue("r1", "t1")
    # Wait for the background task to finish
    await tq.wait_for("r1", "t1")

    cell = await state_manager.get_cell("r1", "t1")
    assert cell is not None
    assert cell.status == CellStatus.FAILED
    assert "API down" in (cell.error_message or "")

    await tq.stop_all()


@pytest.mark.asyncio
async def test_generation_poll_failure_marks_cell_failed(state_manager, db_path):
    """If polling returns a failed status, the cell should be marked failed."""
    await _seed(db_path)
    client = _mock_nlm_client()
    client.poll_status = AsyncMock(return_value={"status": "failed", "error": "gen error"})
    tq = TaskQueue(state_manager, client, max_concurrent=2)

    await tq.enqueue("r1", "t1")
    await tq.wait_for("r1", "t1")

    cell = await state_manager.get_cell("r1", "t1")
    assert cell is not None
    assert cell.status == CellStatus.FAILED
    assert "gen error" in (cell.error_message or "")

    await tq.stop_all()


# ---------------------------------------------------------------------------
# Generation workflow – success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generation_success_marks_completed(state_manager, db_path):
    """A successful generation should mark the cell as completed with artifact path."""
    await _seed(db_path)
    client = _mock_nlm_client()
    tq = TaskQueue(state_manager, client, max_concurrent=2)

    await tq.enqueue("r1", "t1")
    await tq.wait_for("r1", "t1")

    cell = await state_manager.get_cell("r1", "t1")
    assert cell is not None
    assert cell.status == CellStatus.COMPLETED
    assert cell.artifact_path is not None
    assert cell.notebook_id == "nb-123"
    assert cell.error_message is None

    await tq.stop_all()


# ---------------------------------------------------------------------------
# Concurrency control
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_semaphore_limits_concurrency(state_manager, db_path):
    """Only max_concurrent tasks should run simultaneously."""
    await _seed(db_path, "r1", "t1")
    await _seed(db_path, "r2", "t2")
    await _seed(db_path, "r3", "t3")

    concurrent_count = 0
    max_seen = 0
    lock = asyncio.Lock()

    original_create = AsyncMock(return_value="nb-x")

    async def tracking_create(*args, **kwargs):
        nonlocal concurrent_count, max_seen
        async with lock:
            concurrent_count += 1
            if concurrent_count > max_seen:
                max_seen = concurrent_count
        await asyncio.sleep(0.05)
        async with lock:
            concurrent_count -= 1
        return "nb-x"

    client = _mock_nlm_client()
    client.create_notebook = AsyncMock(side_effect=tracking_create)
    tq = TaskQueue(state_manager, client, max_concurrent=2)

    cells = [
        GenerationCell(report_id="r1", template_id="t1", status=CellStatus.NOT_STARTED),
        GenerationCell(report_id="r2", template_id="t2", status=CellStatus.NOT_STARTED),
        GenerationCell(report_id="r3", template_id="t3", status=CellStatus.NOT_STARTED),
    ]
    for c in cells:
        await state_manager.update_cell(c)

    await tq.start_all(cells)

    # Wait for all tasks to complete
    await tq.wait_for("r1", "t1")
    await tq.wait_for("r2", "t2")
    await tq.wait_for("r3", "t3")

    assert max_seen <= 2

    await tq.stop_all()
