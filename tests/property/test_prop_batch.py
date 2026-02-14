"""Property-based tests for batch operations.

Property 15: Start All transitions all eligible cells
**Validates: Requirements 9.1**

For any grid state, executing 'Start All' should transition every cell with
status 'not_started' or 'pending' to 'in_progress', and should not modify
cells with any other status.

Property 16: Pause/Resume round trip
**Validates: Requirements 9.2, 9.3**

For any task queue state, pausing and then immediately resuming should restore
the queue to a state where new tasks can be dequeued, and no tasks should be
lost during the pause/resume cycle.

Property 17: Stop All transitions all in-progress cells
**Validates: Requirements 9.4**

For any grid state, executing 'Stop All' should transition every cell with
status 'in_progress' to 'stopped', and should not modify cells with any other
status.

Property 18: Retry Failed transitions all failed cells
**Validates: Requirements 9.5**

For any grid state, executing 'Retry Failed' should transition every cell with
status 'failed' to 'in_progress' with new Task_IDs, and should not modify
cells with any other status.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from app.models import CellStatus, GenerationCellModel


# ---------------------------------------------------------------------------
# Hypothesis strategies: random GenerationCellModel objects
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

# Strategy for lists of cells (grid states with 0-20 cells)
grid_state_strategy = st.lists(generation_cell_strategy, min_size=0, max_size=20)


# ---------------------------------------------------------------------------
# Pure helper functions for batch operations
# ---------------------------------------------------------------------------

STARTABLE_STATUSES = {CellStatus.NOT_STARTED, CellStatus.PENDING}


def batch_start_all(cells: list[GenerationCellModel]) -> list[GenerationCellModel]:
    """Transition all cells with status 'not_started' or 'pending' to 'in_progress'.

    Cells with any other status are returned unchanged.
    Each transitioned cell receives a new Task_ID and started_at timestamp.
    """
    result: list[GenerationCellModel] = []
    for cell in cells:
        if cell.status in STARTABLE_STATUSES:
            result.append(cell.model_copy(update={
                "status": CellStatus.IN_PROGRESS,
                "task_id": str(uuid.uuid4()),
                "started_at": datetime.now(tz=timezone.utc),
            }))
        else:
            result.append(cell)
    return result


def batch_stop_all(cells: list[GenerationCellModel]) -> list[GenerationCellModel]:
    """Transition all cells with status 'in_progress' to 'stopped'.

    Cells with any other status are returned unchanged.
    """
    result: list[GenerationCellModel] = []
    for cell in cells:
        if cell.status == CellStatus.IN_PROGRESS:
            result.append(cell.model_copy(update={
                "status": CellStatus.STOPPED,
            }))
        else:
            result.append(cell)
    return result


def batch_retry_failed(cells: list[GenerationCellModel]) -> list[GenerationCellModel]:
    """Transition all cells with status 'failed' to 'in_progress' with new Task_IDs.

    Cells with any other status are returned unchanged.
    Each transitioned cell receives a new Task_ID distinct from its previous one.
    """
    result: list[GenerationCellModel] = []
    for cell in cells:
        if cell.status == CellStatus.FAILED:
            new_task_id = str(uuid.uuid4())
            while new_task_id == cell.task_id:
                new_task_id = str(uuid.uuid4())  # pragma: no cover
            result.append(cell.model_copy(update={
                "status": CellStatus.IN_PROGRESS,
                "task_id": new_task_id,
                "started_at": datetime.now(tz=timezone.utc),
                "error_message": None,
            }))
        else:
            result.append(cell)
    return result


# ---------------------------------------------------------------------------
# Pause/Resume: pure boolean flag model
# ---------------------------------------------------------------------------


class QueuePauseState:
    """Simple model of a task queue's pause/resume state.

    When ``accepting`` is True, new tasks can be dequeued.
    When ``accepting`` is False, the queue is paused.
    """

    def __init__(self, accepting: bool = True, pending_count: int = 0):
        self.accepting = accepting
        self.pending_count = pending_count

    def pause(self) -> "QueuePauseState":
        """Pause the queue – stop accepting new dequeues."""
        return QueuePauseState(accepting=False, pending_count=self.pending_count)

    def resume(self) -> "QueuePauseState":
        """Resume the queue – start accepting new dequeues."""
        return QueuePauseState(accepting=True, pending_count=self.pending_count)


# ---------------------------------------------------------------------------
# Property 15: Start All transitions all eligible cells
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(cells=grid_state_strategy)
def test_property_15_start_all_transitions_eligible_cells(
    cells: list[GenerationCellModel],
):
    """Property 15: Start All transitions all eligible cells.

    **Validates: Requirements 9.1**

    For any grid state, executing 'Start All' should transition every cell
    with status 'not_started' or 'pending' to 'in_progress', and should not
    modify cells with any other status.
    """
    result = batch_start_all(cells)

    # Same number of cells
    assert len(result) == len(cells)

    for original, updated in zip(cells, result):
        if original.status in STARTABLE_STATUSES:
            # Eligible cells must transition to in_progress
            assert updated.status == CellStatus.IN_PROGRESS, (
                f"Cell with status '{original.status.value}' should become "
                f"'in_progress', got '{updated.status.value}'"
            )
            # Must have a new Task_ID assigned
            assert updated.task_id is not None, (
                "Started cell must have a Task_ID"
            )
            uuid.UUID(updated.task_id)  # validate UUID format
            # Must have started_at set
            assert updated.started_at is not None
        else:
            # Non-eligible cells must be unchanged
            assert updated.status == original.status, (
                f"Cell with status '{original.status.value}' should not be "
                f"modified, but got '{updated.status.value}'"
            )
            assert updated.task_id == original.task_id
            assert updated.error_message == original.error_message
            assert updated.artifact_path == original.artifact_path

        # Identity fields always preserved
        assert updated.report_id == original.report_id
        assert updated.template_id == original.template_id


@settings(max_examples=100)
@given(cells=grid_state_strategy)
def test_property_15_start_all_count(cells: list[GenerationCellModel]):
    """Property 15: Start All – count verification.

    **Validates: Requirements 9.1**

    The number of in_progress cells after Start All should equal the original
    in_progress count plus the number of eligible (not_started/pending) cells.
    """
    eligible_count = sum(
        1 for c in cells if c.status in STARTABLE_STATUSES
    )
    original_in_progress = sum(
        1 for c in cells if c.status == CellStatus.IN_PROGRESS
    )

    result = batch_start_all(cells)

    new_in_progress = sum(
        1 for c in result if c.status == CellStatus.IN_PROGRESS
    )
    assert new_in_progress == original_in_progress + eligible_count


# ---------------------------------------------------------------------------
# Property 16: Pause/Resume round trip
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    initial_accepting=st.booleans(),
    pending_count=st.integers(min_value=0, max_value=1000),
)
def test_property_16_pause_resume_round_trip(
    initial_accepting: bool,
    pending_count: int,
):
    """Property 16: Pause/Resume round trip.

    **Validates: Requirements 9.2, 9.3**

    For any task queue state, pausing and then immediately resuming should
    restore the queue to a state where new tasks can be dequeued, and no
    tasks should be lost during the pause/resume cycle.
    """
    state = QueuePauseState(accepting=initial_accepting, pending_count=pending_count)

    # Pause then resume
    paused = state.pause()
    assert not paused.accepting, "Queue must not accept tasks while paused"
    assert paused.pending_count == pending_count, "No tasks lost during pause"

    resumed = paused.resume()
    assert resumed.accepting, "Queue must accept tasks after resume"
    assert resumed.pending_count == pending_count, "No tasks lost during resume"


@settings(max_examples=100)
@given(pending_count=st.integers(min_value=0, max_value=1000))
def test_property_16_pause_resume_idempotent(pending_count: int):
    """Property 16: Pause/Resume – multiple cycles preserve state.

    **Validates: Requirements 9.2, 9.3**

    Pausing and resuming multiple times should never lose tasks.
    """
    state = QueuePauseState(accepting=True, pending_count=pending_count)

    for _ in range(5):
        state = state.pause()
        assert not state.accepting
        assert state.pending_count == pending_count

        state = state.resume()
        assert state.accepting
        assert state.pending_count == pending_count


# ---------------------------------------------------------------------------
# Property 17: Stop All transitions all in-progress cells
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(cells=grid_state_strategy)
def test_property_17_stop_all_transitions_in_progress_cells(
    cells: list[GenerationCellModel],
):
    """Property 17: Stop All transitions all in-progress cells.

    **Validates: Requirements 9.4**

    For any grid state, executing 'Stop All' should transition every cell
    with status 'in_progress' to 'stopped', and should not modify cells
    with any other status.
    """
    result = batch_stop_all(cells)

    # Same number of cells
    assert len(result) == len(cells)

    for original, updated in zip(cells, result):
        if original.status == CellStatus.IN_PROGRESS:
            # In-progress cells must transition to stopped
            assert updated.status == CellStatus.STOPPED, (
                f"In-progress cell should become 'stopped', "
                f"got '{updated.status.value}'"
            )
        else:
            # Non-in-progress cells must be unchanged
            assert updated.status == original.status, (
                f"Cell with status '{original.status.value}' should not be "
                f"modified, but got '{updated.status.value}'"
            )
            assert updated.task_id == original.task_id
            assert updated.error_message == original.error_message
            assert updated.artifact_path == original.artifact_path

        # Identity fields always preserved
        assert updated.report_id == original.report_id
        assert updated.template_id == original.template_id


@settings(max_examples=100)
@given(cells=grid_state_strategy)
def test_property_17_stop_all_no_in_progress_remain(
    cells: list[GenerationCellModel],
):
    """Property 17: Stop All – no in_progress cells remain.

    **Validates: Requirements 9.4**

    After Stop All, there should be zero cells with status 'in_progress'.
    """
    result = batch_stop_all(cells)

    remaining_in_progress = sum(
        1 for c in result if c.status == CellStatus.IN_PROGRESS
    )
    assert remaining_in_progress == 0, (
        f"Expected 0 in_progress cells after Stop All, found {remaining_in_progress}"
    )


# ---------------------------------------------------------------------------
# Property 18: Retry Failed transitions all failed cells
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(cells=grid_state_strategy)
def test_property_18_retry_failed_transitions_failed_cells(
    cells: list[GenerationCellModel],
):
    """Property 18: Retry Failed transitions all failed cells.

    **Validates: Requirements 9.5**

    For any grid state, executing 'Retry Failed' should transition every cell
    with status 'failed' to 'in_progress' with new Task_IDs, and should not
    modify cells with any other status.
    """
    result = batch_retry_failed(cells)

    # Same number of cells
    assert len(result) == len(cells)

    for original, updated in zip(cells, result):
        if original.status == CellStatus.FAILED:
            # Failed cells must transition to in_progress
            assert updated.status == CellStatus.IN_PROGRESS, (
                f"Failed cell should become 'in_progress', "
                f"got '{updated.status.value}'"
            )
            # Must have a new Task_ID
            assert updated.task_id is not None, (
                "Retried cell must have a Task_ID"
            )
            uuid.UUID(updated.task_id)  # validate UUID format
            # New Task_ID must differ from old one
            if original.task_id is not None:
                assert updated.task_id != original.task_id, (
                    f"Retried cell must have a NEW Task_ID, "
                    f"but got same: {original.task_id}"
                )
            # started_at must be set
            assert updated.started_at is not None
            # error_message must be cleared
            assert updated.error_message is None
        else:
            # Non-failed cells must be unchanged
            assert updated.status == original.status, (
                f"Cell with status '{original.status.value}' should not be "
                f"modified, but got '{updated.status.value}'"
            )
            assert updated.task_id == original.task_id
            assert updated.error_message == original.error_message
            assert updated.artifact_path == original.artifact_path

        # Identity fields always preserved
        assert updated.report_id == original.report_id
        assert updated.template_id == original.template_id


@settings(max_examples=100)
@given(cells=grid_state_strategy)
def test_property_18_retry_failed_no_failed_remain(
    cells: list[GenerationCellModel],
):
    """Property 18: Retry Failed – no failed cells remain.

    **Validates: Requirements 9.5**

    After Retry Failed, there should be zero cells with status 'failed'.
    """
    result = batch_retry_failed(cells)

    remaining_failed = sum(
        1 for c in result if c.status == CellStatus.FAILED
    )
    assert remaining_failed == 0, (
        f"Expected 0 failed cells after Retry Failed, found {remaining_failed}"
    )


# ---------------------------------------------------------------------------
# Property 5: Batch generation skips completed cells
# **Validates: Requirements 7.1, 7.6**
# ---------------------------------------------------------------------------


def batch_start_with_dedup(cells: list[GenerationCellModel]) -> dict:
    """Simulate batch start with deduplication: skip completed cells.

    Returns dict with 'enqueued', 'skipped', and 'result' cells.
    """
    enqueued = 0
    skipped = 0
    result: list[GenerationCellModel] = []
    for cell in cells:
        if cell.status == CellStatus.COMPLETED:
            skipped += 1
            result.append(cell)
        elif cell.status in STARTABLE_STATUSES:
            enqueued += 1
            result.append(cell.model_copy(update={
                "status": CellStatus.IN_PROGRESS,
                "task_id": str(uuid.uuid4()),
                "started_at": datetime.now(tz=timezone.utc),
            }))
        else:
            result.append(cell)
    return {"enqueued": enqueued, "skipped": skipped, "result": result}


@given(cells=grid_state_strategy)
@settings(max_examples=100)
def test_property_5_batch_skips_completed(cells: list[GenerationCellModel]):
    """Batch start SHALL only enqueue non-completed cells.

    The count of enqueued cells SHALL equal the count of startable cells,
    and the count of skipped cells SHALL include all completed cells.
    """
    counts = batch_start_with_dedup(cells)

    startable = [c for c in cells if c.status in STARTABLE_STATUSES]
    completed = [c for c in cells if c.status == CellStatus.COMPLETED]

    assert counts["enqueued"] == len(startable)
    assert counts["skipped"] == len(completed)
    assert counts["enqueued"] + counts["skipped"] <= len(cells)

    # All completed cells remain completed in result
    result = counts["result"]
    for i, cell in enumerate(cells):
        if cell.status == CellStatus.COMPLETED:
            assert result[i].status == CellStatus.COMPLETED


@given(cells=grid_state_strategy)
@settings(max_examples=50)
def test_property_5_no_completed_cells_enqueued(cells: list[GenerationCellModel]):
    """No completed cell should be transitioned to in_progress by batch start."""
    counts = batch_start_with_dedup(cells)
    result = counts["result"]

    for i, cell in enumerate(cells):
        if cell.status == CellStatus.COMPLETED:
            assert result[i].status == CellStatus.COMPLETED
            assert result[i].task_id == cell.task_id  # unchanged


# ---------------------------------------------------------------------------
# Property 3: Batch progress summary accuracy
# **Validates: Requirements 5.6**
# ---------------------------------------------------------------------------


def compute_progress_summary(cells: list[GenerationCellModel]) -> dict:
    """Compute batch progress summary from cell statuses."""
    counts = {
        "total": len(cells),
        "completed": 0,
        "in_progress": 0,
        "failed": 0,
        "not_started": 0,
        "stopped": 0,
        "pending": 0,
    }
    for cell in cells:
        key = cell.status.value
        if key in counts:
            counts[key] += 1
    return counts


@given(cells=grid_state_strategy)
@settings(max_examples=100)
def test_property_3_progress_summary_accuracy(cells: list[GenerationCellModel]):
    """Progress summary counts SHALL exactly match actual cell status counts,
    and total SHALL equal the sum of all categories."""
    summary = compute_progress_summary(cells)

    # Total must equal sum of all categories
    category_sum = (
        summary["completed"] + summary["in_progress"] + summary["failed"]
        + summary["not_started"] + summary["stopped"] + summary["pending"]
    )
    assert summary["total"] == category_sum

    # Each count must match actual
    for status in CellStatus:
        actual = sum(1 for c in cells if c.status == status)
        assert summary[status.value] == actual


@given(cells=grid_state_strategy)
@settings(max_examples=50)
def test_property_3_progress_counts_non_negative(cells: list[GenerationCellModel]):
    """All progress summary counts SHALL be non-negative."""
    summary = compute_progress_summary(cells)
    for key, value in summary.items():
        assert value >= 0, f"{key} should be non-negative, got {value}"
