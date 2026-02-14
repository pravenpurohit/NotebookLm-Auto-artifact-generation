"""Shared FastAPI dependency helpers.

All route modules import these instead of defining their own.
Components are stored on ``app.state`` during startup (see main.py lifespan).
"""

from __future__ import annotations

from fastapi import Request, WebSocket

from app.artifact_namer import ArtifactNamer
from app.auth import AuthManager
from app.nlm_client import NotebookLMClientWrapper
from app.state_manager import StateManager
from app.task_queue import TaskQueue
from app.template_detector import TemplateDetector
from app.ws_manager import WebSocketManager


def get_state_manager(request: Request) -> StateManager:
    return request.app.state.state_manager


def get_task_queue(request: Request) -> TaskQueue:
    return request.app.state.task_queue


def get_auth_manager(request: Request) -> AuthManager:
    return request.app.state.auth_manager


def get_template_detector(request: Request) -> TemplateDetector:
    return request.app.state.template_detector


def get_artifact_namer(request: Request) -> ArtifactNamer:
    return request.app.state.artifact_namer


def get_nlm_client(request: Request) -> NotebookLMClientWrapper:
    return request.app.state.nlm_client


def get_ws_manager(request: Request) -> WebSocketManager:
    return request.app.state.ws_manager


def get_ws_manager_ws(websocket: WebSocket) -> WebSocketManager:
    return websocket.app.state.ws_manager
