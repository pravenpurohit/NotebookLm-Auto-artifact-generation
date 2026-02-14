"""WebSocket endpoint for live grid updates (Req 7.2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.dependencies import get_ws_manager_ws
from app.ws_manager import WebSocketManager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/grid")
async def ws_grid(
    websocket: WebSocket,
    ws_mgr: WebSocketManager = Depends(get_ws_manager_ws),
):
    """WebSocket endpoint for live Status_Grid updates."""
    await ws_mgr.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_json({"type": "ack", "data": data})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await ws_mgr.disconnect(websocket)
