"""Shared pytest fixtures for Agented tests (Litestar-only after wave 81)."""

import logging
import os
import sys
import warnings

import pytest

logger = logging.getLogger(__name__)

# Ensure the backend app package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Provide each test with an isolated SQLite database.

    Suppresses 'no such table' warnings from daemon threads that may attempt
    DB access during fixture teardown after the temp database is removed.
    These warnings do not affect test correctness since assertions happen
    before teardown.
    """
    warnings.filterwarnings("ignore", message=".*no such table.*")
    warnings.filterwarnings("ignore", message=".*database is locked.*")
    warnings.filterwarnings("ignore", category=pytest.PytestUnhandledThreadExceptionWarning)

    db_file = str(tmp_path / "test.db")
    monkeypatch.setattr("app.config.DB_PATH", db_file)
    monkeypatch.setattr("app.config.SYMLINK_DIR", str(tmp_path / "project_links"))

    from app.database import init_db, seed_predefined_triggers

    init_db()
    seed_predefined_triggers()
    yield db_file


@pytest.fixture(autouse=True)
def reset_rbac_cache():
    """Clear RBAC has_any_keys cache between tests to prevent cross-test interference."""
    try:
        from app.db.rbac import invalidate_key_cache

        invalidate_key_cache()
    except ImportError:
        logger.debug("Could not import invalidate_key_cache (module not loaded)")
    yield
    try:
        from app.db.rbac import invalidate_key_cache

        invalidate_key_cache()
    except ImportError:
        logger.debug("Could not import invalidate_key_cache (module not loaded)")
