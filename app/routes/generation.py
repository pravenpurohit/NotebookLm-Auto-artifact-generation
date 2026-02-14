"""Single generation routes (Req 6.1, 8.1, 8.2, 8.3, 8.4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_state_manager, get_task_queue
from app.models import CellStatus
from app.state_manager import StateManager
from app.task_queue import DuplicateTaskError, TaskQueue

router = APIRouter(prefix="/api/generate", tags=["generation"])


@router.get("/{report_id}/{template_id}/check-duplicate")
async def check_duplicate_prompt(
    report_id: str,
    template_id: str,
    sm: StateManager = Depends(get_state_manager),
):
    """Check if a completed generation exists with the same prompt hash.

    Computes the SHA-256 hash of the template content and checks for a
    completed cell with the same (report_id, prompt_hash).
    Requirement 8.2, 8.3.
    """
    template = await sm.get_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")

    prompt_hash = StateManager.compute_content_hash(template["content"].encode("utf-8"))
    duplicate = await sm.find_duplicate_prompt(report_id, prompt_hash)

    if duplicate is not None:
        return {
            "duplicate": True,
            "existing": duplicate,
            "prompt_hash": prompt_hash,
        }
    return {"duplicate": False, "prompt_hash": prompt_hash}


@router.post("/{report_id}/{template_id}")
async def start_generation(
    report_id: str,
    template_id: str,
    tq: TaskQueue = Depends(get_task_queue),
):
    """Start artifact generation for a single report-template pair (Req 8.1)."""
    try:
        task_id = await tq.enqueue(report_id, template_id)
        return {"status": "started", "task_id": task_id}
    except DuplicateTaskError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.delete("/{report_id}/{template_id}")
async def stop_generation(
    report_id: str,
    template_id: str,
    tq: TaskQueue = Depends(get_task_queue),
):
    """Stop a single in-progress generation task (Req 8.2)."""
    await tq.stop_task(report_id, template_id)
    return {"status": "stopped", "report_id": report_id, "template_id": template_id}


@router.post("/{report_id}/{template_id}/retry")
async def retry_generation(
    report_id: str,
    template_id: str,
    tq: TaskQueue = Depends(get_task_queue),
    sm: StateManager = Depends(get_state_manager),
):
    """Retry a failed or stopped generation task (Req 8.3)."""
    cell = await sm.get_cell(report_id, template_id)
    if cell is None:
        raise HTTPException(status_code=404, detail="Cell not found")
    if cell.status not in (CellStatus.FAILED, CellStatus.STOPPED):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry cell with status '{cell.status.value}'. "
                   f"Only failed or stopped cells can be retried.",
        )
    try:
        task_id = await tq.enqueue(report_id, template_id)
        return {"status": "retrying", "task_id": task_id}
    except DuplicateTaskError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
