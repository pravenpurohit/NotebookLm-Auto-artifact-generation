"""Property-based tests for ArtifactNamer.

Property 1: Notebook name derivation
**Validates: Requirements 3.1, 3.3**

Property 5: Artifact filename derivation
**Validates: Requirements 5.1, 5.3**
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from app.artifact_namer import ArtifactNamer

# Valid report file extensions
VALID_EXTENSIONS = [".pdf", ".md"]

# Strategy for valid extensions
valid_extensions = st.sampled_from(VALID_EXTENSIONS)

# Strategy for report base names: non-empty printable text without path
# separators or newlines.  We exclude dots so that the result of stripping
# the extension is truly extension-free, which lets us verify idempotency
# (the second application is a no-op because there is no dot left).
report_basenames = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        blacklist_characters="/\\\n\r\t\x0b\x0c.",
    ),
    min_size=1,
    max_size=100,
).filter(lambda s: s.strip() == s and len(s.strip()) > 0)


@settings(max_examples=200)
@given(basename=report_basenames, ext=valid_extensions)
def test_property_1_notebook_name_derivation(basename, ext):
    """Property 1: Notebook name derivation.

    **Validates: Requirements 3.1, 3.3**

    For any report filename (with any valid extension), deriving the notebook
    name should produce the filename without its extension, and this operation
    should be consistent (applying it twice to the same input yields the same
    result).
    """
    namer = ArtifactNamer()
    report_filename = basename + ext

    # 1. derive_notebook_name strips the extension
    notebook_name = namer.derive_notebook_name(report_filename)
    assert notebook_name == basename, (
        f"Expected '{basename}' but got '{notebook_name}' "
        f"for filename '{report_filename}'"
    )

    # 2. Idempotency: applying derive_notebook_name to the result (which has
    #    no extension) should return the same value, since stripping a
    #    non-existent extension is a no-op.
    second_pass = namer.derive_notebook_name(notebook_name)
    assert second_pass == notebook_name, (
        f"Idempotency failed: first pass '{notebook_name}', "
        f"second pass '{second_pass}'"
    )


# --- Property 5: Artifact filename derivation ---

# Type keywords that map to artifact types (matching TemplateDetector.TYPE_MAP)
TYPE_KEYWORDS = ["Infographic", "Audio", "Video"]

# Artifact types matching ArtifactNamer.EXTENSION_MAP
ARTIFACT_TYPES = ["infographic", "audio", "video"]

# Expected extensions per artifact type
EXPECTED_EXTENSIONS = {
    "infographic": ".png",
    "audio": ".mp3",
    "video": ".mp4",
}

# Strategy for template number prefix (1-99)
template_numbers = st.integers(min_value=1, max_value=99)

# Strategy for type keyword
type_keywords = st.sampled_from(TYPE_KEYWORDS)

# Strategy for artifact type
artifact_types = st.sampled_from(ARTIFACT_TYPES)

# Strategy for the {Name} portion: non-empty text that doesn't contain
# newlines or the .md extension suffix, and doesn't start/end with whitespace.
# We allow a broad range of characters including spaces, hyphens, etc.
template_names = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        blacklist_characters="/\\\n\r\t\x0b\x0c",
    ),
    min_size=1,
    max_size=100,
).filter(lambda s: s.strip() == s and len(s.strip()) > 0 and not s.endswith(".md"))


@settings(max_examples=200)
@given(
    number=template_numbers,
    type_keyword=type_keywords,
    name=template_names,
    artifact_type=artifact_types,
)
def test_property_5_artifact_filename_derivation(number, type_keyword, name, artifact_type):
    """Property 5: Artifact filename derivation.

    **Validates: Requirements 5.1, 5.3**

    For any valid template filename matching the pattern {number}_{Type}_{Name}.md
    and any artifact type, the Artifact_Namer should produce a filename equal to
    {Name} + the correct extension ('.png' for infographic, '.mp3' for audio,
    '.mp4' for video).
    """
    namer = ArtifactNamer()

    # Build a valid template filename
    template_filename = f"{number:02d}_{type_keyword}_{name}.md"

    # Get the artifact filename
    result = namer.get_artifact_filename(template_filename, artifact_type)

    # The result should be {Name} + correct extension
    expected_ext = EXPECTED_EXTENSIONS[artifact_type]
    expected = name + expected_ext

    assert result == expected, (
        f"Expected '{expected}' but got '{result}' "
        f"for template '{template_filename}' with type '{artifact_type}'"
    )
