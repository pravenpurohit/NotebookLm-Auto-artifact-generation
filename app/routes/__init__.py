"""Route sub-package — re-exports all domain routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.routes.auth import router as auth_router
from app.routes.reauth import router as reauth_router
from app.routes.reports import router as reports_router
from app.routes.templates import router as templates_router
from app.routes.generation import router as generation_router
from app.routes.batch import router as batch_router
from app.routes.grid import router as grid_router
from app.routes.artifacts import router as artifacts_router
from app.routes.notebooks import router as notebooks_router
from app.routes.recovery import router as recovery_router
from app.routes.ws import router as ws_router
from app.routes.pages import router as pages_router

router = APIRouter()

router.include_router(auth_router)
router.include_router(reauth_router)
router.include_router(reports_router)
router.include_router(templates_router)
router.include_router(generation_router)
router.include_router(batch_router)
router.include_router(grid_router)
router.include_router(artifacts_router)
router.include_router(notebooks_router)
router.include_router(recovery_router)
router.include_router(ws_router)
router.include_router(pages_router)
