"""NotebookLM Client Wrapper.

Wraps the notebooklm-py SDK to provide a clean async interface for
notebook creation, artifact generation, status polling, and downloads.

Uses the SDK's sub-API pattern: client.notebooks.*, client.artifacts.*,
client.sources.* — NOT direct methods on the client object.

Requirements: 6.1, 6.2, 6.3, 6.6
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Maps our artifact_type strings to SDK generate/download method names
_GENERATE_METHOD_MAP: dict[str, str] = {
    "infographic": "generate_infographic",
    "audio": "generate_audio",
    "video": "generate_video",
}

_DOWNLOAD_METHOD_MAP: dict[str, str] = {
    "infographic": "download_infographic",
    "audio": "download_audio",
    "video": "download_video",
}


@dataclass
class SessionCredentials:
    """Google session credentials for NotebookLM API access."""

    cookies: dict[str, str] = field(default_factory=dict)
    csrf_token: str = ""
    session_id: str = ""
    token: str | None = None
    user_email: str | None = None


class NotebookLMClientError(Exception):
    """Raised when a NotebookLM API operation fails."""


class NotebookLMClientWrapper:
    """Async wrapper around the notebooklm-py SDK.

    Uses the SDK's sub-API pattern:
    - client.notebooks.create/list/delete/...
    - client.artifacts.generate_*/list/delete/poll_status/download_*/...
    - client.sources.add_file/...

    All SDK calls are wrapped in try/except so the wrapper degrades
    gracefully when the SDK is unavailable (e.g. in test environments).
    """

    def __init__(self, credentials: SessionCredentials) -> None:
        self.credentials = credentials
        self._client: Any | None = None
        self._init_client()

    def _init_client(self) -> None:
        """Attempt to initialise the underlying notebooklm-py client."""
        try:
            from notebooklm import AuthTokens, NotebookLMClient  # type: ignore[import-untyped]

            # Only initialise if we have actual credentials
            if not self.credentials.cookies:
                logger.info("No credentials yet – SDK client deferred until login")
                self._client = None
                return

            auth = AuthTokens(
                cookies=self.credentials.cookies,
                csrf_token=self.credentials.csrf_token,
                session_id=self.credentials.session_id,
            )
            self._client = NotebookLMClient(auth=auth)

            # Verify SDK sub-API attributes exist (startup validation)
            for attr in ("notebooks", "artifacts", "sources"):
                if not hasattr(self._client, attr):
                    logger.error(
                        "SDK client missing expected sub-API '%s'. "
                        "The notebooklm-py version may be incompatible.",
                        attr,
                    )
                    self._client = None
                    return

            logger.info("notebooklm-py SDK client initialised")
        except ImportError:
            logger.warning(
                "notebooklm-py SDK not installed – client will raise on API calls"
            )
            self._client = None
        except Exception as exc:
            logger.error("Failed to initialise notebooklm-py client: %s", exc)
            self._client = None

    def reinit_client(self) -> None:
        """Re-initialise the SDK client (e.g. after login provides credentials)."""
        self._init_client()

    def _ensure_client(self) -> Any:
        """Return the SDK client or raise if unavailable."""
        if self._client is None:
            raise NotebookLMClientError(
                "NotebookLM SDK client is not available. "
                "Ensure notebooklm-py is installed and credentials are valid."
            )
        return self._client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_notebook(self, name: str, source_path: str) -> str:
        """Create a notebook and attach *source_path* as a source.

        Returns the notebook_id assigned by NotebookLM.

        Requirement 6.1: create notebook, attach source.
        Uses: client.notebooks.create() + client.sources.add_file()
        """
        client = self._ensure_client()
        try:
            notebook = await client.notebooks.create(title=name)
            notebook_id: str = notebook.id if hasattr(notebook, "id") else str(notebook)

            await client.sources.add_file(
                notebook_id=notebook_id, file_path=source_path
            )
            logger.info(
                "Created notebook '%s' (id=%s) with source '%s'",
                name,
                notebook_id,
                source_path,
            )
            return notebook_id
        except NotebookLMClientError:
            raise
        except Exception as exc:
            raise NotebookLMClientError(
                f"Failed to create notebook '{name}': {exc}"
            ) from exc

    async def submit_generation(
        self,
        notebook_id: str,
        prompt: str,
        artifact_type: str,
        audio_format: str | None = None,
    ) -> str:
        """Submit an artifact generation request.

        Dispatches to the correct client.artifacts.generate_*() method
        based on artifact_type. Returns the task_id used for polling.

        Requirement 6.1: submit prompt for generation.
        Requirement 6.2: store returned Task_ID.
        """
        client = self._ensure_client()
        try:
            method_name = _GENERATE_METHOD_MAP.get(artifact_type)
            if method_name is None:
                raise NotebookLMClientError(
                    f"Unsupported artifact type: {artifact_type}. "
                    f"Expected one of: {list(_GENERATE_METHOD_MAP.keys())}"
                )

            generate_fn = getattr(client.artifacts, method_name)
            kwargs: dict[str, Any] = {
                "notebook_id": notebook_id,
                "instructions": prompt,
            }
            if artifact_type == "audio" and audio_format is not None:
                # Map our format strings to SDK AudioFormat enum
                try:
                    from notebooklm import AudioFormat as SdkAudioFormat
                    fmt_map = {
                        "DEEP_DIVE": SdkAudioFormat.DEEP_DIVE,
                        "BRIEF": SdkAudioFormat.BRIEF,
                        "CRITIQUE": SdkAudioFormat.CRITIQUE,
                        "DEBATE": SdkAudioFormat.DEBATE,
                    }
                    sdk_fmt = fmt_map.get(audio_format)
                    if sdk_fmt is not None:
                        kwargs["audio_format"] = sdk_fmt
                except ImportError:
                    pass  # SDK not available, skip format

            result = await generate_fn(**kwargs)
            task_id: str = result.task_id if hasattr(result, "task_id") else str(result)
            logger.info(
                "Submitted %s generation for notebook %s – task_id=%s",
                artifact_type,
                notebook_id,
                task_id,
            )
            return task_id
        except NotebookLMClientError:
            raise
        except Exception as exc:
            raise NotebookLMClientError(
                f"Failed to submit {artifact_type} generation for notebook {notebook_id}: {exc}"
            ) from exc

    async def poll_status(
        self, notebook_id: str, task_id: str
    ) -> dict[str, Any]:
        """Poll the generation status for *task_id*.

        Returns a dict with keys: status, progress, error.

        Requirement 6.3: poll for status updates.
        Uses: client.artifacts.poll_status(notebook_id, task_id)
        """
        client = self._ensure_client()
        try:
            result = await client.artifacts.poll_status(
                notebook_id=notebook_id, task_id=task_id
            )

            # GenerationStatus has: .status, .is_complete, .is_failed,
            # .is_in_progress, .error, .url
            if isinstance(result, dict):
                return {
                    "status": result.get("status", "unknown"),
                    "progress": result.get("progress"),
                    "error": result.get("error"),
                }

            return {
                "status": getattr(result, "status", "unknown"),
                "progress": getattr(result, "is_in_progress", None),
                "error": getattr(result, "error", None),
                "is_complete": getattr(result, "is_complete", False),
                "is_failed": getattr(result, "is_failed", False),
            }
        except NotebookLMClientError:
            raise
        except Exception as exc:
            raise NotebookLMClientError(
                f"Failed to poll status for task {task_id}: {exc}"
            ) from exc

    async def download_artifact(
        self,
        notebook_id: str,
        artifact_type: str,
        output_path: str,
    ) -> str:
        """Download the completed artifact to *output_path*.

        Dispatches to the correct client.artifacts.download_*() method
        based on artifact_type. Creates parent directories if needed.
        Returns the absolute file path of the downloaded artifact.

        Requirement 6.6: download artifact to appropriate subdirectory.
        """
        client = self._ensure_client()
        try:
            await asyncio.to_thread(
                os.makedirs, os.path.dirname(output_path) or ".", exist_ok=True
            )

            method_name = _DOWNLOAD_METHOD_MAP.get(artifact_type)
            if method_name is None:
                raise NotebookLMClientError(
                    f"Unsupported artifact type for download: {artifact_type}. "
                    f"Expected one of: {list(_DOWNLOAD_METHOD_MAP.keys())}"
                )

            download_fn = getattr(client.artifacts, method_name)
            await download_fn(notebook_id=notebook_id, output_path=output_path)

            abs_path = os.path.abspath(output_path)
            logger.info(
                "Downloaded %s artifact for notebook %s to %s",
                artifact_type,
                notebook_id,
                abs_path,
            )
            return abs_path
        except NotebookLMClientError:
            raise
        except Exception as exc:
            raise NotebookLMClientError(
                f"Failed to download {artifact_type} artifact for notebook {notebook_id}: {exc}"
            ) from exc

    async def list_notebooks(self) -> list[dict[str, Any]]:
        """List all notebooks in the authenticated account.

        Used for crash recovery (Requirement 10.1).
        Returns a list of dicts with at least 'id' and 'title' keys.
        Uses: client.notebooks.list()
        """
        client = self._ensure_client()
        try:
            notebooks = await client.notebooks.list()

            result: list[dict[str, Any]] = []
            for nb in notebooks:
                if isinstance(nb, dict):
                    result.append(nb)
                else:
                    result.append(
                        {
                            "id": getattr(nb, "id", str(nb)),
                            "title": getattr(nb, "title", ""),
                        }
                    )
            logger.info("Listed %d notebooks", len(result))
            return result
        except NotebookLMClientError:
            raise
        except Exception as exc:
            raise NotebookLMClientError(
                f"Failed to list notebooks: {exc}"
            ) from exc

    async def list_notebook_artifacts(self, notebook_id: str) -> list[dict[str, Any]]:
        """List all artifacts in a specific notebook.

        Returns a list of dicts with id, name, type, created_at keys.
        Uses: client.artifacts.list(notebook_id)

        Requirements: 1.1, 1.2
        """
        client = self._ensure_client()
        try:
            artifacts = await client.artifacts.list(notebook_id=notebook_id)

            result: list[dict[str, Any]] = []
            for a in artifacts:
                if isinstance(a, dict):
                    result.append(a)
                else:
                    result.append(
                        {
                            "id": getattr(a, "id", str(a)),
                            "name": getattr(a, "title", ""),
                            "type": getattr(a, "artifact_type", "unknown"),
                            "created_at": getattr(a, "created_at", None),
                        }
                    )
            logger.info(
                "Listed %d artifacts for notebook %s", len(result), notebook_id
            )
            return result
        except NotebookLMClientError:
            raise
        except Exception as exc:
            raise NotebookLMClientError(
                f"Failed to list artifacts for notebook {notebook_id}: {exc}"
            ) from exc

    async def delete_artifact(self, notebook_id: str, artifact_id: str) -> None:
        """Delete an artifact from a remote notebook.

        Requirement 4.3: call the SDK to delete the artifact.
        Uses: client.artifacts.delete(notebook_id, artifact_id)
        """
        client = self._ensure_client()
        try:
            await client.artifacts.delete(
                notebook_id=notebook_id, artifact_id=artifact_id
            )
            logger.info(
                "Deleted artifact %s from notebook %s", artifact_id, notebook_id
            )
        except NotebookLMClientError:
            raise
        except Exception as exc:
            raise NotebookLMClientError(
                f"Failed to delete artifact {artifact_id} from notebook {notebook_id}: {exc}"
            ) from exc

    async def delete_notebook(self, notebook_id: str) -> None:
        """Delete a notebook from the remote NotebookLM account.

        Requirement 5.2: call the SDK to delete the notebook.
        Uses: client.notebooks.delete(notebook_id)
        """
        client = self._ensure_client()
        try:
            await client.notebooks.delete(notebook_id=notebook_id)
            logger.info("Deleted notebook %s", notebook_id)
        except NotebookLMClientError:
            raise
        except Exception as exc:
            raise NotebookLMClientError(
                f"Failed to delete notebook {notebook_id}: {exc}"
            ) from exc
