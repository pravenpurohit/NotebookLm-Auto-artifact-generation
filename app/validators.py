"""File format validation for report file selection."""

import os


def validate_file_format(filename: str) -> bool:
    """Validate that a file has an accepted format (.pdf or .md).

    Args:
        filename: The filename (or path) to validate.

    Returns:
        True if the file extension is .pdf or .md (case-insensitive), False otherwise.
    """
    _, ext = os.path.splitext(filename)
    return ext.lower() in {".pdf", ".md"}
