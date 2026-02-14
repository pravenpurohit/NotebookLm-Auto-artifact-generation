"""Crash recovery route (Req 10.1–10.5)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_nlm_client, get_state_manager, get_task_queue
from app.nlm_client import NotebookLMClientWrapper
from app.state_manager import StateManager
from app.task_queue import DuplicateTaskError, TaskQueue

router = APIRouter(prefix="/api/recovery", tags=["recovery"])


@router.post("/sync")
async def recovery_sync(
    sm: StateManager = Depends(get_state_manager),
    nlm_client: NotebookLMClientWrapper = Depends(get_nlm_client),
    tq: TaskQueue = Depends(get_task_queue),
):
    """Trigger crash recovery: sync remote notebooks with local state."""
    result = await sm.recover_state(nlm_client)

    for cell in result["in_progress"]:
        try:
            await tq.enqueue(cell.report_id, cell.template_id)
        except DuplicateTaskError:
            pass

    return {
        "matched": len(result["matched"]),
        "in_progress_resumed": len(result["in_progress"]),
        "untracked": [
            nb.get("id") if isinstance(nb, dict) else getattr(nb, "id", None)
            for nb in result["untracked"]
        ],
    }
