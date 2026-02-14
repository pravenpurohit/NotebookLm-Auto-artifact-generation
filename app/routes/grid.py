"""Status grid route (Req 7.1, 7.3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_state_manager
from app.state_manager import StateManager
from app.ws_manager import cell_to_dict

router = APIRouter(prefix="/api/grid", tags=["grid"])


@router.get("")
async def get_grid(sm: StateManager = Depends(get_state_manager)):
    """Return the full status grid: reports, templates, and cells."""
    state = await sm.load_state()
    return {
        "reports": state["reports"],
        "templates": state["templates"],
        "cells": [cell_to_dict(c) for c in state["cells"]],
    }
