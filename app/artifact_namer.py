"""Artifact and notebook naming module.

Derives artifact names from template filenames and notebook names from report filenames.
Uses the same filename pattern as TemplateDetector for consistency.
"""

from __future__ import annotations

import os

from app.models import TEMPLATE_FILENAME_RE


class ArtifactNamer:
    """Derives artifact and notebook names from filenames."""

    EXTENSION_MAP = {
        "infographic": ".png",
        "audio": ".mp3",
        "video": ".mp4",
    }

    _FILENAME_PATTERN = TEMPLATE_FILENAME_RE

    def derive_artifact_name(self, template_filename: str) -> str:
        """Extract the Name portion from {number}_{Type}_{Name}.md.

        Args:
            template_filename: Template filename matching the pattern.

        Returns:
            The extracted {Name} portion.

        Raises:
            ValueError: If the filename does not match the expected pattern.
        """
        match = self._FILENAME_PATTERN.match(template_filename)
        if not match:
            raise ValueError(
                f"Template filename does not match pattern "
                f"{{number}}_{{Type}}_{{Name}}.md: {template_filename!r}"
            )
        return match.group(3)

    def derive_notebook_name(self, report_filename: str) -> str:
        """Strip extension from report filename.

        Args:
            report_filename: Report filename (e.g. "My Report.pdf").

        Returns:
            Filename without extension (e.g. "My Report").
        """
        root, _ = os.path.splitext(report_filename)
        return root

    def get_artifact_filename(self, template_filename: str, artifact_type: str) -> str:
        """Combine derived name with correct extension.

        Args:
            template_filename: Template filename matching the pattern.
            artifact_type: One of "infographic", "audio", or "video".

        Returns:
            Artifact filename with the correct extension.

        Raises:
            ValueError: If the template filename doesn't match or artifact_type is unknown.
        """
        name = self.derive_artifact_name(template_filename)
        ext = self.EXTENSION_MAP.get(artifact_type)
        if ext is None:
            raise ValueError(f"Unknown artifact type: {artifact_type!r}")
        return name + ext
