"""Authentication routes (Req 1.1–1.5)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth import AuthManager, AuthenticationError
from app.dependencies import get_auth_manager, get_nlm_client
from app.nlm_client import NotebookLMClientWrapper

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
async def auth_login(
    auth: AuthManager = Depends(get_auth_manager),
    nlm_client: NotebookLMClientWrapper = Depends(get_nlm_client),
):
    """Initiate Google login and return session credentials."""
    try:
        credentials = await auth.login()
        nlm_client.credentials = credentials
        nlm_client.reinit_client()
        return {
            "status": "authenticated",
            "user_email": credentials.user_email,
        }
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@router.post("/logout")
async def auth_logout(
    auth: AuthManager = Depends(get_auth_manager),
    nlm_client: NotebookLMClientWrapper = Depends(get_nlm_client),
):
    """Clear session credentials and log out."""
    await auth.logout(nlm_client.credentials)
    return {"status": "logged_out"}


@router.get("/status")
async def auth_status(
    auth: AuthManager = Depends(get_auth_manager),
    nlm_client: NotebookLMClientWrapper = Depends(get_nlm_client),
):
    """Check whether the current session is still valid."""
    valid = await auth.validate_session(nlm_client.credentials)
    return {
        "authenticated": valid,
        "user_email": nlm_client.credentials.user_email if valid else None,
    }
