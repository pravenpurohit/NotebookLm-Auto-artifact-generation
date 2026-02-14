from __future__ import annotations

import re
from typing import Optional, List

from pydantic import BaseModel
from datetime import datetime
from enum import Enum


class ArtifactType(str, Enum):
    INFOGRAPHIC = "infographic"
    AUDIO = "audio"
    VIDEO = "video"


class AudioFormat(str, Enum):
    DEEP_DIVE = "DEEP_DIVE"
    BRIEF = "BRIEF"
    CRITIQUE = "CRITIQUE"
    DEBATE = "DEBATE"


class CellStatus(str, Enum):
    NOT_STARTED = "not_started"
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


# Shared template filename pattern: {number}_{Type}_{Name}.md
TEMPLATE_FILENAME_RE = re.compile(r"^(\d+)_([^_]+)_(.+)\.md$")



class ReportModel(BaseModel):
    id: str
    filename: str
    filepath: str
    file_size: Optional[int] = None
    last_modified: Optional[str] = None
    notebook_name: str
    notebook_name_edited: bool = False


class TemplateModel(BaseModel):
    id: str
    filename: str
    number: int
    artifact_type: ArtifactType
    name: str
    audio_format: Optional[AudioFormat] = None
    content: str
    content_edited: bool = False
    is_excluded: bool = False


class GenerationCellModel(BaseModel):
    report_id: str
    template_id: str
    status: CellStatus
    task_id: Optional[str] = None
    notebook_id: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    artifact_path: Optional[str] = None


class ArtifactModel(BaseModel):
    id: str
    report_id: str
    template_id: str
    artifact_type: ArtifactType
    artifact_name: str
    file_path: str
    file_extension: str
    source_location: Optional[str] = None
    source_filename: Optional[str] = None
    created_at: datetime


class GridStateModel(BaseModel):
    reports: List[ReportModel]
    templates: List[TemplateModel]
    cells: List[GenerationCellModel]


class ArtifactFilterModel(BaseModel):
    source_location: Optional[str] = None
    source_filename: Optional[str] = None
    artifact_type: Optional[ArtifactType] = None

# --- Request models for route validation ---

class UpdateReportRequest(BaseModel):
    notebook_name: str


class UpdateTemplateRequest(BaseModel):
    content: str


class RemoteArtifactResponse(BaseModel):
    """A remote artifact fetched from the user's NotebookLM account.

    Requirements: 1.2, 7.5
    """

    id: str
    artifact_name: str
    artifact_type: str
    source_notebook_title: str
    source_notebook_id: str
    created_at: Optional[str] = None
    is_remote: bool = True
    is_linked: bool = False


