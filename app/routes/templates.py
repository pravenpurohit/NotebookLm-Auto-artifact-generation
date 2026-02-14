"""Template CRUD routes (Req 4.11, 4.12)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.dependencies import get_state_manager, get_template_detector
from app.models import UpdateTemplateRequest, UpdateTemplateExclusionRequest
from app.state_manager import StateManager
from app.template_detector import TemplateDetector

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("")
async def list_templates(sm: StateManager = Depends(get_state_manager)):
    """List all loaded templates."""
    return await sm.get_all_templates()


@router.post("", status_code=201)
async def add_template(
    file: UploadFile,
    sm: StateManager = Depends(get_state_manager),
    detector: TemplateDetector = Depends(get_template_detector),
):
    """Add a custom template file (Req 4.11, AC 2.5, 2.8)."""
    filename = file.filename or "unknown.md"

    # AC 2.8: reject non-.md files
    if not filename.lower().endswith(".md"):
        raise HTTPException(
            status_code=400,
            detail=f"Only .md files are accepted. Got: {filename}",
        )

    content = (await file.read()).decode("utf-8")

    info = detector.parse_filename(filename)
    if info is None:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot parse template filename: {filename}",
        )
    info.content = content

    if info.artifact_type == "unknown":
        detected = detector.detect_type_from_content(content)
        if detected:
            info.artifact_type = detected
        else:
            raise HTTPException(
                status_code=400,
                detail="Cannot determine artifact type from filename or content.",
            )

    # AC 2.5: check for existing template with same filename — update instead of duplicate
    existing = await sm.find_template_by_filename(filename)
    if existing:
        await sm.update_template_content(existing["id"], content)
        existing["content"] = content
        existing["content_edited"] = True
        return existing

    template_id = str(uuid.uuid4())
    template = {
        "id": template_id,
        "filename": info.filename,
        "number": info.number,
        "artifact_type": info.artifact_type,
        "name": info.name,
        "audio_format": info.audio_format,
        "content": info.content,
        "content_edited": False,
        "is_excluded": info.is_excluded,
    }
    await sm.persist_templates([template])
    return template


@router.patch("/{template_id}")
async def update_template(
    template_id: str,
    body: UpdateTemplateRequest,
    sm: StateManager = Depends(get_state_manager),
):
    """Edit a template's prompt content (Req 4.12)."""
    found = await sm.update_template_content(template_id, body.content)
    if not found:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"status": "updated", "template_id": template_id}


@router.patch("/{template_id}/exclude")
async def update_template_exclusion(
    template_id: str,
    body: UpdateTemplateExclusionRequest,
    sm: StateManager = Depends(get_state_manager),
):
    """Toggle a template's exclusion status (Req 3.4)."""
    found = await sm.update_template_exclusion(template_id, body.is_excluded)
    if not found:
        raise HTTPException(status_code=404, detail="Template not found")
    return {
        "status": "updated",
        "template_id": template_id,
        "is_excluded": body.is_excluded,
    }
