"""Unit tests for TemplateDetector.

Tests all 13 active templates parse correctly, steering prompt exclusion (Req 4.9),
content-based fallback detection (Req 4.10), and unparseable filename handling.
"""

import os
import tempfile

import pytest

from app.template_detector import TemplateDetector, TemplateInfo


# The 13 active templates following the {number}_{Type}_{Name}.md pattern
ACTIVE_TEMPLATES = [
    {
        "filename": "02_Infographic_One-page Map of a Complex Topic.md",
        "number": 2,
        "artifact_type": "infographic",
        "name": "One-page Map of a Complex Topic",
        "audio_format": None,
    },
    {
        "filename": "03_Audio_DeepDive Overview.md",
        "number": 3,
        "artifact_type": "audio",
        "name": "DeepDive Overview",
        "audio_format": "DEEP_DIVE",
    },
    {
        "filename": "04_Audio_TheBrief Summary.md",
        "number": 4,
        "artifact_type": "audio",
        "name": "TheBrief Summary",
        "audio_format": "BRIEF",
    },
    {
        "filename": "05_Audio_Critique Analysis.md",
        "number": 5,
        "artifact_type": "audio",
        "name": "Critique Analysis",
        "audio_format": "CRITIQUE",
    },
    {
        "filename": "06_Audio_Debate Discussion.md",
        "number": 6,
        "artifact_type": "audio",
        "name": "Debate Discussion",
        "audio_format": "DEBATE",
    },
    {
        "filename": "07_Video_Explainer.md",
        "number": 7,
        "artifact_type": "video",
        "name": "Explainer",
        "audio_format": None,
    },
    {
        "filename": "08_Infographic_Timeline.md",
        "number": 8,
        "artifact_type": "infographic",
        "name": "Timeline",
        "audio_format": None,
    },
    {
        "filename": "09_Infographic_Comparison Chart.md",
        "number": 9,
        "artifact_type": "infographic",
        "name": "Comparison Chart",
        "audio_format": None,
    },
    {
        "filename": "10_Video_Tutorial Walkthrough.md",
        "number": 10,
        "artifact_type": "video",
        "name": "Tutorial Walkthrough",
        "audio_format": None,
    },
    {
        "filename": "11_Audio_DeepDive Technical.md",
        "number": 11,
        "artifact_type": "audio",
        "name": "DeepDive Technical",
        "audio_format": "DEEP_DIVE",
    },
    {
        "filename": "12_Video_Summary Reel.md",
        "number": 12,
        "artifact_type": "video",
        "name": "Summary Reel",
        "audio_format": None,
    },
    {
        "filename": "13_Infographic_Process Flow.md",
        "number": 13,
        "artifact_type": "infographic",
        "name": "Process Flow",
        "audio_format": None,
    },
    {
        "filename": "14_Audio_TheBrief Quick Take.md",
        "number": 14,
        "artifact_type": "audio",
        "name": "TheBrief Quick Take",
        "audio_format": "BRIEF",
    },
]


@pytest.fixture
def detector():
    return TemplateDetector()


class TestParseFilename:
    """Test parse_filename for all 13 active templates (Req 4.1)."""

    @pytest.mark.parametrize(
        "template",
        ACTIVE_TEMPLATES,
        ids=[t["filename"] for t in ACTIVE_TEMPLATES],
    )
    def test_active_template_parses_correctly(self, detector, template):
        result = detector.parse_filename(template["filename"])

        assert result is not None
        assert result.filename == template["filename"]
        assert result.number == template["number"]
        assert result.artifact_type == template["artifact_type"]
        assert result.name == template["name"]
        assert result.audio_format == template["audio_format"]
        assert result.is_excluded is False

    def test_all_active_templates_are_not_excluded(self, detector):
        for template in ACTIVE_TEMPLATES:
            result = detector.parse_filename(template["filename"])
            assert result is not None
            assert result.is_excluded is False


