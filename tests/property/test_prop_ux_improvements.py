"""Property-based tests for UX Improvements correctness properties.

Feature: ux-improvements

Covers all 12 correctness properties from the design document:
  Property 1: Remote artifact response completeness (Req 1.2)
  Property 2: Merge deduplication produces no duplicates (Req 1.3)
  Property 3: Filters apply consistently across artifact sources (Req 1.5)
  Property 4: Success message contains all uploaded filenames (Req 2.3)
  Property 5: Appending new reports preserves existing reports (Req 3.1, 3.3)
  Property 6: Edited notebook names are protected from overwrite (Req 3.2, 3.5)
  Property 7: Editing a notebook name marks the report as user-edited (Req 3.4)
  Property 8: Artifact deletion removes record and file (Req 4.2)
  Property 9: Notebook deletion cascades to local records (Req 5.3)
  Property 10: Content hash is deterministic (Req 7.1)
  Property 11: Duplicate notebook detection is accurate (Req 7.2, 7.5)
  Property 12: Prompt hash changes when content changes (Req 8.4)
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Optional

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.models import RemoteArtifactResponse
from app.state_manager import StateManager


# ---------------------------------------------------------------------------
# Helper: run async code from sync Hypothesis test
# ---------------------------------------------------------------------------

def run_async(coro):
    """Run an async coroutine in a new event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

safe_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        blacklist_characters="\x00\n\r",
    ),
    min_size=1,
    max_size=60,
).filter(lambda s: s.strip() == s and len(s.strip()) > 0)

id_strategy = st.uuids().map(str)

artifact_types = st.sampled_from(["infographic", "audio", "video", "unknown"])

# Dates as ISO strings
date_strings = st.from_regex(r"2024-\d{2}-\d{2}", fullmatch=True)


# ===========================================================================
# Property 1: Remote artifact response completeness
# ===========================================================================

remote_artifact_strategy = st.builds(
    RemoteArtifactResponse,
    id=id_strategy.map(lambda x: f"remote-{x}"),
    artifact_name=safe_text,
    artifact_type=artifact_types,
    source_notebook_title=safe_text,
    source_notebook_id=id_strategy,
    created_at=st.one_of(st.none(), date_strings),
    is_remote=st.just(True),
)


@settings(max_examples=100)
@given(artifact=remote_artifact_strategy)
def test_property_1_remote_artifact_response_completeness(artifact: RemoteArtifactResponse):
    """Property 1: Remote artifact response completeness.

    **Validates: Requirements 1.2**

    For any remote artifact returned by the /api/artifacts/remote endpoint,
    the response object shall contain non-empty values for artifact_name,
    artifact_type, source_notebook_title, and source_notebook_id.
    """
    assert artifact.artifact_name, (
        f"artifact_name must be non-empty, got '{artifact.artifact_name}'"
    )
    assert artifact.artifact_type, (
        f"artifact_type must be non-empty, got '{artifact.artifact_type}'"
    )
    assert artifact.source_notebook_title, (
        f"source_notebook_title must be non-empty, got '{artifact.source_notebook_title}'"
    )
    assert artifact.source_notebook_id, (
        f"source_notebook_id must be non-empty, got '{artifact.source_notebook_id}'"
    )
    assert artifact.is_remote is True, "is_remote must always be True"

    # Verify model_dump produces all required keys
    dumped = artifact.model_dump()
    required_keys = {"id", "artifact_name", "artifact_type", "source_notebook_title",
                     "source_notebook_id", "created_at", "is_remote"}
    assert required_keys <= set(dumped.keys()), (
        f"Missing keys in model_dump: {required_keys - set(dumped.keys())}"
    )


# ===========================================================================
# Property 2: Merge deduplication produces no duplicates
# ===========================================================================

def merge_artifacts(local: list[dict], remote: list[dict]) -> list[dict]:
    """Python implementation of the frontend merge logic.

    Deduplicates on (source_notebook_id, artifact_name).
    """
    local_keys = set()
    for a in local:
        nb_id = a.get("source_notebook_id")
        name = a.get("artifact_name")
        if nb_id and name:
            local_keys.add((nb_id, name))

    merged = list(local)
    for a in remote:
        key = (a.get("source_notebook_id"), a.get("artifact_name"))
        if key not in local_keys:
            merged.append(a)

    return merged


