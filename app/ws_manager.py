"""WebSocket manager for real-time Status_Grid updates.

Tracks active WebSocket connections and broadcasts GenerationCell
status changes to all connected clients.

Requirement 7.2: Status_Grid SHALL update within 2 seconds of a status change.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from fastapi import WebSocket

from app.state_manager import GenerationCell, CellStatus

logger = logging.getLogger(__name__)


@runtime_checkable
class CellBroadcaster(Protocol):
    """Protocol for broadcasting cell updates to connected clients."""

    async def broadcast_cell_update(self, cell: GenerationCell) -> None: ...


def cell_to_dict(cell: GenerationCell) -> dict[str, Any]:
    """Serialize a GenerationCell to a JSON-safe dictionary.

    Single source of truth for cell serialization — used by WebSocket
    broadcasts, the grid API, and the dashboard page route.
    """
    return {
        "report_id": cell.report_id,
        "template_id": cell.template_id,
        "status": cell.status.value if isinstance(cell.status, CellStatus) else cell.status,
        "task_id": cell.task_id,
        "notebook_id": cell.notebook_id,
        "error_message": cell.error_message,
        "started_at": cell.started_at.isoformat() if cell.started_at else None,
        "completed_at": cell.completed_at.isoformat() if cell.completed_at else None,
        "artifact_path": cell.artifact_path,
    }


class WebSocketManager:
    """Manages WebSocket connections and broadcasts cell updates."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection and start tracking it."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket connected. Active connections: %d", len(self.active_connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection from the active list."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("WebSocket disconnected. Active connections: %d", len(self.active_connections))

    async def broadcast_cell_update(self, cell: GenerationCell) -> None:
        """Send a single cell status update to all connected clients.

        Dead connections are removed automatically on send failure.
        """
        message = {"type": "cell_update", "data": cell_to_dict(cell)}
        await self._broadcast(message)

    async def broadcast_batch_update(self, cells: list[GenerationCell]) -> None:
        """Send a batch of cell status updates to all connected clients."""
        message = {
            "type": "batch_update",
            "data": [cell_to_dict(c) for c in cells],
        }
        await self._broadcast(message)

    async def _broadcast(self, message: dict[str, Any]) -> None:
        """Send a JSON message to every active connection.

        Connections that raise on send are treated as dead and removed.
        """
        dead: list[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                logger.warning("Failed to send to WebSocket, marking as dead.")
                dead.append(connection)

        for connection in dead:
            if connection in self.active_connections:
                self.active_connections.remove(connection)

        if dead:
            logger.info(
                "Removed %d dead connection(s). Active connections: %d",
                len(dead),
                len(self.active_connections),
            )
