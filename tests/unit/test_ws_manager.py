"""Unit tests for WebSocketManager."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import pytest

from app.state_manager import CellStatus, GenerationCell
from app.ws_manager import WebSocketManager, cell_to_dict


# ---------------------------------------------------------------------------
# Helpers – lightweight fake WebSocket
# ---------------------------------------------------------------------------

class FakeWebSocket:
    """Minimal stand-in for FastAPI's WebSocket."""

    def __init__(self, *, fail_on_send: bool = False) -> None:
        self.accepted = False
        self.sent_messages: list[dict[str, Any]] = []
        self._fail_on_send = fail_on_send

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data: dict[str, Any]) -> None:
        if self._fail_on_send:
            raise RuntimeError("connection lost")
        self.sent_messages.append(data)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ws_manager() -> WebSocketManager:
    return WebSocketManager()


def _make_cell(**overrides: Any) -> GenerationCell:
    defaults = {
        "report_id": "r1",
        "template_id": "t1",
        "status": CellStatus.IN_PROGRESS,
    }
    defaults.update(overrides)
    return GenerationCell(**defaults)


# ---------------------------------------------------------------------------
# Tests – cell_to_dict
# ---------------------------------------------------------------------------

class TestCellToDict:
    def test_minimal_cell(self) -> None:
        cell = _make_cell()
        d = cell_to_dict(cell)
        assert d["report_id"] == "r1"
        assert d["template_id"] == "t1"
        assert d["status"] == "in_progress"
        assert d["task_id"] is None
        assert d["started_at"] is None

    def test_full_cell(self) -> None:
        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        cell = _make_cell(
            status=CellStatus.COMPLETED,
            task_id="tid-1",
            notebook_id="nb-1",
            error_message=None,
            started_at=now,
            completed_at=now,
            artifact_path="/out/artifact.png",
        )
        d = cell_to_dict(cell)
        assert d["status"] == "completed"
        assert d["task_id"] == "tid-1"
        assert d["started_at"] == now.isoformat()
        assert d["artifact_path"] == "/out/artifact.png"


# ---------------------------------------------------------------------------
# Tests – connect / disconnect
# ---------------------------------------------------------------------------

class TestConnectDisconnect:
    @pytest.mark.asyncio
    async def test_connect_accepts_and_tracks(self, ws_manager: WebSocketManager) -> None:
        ws = FakeWebSocket()
        await ws_manager.connect(ws)
        assert ws.accepted is True
        assert ws in ws_manager.active_connections
        assert len(ws_manager.active_connections) == 1

    @pytest.mark.asyncio
    async def test_multiple_connections(self, ws_manager: WebSocketManager) -> None:
        ws1, ws2 = FakeWebSocket(), FakeWebSocket()
        await ws_manager.connect(ws1)
        await ws_manager.connect(ws2)
        assert len(ws_manager.active_connections) == 2

    @pytest.mark.asyncio
    async def test_disconnect_removes(self, ws_manager: WebSocketManager) -> None:
        ws = FakeWebSocket()
        await ws_manager.connect(ws)
        await ws_manager.disconnect(ws)
        assert ws not in ws_manager.active_connections
        assert len(ws_manager.active_connections) == 0

    @pytest.mark.asyncio
    async def test_disconnect_unknown_is_safe(self, ws_manager: WebSocketManager) -> None:
        ws = FakeWebSocket()
        # Should not raise even though ws was never connected
        await ws_manager.disconnect(ws)
        assert len(ws_manager.active_connections) == 0


# ---------------------------------------------------------------------------
# Tests – broadcast_cell_update
# ---------------------------------------------------------------------------

class TestBroadcastCellUpdate:
    @pytest.mark.asyncio
    async def test_sends_to_all_clients(self, ws_manager: WebSocketManager) -> None:
        ws1, ws2 = FakeWebSocket(), FakeWebSocket()
        await ws_manager.connect(ws1)
        await ws_manager.connect(ws2)

        cell = _make_cell()
        await ws_manager.broadcast_cell_update(cell)

        for ws in (ws1, ws2):
            assert len(ws.sent_messages) == 1
            msg = ws.sent_messages[0]
            assert msg["type"] == "cell_update"
            assert msg["data"]["report_id"] == "r1"

    @pytest.mark.asyncio
    async def test_no_clients_is_noop(self, ws_manager: WebSocketManager) -> None:
        cell = _make_cell()
        # Should not raise
        await ws_manager.broadcast_cell_update(cell)

    @pytest.mark.asyncio
    async def test_dead_connection_removed(self, ws_manager: WebSocketManager) -> None:
        good_ws = FakeWebSocket()
        bad_ws = FakeWebSocket(fail_on_send=True)
        await ws_manager.connect(good_ws)
        await ws_manager.connect(bad_ws)

        cell = _make_cell()
        await ws_manager.broadcast_cell_update(cell)

        # Good client received the message
        assert len(good_ws.sent_messages) == 1
        # Bad client was removed
        assert bad_ws not in ws_manager.active_connections
        assert len(ws_manager.active_connections) == 1


# ---------------------------------------------------------------------------
# Tests – broadcast_batch_update
# ---------------------------------------------------------------------------

class TestBroadcastBatchUpdate:
    @pytest.mark.asyncio
    async def test_sends_batch_to_all_clients(self, ws_manager: WebSocketManager) -> None:
        ws = FakeWebSocket()
        await ws_manager.connect(ws)

        cells = [
            _make_cell(report_id="r1", template_id="t1"),
            _make_cell(report_id="r2", template_id="t2", status=CellStatus.FAILED),
        ]
        await ws_manager.broadcast_batch_update(cells)

        assert len(ws.sent_messages) == 1
        msg = ws.sent_messages[0]
        assert msg["type"] == "batch_update"
        assert len(msg["data"]) == 2
        assert msg["data"][0]["report_id"] == "r1"
        assert msg["data"][1]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_empty_batch(self, ws_manager: WebSocketManager) -> None:
        ws = FakeWebSocket()
        await ws_manager.connect(ws)
        await ws_manager.broadcast_batch_update([])

        msg = ws.sent_messages[0]
        assert msg["type"] == "batch_update"
        assert msg["data"] == []

    @pytest.mark.asyncio
    async def test_dead_connection_removed_on_batch(self, ws_manager: WebSocketManager) -> None:
        bad_ws = FakeWebSocket(fail_on_send=True)
        await ws_manager.connect(bad_ws)

        await ws_manager.broadcast_batch_update([_make_cell()])

        assert bad_ws not in ws_manager.active_connections
        assert len(ws_manager.active_connections) == 0