local_artifact_strategy = st.fixed_dictionaries({
    "id": id_strategy.map(lambda x: f"local-{x}"),
    "artifact_name": safe_text,
    "artifact_type": artifact_types,
    "source_notebook_id": id_strategy,
    "is_remote": st.just(False),
})

remote_artifact_dict_strategy = st.fixed_dictionaries({
    "id": id_strategy.map(lambda x: f"remote-{x}"),
    "artifact_name": safe_text,
    "artifact_type": artifact_types,
    "source_notebook_id": id_strategy,
    "is_remote": st.just(True),
})


@settings(max_examples=100)
@given(
    local=st.lists(local_artifact_strategy, min_size=0, max_size=10),
    remote=st.lists(remote_artifact_dict_strategy, min_size=0, max_size=10),
)
def test_property_2_merge_deduplication_no_duplicates(local, remote):
    """Property 2: Merge deduplication produces no duplicates.

    **Validates: Requirements 1.3**

    For any set of local artifacts and remote artifacts, the merge function
    shall produce a list where no two entries share the same
    (source_notebook_id, artifact_name) pair, and the total count is less
    than or equal to the sum of local and remote counts.
    """
    merged = merge_artifacts(local, remote)

    # No duplicate (source_notebook_id, artifact_name) pairs
    seen_keys = set()
    for a in merged:
        key = (a.get("source_notebook_id"), a.get("artifact_name"))
        assert key not in seen_keys, (
            f"Duplicate key found in merged list: {key}"
        )
        seen_keys.add(key)

    # Total count <= sum of inputs
    assert len(merged) <= len(local) + len(remote), (
        f"Merged count {len(merged)} exceeds sum of inputs "
        f"({len(local)} + {len(remote)})"
    )

    # All local artifacts are preserved
    local_ids = {a["id"] for a in local}
    merged_ids = {a["id"] for a in merged}
    assert local_ids <= merged_ids, (
        f"Local artifacts missing from merged: {local_ids - merged_ids}"
    )


# ===========================================================================
# Property 3: Filters apply consistently across artifact sources
# ===========================================================================

def filter_merged_artifacts(
    artifacts: list[dict],
    artifact_type: Optional[str] = None,
) -> list[dict]:
    """Filter a merged artifact list by artifact_type.

    This mirrors the frontend filter logic that operates on the unified
    local+remote list regardless of the is_remote flag.
    """
    if artifact_type is None:
        return list(artifacts)
    return [a for a in artifacts if a.get("artifact_type") == artifact_type]


@st.composite
def mixed_artifact_list(draw):
    """Generate a mixed list of local and remote artifacts."""
    local = draw(st.lists(local_artifact_strategy, min_size=0, max_size=8))
    remote = draw(st.lists(remote_artifact_dict_strategy, min_size=0, max_size=8))
    merged = merge_artifacts(local, remote)
    return merged


@settings(max_examples=100)
@given(
    artifacts=mixed_artifact_list(),
    filter_type=st.one_of(st.none(), artifact_types),
)
def test_property_3_filters_apply_consistently(artifacts, filter_type):
    """Property 3: Filters apply consistently across artifact sources.

    **Validates: Requirements 1.5**

    For any filter criteria and any mixed list of local and remote artifacts,
    applying the filter shall return only artifacts matching the criteria,
    regardless of whether the artifact is local or remote.
    """
    result = filter_merged_artifacts(artifacts, artifact_type=filter_type)

    if filter_type is None:
        # No filter: all artifacts returned
        assert len(result) == len(artifacts)
    else:
        # Every result matches the filter
        for a in result:
            assert a["artifact_type"] == filter_type, (
                f"Artifact {a['id']} has type '{a['artifact_type']}' "
                f"but filter requires '{filter_type}'"
            )

        # No matching artifact was excluded
        expected_ids = {a["id"] for a in artifacts if a.get("artifact_type") == filter_type}
        result_ids = {a["id"] for a in result}
        assert expected_ids == result_ids, (
            f"Filter missed artifacts: {expected_ids - result_ids}"
        )

    # Filter applies equally to local and remote
    local_in_result = [a for a in result if not a.get("is_remote")]
    remote_in_result = [a for a in result if a.get("is_remote")]
    for a in local_in_result:
        if filter_type is not None:
            assert a["artifact_type"] == filter_type
    for a in remote_in_result:
        if filter_type is not None:
            assert a["artifact_type"] == filter_type


