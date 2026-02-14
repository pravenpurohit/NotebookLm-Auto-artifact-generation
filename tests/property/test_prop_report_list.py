"""Property-based tests for report list operations.

Property 7: Report selection grows active list
**Validates: Requirements 2.3**

For any active report list and any set of new report files (not already in the
list), adding them should increase the list length by exactly the number of new
files added, and all new files should appear in the resulting list.

Property 8: Report removal shrinks active list and grid
**Validates: Requirements 2.4**

For any active report list containing at least one report, removing a report
should decrease the list length by one, and the removed report should no longer
appear in the list or in any Status_Grid row.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.models import CellStatus, ReportModel


# ---------------------------------------------------------------------------
# Pure helper functions modelling report list operations
# ---------------------------------------------------------------------------


def add_reports(
    active_reports: List[ReportModel],
    new_reports: List[ReportModel],
) -> List[ReportModel]:
    """Add new reports to the active report list.

    Only reports whose ``id`` is not already present are added.
    Returns the updated list.
    """
    existing_ids = {r.id for r in active_reports}
    result = list(active_reports)
    for r in new_reports:
        if r.id not in existing_ids:
            result.append(r)
            existing_ids.add(r.id)
    return result


def remove_report(
    active_reports: List[ReportModel],
    report_id: str,
) -> List[ReportModel]:
    """Remove a report from the active report list by id.

    Returns the updated list with the report removed.
    """
    return [r for r in active_reports if r.id != report_id]


def build_grid_cells(
    report_ids: List[str],
    template_ids: List[str],
) -> List[dict]:
    """Build a Status_Grid: one cell per (report_id, template_id) pair."""
    cells: List[dict] = []
    for rid in report_ids:
        for tid in template_ids:
            cells.append({
                "report_id": rid,
                "template_id": tid,
                "status": CellStatus.NOT_STARTED,
            })
    return cells


def remove_report_from_grid(
    cells: List[dict],
    report_id: str,
) -> List[dict]:
    """Remove all grid rows associated with a report."""
    return [c for c in cells if c["report_id"] != report_id]


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

def _make_report(report_id: str, filename: str) -> ReportModel:
    """Create a ReportModel with sensible defaults."""
    return ReportModel(
        id=report_id,
        filename=filename,
        filepath=f"data/uploads/{filename}",
        file_size=1024,
        last_modified=None,
        notebook_name=filename.rsplit(".", 1)[0] if "." in filename else filename,
    )


report_strategy = st.builds(
    _make_report,
    report_id=st.uuids().map(str),
    filename=st.from_regex(r"[a-zA-Z0-9_]{1,30}\.(pdf|md)", fullmatch=True),
)

# Lists of reports with unique IDs (active report list)
active_report_list_strategy = st.lists(
    report_strategy,
    min_size=0,
    max_size=10,
    unique_by=lambda r: r.id,
)

# New reports to add (unique IDs, 1-5 items)
new_reports_strategy = st.lists(
    report_strategy,
    min_size=1,
    max_size=5,
    unique_by=lambda r: r.id,
)

# Template IDs for grid construction
template_ids_strategy = st.lists(
    st.uuids().map(str),
    min_size=1,
    max_size=8,
    unique=True,
)


# ---------------------------------------------------------------------------
# Property 7: Report selection grows active list
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    active_reports=active_report_list_strategy,
    new_reports=new_reports_strategy,
)
def test_property_7_report_selection_grows_list(
    active_reports: List[ReportModel],
    new_reports: List[ReportModel],
):
    """Property 7: Report selection grows active list.

    **Validates: Requirements 2.3**

    For any active report list and any set of new report files (not already
    in the list), adding them should increase the list length by exactly the
    number of new files added, and all new files should appear in the
    resulting list.
    """
    existing_ids = {r.id for r in active_reports}

    # Filter to only truly new reports (not already in the list)
    truly_new = [r for r in new_reports if r.id not in existing_ids]
    assume(len(truly_new) > 0)

    original_length = len(active_reports)
    result = add_reports(active_reports, truly_new)

    # Length increases by exactly the number of new reports
    assert len(result) == original_length + len(truly_new), (
        f"Expected list length {original_length + len(truly_new)}, "
        f"got {len(result)}"
    )

    # All new reports appear in the resulting list
    result_ids = {r.id for r in result}
    for r in truly_new:
        assert r.id in result_ids, (
            f"New report {r.id} not found in resulting list"
        )

    # All original reports are still present
    for r in active_reports:
        assert r.id in result_ids, (
            f"Original report {r.id} missing from resulting list"
        )


@settings(max_examples=100)
@given(
    active_reports=active_report_list_strategy,
    new_reports=new_reports_strategy,
)
def test_property_7_adding_duplicates_does_not_grow_list(
    active_reports: List[ReportModel],
    new_reports: List[ReportModel],
):
    """Property 7: Adding duplicate reports does not grow the list.

    **Validates: Requirements 2.3**

    If all new reports already exist in the active list, the list length
    should remain unchanged.
    """
    assume(len(active_reports) > 0)

    # Use reports already in the list as "new" reports (duplicates)
    duplicates = active_reports[:min(len(active_reports), len(new_reports))]
    original_length = len(active_reports)

    result = add_reports(active_reports, duplicates)

    assert len(result) == original_length, (
        f"Adding duplicates should not change list length. "
        f"Expected {original_length}, got {len(result)}"
    )


# ---------------------------------------------------------------------------
# Property 8: Report removal shrinks active list and grid
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    active_reports=st.lists(
        report_strategy,
        min_size=1,
        max_size=10,
        unique_by=lambda r: r.id,
    ),
    template_ids=template_ids_strategy,
    data=st.data(),
)
def test_property_8_report_removal_shrinks_list_and_grid(
    active_reports: List[ReportModel],
    template_ids: List[str],
    data,
):
    """Property 8: Report removal shrinks active list and grid.

    **Validates: Requirements 2.4**

    For any active report list containing at least one report, removing a
    report should decrease the list length by one, and the removed report
    should no longer appear in the list or in any Status_Grid row.
    """
    # Pick a random report to remove
    report_to_remove = data.draw(st.sampled_from(active_reports))
    removed_id = report_to_remove.id

    original_length = len(active_reports)
    report_ids = [r.id for r in active_reports]

    # Build grid before removal
    grid_before = build_grid_cells(report_ids, template_ids)

    # Remove the report
    updated_reports = remove_report(active_reports, removed_id)
    updated_report_ids = [r.id for r in updated_reports]
    grid_after = remove_report_from_grid(grid_before, removed_id)

    # List length decreases by one
    assert len(updated_reports) == original_length - 1, (
        f"Expected list length {original_length - 1}, got {len(updated_reports)}"
    )

    # Removed report no longer in the list
    assert removed_id not in {r.id for r in updated_reports}, (
        f"Removed report {removed_id} still found in the list"
    )

    # Removed report no longer in any grid row
    grid_report_ids = {c["report_id"] for c in grid_after}
    assert removed_id not in grid_report_ids, (
        f"Removed report {removed_id} still found in grid cells"
    )

    # Grid cell count decreased by exactly len(template_ids)
    assert len(grid_after) == len(grid_before) - len(template_ids), (
        f"Expected grid to shrink by {len(template_ids)} cells, "
        f"but went from {len(grid_before)} to {len(grid_after)}"
    )

    # All remaining reports still have their grid rows
    for rid in updated_report_ids:
        rid_cells = [c for c in grid_after if c["report_id"] == rid]
        assert len(rid_cells) == len(template_ids), (
            f"Report {rid} should have {len(template_ids)} grid cells, "
            f"got {len(rid_cells)}"
        )


@settings(max_examples=100)
@given(
    active_reports=st.lists(
        report_strategy,
        min_size=1,
        max_size=10,
        unique_by=lambda r: r.id,
    ),
    data=st.data(),
)
def test_property_8_report_removal_preserves_other_reports(
    active_reports: List[ReportModel],
    data,
):
    """Property 8: Report removal preserves other reports.

    **Validates: Requirements 2.4**

    Removing a report should not affect any other report in the list.
    """
    report_to_remove = data.draw(st.sampled_from(active_reports))
    removed_id = report_to_remove.id

    updated_reports = remove_report(active_reports, removed_id)

    # Every report that was NOT removed should still be present, unchanged
    expected_remaining = [r for r in active_reports if r.id != removed_id]
    assert len(updated_reports) == len(expected_remaining)

    for expected, actual in zip(expected_remaining, updated_reports):
        assert expected.id == actual.id
        assert expected.filename == actual.filename
        assert expected.filepath == actual.filepath
        assert expected.notebook_name == actual.notebook_name
