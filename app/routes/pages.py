"""Server-rendered page routes."""

from __future__ import annotations

import os

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.state_manager import StateManager
from app.ws_manager import cell_to_dict

TEMPLATES_DIR = os.environ.get("TEMPLATES_DIR", "app/templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

router = APIRouter(tags=["pages"])


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Serve the login page."""
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    """Serve the dashboard page with initial grid data (Req 7.1)."""
    sm: StateManager = request.app.state.state_manager
    state = await sm.load_state()
    grid_data = {
        "reports": [
            {
                "id": r["id"] if isinstance(r, dict) else r.id,
                "filename": r["filename"] if isinstance(r, dict) else r.filename,
                "notebook_name": r["notebook_name"] if isinstance(r, dict) else r.notebook_name,
            }
            for r in state["reports"]
        ],
        "templates": [
            {
                "id": t["id"] if isinstance(t, dict) else t.id,
                "name": t["name"] if isinstance(t, dict) else t.name,
                "artifact_type": t["artifact_type"] if isinstance(t, dict) else t.artifact_type,
            }
            for t in state["templates"]
        ],
        "cells": [cell_to_dict(c) for c in state["cells"]],
    }
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "grid_data": grid_data, "active_page": "dashboard"},
    )


@router.get("/files", response_class=HTMLResponse)
async def files(request: Request) -> HTMLResponse:
    """Serve the file browser page (Req 2.1, 2.2, 2.3, 2.5, 3.1, 3.2)."""
    return templates.TemplateResponse(
        "file_browser.html",
        {"request": request, "active_page": "files"},
    )


@router.get("/artifacts", response_class=HTMLResponse)
async def artifacts_page(request: Request) -> HTMLResponse:
    """Serve the artifact browser page (Req 11.1-11.6)."""
    return templates.TemplateResponse(
        "artifacts.html",
        {"request": request, "active_page": "artifacts"},
    )