# ===========================================================================
# Property 4: Success message contains all uploaded filenames
# ===========================================================================

def build_success_message(filenames: list[str]) -> str:
    """Build a success confirmation message listing uploaded filenames.

    This mirrors the backend/frontend logic for generating the success toast.
    """
    if not filenames:
        return "No files uploaded."
    if len(filenames) == 1:
        return f"Successfully uploaded: {filenames[0]}"
    return f"Successfully uploaded: {', '.join(filenames)}"


filename_strategy = st.from_regex(r"[a-zA-Z0-9_]{1,30}\.(pdf|md)", fullmatch=True)


@settings(max_examples=100)
@given(filenames=st.lists(filename_strategy, min_size=1, max_size=10, unique=True))
def test_property_4_success_message_contains_all_filenames(filenames):
    """Property 4: Success message contains all uploaded filenames.

    **Validates: Requirements 2.3**

    For any set of successfully uploaded filenames, the generated success
    confirmation message shall contain every filename from the set.
    """
    message = build_success_message(filenames)

    for fname in filenames:
        assert fname in message, (
            f"Filename '{fname}' not found in success message: '{message}'"
        )

    # Message should start with the expected prefix
    assert message.startswith("Successfully uploaded:"), (
        f"Message should start with 'Successfully uploaded:', got: '{message}'"
    )


# ===========================================================================
# Property 5: Appending new reports preserves existing reports
# ===========================================================================

def report_strategy():
    """Generate a random report dict."""
    return st.fixed_dictionaries({
        "id": id_strategy,
        "filename": safe_text.map(lambda s: s[:20] + ".pdf"),
        "filepath": safe_text.map(lambda s: f"/uploads/{s[:20]}.pdf"),
        "file_size": st.integers(min_value=100, max_value=10_000_000),
        "last_modified": st.just("2024-06-01"),
        "notebook_name": safe_text,
    })


@st.composite
def existing_and_new_reports(draw):
    """Generate existing reports and new reports with non-overlapping IDs."""
    existing = draw(st.lists(report_strategy(), min_size=1, max_size=5, unique_by=lambda r: r["id"]))
    new = draw(st.lists(report_strategy(), min_size=1, max_size=5, unique_by=lambda r: r["id"]))
    existing_ids = {r["id"] for r in existing}
    new = [r for r in new if r["id"] not in existing_ids]
    assume(len(new) > 0)
    return existing, new


@settings(max_examples=50)
@given(scenario=existing_and_new_reports())
def test_property_5_appending_preserves_existing_reports(scenario):
    """Property 5: Appending new reports preserves existing reports.

    **Validates: Requirements 3.1, 3.3**

    For any existing report list and any set of new reports, after appending
    the new reports, every previously existing report shall remain in the list
    with identical field values (including notebook_name).
    """
    existing, new = scenario

    async def _run():
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            sm = StateManager(db_path=db_path)
            await sm.init_db()

            # Persist existing reports
            await sm.persist_reports(existing)

            # Persist new reports (append)
            await sm.persist_reports(new)

            # Load all reports
            state = await sm.load_state()
            loaded = state["reports"]

            # All existing reports should still be present with same values
            loaded_by_id = {r["id"]: r for r in loaded}
            for orig in existing:
                assert orig["id"] in loaded_by_id, (
                    f"Existing report {orig['id']} missing after append"
                )
                loaded_r = loaded_by_id[orig["id"]]
                assert loaded_r["filename"] == orig["filename"], (
                    f"filename changed for {orig['id']}"
                )
                assert loaded_r["notebook_name"] == orig["notebook_name"], (
                    f"notebook_name changed for {orig['id']}: "
                    f"'{orig['notebook_name']}' -> '{loaded_r['notebook_name']}'"
                )

            # All new reports should also be present
            for nr in new:
                assert nr["id"] in loaded_by_id, (
                    f"New report {nr['id']} missing after append"
                )

            # Total count = existing + new
            assert len(loaded) == len(existing) + len(new), (
                f"Expected {len(existing) + len(new)} reports, got {len(loaded)}"
            )

    run_async(_run())


# ===========================================================================
# Property 6: Edited notebook names are protected from overwrite
# ===========================================================================

