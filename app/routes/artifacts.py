"""Artifact browsing routes (Req 11.1–11.6)."""

from __future__ import annotations

import asyncio
import io
import os
import pathlib
import re
import zipfile
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from app.dependencies import get_nlm_client, get_state_manager
from app.models import RemoteArtifactResponse
from app.nlm_client import NotebookLMClientError, NotebookLMClientWrapper
from app.state_manager import StateManager

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])

# Pattern to extract hash suffix from notebook names like "Name [abcd1234]"
_HASH_SUFFIX_RE = re.compile(r"\[([0-9a-f]{8})\]\s*$")

# Allowed base directory for artifact files (resolved at module load)
_OUTPUT_BASE = os.path.realpath("output")


@router.get("")
async def list_artifacts(
    source_location: Optional[str] = Query(None),
    source_filename: Optional[str] = Query(None),
    artifact_type: Optional[str] = Query(None),
    sm: StateManager = Depends(get_state_manager),
):
    """List artifacts with optional filters (Req 11.1-11.5)."""
    return await sm.list_artifacts(
        source_location=source_location,
        source_filename=source_filename,
        artifact_type=artifact_type,
    )

@router.get("/remote")
async def list_remote_artifacts(
    nlm_client: NotebookLMClientWrapper = Depends(get_nlm_client),
    sm: StateManager = Depends(get_state_manager),
):
    """Fetch artifacts from all remote notebooks (Req 1.1, 1.2, 1.4, 7.5).

    Returns a flat list of RemoteArtifactResponse objects.
    On NLM client failure, returns an empty list with an error message
    so the frontend can display an error banner.

    Parses notebook names for hash suffixes and matches against local
    report content_hashes to flag "already linked" notebooks (Req 7.5).
    """
    try:
        notebooks = await nlm_client.list_notebooks()
    except NotebookLMClientError as exc:
        return {"artifacts": [], "error": str(exc)}

    # Get all local content hashes for linked detection (Req 7.5)
    local_hashes = await sm.get_all_content_hashes()
    # Build a set of hash prefixes (first 8 chars) for matching
    local_hash_prefixes = {h[:8] for h in local_hashes if h}

    # Fetch artifacts from all notebooks in parallel (fixes N+1 sequential fetching)
    sem = asyncio.Semaphore(5)

    async def _fetch_notebook_artifacts(nb: dict) -> list[dict]:
        nb_id = nb.get("id", "")
        nb_title = nb.get("title", "")

        is_linked = False
        match = _HASH_SUFFIX_RE.search(nb_title)
        if match and match.group(1) in local_hash_prefixes:
            is_linked = True

        async with sem:
            try:
                nb_artifacts = await nlm_client.list_notebook_artifacts(nb_id)
            except NotebookLMClientError:
                return []

        results = []
        for idx, a in enumerate(nb_artifacts):
            results.append(
                RemoteArtifactResponse(
                    id=f"remote-{nb_id}-{idx}",
                    artifact_name=a.get("name", ""),
                    artifact_type=a.get("type", "unknown"),
                    source_notebook_title=nb_title,
                    source_notebook_id=nb_id,
                    created_at=a.get("created_at"),
                    is_remote=True,
                    is_linked=is_linked,
                ).model_dump()
            )
        return results

    notebook_results = await asyncio.gather(
        *(_fetch_notebook_artifacts(nb) for nb in notebooks)
    )
    artifacts: list[dict] = []
    for result in notebook_results:
        artifacts.extend(result)

    return {"artifacts": artifacts}


