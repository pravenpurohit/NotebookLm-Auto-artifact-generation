"""NotebookLM Client Wrapper.

Wraps the notebooklm-py SDK to provide a clean async interface for
notebook creation, artifact generation, status polling, and downloads.

Requirements: 6.1, 6.2, 6.3, 6.6
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


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

    Provides create_notebook, submit_generation, poll_status,
    download_artifact, and list_notebooks methods. All SDK calls
    are wrapped in try/except so the wrapper degrades gracefully
    when the SDK is unavailable (e.g. in test environments).
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
        """
        client = self._ensure_client()
        try:
            notebook = await client.create_notebook(title=name)
            notebook_id: str = notebook.id if hasattr(notebook, "id") else str(notebook)

            await client.add_source(notebook_id=notebook_id, file_path=source_path)
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

        Returns the task_id used for polling.

        Requirement 6.1: submit prompt for generation.
        Requirement 6.2: store returned Task_ID.
        """
        client = self._ensure_client()
        try:
            kwargs: dict[str, Any] = {
                "notebook_id": notebook_id,
                "prompt": prompt,
                "artifact_type": artifact_type,
            }
            if audio_format is not None:
                kwargs["audio_format"] = audio_format

            result = await client.generate(**kwargs)
            task_id: str = result.task_id if hasattr(result, "task_id") else str(result)
            logger.info(
                "Submitted generation for notebook %s – task_id=%s",
                notebook_id,
                task_id,
            )
            return task_id
        except NotebookLMClientError:
            raise
        except Exception as exc:
            raise NotebookLMClientError(
                f"Failed to submit generation for notebook {notebook_id}: {exc}"
            ) from exc

    async def poll_status(self, task_id: str) -> dict[str, Any]:
        """Poll the generation status for *task_id*.

        Returns a dict with keys: status, progress, error.

        Requirement 6.3: poll for status updates.
        """
        client = self._ensure_client()
        try:
            result = await client.get_task_status(task_id=task_id)

            if isinstance(result, dict):
                return {
                    "status": result.get("status", "unknown"),
                    "progress": result.get("progress"),
                    "error": result.get("error"),
                }

            return {
                "status": getattr(result, "status", "unknown"),
                "progress": getattr(result, "progress", None),
                "error": getattr(result, "error", None),
            }
        except NotebookLMClientError:
            raise
        except Exception as exc:
            raise NotebookLMClientError(
                f"Failed to poll status for task {task_id}: {exc}"
            ) from exc

    async def download_artifact(self, task_id: str, output_path: str) -> str:
        """Download the completed artifact to *output_path*.

        Creates parent directories if they don't exist.
        Returns the absolute file path of the downloaded artifact.

        Requirement 6.6: download artifact to appropriate subdirectory.
        """
        client = self._ensure_client()
        try:
            await asyncio.to_thread(
                os.makedirs, os.path.dirname(output_path) or ".", exist_ok=True
            )

            await client.download_artifact(task_id=task_id, output_path=output_path)
            abs_path = os.path.abspath(output_path)
            logger.info("Downloaded artifact for task %s to %s", task_id, abs_path)
            return abs_path
        except NotebookLMClientError:
            raise
        except Exception as exc:
            raise NotebookLMClientError(
                f"Failed to download artifact for task {task_id}: {exc}"
            ) from exc

    async def list_notebooks(self) -> list[dict[str, Any]]:
        """List all notebooks in the authenticated account.

        Used for crash recovery (Requirement 10.1).
        Returns a list of dicts with at least 'id' and 'title' keys.
        """
        client = self._ensure_client()
        try:
            notebooks = await client.list_notebooks()

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

        Requirements: 1.1, 1.2
        """
        client = self._ensure_client()
        try:
            artifacts = await client.list_artifacts(notebook_id=notebook_id)

            result: list[dict[str, Any]] = []
            for a in artifacts:
                if isinstance(a, dict):
                    result.append(a)
                else:
                    result.append(
                        {
                            "id": getattr(a, "id", str(a)),
                            "name": getattr(a, "name", ""),
                            "type": getattr(a, "type", "unknown"),
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
        """
        client = self._ensure_client()
        try:
            await client.delete_artifact(
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
        """
        client = self._ensure_client()
        try:
            await client.delete_notebook(notebook_id=notebook_id)
            logger.info("Deleted notebook %s", notebook_id)
        except NotebookLMClientError:
            raise
        except Exception as exc:
            raise NotebookLMClientError(
                f"Failed to delete notebook {notebook_id}: {exc}"
            ) from exc



