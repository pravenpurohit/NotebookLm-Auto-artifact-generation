"""Property-based tests for artifact filtering.

**Feature: notebooklm-dashboard, Property 22: Artifact filtering**

Property 22: Artifact filtering
**Validates: Requirements 11.2, 11.3, 11.4, 11.5**

For any set of artifacts and any combination of filters (source_location,
source_filename, artifact_type), the filtered result should contain only
artifacts that match all active filter criteria, and should contain every
artifact that matches all active filter criteria (no false exclusions).
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.models import ArtifactFilterModel, ArtifactModel, ArtifactType


# ---------------------------------------------------------------------------
# Pure filter function under test
# ---------------------------------------------------------------------------


def filter_artifacts(
    artifacts: List[ArtifactModel],
    filters: ArtifactFilterModel,
) -> List[ArtifactModel]:
    """Filter artifacts by the active criteria in *filters*.

    An artifact is included only if it matches **all** non-None filter fields:
    - source_location must equal the filter value (Req 11.2)
    - source_filename must equal the filter value (Req 11.3)
    - artifact_type must equal the filter value (Req 11.4)

    When multiple filters are active, only artifacts matching every active
    filter are returned (Req 11.5).
    """
    result: List[ArtifactModel] = []
    for artifact in artifacts:
        if filters.source_location is not None:
            if artifact.source_location != filters.source_location:
                continue
        if filters.source_filename is not None:
            if artifact.source_filename != filters.source_filename:
                continue
        if filters.artifact_type is not None:
            if artifact.artifact_type != filters.artifact_type:
                continue
        result.append(artifact)
    return result


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Reusable text strategy for location / filename fields
_safe_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        blacklist_characters="\n\r\t\x0b\x0c",
    ),
    min_size=1,
    max_size=60,
).filter(lambda s: s.strip() == s and len(s.strip()) > 0)

artifact_type_strategy = st.sampled_from(list(ArtifactType))

# Optional variants (None or a value) for filter fields
optional_location = st.one_of(st.none(), _safe_text)
optional_filename = st.one_of(st.none(), _safe_text)
optional_artifact_type = st.one_of(st.none(), artifact_type_strategy)

# Extension map matching ArtifactType
_EXTENSION_MAP = {
    ArtifactType.INFOGRAPHIC: ".png",
    ArtifactType.AUDIO: ".mp3",
    ArtifactType.VIDEO: ".mp4",
}


def _make_artifact(
    artifact_id: str,
    artifact_type: ArtifactType,
    source_location: Optional[str],
    source_filename: Optional[str],
) -> ArtifactModel:
    """Build an ArtifactModel with sensible defaults."""
    return ArtifactModel(
        id=artifact_id,
        report_id="report-1",
        template_id="template-1",
        artifact_type=artifact_type,
        artifact_name=f"artifact-{artifact_id[:8]}",
        file_path=f"output/{artifact_type.value}/{artifact_id}",
        file_extension=_EXTENSION_MAP[artifact_type],
        source_location=source_location,
        source_filename=source_filename,
        created_at=datetime(2025, 1, 1),
    )


artifact_strategy = st.builds(
    _make_artifact,
    artifact_id=st.uuids().map(str),
    artifact_type=artifact_type_strategy,
    source_location=optional_location,
    source_filename=optional_filename,
)

artifact_list_strategy = st.lists(artifact_strategy, min_size=0, max_size=20)

filter_strategy = st.builds(
    ArtifactFilterModel,
    source_location=optional_location,
    source_filename=optional_filename,
    artifact_type=optional_artifact_type,
)


# ---------------------------------------------------------------------------
# Property 22: Artifact filtering
# ---------------------------------------------------------------------------


def _matches_filter(artifact: ArtifactModel, filters: ArtifactFilterModel) -> bool:
    """Reference predicate: does *artifact* satisfy every active filter?"""
    if filters.source_location is not None:
        if artifact.source_location != filters.source_location:
            return False
    if filters.source_filename is not None:
        if artifact.source_filename != filters.source_filename:
            return False
    if filters.artifact_type is not None:
        if artifact.artifact_type != filters.artifact_type:
            return False
    return True


@settings(max_examples=100)
@given(artifacts=artifact_list_strategy, filters=filter_strategy)
def test_property_22_no_false_inclusions(
    artifacts: List[ArtifactModel],
    filters: ArtifactFilterModel,
):
    """Property 22: Artifact filtering – no false inclusions.

    **Validates: Requirements 11.2, 11.3, 11.4, 11.5**

    Every artifact in the filtered result must match all active filter
    criteria.
    """
    result = filter_artifacts(artifacts, filters)

    for artifact in result:
        if filters.source_location is not None:
            assert artifact.source_location == filters.source_location, (
                f"Artifact {artifact.id} has source_location "
                f"'{artifact.source_location}' but filter requires "
                f"'{filters.source_location}'"
            )
        if filters.source_filename is not None:
            assert artifact.source_filename == filters.source_filename, (
                f"Artifact {artifact.id} has source_filename "
                f"'{artifact.source_filename}' but filter requires "
                f"'{filters.source_filename}'"
            )
        if filters.artifact_type is not None:
            assert artifact.artifact_type == filters.artifact_type, (
                f"Artifact {artifact.id} has type "
                f"'{artifact.artifact_type}' but filter requires "
                f"'{filters.artifact_type}'"
            )


@settings(max_examples=100)
@given(artifacts=artifact_list_strategy, filters=filter_strategy)
def test_property_22_no_false_exclusions(
    artifacts: List[ArtifactModel],
    filters: ArtifactFilterModel,
):
    """Property 22: Artifact filtering – no false exclusions.

    **Validates: Requirements 11.2, 11.3, 11.4, 11.5**

    Every artifact in the original set that matches all active filter
    criteria must appear in the filtered result.
    """
    result = filter_artifacts(artifacts, filters)
    result_ids = {a.id for a in result}

    for artifact in artifacts:
        if _matches_filter(artifact, filters):
            assert artifact.id in result_ids, (
                f"Artifact {artifact.id} matches all filters but was "
                f"excluded from the result"
            )


@settings(max_examples=100)
@given(artifacts=artifact_list_strategy, filters=filter_strategy)
def test_property_22_result_is_subset(
    artifacts: List[ArtifactModel],
    filters: ArtifactFilterModel,
):
    """Property 22: Artifact filtering – result is a subset of input.

    **Validates: Requirements 11.2, 11.3, 11.4, 11.5**

    The filtered result must be a subset of the original artifact list
    (no new artifacts are introduced) and must preserve the original order.
    """
    result = filter_artifacts(artifacts, filters)
    input_ids = [a.id for a in artifacts]
    result_ids = [a.id for a in result]

    # Every result id must come from the input
    for rid in result_ids:
        assert rid in input_ids, (
            f"Artifact {rid} in result but not in input"
        )

    # Order is preserved: result ids appear in the same relative order
    input_positions = {aid: i for i, aid in enumerate(input_ids)}
    for i in range(len(result_ids) - 1):
        assert input_positions[result_ids[i]] < input_positions[result_ids[i + 1]], (
            f"Order not preserved: {result_ids[i]} appears after "
            f"{result_ids[i + 1]} in the result but before in the input"
        )


@settings(max_examples=100)
@given(artifacts=artifact_list_strategy)
def test_property_22_empty_filter_returns_all(
    artifacts: List[ArtifactModel],
):
    """Property 22: Artifact filtering – empty filter returns all artifacts.

    **Validates: Requirements 11.5**

    When no filter criteria are active (all None), every artifact should
    be returned.
    """
    empty_filter = ArtifactFilterModel()
    result = filter_artifacts(artifacts, empty_filter)

    assert len(result) == len(artifacts), (
        f"Empty filter should return all {len(artifacts)} artifacts, "
        f"got {len(result)}"
    )
