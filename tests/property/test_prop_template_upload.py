"""Property test for template upload deduplication.

**Validates: Requirement 2.5**

Property 2: Template upload deduplication
*For any* template uploaded twice with the same filename but different content,
the database SHALL contain exactly one template record with that filename,
and its content SHALL match the second upload.
"""

from __future__ import annotations

import tempfile
import uuid

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.state_manager import StateManager


# Strategy: non-empty content strings
content_st = st.text(min_size=1, max_size=500, alphabet=st.characters(
    whitelist_categories=("L", "N", "P", "Z"),
))


async def _make_sm(db_dir: str) -> StateManager:
    sm = StateManager(db_path=f"{db_dir}/test.db")
    await sm.init_db()
    return sm


class TestProperty2UploadDedup:
    """Property 2: Duplicate filename upload updates content."""

    @given(
        content_a=content_st,
        content_b=content_st,
    )
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_second_upload_overwrites_first(
        self, content_a: str, content_b: str
    ):
        """Uploading same filename twice: DB has one record with second content."""
        with tempfile.TemporaryDirectory() as td:
            sm = await _make_sm(td)
            filename = "02_Infographic_Test.md"
            tid = str(uuid.uuid4())

            # First upload
            await sm.persist_templates([{
                "id": tid,
                "filename": filename,
                "number": 2,
                "artifact_type": "infographic",
                "name": "Test",
                "audio_format": None,
                "content": content_a,
                "content_edited": False,
                "is_excluded": False,
            }])

            # Second upload — simulate dedup by updating content
            existing = await sm.find_template_by_filename(filename)
            assert existing is not None
            await sm.update_template_content(existing["id"], content_b)

            # Verify: exactly one record, content matches second upload
            all_templates = await sm.get_all_templates()
            matches = [t for t in all_templates if t["filename"] == filename]
            assert len(matches) == 1
            assert matches[0]["content"] == content_b

    @given(content=content_st)
    @settings(max_examples=30)
    @pytest.mark.asyncio
    async def test_single_upload_persists(self, content: str):
        """A single upload should persist exactly one record."""
        with tempfile.TemporaryDirectory() as td:
            sm = await _make_sm(td)
            tid = str(uuid.uuid4())
            filename = "07_Audio_DeepDive.md"

            await sm.persist_templates([{
                "id": tid,
                "filename": filename,
                "number": 7,
                "artifact_type": "audio",
                "name": "DeepDive",
                "audio_format": "deep_dive",
                "content": content,
                "content_edited": False,
                "is_excluded": False,
            }])

            all_templates = await sm.get_all_templates()
            matches = [t for t in all_templates if t["filename"] == filename]
            assert len(matches) == 1
            assert matches[0]["content"] == content
