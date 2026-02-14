"""Report CRUD routes (Req 2.1, 2.3, 2.4, 2.5, 3.2)."""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.artifact_namer import ArtifactNamer
from app.dependencies import get_artifact_namer, get_state_manager
from app.models import UpdateReportRequest
from app.state_manager import StateManager
from app.validators import validate_file_format

router = APIRouter(prefix="/api/reports", tags=["reports"])

MAX_UPLOAD_SIZE = 50 * 1024 * 1024
_SAFE_FILENAME_RE = re.compile(r"[^\w\s\-\.]", re.UNICODE)


def _sanitize_filename(filename: str) -> str:
    """Strip path components and dangerous characters from a filename."""
    filename = os.path.basename(filename)
    filename = _SAFE_FILENAME_RE.sub("_", filename)
    return filename or "unnamed"


def _write_file(path: str, data: bytes) -> None:
    """Write bytes to a file (sync helper for asyncio.to_thread)."""
    with open(path, "wb") as fh:
        fh.write(data)


@router.get("")
async def list_reports(sm: StateManager = Depends(get_state_manager)):
    """List all active reports."""
    return await sm.get_all_reports()


@router.post("", status_code=201)
async def add_reports(
    files: List[UploadFile],
    sm: StateManager = Depends(get_state_manager),
    namer: ArtifactNamer = Depends(get_artifact_namer),
):
    """Add one or more report files to the active list."""
    added: list[dict[str, Any]] = []
    for f in files:
        filename = _sanitize_filename(f.filename or "unknown")
        if not validate_file_format(filename):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file format: {filename}. Only PDF and MD files are accepted.",
            )

        content = await f.read()
        if len(content) > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large: {filename}. Maximum size is 50 MB.",
            )

        report_id = str(uuid.uuid4())
        notebook_name = namer.derive_notebook_name(filename)

        # Compute content hash for duplicate detection (Req 7.1)
        content_hash = StateManager.compute_content_hash(content)
        hash_suffix = content_hash[:8]
        # Include hash suffix in notebook name (Req 7.4)
        notebook_name = f"{notebook_name} [{hash_suffix}]"

        upload_dir = "data/uploads"
        await asyncio.to_thread(os.makedirs, upload_dir, exist_ok=True)
        filepath = os.path.join(upload_dir, filename)
        await asyncio.to_thread(_write_file, filepath, content)

        report = {
            "id": report_id,
            "filename": filename,
            "filepath": filepath,
            "file_size": len(content),
            "last_modified": datetime.now(timezone.utc).isoformat(),
            "notebook_name": notebook_name,
            "notebook_name_edited": False,
            "content_hash": content_hash,
        }
        await sm.persist_reports([report])
        added.append(report)

    return added


@router.delete("/{report_id}")
async def delete_report(
    report_id: str,
    sm: StateManager = Depends(get_state_manager),
):
    """Remove a report and its associated generation cells (Req 2.4)."""
    found = await sm.delete_report(report_id)
    if not found:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"status": "deleted", "report_id": report_id}


@router.patch("/{report_id}")
async def update_report(
    report_id: str,
    body: UpdateReportRequest,
    sm: StateManager = Depends(get_state_manager),
):
    """Update a report's notebook name (Req 3.2)."""
    found = await sm.update_report_notebook_name(report_id, body.notebook_name)
    if not found:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"status": "updated", "report_id": report_id, "notebook_name": body.notebook_name}
