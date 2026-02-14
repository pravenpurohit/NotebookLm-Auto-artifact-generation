"""Template detection and classification module.

Parses template filenames and classifies them by artifact type and audio format.
Supports content-based fallback detection when filename parsing is insufficient.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from app.models import TEMPLATE_FILENAME_RE


@dataclass
class TemplateInfo:
    filename: str
    number: int
    artifact_type: str  # "infographic" | "audio" | "video"
    name: str  # Extracted display name
    audio_format: str | None  # "DEEP_DIVE" | "BRIEF" | "CRITIQUE" | "DEBATE" | None
    content: str  # Raw markdown content
    is_excluded: bool  # True for steering prompts


class TemplateDetector:
    FILENAME_PATTERN = TEMPLATE_FILENAME_RE.pattern
    EXCLUDED_FILES = {"01_Steering Prompt.md"}

    TYPE_MAP = {
        "Infographic": "infographic",
        "Audio": "audio",
        "Video": "video",
    }

    AUDIO_FORMAT_MAP = {
        "DeepDive": "DEEP_DIVE",
        "TheBrief": "BRIEF",
        "Critique": "CRITIQUE",
        "Debate": "DEBATE",
    }

    def parse_filename(self, filename: str) -> TemplateInfo | None:
        """Parse a template filename into TemplateInfo. Returns None if unparseable."""
        match = re.match(self.FILENAME_PATTERN, filename)
        if not match:
            return None

        number = int(match.group(1))
        type_part = match.group(2)
        name_part = match.group(3)

        is_excluded = filename in self.EXCLUDED_FILES

        # Determine artifact type from the type portion of the filename
        artifact_type = self.TYPE_MAP.get(type_part)

        # Determine audio format from the name portion
        audio_format = self._detect_audio_format(name_part)

        return TemplateInfo(
            filename=filename,
            number=number,
            artifact_type=artifact_type or "unknown",
            name=name_part,
            audio_format=audio_format,
            content="",
            is_excluded=is_excluded,
        )

    def detect_type_from_content(self, content: str) -> str | None:
        """Fallback: detect artifact type from template file content."""
        content_lower = content.lower()

        # Check for type keywords in content, ordered by specificity
        for keyword, artifact_type in [
            ("infographic", "infographic"),
            ("audio", "audio"),
            ("video", "video"),
        ]:
            if keyword in content_lower:
                return artifact_type

        return None

    def load_templates(self, directory: str) -> list[TemplateInfo]:
        """Load and classify all templates from a directory."""
        templates: list[TemplateInfo] = []

        if not os.path.isdir(directory):
            return templates

        for filename in sorted(os.listdir(directory)):
            if not filename.endswith(".md"):
                continue

            filepath = os.path.join(directory, filename)
            if not os.path.isfile(filepath):
                continue

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
            except (OSError, UnicodeDecodeError):
                continue

            info = self.parse_filename(filename)

            # Handle excluded files that may not match the standard pattern
            if info is None and filename in self.EXCLUDED_FILES:
                info = TemplateInfo(
                    filename=filename,
                    number=0,
                    artifact_type="unknown",
                    name=filename,
                    audio_format=None,
                    content=content,
                    is_excluded=True,
                )
                templates.append(info)
                continue

            if info is None:
                continue

            info.content = content

            # Fallback: if type couldn't be determined from filename, try content
            if info.artifact_type == "unknown":
                detected = self.detect_type_from_content(content)
                if detected:
                    info.artifact_type = detected

            templates.append(info)

        return templates

    def _detect_audio_format(self, name: str) -> str | None:
        """Detect audio format from the name portion of the filename."""
        for keyword, fmt in self.AUDIO_FORMAT_MAP.items():
            if keyword in name:
                return fmt
        return None