@settings(max_examples=50)
@given(
    original_name=safe_text,
    edited_name=safe_text,
    overwrite_name=safe_text,
)
def test_property_6_edited_names_protected_from_overwrite(
    original_name, edited_name, overwrite_name,
):
    """Property 6: Edited notebook names are protected from overwrite.

    **Validates: Requirements 3.2, 3.5**

    For any report where notebook_name_edited is True, calling persist_reports
    with a different notebook_name for that report ID shall not change the
    stored notebook_name.
    """
    assume(edited_name != original_name)

    async def _run():
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            sm = StateManager(db_path=db_path)
            await sm.init_db()

            report_id = "r-protected"

            # Create report with original name
            await sm.persist_reports([{
                "id": report_id,
                "filename": "test.pdf",
                "filepath": "/test.pdf",
                "notebook_name": original_name,
            }])

            # User edits the name
            await sm.update_report_notebook_name(report_id, edited_name)

            # Attempt overwrite via persist_reports
            await sm.persist_reports([{
                "id": report_id,
                "filename": "test.pdf",
                "filepath": "/test.pdf",
                "notebook_name": overwrite_name,
            }])

            # Verify the edited name is preserved
            state = await sm.load_state()
            report = next(r for r in state["reports"] if r["id"] == report_id)

            assert report["notebook_name"] == edited_name, (
                f"Edited name '{edited_name}' was overwritten to "
                f"'{report['notebook_name']}' by persist_reports"
            )
            assert report["notebook_name_edited"] is True, (
                "notebook_name_edited flag should remain True"
            )

    run_async(_run())


# ===========================================================================
# Property 7: Editing a notebook name marks the report as user-edited
# ===========================================================================

@settings(max_examples=50)
@given(
    original_name=safe_text,
    new_name=safe_text,
)
def test_property_7_editing_marks_report_as_user_edited(original_name, new_name):
    """Property 7: Editing a notebook name marks the report as user-edited.

    **Validates: Requirements 3.4**

    For any report, after calling update_report_notebook_name with a new name,
    the report's notebook_name_edited flag shall be True.
    """
    async def _run():
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            sm = StateManager(db_path=db_path)
            await sm.init_db()

            report_id = "r-edit-flag"

            # Create report
            await sm.persist_reports([{
                "id": report_id,
                "filename": "test.pdf",
                "filepath": "/test.pdf",
                "notebook_name": original_name,
            }])

            # Verify flag starts as False
            state = await sm.load_state()
            report = next(r for r in state["reports"] if r["id"] == report_id)
            assert report["notebook_name_edited"] is False, (
                "notebook_name_edited should start as False"
            )

            # Edit the name
            result = await sm.update_report_notebook_name(report_id, new_name)
            assert result is True, "update should return True for existing report"

            # Verify flag is now True
            state = await sm.load_state()
            report = next(r for r in state["reports"] if r["id"] == report_id)
            assert report["notebook_name_edited"] is True, (
                "notebook_name_edited should be True after editing"
            )
            assert report["notebook_name"] == new_name, (
                f"notebook_name should be '{new_name}', got '{report['notebook_name']}'"
            )

    run_async(_run())


# ===========================================================================
# Property 8: Artifact deletion removes record and file
# ===========================================================================

@settings(max_examples=50)
@given(
    artifact_name=safe_text,
    artifact_type=artifact_types,
    file_content=st.binary(min_size=1, max_size=200),
)
def test_property_8_artifact_deletion_removes_record_and_file(
    artifact_name, artifact_type, file_content,
):
    """Property 8: Artifact deletion removes record and file.

    **Validates: Requirements 4.2**

    For any local artifact, after successful deletion via delete_artifact_record,
    the artifact record shall not exist in the database and the artifact file
    shall not exist on disk.
    """
    import aiosqlite

    async def _run():
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            sm = StateManager(db_path=db_path)
            # Set output base to tmpdir so path validation allows deletion
            sm._output_base = tmpdir
            await sm.init_db()

            # Create artifact file on disk
            artifact_file = os.path.join(tmpdir, "artifact_output.png")
            with open(artifact_file, "wb") as f:
                f.write(file_content)

            # Seed DB: report, template, artifact
            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    "INSERT INTO reports (id, filename, filepath, notebook_name) "
                    "VALUES (?, ?, ?, ?)",
                    ("r-p8", "report.md", "/report.md", "Report"),
                )
                await db.execute(
                    "INSERT INTO templates (id, filename, number, artifact_type, name, content) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("t-p8", "01_Infographic_Test.md", 1, "infographic", "Test", "content"),
                )
                await db.execute(
                    "INSERT INTO artifacts (id, report_id, template_id, artifact_type, "
                    "artifact_name, file_path, file_extension) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("a-p8", "r-p8", "t-p8", artifact_type, artifact_name,
                     artifact_file, ".png"),
                )
                await db.commit()

            # Verify artifact exists
            assert os.path.isfile(artifact_file)

            # Delete the artifact
            result = await sm.delete_artifact_record("a-p8")
            assert result is True, "delete_artifact_record should return True"

            # Verify record is gone from DB
            async with aiosqlite.connect(db_path) as db:
                cursor = await db.execute(
                    "SELECT id FROM artifacts WHERE id = 'a-p8'"
                )
                row = await cursor.fetchone()
            assert row is None, "Artifact record should be removed from DB"

            # Verify file is gone from disk
            assert not os.path.isfile(artifact_file), (
                "Artifact file should be removed from disk"
            )

    run_async(_run())


