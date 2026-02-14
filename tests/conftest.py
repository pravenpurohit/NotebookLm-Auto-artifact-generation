"""Shared pytest fixtures for the test suite.

Provides:
  - nlm_cleanup: Tracks notebook IDs created during tests and deletes them
    in teardown. Logs warnings on cleanup failures without failing the test.

Requirements: 6.1, 6.2, 6.3
"""

from __future__ import annotations

import logging

import pytest_asyncio

logger = logging.getLogger(__name__)


@pytest_asyncio.fixture
async def nlm_cleanup(request):
    """Track created notebook IDs and delete them during teardown.

    Usage::

        async def test_something(nlm_cleanup, nlm_client):
            nb_id = await nlm_client.create_notebook(...)
            nlm_cleanup.append(nb_id)
            # ... test logic ...
            # Teardown automatically deletes nb_id

    The fixture accepts any object with an async ``delete_notebook`` method.
    Set ``nlm_cleanup.client`` to the NLM client instance so teardown can
    call it.  If no client is set, teardown is skipped with a debug log.

    Requirements:
      6.1 — test teardown deletes notebooks created via NLM_Client
      6.2 — cleanup failures are logged as warnings, tests are not failed
      6.3 — implemented as a pytest fixture tracking created notebook IDs
    """

    class _CleanupTracker:
        """Lightweight tracker that stores notebook IDs and an NLM client."""

        def __init__(self) -> None:
            self.notebook_ids: list[str] = []
            self.client = None

        # Allow list-like append for convenience
        def append(self, notebook_id: str) -> None:  # noqa: D401
            self.notebook_ids.append(notebook_id)

        def __iter__(self):
            return iter(self.notebook_ids)

        def __len__(self):
            return len(self.notebook_ids)

    tracker = _CleanupTracker()
    yield tracker

    # --- Teardown ---
    if not tracker.notebook_ids:
        return

    if tracker.client is None:
        logger.debug(
            "nlm_cleanup: no client set — skipping teardown for %d notebook(s)",
            len(tracker.notebook_ids),
        )
        return

    for nb_id in tracker.notebook_ids:
        try:
            await tracker.client.delete_notebook(nb_id)
            logger.info("nlm_cleanup: deleted notebook %s", nb_id)
        except Exception as exc:
            logger.warning(
                "Test cleanup failed for notebook %s: %s", nb_id, exc
            )
