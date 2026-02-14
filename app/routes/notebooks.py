"""Notebook management routes (Req 5.2, 5.3, 5.4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_nlm_client, get_state_manager
from app.nlm_client import NotebookLMClientError, NotebookLMClientWrapper
from app.state_manager import StateManager

router = APIRouter(prefix="/api/notebooks", tags=["notebooks"])


@router.delete("/{notebook_id}")
async def delete_notebook(
    notebook_id: str,
    sm: StateManager = Depends(get_state_manager),
    nlm_client: NotebookLMClientWrapper = Depends(get_nlm_client),
):
    """Delete a notebook and all associated local records.

    1. Call NLM SDK to delete the remote notebook (Req 5.2)
    2. Remove all local generation cells and artifacts for this notebook (Req 5.3)
    3. Return 200 on success, error on failure (Req 5.4)
    """
    try:
        await nlm_client.delete_notebook(notebook_id)
    except NotebookLMClientError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    deleted_count = await sm.delete_notebook_records(notebook_id)

    return {
        "status": "ok",
        "message": f"Notebook deleted. Removed {deleted_count} local generation cell(s).",
    }
