"""Property-based tests for TemplateDetector.

Property 2: Template type classification from filename
**Validates: Requirements 4.2, 4.3, 4.4**

Property 3: Audio format detection from filename
**Validates: Requirements 4.5, 4.6, 4.7, 4.8**

Property 4: Template filename parsing round trip
**Validates: Requirements 4.1**
"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.template_detector import TemplateDetector


# Reverse map: artifact_type -> filename type keyword
REVERSE_TYPE_MAP = {v: k for k, v in TemplateDetector.TYPE_MAP.items()}

# Strategy for valid type keywords from TYPE_MAP keys
type_keywords = st.sampled_from(list(TemplateDetector.TYPE_MAP.keys()))

# Strategy for valid positive integers (template numbers)
valid_numbers = st.integers(min_value=1, max_value=9999)

# Strategy for valid template names:
# - Non-empty
# - No underscores at the start (would break the regex split)
# - No newlines
# - Printable characters only
valid_names = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        blacklist_characters="_\n\r\t\x0b\x0c",
    ),
    min_size=1,
    max_size=80,
).filter(lambda s: s.strip() == s and len(s.strip()) > 0)


@settings(max_examples=200)
@given(number=valid_numbers, type_keyword=type_keywords, name=valid_names)
def test_property_4_template_filename_parsing_round_trip(number, type_keyword, name):
    """Property 4: Template filename parsing round trip.

    **Validates: Requirements 4.1**

    For any valid TemplateInfo (number, type, name), formatting as
    {number}_{Type}_{Name}.md and parsing back should yield equivalent values.
    """
    # The name must not contain ".md" at the end (would confuse extension stripping)
    assume(not name.endswith(".md"))
    # Name must not be empty after filtering
    assume(len(name) > 0)

    # Format into the canonical filename pattern
    filename = f"{number:02d}_{type_keyword}_{name}.md"

    # Parse it back
    detector = TemplateDetector()
    result = detector.parse_filename(filename)

    # The parse should succeed
    assert result is not None, f"Failed to parse generated filename: {filename}"

    # Round-trip: values should match
    assert result.number == number
    expected_artifact_type = TemplateDetector.TYPE_MAP[type_keyword]
    assert result.artifact_type == expected_artifact_type
    assert result.name == name
    assert result.filename == filename


@settings(max_examples=200)
@given(number=valid_numbers, type_keyword=type_keywords, name=valid_names)
def test_property_2_template_type_classification_from_filename(number, type_keyword, name):
    """Property 2: Template type classification from filename.

    **Validates: Requirements 4.2, 4.3, 4.4**

    For any template filename containing one of the type keywords
    ('Infographic', 'Audio', 'Video'), the Template_Detector should classify
    it as the corresponding artifact type ('infographic', 'audio', 'video')
    according to the TYPE_MAP.
    """
    assume(not name.endswith(".md"))
    assume(len(name) > 0)

    # Build a filename with the chosen type keyword
    filename = f"{number:02d}_{type_keyword}_{name}.md"

    detector = TemplateDetector()
    result = detector.parse_filename(filename)

    assert result is not None, f"Failed to parse filename: {filename}"

    # The classified artifact_type must match TYPE_MAP for the keyword
    expected_type = TemplateDetector.TYPE_MAP[type_keyword]
    assert result.artifact_type == expected_type, (
        f"Expected artifact_type '{expected_type}' for keyword '{type_keyword}', "
        f"got '{result.artifact_type}' (filename: {filename})"
    )


# Strategy for audio format keywords from AUDIO_FORMAT_MAP keys
audio_format_keywords = st.sampled_from(list(TemplateDetector.AUDIO_FORMAT_MAP.keys()))

# Strategy for name suffixes that don't accidentally contain another audio format keyword
# to keep the test deterministic about which keyword is matched
safe_name_suffixes = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        blacklist_characters="_\n\r\t\x0b\x0c",
    ),
    min_size=0,
    max_size=40,
).filter(
    lambda s: not any(
        kw in s for kw in TemplateDetector.AUDIO_FORMAT_MAP.keys()
    )
)


@settings(max_examples=200)
@given(
    number=valid_numbers,
    audio_keyword=audio_format_keywords,
    prefix=safe_name_suffixes,
    suffix=safe_name_suffixes,
)
def test_property_3_audio_format_detection_from_filename(
    number, audio_keyword, prefix, suffix
):
    """Property 3: Audio format detection from filename.

    **Validates: Requirements 4.5, 4.6, 4.7, 4.8**

    For any audio template filename containing one of the audio format keywords
    ('DeepDive', 'TheBrief', 'Critique', 'Debate'), the Template_Detector should
    set the audio_format to the corresponding value ('DEEP_DIVE', 'BRIEF',
    'CRITIQUE', 'DEBATE') according to the AUDIO_FORMAT_MAP.
    """
    # Build a name that contains exactly the chosen audio keyword
    name = f"{prefix}{audio_keyword}{suffix}"
    assume(len(name.strip()) > 0)
    assume(not name.endswith(".md"))

    # Audio templates use "Audio" as the type keyword
    filename = f"{number:02d}_Audio_{name}.md"

    detector = TemplateDetector()
    result = detector.parse_filename(filename)

    assert result is not None, f"Failed to parse filename: {filename}"

    # The artifact type should be audio
    assert result.artifact_type == "audio", (
        f"Expected artifact_type 'audio', got '{result.artifact_type}'"
    )

    # The audio_format must match the AUDIO_FORMAT_MAP for the keyword
    expected_format = TemplateDetector.AUDIO_FORMAT_MAP[audio_keyword]
    assert result.audio_format == expected_format, (
        f"Expected audio_format '{expected_format}' for keyword '{audio_keyword}', "
        f"got '{result.audio_format}' (filename: {filename})"
    )