@router.get("/download-all")
async def download_all_artifacts(
    sm: StateManager = Depends(get_state_manager),
):
    """Stream a ZIP of all completed artifacts for offline use (AC 10.4).

    Validates each artifact path stays within the output directory.
    Returns 404 if no completed artifacts exist.
    """
    cells = await sm.get_all_cells()
    completed = [c for c in cells if c.status.value == "completed" and c.artifact_path]

    if not completed:
        raise HTTPException(status_code=404, detail="No completed artifacts to download")

    output_base = pathlib.Path(_OUTPUT_BASE).resolve()

    def _build_zip() -> io.BytesIO:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for cell in completed:
                fpath = pathlib.Path(cell.artifact_path).resolve()
                if not fpath.is_relative_to(output_base):
                    continue
                if not fpath.is_file():
                    continue
                arcname = fpath.relative_to(output_base)
                zf.write(str(fpath), str(arcname))
        buf.seek(0)
        return buf

    zip_buf = await asyncio.to_thread(_build_zip)

    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=artifacts.zip"},
    )


@router.delete("/{artifact_id}")
async def delete_artifact(
    artifact_id: str,
    sm: StateManager = Depends(get_state_manager),
    nlm_client: NotebookLMClientWrapper = Depends(get_nlm_client),
):
    """Delete an artifact by ID (Req 4.2, 4.3, 4.4).

    For local artifacts: removes DB record and deletes file from disk.
    For remote artifacts (id starts with 'remote-'): calls NLM SDK to delete.
    """
    if artifact_id.startswith("remote-"):
        # Remote artifact: extract notebook_id from "remote-{notebook_id}-{index}"
        # Use rsplit to handle notebook_ids containing hyphens (e.g. UUIDs)
        prefix_and_nb = artifact_id[len("remote-"):]  # strip "remote-" prefix
        parts = prefix_and_nb.rsplit("-", 1)
        if len(parts) < 2:
            raise HTTPException(status_code=400, detail="Invalid remote artifact ID format")
        notebook_id = parts[0]
        try:
            await nlm_client.delete_artifact(notebook_id, artifact_id)
        except NotebookLMClientError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        return {"status": "ok", "message": "Remote artifact deleted"}
    else:
        # Local artifact: remove from DB and disk
        deleted = await sm.delete_artifact_record(artifact_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Artifact not found")
        return {"status": "ok", "message": "Artifact deleted"}


@router.get("/{artifact_id}")
async def get_artifact(
    artifact_id: str,
    sm: StateManager = Depends(get_state_manager),
):
    """Get or download a specific artifact by ID."""
    artifact = await sm.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    file_path = artifact["file_path"]
    # Validate the resolved path stays within the expected output directory
    resolved_path = pathlib.Path(file_path).resolve()
    output_base = pathlib.Path(_OUTPUT_BASE).resolve()
    if not resolved_path.is_relative_to(output_base):
        raise HTTPException(status_code=403, detail="Access denied: path outside allowed directory")
    resolved = str(resolved_path)
    if not await asyncio.to_thread(os.path.isfile, resolved):
        raise HTTPException(status_code=404, detail="Artifact file not found on disk")

    return FileResponse(
        path=resolved,
        filename=artifact["artifact_name"] + artifact["file_extension"],
        media_type="application/octet-stream",
    )


@router.get("/{artifact_id}/preview")
async def preview_artifact(
    artifact_id: str,
    sm: StateManager = Depends(get_state_manager),
):
    """Inline preview of an artifact (Req 11.6)."""
    artifact = await sm.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    resolved_path = pathlib.Path(artifact["file_path"]).resolve()
    output_base = pathlib.Path(_OUTPUT_BASE).resolve()
    if not resolved_path.is_relative_to(output_base):
        raise HTTPException(status_code=403, detail="Access denied: path outside allowed directory")
    resolved = str(resolved_path)
    if not await asyncio.to_thread(os.path.isfile, resolved):
        raise HTTPException(status_code=404, detail="Artifact file not found on disk")

    media_types = {
        "infographic": "image/png",
        "audio": "audio/mpeg",
        "video": "video/mp4",
    }
    media_type = media_types.get(artifact["artifact_type"], "application/octet-stream")
    return FileResponse(path=resolved, media_type=media_type)
