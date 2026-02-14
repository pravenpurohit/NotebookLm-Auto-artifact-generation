"""State Manager - SQLite persistence for the NotebookLM Dashboard."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import pathlib
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import aiosqlite

logger = logging.getLogger(__name__)

from app.models import CellStatus

if TYPE_CHECKING:
    from app.ws_manager import CellBroadcaster

# Fixed base directory for artifact files — path validation checks against this
_OUTPUT_BASE = str(pathlib.Path("output").resolve())

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL,
    file_size INTEGER,
    last_modified TEXT,
    notebook_name TEXT NOT NULL,
    notebook_name_edited BOOLEAN DEFAULT FALSE,
    content_hash TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS templates (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    number INTEGER NOT NULL,
    artifact_type TEXT NOT NULL CHECK(artifact_type IN ('infographic', 'audio', 'video')),
    name TEXT NOT NULL,
    audio_format TEXT CHECK(audio_format IN ('DEEP_DIVE', 'BRIEF', 'CRITIQUE', 'DEBATE', NULL)),
    content TEXT NOT NULL,
    content_edited BOOLEAN DEFAULT FALSE,
    is_excluded BOOLEAN DEFAULT FALSE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS generation_cells (
    report_id TEXT NOT NULL REFERENCES reports(id),
    template_id TEXT NOT NULL REFERENCES templates(id),
    status TEXT NOT NULL DEFAULT 'not_started'
        CHECK(status IN ('not_started', 'pending', 'in_progress', 'completed', 'failed', 'stopped')),
    task_id TEXT,
    notebook_id TEXT,
    error_message TEXT,
    started_at TEXT,
    completed_at TEXT,
    artifact_path TEXT,
    prompt_hash TEXT,
    PRIMARY KEY (report_id, template_id)
);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL REFERENCES reports(id),
    template_id TEXT NOT NULL REFERENCES templates(id),
    artifact_type TEXT NOT NULL,
    artifact_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_extension TEXT NOT NULL,
    source_location TEXT,
    source_filename TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cells_status ON generation_cells(status);
CREATE INDEX IF NOT EXISTS idx_cells_task_id ON generation_cells(task_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_type ON artifacts(artifact_type);
CREATE INDEX IF NOT EXISTS idx_artifacts_source ON artifacts(source_filename);
"""


@dataclass
class GenerationCell:
    """In-memory representation of a generation_cells row."""

    report_id: str
    template_id: str
    status: CellStatus
    task_id: str | None = None
    notebook_id: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    artifact_path: str | None = None
    prompt_hash: str | None = None


def _row_to_cell(row: aiosqlite.Row) -> GenerationCell:
    """Convert a database row to a GenerationCell."""
    return GenerationCell(
        report_id=row[0],
        template_id=row[1],
        status=CellStatus(row[2]),
        task_id=row[3],
        notebook_id=row[4],
        error_message=row[5],
        started_at=datetime.fromisoformat(row[6]) if row[6] else None,
        completed_at=datetime.fromisoformat(row[7]) if row[7] else None,
        artifact_path=row[8],
        prompt_hash=row[9] if len(row) > 9 else None,
    )