class TestSteeringPromptExclusion:
    """Test that steering prompt is excluded (Req 4.9)."""

    def test_steering_prompt_is_excluded(self, detector):
        """01_Steering Prompt.md should not match the standard pattern
        but is handled by load_templates as excluded."""
        result = detector.parse_filename("01_Steering Prompt.md")
        # The filename doesn't match {number}_{Type}_{Name}.md pattern
        # because "Steering Prompt" has a space and no third group
        assert result is None

    def test_steering_prompt_in_excluded_files(self, detector):
        assert "01_Steering Prompt.md" in detector.EXCLUDED_FILES

    def test_load_templates_marks_steering_prompt_excluded(self, detector):
        """When loaded from directory, steering prompt should have is_excluded=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create the steering prompt file
            steering_path = os.path.join(tmpdir, "01_Steering Prompt.md")
            with open(steering_path, "w") as f:
                f.write("This is a steering prompt.")

            # Create one active template for comparison
            active_path = os.path.join(tmpdir, "02_Infographic_Test.md")
            with open(active_path, "w") as f:
                f.write("Infographic template content.")

            templates = detector.load_templates(tmpdir)

            steering = [t for t in templates if t.filename == "01_Steering Prompt.md"]
            assert len(steering) == 1
            assert steering[0].is_excluded is True

            active = [t for t in templates if t.filename == "02_Infographic_Test.md"]
            assert len(active) == 1
            assert active[0].is_excluded is False


class TestContentBasedFallback:
    """Test content-based fallback detection (Req 4.10)."""

    def test_detect_infographic_from_content(self, detector):
        content = "Generate an infographic showing the key concepts."
        assert detector.detect_type_from_content(content) == "infographic"

    def test_detect_audio_from_content(self, detector):
        content = "Create an audio discussion about the topic."
        assert detector.detect_type_from_content(content) == "audio"

    def test_detect_video_from_content(self, detector):
        content = "Produce a video explainer for this subject."
        assert detector.detect_type_from_content(content) == "video"

    def test_detect_none_when_no_keywords(self, detector):
        content = "This template has no type keywords at all."
        assert detector.detect_type_from_content(content) is None

    def test_case_insensitive_detection(self, detector):
        content = "This is an INFOGRAPHIC template."
        assert detector.detect_type_from_content(content) == "infographic"

    def test_infographic_takes_priority_over_audio(self, detector):
        """When multiple keywords present, infographic is checked first."""
        content = "This infographic includes audio narration."
        assert detector.detect_type_from_content(content) == "infographic"

    def test_fallback_used_in_load_templates(self, detector):
        """When filename type is unknown, content fallback should classify it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a template with an unknown type in filename
            filepath = os.path.join(tmpdir, "99_Custom_My Template.md")
            with open(filepath, "w") as f:
                f.write("Generate a video summary of the research.")

            templates = detector.load_templates(tmpdir)

            assert len(templates) == 1
            assert templates[0].artifact_type == "video"
            assert templates[0].name == "My Template"


class TestUnparseableFilenames:
    """Test that unparseable filenames return None."""

    @pytest.mark.parametrize(
        "filename",
        [
            "readme.md",
            "template.txt",
            "no_number_Type_Name.md",
            "_Audio_Missing Number.md",
            "02_Audio.md",  # missing name part
            "not_a_template",
            "",
        ],
        ids=[
            "plain_md",
            "wrong_extension",
            "no_leading_number",
            "missing_number",
            "missing_name",
            "no_extension",
            "empty_string",
        ],
    )
    def test_unparseable_returns_none(self, detector, filename):
        assert detector.parse_filename(filename) is None


class TestLoadTemplates:
    """Test load_templates directory loading."""

    def test_empty_directory(self, detector):
        with tempfile.TemporaryDirectory() as tmpdir:
            templates = detector.load_templates(tmpdir)
            assert templates == []

    def test_nonexistent_directory(self, detector):
        templates = detector.load_templates("/nonexistent/path")
        assert templates == []

    def test_skips_non_md_files(self, detector):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a non-md file
            with open(os.path.join(tmpdir, "notes.txt"), "w") as f:
                f.write("not a template")

            templates = detector.load_templates(tmpdir)
            assert templates == []

    def test_loads_content_into_template_info(self, detector):
        with tempfile.TemporaryDirectory() as tmpdir:
            content = "# Audio DeepDive\nGenerate a deep dive."
            filepath = os.path.join(tmpdir, "03_Audio_DeepDive Overview.md")
            with open(filepath, "w") as f:
                f.write(content)

            templates = detector.load_templates(tmpdir)

            assert len(templates) == 1
            assert templates[0].content == content
            assert templates[0].audio_format == "DEEP_DIVE"
