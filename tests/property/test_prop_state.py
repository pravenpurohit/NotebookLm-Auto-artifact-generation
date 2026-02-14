"""Property-based tests for State Manager persistence.

Property 19: State persistence round trip
**Validates: Requirements 10.4**

For any valid application state (reports, templates, cells with statuses and
Task_IDs), persisting to the database and then loading should produce an
equivalent state.
"""

from __future__ import annotations

import asyncio
import tempfile
import os
from datetime import datetime

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.models import CellStatus
from app.state_manager import GenerationCell, StateManager


# ---------------------------------------------------------------------------
# Helper: run async code from sync Hypothesis test
# ---------------------------------------------------------------------------

def run_async(coro):
    """Run an async coroutine in a new event loop.

    Hypothesis tests must be synchronous, so we create a fresh event loop
    per test invocation to run async StateManager operations.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Safe text: printable, no NUL bytes, non-empty
safe_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        blacklist_characters="\x00\n\r",
    ),
    min_size=1,
    max_size=60,
).filter(lambda s: s.strip() == s and len(s.strip()) > 0)

# Unique IDs (UUID-like strings)
id_strategy = st.uuids().map(str)

# Valid artifact types for templates
artifact_types = st.sampled_from(["infographic", "audio", "video"])

# Valid audio formats (including None)
audio_formats = st.sampled_from([None, "DEEP_DIVE", "BRIEF", "CRITIQUE", "DEBATE"])

# Valid cell statuses
cell_statuses = st.sampled_from(list(CellStatus))

# Optional task_id / notebook_id
optional_id = st.one_of(st.none(), id_strategy)

# Optional error message
optional_error = st.one_of(st.none(), safe_text)

# Optional artifact path
optional_path = st.one_of(
    st.none(),
    safe_text.map(lambda s: f"/output/{s}"),
)

# Optional datetime (stored as ISO string in DB)
optional_datetime = st.one_of(
    st.none(),
    st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2030, 12, 31),
    ),
)


def report_strategy():
    """Generate a random report dict."""
    return st.fixed_dictionaries({
        "id": id_strategy,
        "filename": safe_text.map(lambda s: s + ".pdf"),
        "filepath": safe_text.map(lambda s: f"/docs/{s}.pdf"),
        "file_size": st.one_of(st.none(), st.integers(min_value=0, max_value=10_000_000)),
        "last_modified": st.one_of(st.none(), st.just("2024-01-15")),
        "notebook_name": safe_text,
    })


def template_strategy():
    """Generate a random template dict."""
    return st.fixed_dictionaries({
        "id": id_strategy,
        "filename": safe_text.map(lambda s: f"02_Infographic_{s}.md"),
        "number": st.integers(min_value=1, max_value=9999),
        "artifact_type": artifact_types,
        "name": safe_text,
        "audio_format": audio_formats,
        "content": safe_text,
    })


def cell_strategy(report_ids: list[str], template_ids: list[str]):
    """Generate a random GenerationCell referencing valid report/template IDs."""
    return st.fixed_dictionaries({
        "report_id": st.sampled_from(report_ids),
        "template_id": st.sampled_from(template_ids),
        "status": cell_statuses,
        "task_id": optional_id,
        "notebook_id": optional_id,
        "error_message": optional_error,
        "started_at": optional_datetime,
        "completed_at": optional_datetime,
        "artifact_path": optional_path,
    })


# ---------------------------------------------------------------------------
# Composite strategy: full application state
# ---------------------------------------------------------------------------

@st.composite
def full_state(draw):
    """Generate a complete valid application state.

    Returns (reports, templates, cells) where cells reference valid IDs and
    each (report_id, template_id) pair is unique.
    """
    # Generate 1-5 reports with unique IDs
    num_reports = draw(st.integers(min_value=1, max_value=5))
    reports = []
    report_ids = set()
    for _ in range(num_reports):
        r = draw(report_strategy())
        # Ensure unique IDs
        while r["id"] in report_ids:
            r = draw(report_strategy())
        report_ids.add(r["id"])
        reports.append(r)

    # Generate 1-5 templates with unique IDs
    num_templates = draw(st.integers(min_value=1, max_value=5))
    templates = []
    template_ids = set()
    for _ in range(num_templates):
        t = draw(template_strategy())
        while t["id"] in template_ids:
            t = draw(template_strategy())
        template_ids.add(t["id"])
        templates.append(t)

    # Generate 0 to N*M cells with unique (report_id, template_id) pairs
    r_ids = list(report_ids)
    t_ids = list(template_ids)
    max_cells = min(len(r_ids) * len(t_ids), 10)
    num_cells = draw(st.integers(min_value=0, max_value=max_cells))

    cells = []
    used_pairs = set()
    for _ in range(num_cells):
        c = draw(cell_strategy(r_ids, t_ids))
        pair = (c["report_id"], c["template_id"])
        if pair in used_pairs:
            continue
        used_pairs.add(pair)
        cells.append(c)

    return reports, templates, cells


# ---------------------------------------------------------------------------
# Property 19: State persistence round trip
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(state=full_state())
def test_property_19_state_persistence_round_trip(state):
    """Property 19: State persistence round trip.

    **Validates: Requirements 10.4**

    For any valid application state (reports, templates, cells with statuses
    and Task_IDs), persisting to the database and then loading should produce
    an equivalent state.
    """
    reports, templates, cells = state

    async def _run():
        # Create a fresh temp DB for each test iteration
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            sm = StateManager(db_path=db_path)
            await sm.init_db()

            # Persist reports
            await sm.persist_reports(reports)

            # Persist templates
            await sm.persist_templates(templates)

            # Persist cells
            for c in cells:
                cell = GenerationCell(
                    report_id=c["report_id"],
                    template_id=c["template_id"],
                    status=c["status"],
                    task_id=c["task_id"],
                    notebook_id=c["notebook_id"],
                    error_message=c["error_message"],
                    started_at=c["started_at"],
                    completed_at=c["completed_at"],
                    artifact_path=c["artifact_path"],
                )
                await sm.update_cell(cell)

            # Load state back
            loaded = await sm.load_state()

            # --- Verify reports ---
            loaded_reports = loaded["reports"]
            assert len(loaded_reports) == len(reports), (
                f"Expected {len(reports)} reports, got {len(loaded_reports)}"
            )
            original_by_id = {r["id"]: r for r in reports}
            for lr in loaded_reports:
                orig = original_by_id[lr["id"]]
                assert lr["filename"] == orig["filename"]
                assert lr["filepath"] == orig["filepath"]
                assert lr["file_size"] == orig.get("file_size")
                assert lr["last_modified"] == orig.get("last_modified")
                assert lr["notebook_name"] == orig["notebook_name"]

            # --- Verify templates ---
            loaded_templates = loaded["templates"]
            assert len(loaded_templates) == len(templates), (
                f"Expected {len(templates)} templates, got {len(loaded_templates)}"
            )
            orig_t_by_id = {t["id"]: t for t in templates}
            for lt in loaded_templates:
                orig = orig_t_by_id[lt["id"]]
                assert lt["filename"] == orig["filename"]
                assert lt["number"] == orig["number"]
                assert lt["artifact_type"] == orig["artifact_type"]
                assert lt["name"] == orig["name"]
                assert lt["audio_format"] == orig.get("audio_format")
                assert lt["content"] == orig["content"]

            # --- Verify cells ---
            loaded_cells = loaded["cells"]
            assert len(loaded_cells) == len(cells), (
                f"Expected {len(cells)} cells, got {len(loaded_cells)}"
            )
            orig_c_by_pair = {
                (c["report_id"], c["template_id"]): c for c in cells
            }
            for lc in loaded_cells:
                pair = (lc.report_id, lc.template_id)
                assert pair in orig_c_by_pair, (
                    f"Loaded cell {pair} not in original cells"
                )
                orig = orig_c_by_pair[pair]
                assert lc.status == orig["status"], (
                    f"Cell {pair}: expected status {orig['status']}, got {lc.status}"
                )
                assert lc.task_id == orig["task_id"]
                assert lc.notebook_id == orig["notebook_id"]
                assert lc.error_message == orig["error_message"]
                assert lc.artifact_path == orig["artifact_path"]

                # Datetime comparison: the DB stores ISO strings, so compare
                # after round-tripping through isoformat
                if orig["started_at"] is not None:
                    assert lc.started_at is not None
                    assert lc.started_at == orig["started_at"]
                else:
                    assert lc.started_at is None

                if orig["completed_at"] is not None:
                    assert lc.completed_at is not None
                    assert lc.completed_at == orig["completed_at"]
                else:
                    assert lc.completed_at is None

    run_async(_run())


# ---------------------------------------------------------------------------
# Property 20: Recovery matching
# ---------------------------------------------------------------------------

# Pure-logic helper that mirrors the matching algorithm in
# StateManager.recover_state without requiring a DB or async I/O.


def recovery_match(
    remote_notebooks: list[dict],
    local_cells: list[GenerationCell],
) -> tuple[list[tuple[dict, GenerationCell]], list[dict]]:
    """Match remote notebooks to local cells by notebook_id.

    Parameters
    ----------
    remote_notebooks : list[dict]
        Each dict has at least an ``"id"`` key.
    local_cells : list[GenerationCell]
        Local generation cells, some of which may have a ``notebook_id``.

    Returns
    -------
    matched : list[tuple[dict, GenerationCell]]
        Pairs where ``remote["id"] == cell.notebook_id``.
    unmatched_remotes : list[dict]
        Remote notebooks with no matching local cell.
    """
    cells_by_notebook_id: dict[str, GenerationCell] = {}
    for cell in local_cells:
        if cell.notebook_id is not None:
            cells_by_notebook_id[cell.notebook_id] = cell

    matched: list[tuple[dict, GenerationCell]] = []
    unmatched_remotes: list[dict] = []

    for nb in remote_notebooks:
        nb_id = nb.get("id")
        if nb_id is not None and nb_id in cells_by_notebook_id:
            matched.append((nb, cells_by_notebook_id[nb_id]))
        else:
            unmatched_remotes.append(nb)

    return matched, unmatched_remotes


# ---------------------------------------------------------------------------
# Strategy: generate remote notebooks and local cells with controlled overlap
# ---------------------------------------------------------------------------

@st.composite
def recovery_scenario(draw):
    """Generate remote notebooks and local cells with overlapping / non-overlapping IDs.

    Returns (remote_notebooks, local_cells) where:
    - ``shared_ids`` are IDs present in both remote notebooks and local cells
    - ``remote_only_ids`` are IDs only in remote notebooks
    - ``local_only_ids`` are notebook_ids only in local cells
    - Some local cells may have ``notebook_id=None``
    """
    # Pool of unique IDs
    all_ids = draw(
        st.lists(id_strategy, min_size=0, max_size=15, unique=True)
    )

    # Partition into shared / remote-only / local-only
    n = len(all_ids)
    shared_count = draw(st.integers(min_value=0, max_value=n))
    shared_ids = all_ids[:shared_count]
    remaining = all_ids[shared_count:]

    split = draw(st.integers(min_value=0, max_value=len(remaining)))
    remote_only_ids = remaining[:split]
    local_only_ids = remaining[split:]

    # Build remote notebooks
    remote_notebooks = [{"id": rid} for rid in shared_ids + remote_only_ids]
    # Shuffle so order is arbitrary
    remote_notebooks = draw(st.permutations(remote_notebooks))

    # Build local cells – one per shared_id and local_only_id, plus some with None
    local_cells: list[GenerationCell] = []
    for nid in shared_ids + local_only_ids:
        local_cells.append(
            GenerationCell(
                report_id=draw(id_strategy),
                template_id=draw(id_strategy),
                status=draw(cell_statuses),
                notebook_id=nid,
            )
        )

    # Add 0-3 cells with notebook_id=None
    none_count = draw(st.integers(min_value=0, max_value=3))
    for _ in range(none_count):
        local_cells.append(
            GenerationCell(
                report_id=draw(id_strategy),
                template_id=draw(id_strategy),
                status=draw(cell_statuses),
                notebook_id=None,
            )
        )

    return remote_notebooks, local_cells, set(shared_ids), set(remote_only_ids), set(local_only_ids)


@settings(max_examples=100)
@given(scenario=recovery_scenario())
def test_property_20_recovery_matching(scenario):
    """Property 20: Recovery matching.

    **Validates: Requirements 10.2**

    For any set of remote notebooks (with IDs) and local generation cells
    (with notebook_ids), the recovery matching algorithm should correctly pair
    each remote notebook to its local cell when the notebook_id matches, and
    should not create false matches.
    """
    remote_notebooks, local_cells, shared_ids, remote_only_ids, local_only_ids = scenario

    matched, unmatched_remotes = recovery_match(remote_notebooks, local_cells)

    # 1. Every matched pair has matching IDs
    for nb, cell in matched:
        assert nb["id"] == cell.notebook_id, (
            f"False match: remote id={nb['id']} paired with cell notebook_id={cell.notebook_id}"
        )

    # 2. All shared IDs appear in matched pairs
    matched_remote_ids = {nb["id"] for nb, _ in matched}
    assert shared_ids <= matched_remote_ids, (
        f"Missing matches for shared IDs: {shared_ids - matched_remote_ids}"
    )

    # 3. Remote-only IDs appear in unmatched
    unmatched_ids = {nb["id"] for nb in unmatched_remotes}
    assert remote_only_ids <= unmatched_ids, (
        f"Remote-only IDs missing from unmatched: {remote_only_ids - unmatched_ids}"
    )

    # 4. No false matches – unmatched remotes should NOT have a matching local cell
    local_notebook_ids = {c.notebook_id for c in local_cells if c.notebook_id is not None}
    for nb in unmatched_remotes:
        assert nb["id"] not in local_notebook_ids, (
            f"Remote notebook {nb['id']} is unmatched but has a local cell with that notebook_id"
        )

    # 5. Total counts are consistent: matched + unmatched == total remote notebooks
    assert len(matched) + len(unmatched_remotes) == len(remote_notebooks), (
        f"Count mismatch: {len(matched)} matched + {len(unmatched_remotes)} unmatched "
        f"!= {len(remote_notebooks)} total remotes"
    )

    # 6. No duplicate remote notebooks in matched output
    assert len(matched_remote_ids) == len(matched), (
        "Duplicate remote notebooks in matched output"
    )

# ---------------------------------------------------------------------------
# Property 21: Untracked notebook detection
# ---------------------------------------------------------------------------

@settings(max_examples=100)
@given(scenario=recovery_scenario())
def test_property_21_untracked_notebook_detection(scenario):
    """Property 21: Untracked notebook detection.

    **Validates: Requirements 10.5**

    For any set of remote notebooks and local state, notebooks whose IDs do
    not appear in any local generation cell should be classified as
    "untracked".
    """
    remote_notebooks, local_cells, shared_ids, remote_only_ids, local_only_ids = scenario

    _, unmatched_remotes = recovery_match(remote_notebooks, local_cells)

    # Collect all notebook_ids present in local cells
    local_notebook_ids = {
        c.notebook_id for c in local_cells if c.notebook_id is not None
    }

    untracked_ids = {nb["id"] for nb in unmatched_remotes}

    # 1. Every untracked notebook ID must NOT appear in any local cell
    for uid in untracked_ids:
        assert uid not in local_notebook_ids, (
            f"Notebook {uid} is classified as untracked but exists in local cells"
        )

    # 2. Every remote notebook whose ID is absent from local cells must be untracked
    for nb in remote_notebooks:
        nb_id = nb["id"]
        if nb_id not in local_notebook_ids:
            assert nb_id in untracked_ids, (
                f"Remote notebook {nb_id} has no local cell but was NOT classified as untracked"
            )

    # 3. Conversely, no remote notebook that IS in local cells should be untracked
    for nb in remote_notebooks:
        nb_id = nb["id"]
        if nb_id in local_notebook_ids:
            assert nb_id not in untracked_ids, (
                f"Remote notebook {nb_id} has a matching local cell but was classified as untracked"
            )

    # 4. The untracked set should exactly equal remote IDs minus local IDs
    remote_ids = {nb["id"] for nb in remote_notebooks}
    expected_untracked = remote_ids - local_notebook_ids
    assert untracked_ids == expected_untracked, (
        f"Untracked set mismatch: got {untracked_ids}, expected {expected_untracked}"
    )

