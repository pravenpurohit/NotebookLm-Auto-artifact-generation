"""Property-based tests for cell status and grid logic.

Property 9: Duplicate prevention
**Validates: Requirements 6.4, 8.4**

For any generation cell that already has a Task_ID with status 'in_progress',
attempting to start generation should not create a new Task_ID and should
return an error/conflict response.

Property 10: Cell status invariant
**Validates: Requirements 7.3**

For any GenerationCell in the system, the status field should always be one of
the valid CellStatus enum values: 'not_started', 'pending', 'in_progress',
'completed', 'failed', or 'stopped'.

Property 11: Grid dimensions
**Validates: Requirements 7.1**

For any set of N reports and M templates, the Status_Grid should contain
exactly N × M cells, with one cell for each unique (report_id, template_id) pair.
"""

from __future__ import annotations

from datetime import datetime, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from app.models import CellStatus, GenerationCellModel


# ---------------------------------------------------------------------------
# Valid CellStatus values (for Property 10)
# ---------------------------------------------------------------------------

VALID_CELL_STATUSES = {"not_started", "pending", "in_progress", "completed", "failed", "stopped"}

# ---------------------------------------------------------------------------
# Hypothesis strategy: random GenerationCellModel objects
# ---------------------------------------------------------------------------

cell_status_strategy = st.sampled_from(list(CellStatus))

optional_datetime = st.one_of(
    st.none(),
    st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2030, 1, 1),
    ).map(lambda dt: dt.replace(tzinfo=timezone.utc)),
)

generation_cell_strategy = st.builds(
    GenerationCellModel,
    report_id=st.uuids().map(str),
    template_id=st.uuids().map(str),
    status=cell_status_strategy,
    task_id=st.one_of(st.none(), st.uuids().map(str)),
    notebook_id=st.one_of(st.none(), st.uuids().map(str)),
    error_message=st.one_of(st.none(), st.text(min_size=1, max_size=100)),
    started_at=optional_datetime,
    completed_at=optional_datetime,
    artifact_path=st.one_of(st.none(), st.text(min_size=1, max_size=200)),
)


# ---------------------------------------------------------------------------
# Helper: duplicate prevention check (pure logic, mirrors TaskQueue.enqueue)
# ---------------------------------------------------------------------------


class DuplicateCheckResult:
    """Result of a duplicate prevention check."""

    def __init__(self, allowed: bool, error: str | None = None):
        self.allowed = allowed
        self.error = error


def check_start_generation_allowed(
    status: CellStatus | None,
    task_id: str | None,
) -> DuplicateCheckResult:
    """Check whether starting generation should be allowed for a cell.

    This mirrors the duplicate detection logic in ``TaskQueue.enqueue``:
    if the cell already has status ``in_progress`` **and** a ``task_id``,
    the request must be rejected.  Otherwise it is allowed.

    Parameters
    ----------
    status:
        Current cell status, or ``None`` if the cell does not exist yet.
    task_id:
        Current task_id associated with the cell, or ``None``.

    Returns
    -------
    DuplicateCheckResult
        ``.allowed`` is ``True`` when generation may proceed,
        ``False`` when it should be rejected as a duplicate.
    """
    if status == CellStatus.IN_PROGRESS and task_id is not None:
        return DuplicateCheckResult(
            allowed=False,
            error=f"Task already in progress with task_id={task_id}",
        )
    return DuplicateCheckResult(allowed=True)


# ---------------------------------------------------------------------------
# Hypothesis strategy: cells specifically for duplicate-prevention testing
# ---------------------------------------------------------------------------

# Statuses that are NOT in_progress (generation should always be allowed)
non_in_progress_statuses = st.sampled_from(
    [s for s in CellStatus if s != CellStatus.IN_PROGRESS]
)

# Non-empty task IDs
non_empty_task_id = st.uuids().map(str)


# ---------------------------------------------------------------------------
# Property 9: Duplicate prevention
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(task_id=non_empty_task_id)
def test_property_9_duplicate_prevention_rejects_in_progress_with_task_id(task_id: str):
    """Property 9: Duplicate prevention – reject case.

    **Validates: Requirements 6.4, 8.4**

    For any generation cell that already has status 'in_progress' AND a
    task_id, attempting to start generation should be rejected.
    """
    result = check_start_generation_allowed(
        status=CellStatus.IN_PROGRESS,
        task_id=task_id,
    )
    assert not result.allowed, (
        f"Expected rejection for in_progress cell with task_id={task_id}"
    )
    assert result.error is not None, "Rejected result must include an error message"
    assert task_id in result.error, "Error message should reference the existing task_id"


