"""Re-authentication routes with SSE streaming.

Provides endpoints to launch the Playwright browser login flow
and stream status updates to the frontend via Server-Sent Events.

Requirements: 1.1, 1.2, 1.3, 3.1, 4.1, 4.2, 5.1
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from app.auth import AuthManager, AuthenticationError, ReauthPhase, ReauthStatus
from app.dependencies import get_auth_manager, get_nlm_client
from app.nlm_client import NotebookLMClientWrapper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/reauth")
async def start_reauth(
    auth: AuthManager = Depends(get_auth_manager),
) -> JSONResponse:
    """Launch the Playwright browser login flow.

    Returns ``{"session_id": ...}`` on success.
    Returns 409 if a reauth session is already active.
    Returns 503 if Playwright is not available.

    Requirements: 1.1, 1.2, 1.3, 5.1
    """
    if auth.reauth_active:
        return JSONResponse(
            status_code=409,
            content={"detail": "A re-authentication session is already in progress."},
        )

    if not auth.playwright_available:
        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    "Browser automation is not available. "
                    "Run `playwright install chromium` to enable re-authentication."
                )
            },
        )

    if not auth.sdk_available:
        return JSONResponse(
            status_code=503,
            content={"detail": "NotebookLM SDK is not installed."},
        )

    session_id = uuid.uuid4().hex
    return JSONResponse(
        status_code=200,
        content={"session_id": session_id},
    )


@router.get("/reauth/status/{session_id}")
async def reauth_status(
    session_id: str,
    request: Request,
    auth: AuthManager = Depends(get_auth_manager),
    nlm_client: NotebookLMClientWrapper = Depends(get_nlm_client),
) -> EventSourceResponse:
    """SSE stream of reauth status updates.

    Calls ``auth.browser_login()`` with a callback that yields events.
    On ``authenticated``: updates credentials, reinits client, emits final event.
    On terminal events: emits event and closes stream.

    Requirements: 3.1, 3.2, 3.3, 4.1, 4.2
    """

    async def event_generator() -> AsyncGenerator[dict, None]:
        status_queue: asyncio.Queue[ReauthStatus] = asyncio.Queue()

        async def status_callback(status: ReauthStatus) -> None:
            await status_queue.put(status)

        login_task = asyncio.create_task(
            auth.browser_login(status_callback=status_callback)
        )

        try:
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    login_task.cancel()
                    auth.cancel_reauth()
                    return

                try:
                    status = await asyncio.wait_for(
                        status_queue.get(), timeout=0.5
                    )
                except asyncio.TimeoutError:
                    # No status yet; check if login task finished with error
                    if login_task.done():
                        exc = login_task.exception()
                        if exc is not None:
                            yield {
                                "event": "reauth_status",
                                "data": json.dumps({
                                    "phase": ReauthPhase.ERROR.value,
                                    "message": str(exc),
                                    "error": str(exc),
                                }),
                            }
                        return
                    continue

                event_data = {
                    "phase": status.phase.value,
                    "message": status.message,
                    "error": status.error,
                }

                yield {
                    "event": "reauth_status",
                    "data": json.dumps(event_data),
                }

                if status.phase == ReauthPhase.LOGIN_DETECTED:
                    # Wait for browser_login to return credentials
                    try:
                        credentials = await login_task
                        # Update shared credentials and reinit client
                        nlm_client.credentials = credentials
                        nlm_client.reinit_client()

                        yield {
                            "event": "reauth_status",
                            "data": json.dumps({
                                "phase": ReauthPhase.AUTHENTICATED.value,
                                "message": "Authentication successful.",
                                "error": None,
                            }),
                        }
                    except AuthenticationError as exc:
                        yield {
                            "event": "reauth_status",
                            "data": json.dumps({
                                "phase": ReauthPhase.ERROR.value,
                                "message": str(exc),
                                "error": str(exc),
                            }),
                        }
                    return

                if status.phase in (
                    ReauthPhase.ERROR,
                    ReauthPhase.TIMEOUT,
                    ReauthPhase.CANCELLED,
                ):
                    # Ensure login task completes
                    if not login_task.done():
                        try:
                            await login_task
                        except (AuthenticationError, asyncio.CancelledError):
                            pass
                    return

        except asyncio.CancelledError:
            auth.cancel_reauth()
            if not login_task.done():
                login_task.cancel()
                try:
                    await login_task
                except (AuthenticationError, asyncio.CancelledError):
                    pass

    return EventSourceResponse(event_generator())
