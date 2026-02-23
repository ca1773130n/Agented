"""Shared pytest fixtures for Agented tests."""

import os
import sys
import warnings

import pytest

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
    # Suppress SQLite table-not-found warnings from daemon threads during teardown
    warnings.filterwarnings("ignore", message=".*no such table.*")
    warnings.filterwarnings("ignore", message=".*database is locked.*")
    # Suppress PytestUnhandledThreadExceptionWarning from daemon thread teardown race
    # (workflow execution threads access temp DB after pytest fixture cleanup)
    warnings.filterwarnings("ignore", category=pytest.PytestUnhandledThreadExceptionWarning)

    db_file = str(tmp_path / "test.db")
    monkeypatch.setattr("app.config.DB_PATH", db_file)
    monkeypatch.setattr("app.config.SYMLINK_DIR", str(tmp_path / "project_links"))

    from app.database import init_db, seed_predefined_triggers

    init_db()
    seed_predefined_triggers()
    yield db_file


@pytest.fixture(scope="session")
def app():
    """Create a Flask test application once per session.

    The app is reused across all tests; per-test DB isolation is handled
    by the ``isolated_db`` fixture which patches ``config.DB_PATH`` before
    each test.  Because ``get_connection()`` reads ``DB_PATH`` dynamically,
    the session-scoped app always connects to the correct temp database.
    """
    from app import create_app

    application = create_app(config={"TESTING": True})
    return application


@pytest.fixture()
def client(app):
    """Flask test client."""
    return app.test_client()