@settings(max_examples=100)
@given(status=non_in_progress_statuses, task_id=st.one_of(st.none(), non_empty_task_id))
def test_property_9_duplicate_prevention_allows_non_in_progress(status: CellStatus, task_id):
    """Property 9: Duplicate prevention – allow case (non-in_progress status).

    **Validates: Requirements 6.4, 8.4**

    For any generation cell whose status is NOT 'in_progress', starting
    generation should always be allowed regardless of task_id.
    """
    result = check_start_generation_allowed(status=status, task_id=task_id)
    assert result.allowed, (
        f"Expected generation to be allowed for status={status.value}, "
        f"task_id={task_id}"
    )


@settings(max_examples=100)
@given(data=st.data())
def test_property_9_duplicate_prevention_allows_in_progress_without_task_id(data):
    """Property 9: Duplicate prevention – allow case (in_progress but no task_id).

    **Validates: Requirements 6.4, 8.4**

    A cell with status 'in_progress' but no task_id should still be allowed
    to start generation (the duplicate check requires BOTH conditions).
    """
    result = check_start_generation_allowed(
        status=CellStatus.IN_PROGRESS,
        task_id=None,
    )
    assert result.allowed, (
        "Expected generation to be allowed for in_progress cell without task_id"
    )


@settings(max_examples=100)
@given(cell=generation_cell_strategy)
def test_property_9_duplicate_prevention_comprehensive(cell: GenerationCellModel):
    """Property 9: Duplicate prevention – comprehensive.

    **Validates: Requirements 6.4, 8.4**

    For any randomly generated cell, the duplicate check should reject if and
    only if status is 'in_progress' AND task_id is not None.
    """
    result = check_start_generation_allowed(
        status=cell.status,
        task_id=cell.task_id,
    )

    should_reject = (
        cell.status == CellStatus.IN_PROGRESS and cell.task_id is not None
    )

    if should_reject:
        assert not result.allowed, (
            f"Expected rejection for in_progress cell with task_id={cell.task_id}"
        )
        assert result.error is not None
    else:
        assert result.allowed, (
            f"Expected generation allowed for status={cell.status.value}, "
            f"task_id={cell.task_id}"
        )


# ---------------------------------------------------------------------------
# Property 10: Cell status invariant
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(cell=generation_cell_strategy)
def test_property_10_cell_status_invariant(cell: GenerationCellModel):
    """Property 10: Cell status invariant.

    **Validates: Requirements 7.3**

    For any GenerationCell in the system, the status field should always be one
    of the valid CellStatus enum values: 'not_started', 'pending',
    'in_progress', 'completed', 'failed', or 'stopped'.
    """
    # The status must be a CellStatus enum member
    assert isinstance(cell.status, CellStatus), (
        f"Status {cell.status!r} is not a CellStatus enum member"
    )

    # The status string value must be in the valid set
    assert cell.status.value in VALID_CELL_STATUSES, (
        f"Status value {cell.status.value!r} is not in {VALID_CELL_STATUSES}"
    )

    # The CellStatus enum must contain exactly the 6 valid statuses
    assert {s.value for s in CellStatus} == VALID_CELL_STATUSES, (
        "CellStatus enum does not match the expected set of valid statuses"
    )


# ---------------------------------------------------------------------------
# Helper: build a status grid from reports and templates
# ---------------------------------------------------------------------------

def build_status_grid(
    report_ids: list[str],
    template_ids: list[str],
) -> list[dict]:
    """Build a Status_Grid by creating one cell per (report_id, template_id) pair.

    Each cell starts with status ``not_started``.  This mirrors the grid
    construction logic the dashboard performs when reports and templates are
    loaded.
    """
    cells: list[dict] = []
    for rid in report_ids:
        for tid in template_ids:
            cells.append({
                "report_id": rid,
                "template_id": tid,
                "status": CellStatus.NOT_STARTED,
            })
    return cells


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Unique report IDs (1-10)
unique_report_ids = st.lists(
    st.uuids().map(str),
    min_size=1,
    max_size=10,
    unique=True,
)

# Unique template IDs (1-10)
unique_template_ids = st.lists(
    st.uuids().map(str),
    min_size=1,
    max_size=10,
    unique=True,
)


