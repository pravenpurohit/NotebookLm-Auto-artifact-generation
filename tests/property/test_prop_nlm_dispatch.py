"""Property test for SDK method dispatch by artifact type.

**Validates: Requirements 1.7, 1.9**

Property 1: SDK method dispatch by artifact type
*For any* valid artifact type (infographic, audio, video), the wrapper's
`submit_generation` method SHALL dispatch to the correct SDK `generate_*`
method, and the `download_artifact` method SHALL dispatch to the correct
`download_*` method.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import tempfile

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from app.nlm_client import (
    NotebookLMClientError,
    NotebookLMClientWrapper,
    SessionCredentials,
    _DOWNLOAD_METHOD_MAP,
    _GENERATE_METHOD_MAP,
)

# Strategy: pick from the valid artifact types
artifact_type_st = st.sampled_from(["infographic", "audio", "video"])
# Strategy: arbitrary non-empty strings for IDs and prompts
notebook_id_st = st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N", "Pd")))
prompt_st = st.text(min_size=1, max_size=200)


def _make_mock_sdk_client() -> MagicMock:
    """Create a mock SDK client with all sub-API generate/download methods."""
    client = MagicMock()
    client.notebooks = MagicMock()
    client.artifacts = MagicMock()
    client.sources = MagicMock()

    # Stub all generate methods
    for method_name in _GENERATE_METHOD_MAP.values():
        result = MagicMock()
        result.task_id = "task-123"
        setattr(client.artifacts, method_name, AsyncMock(return_value=result))

    # Stub all download methods
    for method_name in _DOWNLOAD_METHOD_MAP.values():
        setattr(client.artifacts, method_name, AsyncMock())

    return client


def _make_wrapper(mock_client: MagicMock) -> NotebookLMClientWrapper:
    creds = SessionCredentials(cookies={"sid": "x"}, csrf_token="t", session_id="s")
    w = NotebookLMClientWrapper(creds)
    w._client = mock_client
    return w


class TestProperty1SubmitGenerationDispatch:
    """Property 1 (submit): For any valid artifact type, submit_generation
    dispatches to the correct SDK generate_* method."""

    @given(atype=artifact_type_st, nb_id=notebook_id_st, prompt=prompt_st)
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_dispatches_to_correct_generate_method(
        self, atype: str, nb_id: str, prompt: str
    ):
        mock = _make_mock_sdk_client()
        w = _make_wrapper(mock)

        task_id = await w.submit_generation(nb_id, prompt, atype)

        # The correct generate method should have been called
        expected_method = _GENERATE_METHOD_MAP[atype]
        called_fn = getattr(mock.artifacts, expected_method)
        called_fn.assert_called_once_with(
            notebook_id=nb_id, instructions=prompt
        )

        # No other generate methods should have been called
        for other_type, other_method in _GENERATE_METHOD_MAP.items():
            if other_type != atype:
                other_fn = getattr(mock.artifacts, other_method)
                other_fn.assert_not_called()

        assert task_id == "task-123"


class TestProperty1DownloadArtifactDispatch:
    """Property 1 (download): For any valid artifact type, download_artifact
    dispatches to the correct SDK download_* method."""

    @given(atype=artifact_type_st, nb_id=notebook_id_st)
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_dispatches_to_correct_download_method(
        self, atype: str, nb_id: str
    ):
        mock = _make_mock_sdk_client()
        w = _make_wrapper(mock)

        with tempfile.TemporaryDirectory() as td:
            out_path = f"{td}/artifact.{atype}"
            await w.download_artifact(nb_id, atype, out_path)

            expected_method = _DOWNLOAD_METHOD_MAP[atype]
            called_fn = getattr(mock.artifacts, expected_method)
            called_fn.assert_called_once_with(
                notebook_id=nb_id, output_path=out_path
            )

            for other_type, other_method in _DOWNLOAD_METHOD_MAP.items():
                if other_type != atype:
                    other_fn = getattr(mock.artifacts, other_method)
                    other_fn.assert_not_called()


class TestProperty1InvalidTypeRejection:
    """Property 1 (negative): For any string NOT in the valid set,
    both submit_generation and download_artifact SHALL raise."""

    @given(
        bad_type=st.text(min_size=1, max_size=30).filter(
            lambda s: s not in _GENERATE_METHOD_MAP
        )
    )
    @settings(max_examples=30)
    @pytest.mark.asyncio
    async def test_submit_rejects_invalid_type(self, bad_type: str):
        mock = _make_mock_sdk_client()
        w = _make_wrapper(mock)

        with pytest.raises(NotebookLMClientError, match="Unsupported artifact type"):
            await w.submit_generation("nb-1", "prompt", bad_type)

    @given(
        bad_type=st.text(min_size=1, max_size=30).filter(
            lambda s: s not in _DOWNLOAD_METHOD_MAP
        )
    )
    @settings(max_examples=30)
    @pytest.mark.asyncio
    async def test_download_rejects_invalid_type(self, bad_type: str):
        mock = _make_mock_sdk_client()
        w = _make_wrapper(mock)

        with tempfile.TemporaryDirectory() as td:
            with pytest.raises(NotebookLMClientError, match="Unsupported artifact type"):
                await w.download_artifact("nb-1", bad_type, f"{td}/x")
