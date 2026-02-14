"""Unit tests for ArtifactNamer.

Tests artifact name derivation from template filenames (Req 5.2),
notebook name derivation from report filenames (Req 3.1),
artifact filename generation, and error cases.
"""

import pytest

from app.artifact_namer import ArtifactNamer


@pytest.fixture
def namer():
    return ArtifactNamer()


class TestDeriveArtifactName:
    """Test derive_artifact_name extracts the {Name} portion (Req 5.1, 5.2)."""

    def test_specific_example_from_requirements(self, namer):
        """Req 5.2: '02_Infographic_One-page Map of a Complex Topic.md'
        → 'One-page Map of a Complex Topic'."""
        result = namer.derive_artifact_name(
            "02_Infographic_One-page Map of a Complex Topic.md"
        )
        assert result == "One-page Map of a Complex Topic"

    def test_audio_template(self, namer):
        result = namer.derive_artifact_name("03_Audio_DeepDive Overview.md")
        assert result == "DeepDive Overview"

    def test_video_template(self, namer):
        result = namer.derive_artifact_name("07_Video_Explainer.md")
        assert result == "Explainer"

    def test_multi_word_name(self, namer):
        result = namer.derive_artifact_name("10_Video_Tutorial Walkthrough.md")
        assert result == "Tutorial Walkthrough"

    def test_name_with_hyphen(self, namer):
        result = namer.derive_artifact_name("15_Infographic_Step-by-Step Guide.md")
        assert result == "Step-by-Step Guide"

    def test_invalid_filename_raises(self, namer):
        with pytest.raises(ValueError, match="does not match pattern"):
            namer.derive_artifact_name("readme.md")

    def test_missing_name_part_raises(self, namer):
        with pytest.raises(ValueError, match="does not match pattern"):
            namer.derive_artifact_name("02_Audio.md")

    def test_empty_string_raises(self, namer):
        with pytest.raises(ValueError, match="does not match pattern"):
            namer.derive_artifact_name("")

    def test_no_extension_raises(self, namer):
        with pytest.raises(ValueError, match="does not match pattern"):
            namer.derive_artifact_name("02_Infographic_Name")


class TestDeriveNotebookName:
    """Test derive_notebook_name strips extension (Req 3.1, 3.3)."""

    def test_pdf_extension(self, namer):
        assert namer.derive_notebook_name("My Report.pdf") == "My Report"

    def test_md_extension(self, namer):
        assert namer.derive_notebook_name("Research.md") == "Research"

    def test_multi_dot_filename(self, namer):
        assert namer.derive_notebook_name("v2.1.Report.pdf") == "v2.1.Report"

    def test_no_extension(self, namer):
        assert namer.derive_notebook_name("JustAName") == "JustAName"


class TestGetArtifactFilename:
    """Test get_artifact_filename combines name + correct extension (Req 5.3)."""

    def test_infographic_png(self, namer):
        result = namer.get_artifact_filename(
            "02_Infographic_One-page Map of a Complex Topic.md", "infographic"
        )
        assert result == "One-page Map of a Complex Topic.png"

    def test_audio_mp3(self, namer):
        result = namer.get_artifact_filename("03_Audio_DeepDive Overview.md", "audio")
        assert result == "DeepDive Overview.mp3"

    def test_video_mp4(self, namer):
        result = namer.get_artifact_filename("07_Video_Explainer.md", "video")
        assert result == "Explainer.mp4"

    def test_unknown_artifact_type_raises(self, namer):
        with pytest.raises(ValueError, match="Unknown artifact type"):
            namer.get_artifact_filename("02_Infographic_Test.md", "document")

    def test_invalid_template_filename_raises(self, namer):
        with pytest.raises(ValueError, match="does not match pattern"):
            namer.get_artifact_filename("bad_filename.md", "audio")