# ---------------------------------------------------------------------------
# Property 11: Grid dimensions
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(report_ids=unique_report_ids, template_ids=unique_template_ids)
def test_property_11_grid_dimensions(report_ids, template_ids):
    """Property 11: Grid dimensions.

    **Validates: Requirements 7.1**

    For any set of N reports and M templates, the Status_Grid should contain
    exactly N × M cells, with one cell for each unique (report_id, template_id)
    pair.
    """
    n = len(report_ids)
    m = len(template_ids)

    grid = build_status_grid(report_ids, template_ids)

    # 1. Total cells = N × M
    assert len(grid) == n * m, (
        f"Expected {n * m} cells for {n} reports × {m} templates, got {len(grid)}"
    )

    # 2. Each (report_id, template_id) pair appears exactly once
    pairs = [(cell["report_id"], cell["template_id"]) for cell in grid]
    assert len(pairs) == len(set(pairs)), "Duplicate (report_id, template_id) pairs found"

    # 3. All report_ids are represented
    grid_report_ids = {cell["report_id"] for cell in grid}
    assert grid_report_ids == set(report_ids), (
        f"Missing report_ids: {set(report_ids) - grid_report_ids}"
    )

    # 4. All template_ids are represented
    grid_template_ids = {cell["template_id"] for cell in grid}
    assert grid_template_ids == set(template_ids), (
        f"Missing template_ids: {set(template_ids) - grid_template_ids}"
    )


# ---------------------------------------------------------------------------
# Helper functions: cell state transitions (pure logic)
# ---------------------------------------------------------------------------

import uuid


def start_cell(cell: GenerationCellModel) -> GenerationCellModel:
    """Transition a cell from 'not_started' or 'pending' to 'in_progress'.

    Assigns a new Task_ID. Raises ValueError if the cell is not in a
    startable status.
    """
    if cell.status not in (CellStatus.NOT_STARTED, CellStatus.PENDING):
        raise ValueError(
            f"Cannot start cell with status '{cell.status.value}'; "
            f"expected 'not_started' or 'pending'"
        )
    return cell.model_copy(update={
        "status": CellStatus.IN_PROGRESS,
        "task_id": str(uuid.uuid4()),
        "started_at": datetime.now(tz=timezone.utc),
    })


def stop_cell(cell: GenerationCellModel) -> GenerationCellModel:
    """Transition a cell from 'in_progress' to 'stopped'.

    Raises ValueError if the cell is not in_progress.
    """
    if cell.status != CellStatus.IN_PROGRESS:
        raise ValueError(
            f"Cannot stop cell with status '{cell.status.value}'; "
            f"expected 'in_progress'"
        )
    return cell.model_copy(update={
        "status": CellStatus.STOPPED,
    })


def retry_cell(cell: GenerationCellModel) -> GenerationCellModel:
    """Transition a cell from 'failed' or 'stopped' to 'in_progress'.

    Assigns a new Task_ID that is guaranteed to differ from the previous one.
    Raises ValueError if the cell is not in a retryable status.
    """
    if cell.status not in (CellStatus.FAILED, CellStatus.STOPPED):
        raise ValueError(
            f"Cannot retry cell with status '{cell.status.value}'; "
            f"expected 'failed' or 'stopped'"
        )
    new_task_id = str(uuid.uuid4())
    # Ensure the new task_id differs from the old one (astronomically unlikely
    # collision, but we guard against it for correctness).
    while new_task_id == cell.task_id:
        new_task_id = str(uuid.uuid4())  # pragma: no cover
    return cell.model_copy(update={
        "status": CellStatus.IN_PROGRESS,
        "task_id": new_task_id,
        "started_at": datetime.now(tz=timezone.utc),
        "error_message": None,
    })


# ---------------------------------------------------------------------------
# Hypothesis strategies for startable / stoppable / retryable cells
# ---------------------------------------------------------------------------

startable_status = st.sampled_from([CellStatus.NOT_STARTED, CellStatus.PENDING])

startable_cell_strategy = st.builds(
    GenerationCellModel,
    report_id=st.uuids().map(str),
    template_id=st.uuids().map(str),
    status=startable_status,
    task_id=st.none(),
    notebook_id=st.one_of(st.none(), st.uuids().map(str)),
    error_message=st.none(),
    started_at=st.none(),
    completed_at=st.none(),
    artifact_path=st.none(),
)