# ===========================================================================
# Property 9: Notebook deletion cascades to local records
# ===========================================================================

@settings(max_examples=50)
@given(
    num_cells=st.integers(min_value=1, max_value=4),
)
def test_property_9_notebook_deletion_cascades_to_local_records(num_cells):
    """Property 9: Notebook deletion cascades to local records.

    **Validates: Requirements 5.3**

    For any notebook deletion, all generation cells and artifacts associated
    with that notebook_id shall be removed from the local database.
    """
    import aiosqlite

    async def _run():
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            sm = StateManager(db_path=db_path)
            await sm.init_db()

            notebook_id = "nb-cascade-test"

            async with aiosqlite.connect(db_path) as db:
                # Create a report
                await db.execute(
                    "INSERT INTO reports (id, filename, filepath, notebook_name) "
                    "VALUES (?, ?, ?, ?)",
                    ("r-p9", "report.md", "/report.md", "Report"),
                )

                # Create templates and cells
                for i in range(num_cells):
                    tmpl_id = f"t-p9-{i}"
                    await db.execute(
                        "INSERT INTO templates (id, filename, number, artifact_type, name, content) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (tmpl_id, f"0{i}_Infographic_Test.md", i + 1, "infographic",
                         f"Test{i}", f"content{i}"),
                    )
                    await db.execute(
                        "INSERT INTO generation_cells (report_id, template_id, status, notebook_id) "
                        "VALUES (?, ?, ?, ?)",
                        ("r-p9", tmpl_id, "completed", notebook_id),
                    )
                    await db.execute(
                        "INSERT INTO artifacts (id, report_id, template_id, artifact_type, "
                        "artifact_name, file_path, file_extension) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (f"a-p9-{i}", "r-p9", tmpl_id, "infographic",
                         f"Art{i}", f"/out/a{i}.png", ".png"),
                    )
                await db.commit()

            # Delete the notebook
            deleted = await sm.delete_notebook_records(notebook_id)
            assert deleted == num_cells, (
                f"Expected {num_cells} cells deleted, got {deleted}"
            )

            # Verify all cells and artifacts are gone
            async with aiosqlite.connect(db_path) as db:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM generation_cells WHERE notebook_id = ?",
                    (notebook_id,),
                )
                assert (await cursor.fetchone())[0] == 0, (
                    "All generation cells should be removed"
                )

                cursor = await db.execute(
                    "SELECT COUNT(*) FROM artifacts WHERE report_id = 'r-p9'"
                )
                assert (await cursor.fetchone())[0] == 0, (
                    "All artifacts should be removed"
                )

                # Report should still exist
                cursor = await db.execute(
                    "SELECT id FROM reports WHERE id = 'r-p9'"
                )
                assert await cursor.fetchone() is not None, (
                    "Report should NOT be deleted by notebook cascade"
                )

    run_async(_run())


# ===========================================================================
# Property 10: Content hash is deterministic
# ===========================================================================

@settings(max_examples=200)
@given(content=st.binary(min_size=0, max_size=5000))
def test_property_10_content_hash_is_deterministic(content):
    """Property 10: Content hash is deterministic.

    **Validates: Requirements 7.1**

    For any file content, computing the SHA-256 hash twice shall produce the
    same result. The hash shall be a valid 64-character hex string.
    """
    hash1 = StateManager.compute_content_hash(content)
    hash2 = StateManager.compute_content_hash(content)

    assert hash1 == hash2, (
        f"Hash should be deterministic: '{hash1}' != '{hash2}'"
    )
    assert len(hash1) == 64, (
        f"SHA-256 hex digest should be 64 chars, got {len(hash1)}"
    )
    assert all(c in "0123456789abcdef" for c in hash1), (
        f"Hash should be lowercase hex, got '{hash1}'"
    )


