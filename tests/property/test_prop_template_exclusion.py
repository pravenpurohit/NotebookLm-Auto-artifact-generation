"""Property test for template exclusion toggle idempotency.

**Validates: Requirements 3.4**

Property 6: Template exclusion toggle is idempotent
*For any* template, toggling `is_excluded` to `true` twice SHALL leave the
template excluded, and toggling to `false` twice SHALL leave it included.
The final state depends only on the last toggle value, not the history.
"""

from __future__ import annotations

import tempfile
import uuid

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.state_manager import StateManager

# Strategy: random sequence of boolean toggles (1-10 toggles)
toggle_sequence_st = st.lists(st.booleans(), min_size=1, max_size=10)

# Strategy: initial exclusion state
initial_excluded_st = st.booleans()


async def _make_sm_with_template(
    db_dir: str, template_id: str, is_excluded: bool
) -> StateManager:
    """Create a StateManager with one seeded template."""
    sm = StateManager(db_path=f"{db_dir}/test.db")
    await sm.init_db()
    await sm.persist_templates([{
        "id": template_id,
        "filename": "02_Infographic_Test.md",
        "number": 2,
        "artifact_type": "infographic",
        "name": "Test",
        "audio_format": None,
        "content": "prompt content",
        "content_edited": False,
        "is_excluded": is_excluded,
    }])
    return sm


class TestProperty6ExclusionIdempotency:
    """Property 6: The final exclusion state depends only on the last toggle."""

    @given(
        initial=initial_excluded_st,
        toggles=toggle_sequence_st,
    )
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_final_state_equals_last_toggle(
        self, initial: bool, toggles: list[bool]
    ):
        with tempfile.TemporaryDirectory() as td:
            tid = str(uuid.uuid4())
            sm = await _make_sm_with_template(td, tid, initial)

            # Apply all toggles in sequence
            for value in toggles:
                result = await sm.update_template_exclusion(tid, value)
                assert result is True

            # Final state should match the last toggle value
            t = await sm.get_template(tid)
            assert t is not None
            assert t["is_excluded"] is toggles[-1]

    @given(value=st.booleans())
    @settings(max_examples=20)
    @pytest.mark.asyncio
    async def test_double_toggle_is_idempotent(self, value: bool):
        """Applying the same value twice should be identical to applying it once."""
        with tempfile.TemporaryDirectory() as td:
            tid = str(uuid.uuid4())
            sm = await _make_sm_with_template(td, tid, not value)

            await sm.update_template_exclusion(tid, value)
            t1 = await sm.get_template(tid)

            await sm.update_template_exclusion(tid, value)
            t2 = await sm.get_template(tid)

            assert t1["is_excluded"] == t2["is_excluded"] == value
