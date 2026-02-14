"""Asyncio-based task queue for artifact generation.

Manages concurrency with pause/resume/stop semantics. Each generation
task follows the workflow: create notebook → submit prompt → poll → download.

Requirements: 6.1, 6.2, 6.4, 8.1, 8.2, 8.3, 9.1, 9.2, 9.3, 9.4, 9.5
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.artifact_namer import ArtifactNamer
from app.models import CellStatus
from app.nlm_client import NotebookLMClientError, NotebookLMClientWrapper
from app.state_manager import GenerationCell, StateManager

logger = logging.getLogger(__name__)

# Polling interval in seconds when checking generation status
_POLL_INTERVAL = 5.0


class DuplicateTaskError(Exception):
    """Raised when a duplicate in-progress task is enqueued."""


class TaskQueue:
    """Manages artifact generation concurrency with pause/resume/stop.

    Parameters
    ----------
    state_manager : StateManager
        Persistence layer for cell state.
    nlm_client : NotebookLMClientWrapper
        Client for NotebookLM API calls.
    max_concurrent : int
        Maximum number of concurrent generation tasks.
    """

    def __init__(
        self,
        state_manager: StateManager,
        nlm_client: NotebookLMClientWrapper,
        max_concurrent: int = 2,
    ) -> None:
        self.state_manager = state_manager
        self.nlm_client = nlm_client
        self.max_concurrent = max_concurrent
        self._artifact_namer = ArtifactNamer()

        # Concurrency control
        self._semaphore = asyncio.Semaphore(max_concurrent)

        # Pause/resume: event is *set* when running, *cleared* when paused
        self._resume_event = asyncio.Event()
        self._resume_event.set()

        # Track running asyncio tasks keyed by (report_id, template_id)
        self._running_tasks: dict[tuple[str, str], asyncio.Task[None]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def enqueue(self, report_id: str, template_id: str) -> str:
        """Add a generation task. Returns Task_ID.

        Raises DuplicateTaskError if the cell already has an in-progress task
        (Req 6.4 – duplicate prevention).
        """
        cell = await self.state_manager.get_cell(report_id, template_id)

        # Duplicate detection: if already in_progress, return existing task_id
        if cell is not None and cell.status == CellStatus.IN_PROGRESS and cell.task_id:
            raise DuplicateTaskError(
                f"Task already in progress for ({report_id}, {template_id}) "
                f"with task_id={cell.task_id}"
            )

        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        new_cell = GenerationCell(
            report_id=report_id,
            template_id=template_id,
            status=CellStatus.IN_PROGRESS,
            task_id=task_id,
            notebook_id=cell.notebook_id if cell else None,
            error_message=None,
            started_at=now,
            completed_at=None,
            artifact_path=cell.artifact_path if cell else None,
        )
        await self.state_manager.update_cell(new_cell)

        # Launch the background generation task
        key = (report_id, template_id)
        task = asyncio.create_task(self._run_generation(new_cell))
        self._running_tasks[key] = task
        task.add_done_callback(lambda _t: self._running_tasks.pop(key, None))

        logger.info(
            "Enqueued task %s for (%s, %s)", task_id, report_id, template_id
        )
        return task_id

    async def start_all(self, cells: list[GenerationCell]) -> None:
        """Enqueue all not_started/pending cells (Req 9.1)."""
        for cell in cells:
            if cell.status in (CellStatus.NOT_STARTED, CellStatus.PENDING):
                try:
                    await self.enqueue(cell.report_id, cell.template_id)
                except DuplicateTaskError:
                    logger.debug(
                        "Skipping duplicate (%s, %s)",
                        cell.report_id,
                        cell.template_id,
                    )

    async def pause(self) -> None:
        """Stop dequeuing new tasks. In-progress tasks continue (Req 9.2)."""
        self._resume_event.clear()
        logger.info("Task queue paused")

    async def resume(self) -> None:
        """Resume dequeuing tasks (Req 9.3)."""
        self._resume_event.set()
        logger.info("Task queue resumed")

    async def stop_all(self) -> None:
        """Cancel all in-progress tasks and set status to stopped (Req 9.4)."""
        keys = list(self._running_tasks.keys())
        for report_id, template_id in keys:
            await self.stop_task(report_id, template_id)

    async def retry_failed(self) -> None:
        """Re-enqueue all failed cells with new Task_IDs (Req 9.5)."""
        failed_cells = await self.state_manager.get_cells_by_status(CellStatus.FAILED)
        for cell in failed_cells:
            try:
                await self.enqueue(cell.report_id, cell.template_id)
            except DuplicateTaskError:
                logger.debug(
                    "Skipping duplicate on retry (%s, %s)",
                    cell.report_id,
                    cell.template_id,
                )
    async def wait_for(self, report_id: str, template_id: str) -> None:
        """Await completion of a specific generation task.

        Useful in tests to avoid flaky ``asyncio.sleep()`` waits.
        Returns immediately if no task is running for the given key.
        """
        key = (report_id, template_id)
        task = self._running_tasks.get(key)
        if task is not None:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    async def stop_task(self, report_id: str, template_id: str) -> None:
        """Cancel a specific in-progress task (Req 8.2)."""
        key = (report_id, template_id)
        task = self._running_tasks.pop(key, None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Mark cell as stopped regardless of whether we found a running task
        cell = await self.state_manager.get_cell(report_id, template_id)
        if cell is not None and cell.status == CellStatus.IN_PROGRESS:
            cell.status = CellStatus.STOPPED
            cell.completed_at = datetime.now(timezone.utc)
            await self.state_manager.update_cell(cell)
            logger.info("Stopped task for (%s, %s)", report_id, template_id)

    # ------------------------------------------------------------------
    # Internal generation workflow
    # ------------------------------------------------------------------

    async def _run_generation(self, cell: GenerationCell) -> None:
        """Execute the full generation workflow for a single cell.

        Workflow: wait for semaphore → wait if paused → create notebook →
        submit generation → poll until done → download artifact.
        """
        report_id = cell.report_id
        template_id = cell.template_id

        try:
            # Acquire semaphore for concurrency control
            async with self._semaphore:
                # Wait if paused (Req 9.2/9.3)
                await self._resume_event.wait()

                # Fetch report and template info from state
                report = await self.state_manager.get_report(report_id)
                template = await self.state_manager.get_template(template_id)

                if report is None or template is None:
                    raise ValueError(
                        f"Report ({report_id}) or template ({template_id}) not found in state"
                    )

                # Compute and store prompt hash (Req 8.1)
                prompt_hash = StateManager.compute_content_hash(
                    template["content"].encode("utf-8")
                )
                cell.prompt_hash = prompt_hash
                await self.state_manager.update_cell(cell)

                # Step 1: Create notebook and attach source (Req 6.1)
                notebook_id = await self._create_and_attach_notebook(cell, report)

                # Step 2: Submit generation and poll (Req 6.1, 6.2, 6.3)
                nlm_task_id = await self._submit_and_poll(cell, notebook_id, template)

                # Step 3: Download artifact and mark complete (Req 6.6)
                await self._download_and_complete(cell, template, nlm_task_id)

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            logger.error(
                "Generation failed for (%s, %s): %s",
                report_id,
                template_id,
                exc,
            )
            cell.status = CellStatus.FAILED
            cell.error_message = str(exc)
            cell.completed_at = datetime.now(timezone.utc)
            await self.state_manager.update_cell(cell)

    async def _create_and_attach_notebook(
        self, cell: GenerationCell, report: dict[str, Any]
    ) -> str:
        """Create a notebook and attach the report source. Returns notebook_id.

        Before creating, checks if a notebook with the same content_hash
        already exists (Req 7.2). If found, reuses the existing notebook_id
        and logs a warning (Req 7.3).
        """
        # Duplicate detection: check for existing notebook with same content hash
        content_hash = report.get("content_hash")
        if content_hash:
            existing = await self.state_manager.find_notebook_by_content_hash(content_hash)
            if existing and existing["notebook_id"]:
                logger.warning(
                    "Duplicate notebook detected for report %s (hash=%s). "
                    "Reusing existing notebook %s from report %s.",
                    report["id"],
                    content_hash[:8],
                    existing["notebook_id"],
                    existing["report_id"],
                )
                cell.notebook_id = existing["notebook_id"]
                await self.state_manager.update_cell(cell)
                return existing["notebook_id"]

        # Use the report's notebook_name which includes the hash suffix (Req 7.4)
        notebook_name = report.get("notebook_name") or self._artifact_namer.derive_notebook_name(report["filename"])
        notebook_id = await self.nlm_client.create_notebook(
            name=notebook_name, source_path=report["filepath"]
        )
        cell.notebook_id = notebook_id
        await self.state_manager.update_cell(cell)
        return notebook_id

    async def _submit_and_poll(
        self, cell: GenerationCell, notebook_id: str, template: dict[str, Any]
    ) -> str:
        """Submit generation prompt and poll until done. Returns nlm_task_id."""
        nlm_task_id = await self.nlm_client.submit_generation(
            notebook_id=notebook_id,
            prompt=template["content"],
            artifact_type=template["artifact_type"],
            audio_format=template.get("audio_format"),
        )
        cell.task_id = nlm_task_id
        await self.state_manager.update_cell(cell)
        await self._poll_until_done(nlm_task_id)
        return nlm_task_id

    async def _download_and_complete(
        self, cell: GenerationCell, template: dict[str, Any], nlm_task_id: str
    ) -> None:
        """Download the artifact and mark the cell as completed."""
        artifact_type = template["artifact_type"]
        artifact_filename = self._artifact_namer.get_artifact_filename(
            template["filename"], artifact_type
        )
        output_dir = self._output_dir_for_type(artifact_type)
        output_path = f"{output_dir}/{artifact_filename}"

        downloaded_path = await self.nlm_client.download_artifact(
            task_id=nlm_task_id, output_path=output_path
        )

        cell.status = CellStatus.COMPLETED
        cell.completed_at = datetime.now(timezone.utc)
        cell.artifact_path = downloaded_path
        cell.error_message = None
        await self.state_manager.update_cell(cell)
        logger.info(
            "Completed generation for (%s, %s) → %s",
            cell.report_id,
            cell.template_id,
            downloaded_path,
        )

    async def _poll_until_done(self, task_id: str) -> None:
        """Poll NLM API until the task completes or fails.

        Raises NotebookLMClientError if the task fails or times out
        (max 360 iterations × 5s = 30 minutes).
        """
        max_polls = 360
        for _ in range(max_polls):
            result = await self.nlm_client.poll_status(task_id)
            status = result.get("status", "unknown")

            if status == "completed":
                return
            if status in ("failed", "error"):
                error_msg = result.get("error") or "Generation failed"
                raise NotebookLMClientError(error_msg)

            await asyncio.sleep(_POLL_INTERVAL)

        raise NotebookLMClientError("Generation timed out")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _output_dir_for_type(artifact_type: str) -> str:
        """Return the output subdirectory for the given artifact type."""
        dirs = {
            "infographic": "output/infographics",
            "audio": "output/audio",
            "video": "output/video",
        }
        return dirs.get(artifact_type, "output")