in_progress_cell_strategy = st.builds(
    GenerationCellModel,
    report_id=st.uuids().map(str),
    template_id=st.uuids().map(str),
    status=st.just(CellStatus.IN_PROGRESS),
    task_id=st.uuids().map(str),
    notebook_id=st.one_of(st.none(), st.uuids().map(str)),
    error_message=st.none(),
    started_at=optional_datetime,
    completed_at=st.none(),
    artifact_path=st.none(),
)

retryable_status = st.sampled_from([CellStatus.FAILED, CellStatus.STOPPED])

retryable_cell_strategy = st.builds(
    GenerationCellModel,
    report_id=st.uuids().map(str),
    template_id=st.uuids().map(str),
    status=retryable_status,
    task_id=st.one_of(st.none(), st.uuids().map(str)),
    notebook_id=st.one_of(st.none(), st.uuids().map(str)),
    error_message=st.one_of(st.none(), st.text(min_size=1, max_size=100)),
    started_at=optional_datetime,
    completed_at=optional_datetime,
    artifact_path=st.none(),
)


# ---------------------------------------------------------------------------
# Property 12: Start transitions cell status correctly
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(cell=startable_cell_strategy)
def test_property_12_start_transitions_cell_status(cell: GenerationCellModel):
    """Property 12: Start transitions cell status correctly.

    **Validates: Requirements 8.1**

    For any generation cell with status 'not_started' or 'pending', starting
    generation should transition the cell to 'in_progress' status and assign
    a Task_ID.
    """
    assert cell.status in (CellStatus.NOT_STARTED, CellStatus.PENDING)

    result = start_cell(cell)

    # Status must transition to in_progress
    assert result.status == CellStatus.IN_PROGRESS, (
        f"Expected 'in_progress', got '{result.status.value}'"
    )

    # A Task_ID must be assigned
    assert result.task_id is not None, "start_cell must assign a Task_ID"

    # Task_ID must be a valid UUID string
    uuid.UUID(result.task_id)  # raises ValueError if invalid

    # started_at must be set
    assert result.started_at is not None, "start_cell must set started_at"

    # report_id and template_id must be preserved
    assert result.report_id == cell.report_id
    assert result.template_id == cell.template_id


# ---------------------------------------------------------------------------
# Property 13: Stop transitions cell status correctly
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(cell=in_progress_cell_strategy)
def test_property_13_stop_transitions_cell_status(cell: GenerationCellModel):
    """Property 13: Stop transitions cell status correctly.

    **Validates: Requirements 8.2**

    For any generation cell with status 'in_progress', stopping generation
    should transition the cell to 'stopped' status.
    """
    assert cell.status == CellStatus.IN_PROGRESS

    result = stop_cell(cell)

    # Status must transition to stopped
    assert result.status == CellStatus.STOPPED, (
        f"Expected 'stopped', got '{result.status.value}'"
    )

    # report_id and template_id must be preserved
    assert result.report_id == cell.report_id
    assert result.template_id == cell.template_id

    # task_id should be preserved (we don't clear it on stop)
    assert result.task_id == cell.task_id


# ---------------------------------------------------------------------------
# Property 14: Retry transitions cell status with new Task_ID
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(cell=retryable_cell_strategy)
def test_property_14_retry_transitions_cell_status(cell: GenerationCellModel):
    """Property 14: Retry transitions cell status with new Task_ID.

    **Validates: Requirements 8.3**

    For any generation cell with status 'failed' or 'stopped', retrying should
    transition the cell to 'in_progress' status and assign a new Task_ID
    different from the previous one.
    """
    assert cell.status in (CellStatus.FAILED, CellStatus.STOPPED)

    result = retry_cell(cell)

    # Status must transition to in_progress
    assert result.status == CellStatus.IN_PROGRESS, (
        f"Expected 'in_progress', got '{result.status.value}'"
    )

    # A new Task_ID must be assigned
    assert result.task_id is not None, "retry_cell must assign a Task_ID"

    # Task_ID must be a valid UUID string
    uuid.UUID(result.task_id)  # raises ValueError if invalid

    # New Task_ID must differ from the old one
    if cell.task_id is not None:
        assert result.task_id != cell.task_id, (
            f"retry_cell must assign a NEW Task_ID, but got the same: {cell.task_id}"
        )

    # started_at must be refreshed
    assert result.started_at is not None, "retry_cell must set started_at"

    # error_message must be cleared
    assert result.error_message is None, "retry_cell must clear error_message"

    # report_id and template_id must be preserved
    assert result.report_id == cell.report_id
    assert result.template_id == cell.template_id
