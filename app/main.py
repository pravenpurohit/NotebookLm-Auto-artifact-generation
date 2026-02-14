"""FastAPI application entry point for the NotebookLM Dashboard.

Wires all backend components together, mounts static files,
and runs startup initialization (DB, templates, recovery).

Requirements: 1.1, 10.1
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.artifact_namer import ArtifactNamer
from app.auth import AuthManager
from app.nlm_client import NotebookLMClientWrapper, NotebookLMClientError, SessionCredentials
from app.routes import router
from app.state_manager import StateManager
from app.task_queue import TaskQueue
from app.template_detector import TemplateDetector
from app.ws_manager import WebSocketManager

logger = logging.getLogger(__name__)

# Paths
DB_PATH = os.environ.get("DASHBOARD_DB_PATH", "data/dashboard.db")
PROMPTS_DIR = os.environ.get("PROMPTS_DIR", "prompts")
STATIC_DIR = os.environ.get("STATIC_DIR", "static")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: initialize components on startup, clean up on shutdown."""

    # --- Component wiring ---
    ws_manager = WebSocketManager()
    auth_manager = AuthManager()
    template_detector = TemplateDetector()
    artifact_namer = ArtifactNamer()

    # Ensure data directory exists for the SQLite database
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)

    state_manager = StateManager(db_path=DB_PATH, ws_manager=ws_manager)
    await state_manager.open()

    credentials = SessionCredentials()
    nlm_client = NotebookLMClientWrapper(credentials=credentials)

    task_queue = TaskQueue(
        state_manager=state_manager,
        nlm_client=nlm_client,
        max_concurrent=int(os.environ.get("MAX_CONCURRENT_TASKS", "2")),
    )

    # Store components on app.state so dependency helpers can access them
    app.state.ws_manager = ws_manager
    app.state.auth_manager = auth_manager
    app.state.template_detector = template_detector
    app.state.artifact_namer = artifact_namer
    app.state.state_manager = state_manager
    app.state.nlm_client = nlm_client
    app.state.task_queue = task_queue

    # --- Startup: initialize DB ---
    logger.info("Initializing database at %s", DB_PATH)
    await state_manager.init_db()

    # --- Startup: load templates from prompts directory ---
    if os.path.isdir(PROMPTS_DIR):
        templates = template_detector.load_templates(PROMPTS_DIR)
        non_excluded = [t for t in templates if not t.is_excluded]
        if non_excluded:
            template_dicts = [
                {
                    "id": f"tpl-{t.number:02d}-{t.name[:40]}",
                    "filename": t.filename,
                    "number": t.number,
                    "artifact_type": t.artifact_type,
                    "name": t.name,
                    "audio_format": t.audio_format,
                    "content": t.content,
                    "content_edited": False,
                    "is_excluded": t.is_excluded,
                }
                for t in non_excluded
            ]
            await state_manager.persist_templates(template_dicts)
            logger.info("Loaded %d templates from %s", len(non_excluded), PROMPTS_DIR)
    else:
        logger.warning("Prompts directory not found: %s", PROMPTS_DIR)

    # --- Startup: crash recovery (Req 10.1) ---
    try:
        if auth_manager.sdk_available and credentials.cookies:
            result = await state_manager.recover_state(nlm_client)
            logger.info(
                "Recovery complete: %d matched, %d in-progress, %d untracked",
                len(result["matched"]),
                len(result["in_progress"]),
                len(result["untracked"]),
            )
            for cell in result["in_progress"]:
                try:
                    await task_queue.enqueue(cell.report_id, cell.template_id)
                except Exception:
                    logger.warning(
                        "Could not resume task for (%s, %s)",
                        cell.report_id,
                        cell.template_id,
                    )
        else:
            logger.info("Skipping recovery – no active session credentials")
    except Exception as exc:
        logger.error("Crash recovery failed: %s", exc)

    logger.info("NotebookLM Dashboard startup complete")

    yield

    # --- Shutdown ---
    logger.info("Shutting down – stopping task queue")
    await task_queue.stop_all()
    await state_manager.close()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="NotebookLM Dashboard",
        description="Generate NotebookLM artifacts from deep research reports",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Mount static files
    if os.path.isdir(STATIC_DIR):
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # Include all routes (API + pages + WebSocket)
    app.include_router(router)

    # Global exception handlers for consistent error shape (Section 14)
    @app.exception_handler(NotebookLMClientError)
    async def nlm_client_error_handler(request: Request, exc: NotebookLMClientError):
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    return app


app = create_app()