class StateManager:
    """Manages persistence of application state to SQLite.

    Parameters
    ----------
    db_path : str
        File path for the SQLite database.
    ws_manager : CellBroadcaster | None
        WebSocket manager used to broadcast state changes.
    """

    def __init__(self, db_path: str, ws_manager: CellBroadcaster | None = None) -> None:
        self.db_path = db_path
        self.ws_manager = ws_manager
        self._db: aiosqlite.Connection | None = None
        self._output_base: str = _OUTPUT_BASE

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def open(self) -> None:
        """Open a persistent database connection."""
        if self._db is not None:
            return
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute("PRAGMA journal_mode=WAL;")
        await self._db.execute("PRAGMA foreign_keys=ON;")

    async def close(self) -> None:
        """Close the persistent database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def _conn(self) -> aiosqlite.Connection:
        """Return the persistent connection, raising if not opened."""
        if self._db is None:
            raise RuntimeError("StateManager.open() must be called before database operations")
        return self._db

    async def init_db(self) -> None:
        """Create all tables and indexes if they don't already exist."""
        # init_db can work with or without a persistent connection
        # (for backwards compatibility with tests that don't call open())
        if self._db is not None:
            await self._db.executescript(_SCHEMA_SQL)
            # Migrate: add content_hash column if missing (for existing DBs)
            await self._migrate_content_hash(self._db)
            # Migrate: add prompt_hash column if missing (for existing DBs)
            await self._migrate_prompt_hash(self._db)
            await self._db.commit()
        else:
            async with aiosqlite.connect(self.db_path) as db:
                await db.executescript(_SCHEMA_SQL)
                await self._migrate_content_hash(db)
                await self._migrate_prompt_hash(db)
                await db.execute("PRAGMA journal_mode=WAL;")
                await db.execute("PRAGMA foreign_keys=ON;")
                await db.commit()
    @staticmethod
    async def _migrate_content_hash(db: aiosqlite.Connection) -> None:
        """Add content_hash column to reports table if it doesn't exist."""
        cursor = await db.execute("PRAGMA table_info(reports)")
        columns = [row[1] for row in await cursor.fetchall()]
        if "content_hash" not in columns:
            await db.execute(
                "ALTER TABLE reports ADD COLUMN content_hash TEXT"
            )

    @staticmethod
    async def _migrate_prompt_hash(db: aiosqlite.Connection) -> None:
        """Add prompt_hash column to generation_cells table if it doesn't exist."""
        cursor = await db.execute("PRAGMA table_info(generation_cells)")
        columns = [row[1] for row in await cursor.fetchall()]
        if "prompt_hash" not in columns:
            await db.execute(
                "ALTER TABLE generation_cells ADD COLUMN prompt_hash TEXT"
            )

    @staticmethod
    def compute_content_hash(content: bytes) -> str:
        """Compute SHA-256 hex digest of file content."""
        return hashlib.sha256(content).hexdigest()

    # ------------------------------------------------------------------
    # Connection helper
    # ------------------------------------------------------------------

    async def _get_db(self):
        """Return the persistent connection or open a temporary one.

        When open() has been called, returns the persistent connection.
        Otherwise opens a one-shot connection (backwards compat for tests).
        """
        if self._db is not None:
            return self._db
        # Fallback: open a temporary connection
        db = await aiosqlite.connect(self.db_path)
        await db.execute("PRAGMA foreign_keys=ON;")
        return db

    async def _release_db(self, db: aiosqlite.Connection) -> None:
        """Close the connection only if it's a temporary one."""
        if db is not self._db:
            await db.close()

    # ------------------------------------------------------------------
    # Cell CRUD
    # ------------------------------------------------------------------

    async def get_cell(self, report_id: str, template_id: str) -> GenerationCell | None:
        """Return a single cell or *None* if it doesn't exist."""
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT report_id, template_id, status, task_id, notebook_id, "
                "error_message, started_at, completed_at, artifact_path, prompt_hash "
                "FROM generation_cells WHERE report_id = ? AND template_id = ?",
                (report_id, template_id),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return _row_to_cell(row)
        finally:
            await self._release_db(db)

    async def update_cell(self, cell: GenerationCell) -> None:
        """Upsert a cell and broadcast the change via WebSocket."""
        db = await self._get_db()
        try:
            await db.execute(
                "INSERT OR REPLACE INTO generation_cells "
                "(report_id, template_id, status, task_id, notebook_id, "
                "error_message, started_at, completed_at, artifact_path, prompt_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    cell.report_id,
                    cell.template_id,
                    cell.status.value if isinstance(cell.status, CellStatus) else cell.status,
                    cell.task_id,
                    cell.notebook_id,
                    cell.error_message,
                    cell.started_at.isoformat() if cell.started_at else None,
                    cell.completed_at.isoformat() if cell.completed_at else None,
                    cell.artifact_path,
                    cell.prompt_hash,
                ),
            )
            await db.commit()
        finally:
            await self._release_db(db)

        # Broadcast if a ws_manager is wired up
        if self.ws_manager is not None:
            await self.ws_manager.broadcast_cell_update(cell)

    async def get_all_cells(self) -> list[GenerationCell]:
        """Return every generation cell."""
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT report_id, template_id, status, task_id, notebook_id, "
                "error_message, started_at, completed_at, artifact_path, prompt_hash "
                "FROM generation_cells"
            )
            rows = await cursor.fetchall()
            return [_row_to_cell(r) for r in rows]
        finally:
            await self._release_db(db)

    async def get_cells_by_status(self, status: CellStatus) -> list[GenerationCell]:
        """Return all cells matching the given status."""
        status_val = status.value if isinstance(status, CellStatus) else status
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT report_id, template_id, status, task_id, notebook_id, "
                "error_message, started_at, completed_at, artifact_path, prompt_hash "
                "FROM generation_cells WHERE status = ?",
                (status_val,),
            )
            rows = await cursor.fetchall()
            return [_row_to_cell(r) for r in rows]
        finally:
            await self._release_db(db)

    # ------------------------------------------------------------------
    # Reports / Templates persistence
    # ------------------------------------------------------------------

    async def persist_reports(self, reports: list) -> None:
        """Persist a list of report dicts/models, protecting user-edited notebook names."""
        db = await self._get_db()
        try:
            for r in reports:
                if isinstance(r, dict):
                    vals = r
                else:
                    vals = {
                        "id": r.id,
                        "filename": r.filename,
                        "filepath": r.filepath,
                        "file_size": r.file_size,
                        "last_modified": r.last_modified,
                        "notebook_name": r.notebook_name,
                        "notebook_name_edited": getattr(r, "notebook_name_edited", False),
                        "content_hash": getattr(r, "content_hash", None),
                    }

                content_hash = vals.get("content_hash")

                # Check if report already exists and whether its name was edited
                cursor = await db.execute(
                    "SELECT notebook_name_edited FROM reports WHERE id = ?",
                    (vals["id"],),
                )
                existing = await cursor.fetchone()

                if existing is None:
                    # New report – normal INSERT
                    await db.execute(
                        "INSERT INTO reports "
                        "(id, filename, filepath, file_size, last_modified, notebook_name, notebook_name_edited, content_hash) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            vals["id"],
                            vals["filename"],
                            vals["filepath"],
                            vals.get("file_size"),
                            vals.get("last_modified"),
                            vals["notebook_name"],
                            vals.get("notebook_name_edited", False),
                            content_hash,
                        ),
                    )
                elif existing[0]:
                    # Existing report with user-edited name – update all fields EXCEPT notebook_name and notebook_name_edited
                    await db.execute(
                        "UPDATE reports SET filename = ?, filepath = ?, file_size = ?, last_modified = ?, "
                        "content_hash = ? WHERE id = ?",
                        (
                            vals["filename"],
                            vals["filepath"],
                            vals.get("file_size"),
                            vals.get("last_modified"),
                            content_hash,
                            vals["id"],
                        ),
                    )
                else:
                    # Existing report with non-edited name – update all fields normally
                    await db.execute(
                        "UPDATE reports SET filename = ?, filepath = ?, file_size = ?, last_modified = ?, "
                        "notebook_name = ?, notebook_name_edited = ?, content_hash = ? WHERE id = ?",
                        (
                            vals["filename"],
                            vals["filepath"],
                            vals.get("file_size"),
                            vals.get("last_modified"),
                            vals["notebook_name"],
                            vals.get("notebook_name_edited", False),
                            content_hash,
                            vals["id"],
                        ),
                    )
            await db.commit()
        finally:
            await self._release_db(db)

    async def persist_templates(self, templates: list) -> None:
        """Persist a list of template dicts/models using INSERT OR REPLACE."""
        db = await self._get_db()
        try:
            for t in templates:
                if isinstance(t, dict):
                    vals = t
                else:
                    vals = {
                        "id": t.id,
                        "filename": t.filename,
                        "number": t.number,
                        "artifact_type": t.artifact_type.value if hasattr(t.artifact_type, "value") else t.artifact_type,
                        "name": t.name,
                        "audio_format": t.audio_format.value if hasattr(t.audio_format, "value") and t.audio_format else t.audio_format,
                        "content": t.content,
                        "content_edited": getattr(t, "content_edited", False),
                        "is_excluded": getattr(t, "is_excluded", False),
                    }
                await db.execute(
                    "INSERT OR REPLACE INTO templates "
                    "(id, filename, number, artifact_type, name, audio_format, content, content_edited, is_excluded) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        vals["id"],
                        vals["filename"],
                        vals["number"],
                        vals["artifact_type"],
                        vals["name"],
                        vals.get("audio_format"),
                        vals["content"],
                        vals.get("content_edited", False),
                        vals.get("is_excluded", False),
                    ),
                )
            await db.commit()
        finally:
            await self._release_db(db)

    # ------------------------------------------------------------------
    # Report / Template mutations
    # ------------------------------------------------------------------

    async def delete_report(self, report_id: str) -> bool:
        """Delete a report and its associated generation cells.

        Returns True if the report existed, False otherwise.
        """
        db = await self._get_db()
        try:
            await db.execute("DELETE FROM generation_cells WHERE report_id = ?", (report_id,))
            cursor = await db.execute("DELETE FROM reports WHERE id = ?", (report_id,))
            await db.commit()
            return cursor.rowcount > 0
        finally:
            await self._release_db(db)

    async def update_report_notebook_name(self, report_id: str, notebook_name: str) -> bool:
        """Update a report's notebook name. Returns True if found."""
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "UPDATE reports SET notebook_name = ?, notebook_name_edited = TRUE WHERE id = ?",
                (notebook_name, report_id),
            )
            await db.commit()
            return cursor.rowcount > 0
        finally:
            await self._release_db(db)

    async def update_template_content(self, template_id: str, content: str) -> bool:
        """Update a template's prompt content. Returns True if found."""
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "UPDATE templates SET content = ?, content_edited = TRUE WHERE id = ?",
                (content, template_id),
            )
            await db.commit()
            return cursor.rowcount > 0
        finally:
            await self._release_db(db)

    async def update_template_exclusion(self, template_id: str, is_excluded: bool) -> bool:
        """Toggle a template's is_excluded flag. Returns True if found."""
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "UPDATE templates SET is_excluded = ? WHERE id = ?",
                (is_excluded, template_id),
            )
            await db.commit()
            return cursor.rowcount > 0
        finally:
            await self._release_db(db)

    # ------------------------------------------------------------------
    # Targeted single-entity queries (avoids full load_state over-fetch)
    # ------------------------------------------------------------------

    async def get_template(self, template_id: str) -> dict | None:
        """Return a single template by ID, or None if not found."""
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT id, filename, number, artifact_type, name, audio_format, "
                "content, content_edited, is_excluded, created_at "
                "FROM templates WHERE id = ?",
                (template_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return {
                "id": row[0],
                "filename": row[1],
                "number": row[2],
                "artifact_type": row[3],
                "name": row[4],
                "audio_format": row[5],
                "content": row[6],
                "content_edited": bool(row[7]),
                "is_excluded": bool(row[8]),
                "created_at": row[9],
            }
        finally:
            await self._release_db(db)

    async def get_report(self, report_id: str) -> dict | None:
        """Return a single report by ID, or None if not found."""
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT id, filename, filepath, file_size, last_modified, "
                "notebook_name, notebook_name_edited, created_at, content_hash "
                "FROM reports WHERE id = ?",
                (report_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return {
                "id": row[0],
                "filename": row[1],
                "filepath": row[2],
                "file_size": row[3],
                "last_modified": row[4],
                "notebook_name": row[5],
                "notebook_name_edited": bool(row[6]),
                "created_at": row[7],
                "content_hash": row[8],
            }
        finally:
            await self._release_db(db)

    async def get_all_reports(self) -> list[dict]:
        """Return all reports."""
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT id, filename, filepath, file_size, last_modified, "
                "notebook_name, notebook_name_edited, created_at, content_hash FROM reports"
            )
            rows = await cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "filename": row[1],
                    "filepath": row[2],
                    "file_size": row[3],
                    "last_modified": row[4],
                    "notebook_name": row[5],
                    "notebook_name_edited": bool(row[6]),
                    "created_at": row[7],
                    "content_hash": row[8],
                }
                for row in rows
            ]
        finally:
            await self._release_db(db)

    async def get_all_templates(self) -> list[dict]:
        """Return all templates."""
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT id, filename, number, artifact_type, name, audio_format, "
                "content, content_edited, is_excluded, created_at FROM templates"
            )
            rows = await cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "filename": row[1],
                    "number": row[2],
                    "artifact_type": row[3],
                    "name": row[4],
                    "audio_format": row[5],
                    "content": row[6],
                    "content_edited": bool(row[7]),
                    "is_excluded": bool(row[8]),
                    "created_at": row[9],
                }
                for row in rows
            ]
        finally:
            await self._release_db(db)
    async def find_template_by_filename(self, filename: str) -> dict | None:
        """Find a template by filename, or None if not found."""
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT id, filename, number, artifact_type, name, audio_format, "
                "content, content_edited, is_excluded, created_at "
                "FROM templates WHERE filename = ?",
                (filename,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return {
                "id": row[0],
                "filename": row[1],
                "number": row[2],
                "artifact_type": row[3],
                "name": row[4],
                "audio_format": row[5],
                "content": row[6],
                "content_edited": bool(row[7]),
                "is_excluded": bool(row[8]),
                "created_at": row[9],
            }
        finally:
            await self._release_db(db)


    # ------------------------------------------------------------------
    # Artifact queries
    # ------------------------------------------------------------------

    async def list_artifacts(
        self,
        source_location: str | None = None,
        source_filename: str | None = None,
        artifact_type: str | None = None,
    ) -> list[dict]:
        """List artifacts with optional filters."""
        db = await self._get_db()
        try:
            query = (
                "SELECT a.id, a.report_id, a.template_id, a.artifact_type, a.artifact_name, "
                "a.file_path, a.file_extension, a.source_location, a.source_filename, "
                "a.created_at, gc.notebook_id "
                "FROM artifacts a "
                "LEFT JOIN generation_cells gc "
                "ON a.report_id = gc.report_id AND a.template_id = gc.template_id "
                "WHERE 1=1"
            )
            params: list = []

            if source_location is not None:
                query += " AND a.source_location = ?"
                params.append(source_location)
            if source_filename is not None:
                query += " AND a.source_filename = ?"
                params.append(source_filename)
            if artifact_type is not None:
                query += " AND a.artifact_type = ?"
                params.append(artifact_type)

            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

            return [
                {
                    "id": row[0],
                    "report_id": row[1],
                    "template_id": row[2],
                    "artifact_type": row[3],
                    "artifact_name": row[4],
                    "file_path": row[5],
                    "file_extension": row[6],
                    "source_location": row[7],
                    "source_filename": row[8],
                    "created_at": row[9],
                    "source_notebook_id": row[10],
                }
                for row in rows
            ]
        finally:
            await self._release_db(db)

    async def get_artifact(self, artifact_id: str) -> dict | None:
        """Get artifact metadata by ID. Returns None if not found."""
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT id, file_path, artifact_name, file_extension, artifact_type "
                "FROM artifacts WHERE id = ?",
                (artifact_id,),
            )
            row = await cursor.fetchone()

            if row is None:
                return None
            return {
                "id": row[0],
                "file_path": row[1],
                "artifact_name": row[2],
                "file_extension": row[3],
                "artifact_type": row[4],
            }
        finally:
            await self._release_db(db)

    async def delete_artifact_record(self, artifact_id: str) -> bool:
        """Delete an artifact record from the database and its file from disk.

        Returns True if the artifact existed, False otherwise.

        Requirement 4.2: remove artifact record and delete file from disk.
        """
        db = await self._get_db()
        try:
            # Fetch file path before deleting the record
            cursor = await db.execute(
                "SELECT file_path FROM artifacts WHERE id = ?",
                (artifact_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return False

            file_path = row[0]

            # Delete the database record
            await db.execute("DELETE FROM artifacts WHERE id = ?", (artifact_id,))
            await db.commit()

            # Delete the file from disk if it exists (async to avoid blocking event loop)
            if file_path:
                resolved = pathlib.Path(file_path).resolve()
                output_base = pathlib.Path(self._output_base).resolve()
                if not resolved.is_relative_to(output_base):
                    logger.warning("Skipping file deletion — resolved path outside output directory: %s", resolved)
                elif await asyncio.to_thread(os.path.isfile, str(resolved)):
                    await asyncio.to_thread(os.remove, str(resolved))
                    logger.info("Deleted artifact file: %s", resolved)

            logger.info("Deleted artifact record: %s", artifact_id)
            return True
        finally:
            await self._release_db(db)

    async def delete_notebook_records(self, notebook_id: str) -> int:
        """Remove all local records associated with a notebook.

        Cascade logic:
        1. Find all generation_cells with the given notebook_id
        2. For each cell, delete artifacts matching (report_id, template_id)
        3. Delete the generation_cells themselves

        Returns the number of generation cells deleted.

        Requirement 5.3: remove all associated local records.
        """
        db = await self._get_db()
        try:
            # Find generation cells for this notebook
            cursor = await db.execute(
                "SELECT report_id, template_id FROM generation_cells WHERE notebook_id = ?",
                (notebook_id,),
            )
            cells = await cursor.fetchall()

            if not cells:
                return 0

            # Delete artifacts for each cell, then delete artifact files from disk
            for report_id, template_id in cells:
                # Get file paths before deleting records
                file_cursor = await db.execute(
                    "SELECT file_path FROM artifacts WHERE report_id = ? AND template_id = ?",
                    (report_id, template_id),
                )
                file_rows = await file_cursor.fetchall()

                await db.execute(
                    "DELETE FROM artifacts WHERE report_id = ? AND template_id = ?",
                    (report_id, template_id),
                )

                # Delete files from disk (async to avoid blocking event loop)
                for (file_path,) in file_rows:
                    if file_path:
                        resolved = pathlib.Path(file_path).resolve()
                        output_base = pathlib.Path(self._output_base).resolve()
                        if not resolved.is_relative_to(output_base):
                            logger.warning("Skipping file deletion — resolved path outside output directory: %s", resolved)
                        elif await asyncio.to_thread(os.path.isfile, str(resolved)):
                            await asyncio.to_thread(os.remove, str(resolved))
                            logger.info("Deleted artifact file: %s", resolved)

            # Delete the generation cells
            await db.execute(
                "DELETE FROM generation_cells WHERE notebook_id = ?",
                (notebook_id,),
            )
            await db.commit()

            deleted_count = len(cells)
            logger.info(
                "Deleted %d generation cells and associated artifacts for notebook %s",
                deleted_count,
                notebook_id,
            )
            return deleted_count
        finally:
            await self._release_db(db)
    async def find_notebook_by_content_hash(self, content_hash: str) -> dict | None:
        """Find an existing notebook linked to a report with the given content hash.

        Checks if any generation cell has a notebook_id linked to a report
        with the same content_hash. Returns dict with notebook info if found,
        None otherwise.

        Requirement 7.2: check if a notebook already exists with the same content hash.
        """
        if not content_hash:
            return None
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT gc.notebook_id, r.id, r.filename, r.notebook_name "
                "FROM generation_cells gc "
                "JOIN reports r ON gc.report_id = r.id "
                "WHERE r.content_hash = ? AND gc.notebook_id IS NOT NULL "
                "LIMIT 1",
                (content_hash,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return {
                "notebook_id": row[0],
                "report_id": row[1],
                "filename": row[2],
                "notebook_name": row[3],
            }
        finally:
            await self._release_db(db)

    async def get_all_content_hashes(self) -> set[str]:
        """Return a set of all non-null content_hash values from reports.

        Used by the remote notebook listing to flag 'already linked' notebooks.
        Requirement 7.5.
        """
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT DISTINCT content_hash FROM reports WHERE content_hash IS NOT NULL"
            )
            rows = await cursor.fetchall()
            return {row[0] for row in rows}
        finally:
            await self._release_db(db)
    async def find_duplicate_prompt(self, report_id: str, prompt_hash: str) -> dict | None:
        """Find a completed generation cell with the same (report_id, prompt_hash).

        Returns dict with existing cell info if found, None otherwise.
        Requirement 8.2: check if a completed cell exists with the same prompt hash.
        """
        if not prompt_hash:
            return None
        db = await self._get_db()
        try:
            cursor = await db.execute(
                "SELECT gc.report_id, gc.template_id, gc.artifact_path, gc.notebook_id "
                "FROM generation_cells gc "
                "WHERE gc.report_id = ? AND gc.prompt_hash = ? AND gc.status = 'completed' "
                "LIMIT 1",
                (report_id, prompt_hash),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return {
                "report_id": row[0],
                "template_id": row[1],
                "artifact_path": row[2],
                "notebook_id": row[3],
            }
        finally:
            await self._release_db(db)




    # ------------------------------------------------------------------
    # Full state load
    # ------------------------------------------------------------------

    async def load_state(self) -> dict:
        """Load full state from DB.

        Returns a dict with keys ``reports``, ``templates``, and ``cells``.
        """
        db = await self._get_db()
        try:
            # Reports
            cursor = await db.execute(
                "SELECT id, filename, filepath, file_size, last_modified, "
                "notebook_name, notebook_name_edited, created_at, content_hash FROM reports"
            )
            report_rows = await cursor.fetchall()
            reports = [
                {
                    "id": row[0],
                    "filename": row[1],
                    "filepath": row[2],
                    "file_size": row[3],
                    "last_modified": row[4],
                    "notebook_name": row[5],
                    "notebook_name_edited": bool(row[6]),
                    "created_at": row[7],
                    "content_hash": row[8],
                }
                for row in report_rows
            ]

            # Templates
            cursor = await db.execute(
                "SELECT id, filename, number, artifact_type, name, audio_format, "
                "content, content_edited, is_excluded, created_at FROM templates"
            )
            template_rows = await cursor.fetchall()
            templates = [
                {
                    "id": row[0],
                    "filename": row[1],
                    "number": row[2],
                    "artifact_type": row[3],
                    "name": row[4],
                    "audio_format": row[5],
                    "content": row[6],
                    "content_edited": bool(row[7]),
                    "is_excluded": bool(row[8]),
                    "created_at": row[9],
                }
                for row in template_rows
            ]

            # Cells
            cursor = await db.execute(
                "SELECT report_id, template_id, status, task_id, notebook_id, "
                "error_message, started_at, completed_at, artifact_path, prompt_hash "
                "FROM generation_cells"
            )
            cell_rows = await cursor.fetchall()
            cells = [_row_to_cell(r) for r in cell_rows]

            return {"reports": reports, "templates": templates, "cells": cells}
        finally:
            await self._release_db(db)

    async def recover_state(self, nlm_client: object) -> dict:
        """Recover state after a crash by matching remote notebooks to local cells.

        Calls ``nlm_client.list_notebooks()`` to retrieve all remote notebooks,
        loads local generation cells from the DB, and matches them by
        ``notebook_id``.

        Parameters
        ----------
        nlm_client : NotebookLMClientWrapper
            Client used to list remote notebooks.

        Returns
        -------
        dict
            ``matched``   – list of ``(remote_notebook, local_cell)`` tuples
            ``in_progress`` – subset of matched local cells with status IN_PROGRESS
            ``untracked`` – remote notebooks with no local cell match

        Requirements: 10.1, 10.2, 10.3, 10.5
        """
        # 10.1 – Retrieve all notebooks from the Google account
        remote_notebooks = await nlm_client.list_notebooks()

        # Load local cells from DB
        local_cells = await self.get_all_cells()

        # Build a lookup: notebook_id -> GenerationCell
        cells_by_notebook_id: dict[str, GenerationCell] = {}
        for cell in local_cells:
            if cell.notebook_id is not None:
                cells_by_notebook_id[cell.notebook_id] = cell

        matched: list[tuple[dict, GenerationCell]] = []
        in_progress: list[GenerationCell] = []
        untracked: list[dict] = []

        for nb in remote_notebooks:
            nb_id = nb.get("id") if isinstance(nb, dict) else getattr(nb, "id", None)
            if nb_id is not None and nb_id in cells_by_notebook_id:
                cell = cells_by_notebook_id[nb_id]
                # 10.2 – Match retrieved notebooks to local cells
                matched.append((nb, cell))
                # 10.3 – Flag in-progress tasks for polling resumption
                if cell.status == CellStatus.IN_PROGRESS:
                    in_progress.append(cell)
            else:
                # 10.5 – Untracked notebooks (no local match)
                untracked.append(nb)

        return {
            "matched": matched,
            "in_progress": in_progress,
            "untracked": untracked,
        }

