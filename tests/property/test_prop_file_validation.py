"""Property-based tests for file format validation.

Property 6: File format validation
**Validates: Requirements 2.5**
"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.validators import validate_file_format


# Accepted file extensions
ACCEPTED_EXTENSIONS = [".pdf", ".md"]

# A broad set of rejected extensions (common file types that are NOT pdf/md)
REJECTED_EXTENSIONS = [
    ".txt", ".csv", ".json", ".xml", ".html", ".docx", ".doc",
    ".xlsx", ".xls", ".pptx", ".png", ".jpg", ".jpeg", ".gif",
    ".mp3", ".mp4", ".wav", ".zip", ".tar", ".gz", ".py", ".js",
    ".ts", ".rb", ".java", ".c", ".cpp", ".h", ".rs", ".go",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".log", ".bak",
    ".exe", ".dll", ".so", ".bin", ".dat", ".sql", ".sh",
]

# Strategy for base filenames: non-empty text without path separators,
# dots, or whitespace-only strings. This ensures the extension we append
# is the only extension in the filename.
safe_basenames = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        blacklist_characters="/\\\n\r\t\x0b\x0c.",
    ),
    min_size=1,
    max_size=100,
).filter(lambda s: len(s.strip()) > 0)

# Strategy for accepted extensions (case variations)
accepted_ext_strategy = st.sampled_from(ACCEPTED_EXTENSIONS).flatmap(
    lambda ext: st.sampled_from([ext, ext.upper(), ext.capitalize()])
)

# Strategy for rejected extensions
rejected_ext_strategy = st.sampled_from(REJECTED_EXTENSIONS)

# Strategy for arbitrary extensions that are NOT .pdf or .md (any case)
# This generates random short strings prefixed with a dot
arbitrary_rejected_ext = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=10,
).filter(
    lambda s: s.lower() not in ("pdf", "md")
).map(lambda s: "." + s)


@settings(max_examples=200)
@given(basename=safe_basenames, ext=accepted_ext_strategy)
def test_property_6_accepted_formats(basename, ext):
    """Property 6: File format validation — accepted files.

    **Validates: Requirements 2.5**

    For any filename with extension '.pdf' or '.md' (case-insensitive),
    the validator should accept the file.
    """
    filename = basename + ext
    assert validate_file_format(filename) is True, (
        f"Expected acceptance for '{filename}' with extension '{ext}'"
    )


@settings(max_examples=200)
@given(basename=safe_basenames, ext=rejected_ext_strategy)
def test_property_6_rejected_known_formats(basename, ext):
    """Property 6: File format validation — rejected known formats.

    **Validates: Requirements 2.5**

    For any filename whose extension is not '.pdf' or '.md',
    the file selection validator should reject the file.
    """
    filename = basename + ext
    assert validate_file_format(filename) is False, (
        f"Expected rejection for '{filename}' with extension '{ext}'"
    )


@settings(max_examples=200)
@given(basename=safe_basenames, ext=arbitrary_rejected_ext)
def test_property_6_rejected_arbitrary_formats(basename, ext):
    """Property 6: File format validation — rejected arbitrary extensions.

    **Validates: Requirements 2.5**

    For any filename with a randomly generated extension that is not
    '.pdf' or '.md', the validator should reject the file.
    """
    filename = basename + ext
    assert validate_file_format(filename) is False, (
        f"Expected rejection for '{filename}' with extension '{ext}'"
    )


@settings(max_examples=100)
@given(basename=safe_basenames)
def test_property_6_no_extension_rejected(basename):
    """Property 6: File format validation — no extension rejected.

    **Validates: Requirements 2.5**

    For any filename without an extension, the validator should reject the file.
    """
    # basename has no dots, so os.path.splitext returns empty extension
    assert validate_file_format(basename) is False, (
        f"Expected rejection for extensionless filename '{basename}'"
    )
