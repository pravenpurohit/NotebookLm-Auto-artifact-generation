"""Batch generation routes (Req 9.1–9.5)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_state_manager, get_task_queue
from app.state_manager import StateManager
from app.task_queue import TaskQueue

router = APIRouter(prefix="/api/batch", tags=["batch"])


@router.post("/start")
async def batch_start(
    tq: TaskQueue = Depends(get_task_queue),
    sm: StateManager = Depends(get_state_manager),
):
    """Start all not_started/pending generation tasks (Req 9.1)."""
    cells = await sm.get_all_cells()
    counts = await tq.start_all(cells)
    return {
        "status": "batch_started",
        "enqueued": counts["enqueued"],
        "skipped": counts["skipped"],
    }


@router.post("/pause")
async def batch_pause(tq: TaskQueue = Depends(get_task_queue)):
    """Pause submission of new tasks (Req 9.2)."""
    await tq.pause()
    return {"status": "paused"}


@router.post("/resume")
async def batch_resume(tq: TaskQueue = Depends(get_task_queue)):
    """Resume submitting paused tasks (Req 9.3)."""
    await tq.resume()
    return {"status": "resumed"}


@router.post("/stop")
async def batch_stop(tq: TaskQueue = Depends(get_task_queue)):
    """Stop all in-progress generation tasks (Req 9.4)."""
    await tq.stop_all()
    return {"status": "batch_stopped"}


@router.post("/retry-failed")
async def batch_retry_failed(tq: TaskQueue = Depends(get_task_queue)):
    """Retry all failed generation tasks (Req 9.5)."""
    await tq.retry_failed()
    return {"status": "retrying_failed"}
