"""Property tests for deduplication key determinism.

**Validates: Requirements 7.2, 7.4**

Property 4: Deduplication key determinism
*For any* report content and template content, computing the deduplication key
twice SHALL produce the same result. Different content SHALL produce different
keys (with high probability).
"""

from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.state_manager import StateManager


class TestProperty4DedupKeyDeterminism:
    """Property 4: compute_content_hash is deterministic and collision-resistant."""

    @given(content=st.binary(min_size=1, max_size=4096))
    @settings(max_examples=100)
    def test_same_content_same_hash(self, content: bytes):
        """Computing hash twice on the same content produces the same result."""
        h1 = StateManager.compute_content_hash(content)
        h2 = StateManager.compute_content_hash(content)
        assert h1 == h2

    @given(
        content_a=st.binary(min_size=1, max_size=4096),
        content_b=st.binary(min_size=1, max_size=4096),
    )
    @settings(max_examples=100)
    def test_different_content_different_hash(self, content_a: bytes, content_b: bytes):
        """Different content should produce different hashes (with high probability)."""
        assume(content_a != content_b)
        h1 = StateManager.compute_content_hash(content_a)
        h2 = StateManager.compute_content_hash(content_b)
        assert h1 != h2

    @given(content=st.binary(min_size=1, max_size=4096))
    @settings(max_examples=50)
    def test_hash_is_hex_string(self, content: bytes):
        """Hash output should be a valid hex string of expected length (SHA-256 = 64 chars)."""
        h = StateManager.compute_content_hash(content)
        assert isinstance(h, str)
        assert len(h) == 64
        assert all(c in '0123456789abcdef' for c in h)