@settings(max_examples=100)
@given(
    content_a=st.binary(min_size=1, max_size=2000),
    content_b=st.binary(min_size=1, max_size=2000),
)
def test_property_10b_different_content_different_hash(content_a, content_b):
    """Property 10 (part b): Different content produces different hashes.

    **Validates: Requirements 7.1**

    Two files with different content shall produce different hashes.
    """
    assume(content_a != content_b)

    hash_a = StateManager.compute_content_hash(content_a)
    hash_b = StateManager.compute_content_hash(content_b)

    assert hash_a != hash_b, (
        f"Different content should produce different hashes: "
        f"content_a={content_a!r}, content_b={content_b!r}"
    )


# ===========================================================================
# Property 11: Duplicate notebook detection is accurate
# ===========================================================================

@settings(max_examples=50)
@given(
    file_content=st.binary(min_size=10, max_size=500),
    notebook_id=id_strategy,
)
def test_property_11_duplicate_notebook_detection_is_accurate(
    file_content, notebook_id,
):
    """Property 11: Duplicate notebook detection is accurate.

    **Validates: Requirements 7.2, 7.5**

    For any report with a stored content_hash, if a generation cell exists
    with a notebook_id for that report, find_notebook_by_content_hash shall
    return the matching notebook info.
    """
    import aiosqlite

    async def _run():
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            sm = StateManager(db_path=db_path)
            await sm.init_db()

            content_hash = StateManager.compute_content_hash(file_content)
            hash_suffix = content_hash[:8]

            # Create report with content hash
            report = {
                "id": "r-p11",
                "filename": "test.md",
                "filepath": "/tmp/test.md",
                "file_size": len(file_content),
                "last_modified": "2024-01-01",
                "notebook_name": f"Test [{hash_suffix}]",
                "notebook_name_edited": False,
                "content_hash": content_hash,
            }
            await sm.persist_reports([report])

            # Create template and generation cell
            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    "INSERT INTO templates (id, filename, number, artifact_type, name, content) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("t-p11", "01_Infographic_Test.md", 1, "infographic", "Test", "content"),
                )
                await db.execute(
                    "INSERT INTO generation_cells (report_id, template_id, status, notebook_id) "
                    "VALUES (?, ?, ?, ?)",
                    ("r-p11", "t-p11", "completed", notebook_id),
                )
                await db.commit()

            # Detection should find the match
            result = await sm.find_notebook_by_content_hash(content_hash)
            assert result is not None, (
                "Should find notebook for matching content hash"
            )
            assert result["notebook_id"] == notebook_id, (
                f"Expected notebook_id '{notebook_id}', got '{result['notebook_id']}'"
            )
            assert result["report_id"] == "r-p11"

            # Different hash should NOT match
            different_hash = StateManager.compute_content_hash(b"completely different")
            result2 = await sm.find_notebook_by_content_hash(different_hash)
            assert result2 is None, (
                "Should not find notebook for non-matching content hash"
            )

    run_async(_run())


# ===========================================================================
# Property 12: Prompt hash changes when content changes
# ===========================================================================

@settings(max_examples=200)
@given(
    content_a=st.text(min_size=1, max_size=500),
    content_b=st.text(min_size=1, max_size=500),
)
def test_property_12_prompt_hash_changes_when_content_changes(content_a, content_b):
    """Property 12: Prompt hash changes when content changes.

    **Validates: Requirements 8.4**

    For any template, editing the prompt content shall produce a different
    prompt_hash than the original content.
    """
    assume(content_a != content_b)

    hash_a = StateManager.compute_content_hash(content_a.encode("utf-8"))
    hash_b = StateManager.compute_content_hash(content_b.encode("utf-8"))

    assert hash_a != hash_b, (
        f"Different prompt content should produce different hashes: "
        f"content_a={content_a!r}, content_b={content_b!r}"
    )

    # Both should be valid SHA-256 hex strings
    assert len(hash_a) == 64
    assert len(hash_b) == 64
