"""Shared pytest fixtures for Agented tests (Litestar-only after wave 81)."""

import logging
import os
import shutil
import sys
import warnings

import pytest

logger = logging.getLogger(__name__)

# Ensure the backend app package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# test_stream.py is a manual script that shells out to the `claude` CLI on
# import. CI runners don't have it installed, so collection fails. Skip
# only when the binary isn't on PATH; locally it auto-runs as before.
collect_ignore = []
if shutil.which("claude") is None:
    collect_ignore.append("test_stream.py")


@pytest.fixture(autouse=True)
def _allow_bootstrap(monkeypatch):
    """Bootstrap (empty-DB) auth is fail-closed in production and requires an
    explicit opt-in (AGENTED_ALLOW_BOOTSTRAP=1, see auth middleware/provide_caller).
    The test suite drives routes against an empty user_roles table, so opt in
    here. Tests that specifically assert fail-closed behaviour can override by
    deleting the env var via their own monkeypatch."""
    monkeypatch.setenv("AGENTED_ALLOW_BOOTSTRAP", "1")
    yield


@pytest.fixture(autouse=True)
def _reset_rate_limit_overrides():
    """v0.5.14: rate_limit_guard._PER_ROUTE_OVERRIDES is module-global.
    Tests that spin up the full Litestar app via on_startup populate it
    via the eager walker; without a reset, those entries leak into
    subsequent tests in OTHER files that don't clear the registry."""
    try:
        from app_litestar.rate_limit_guard import clear_overrides
    except Exception:
        yield
        return
    clear_overrides()
    yield
    clear_overrides()


# isolated_db is parametrized over sqlite|postgres (26-01). The postgres param
# only appears when a Postgres DATABASE_URL is configured (CI or a local
# testcontainers-backed URL) — otherwise the fixture is NOT parametrized, so the
# zero-config default run stays SQLite-only and every test ID is unchanged
# (byte-for-byte invariant).
def _db_backends():
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith(("postgres://", "postgresql://")):
        return ["sqlite", "postgres"]
    return None  # unparametrized → SQLite path, unchanged behavior


@pytest.fixture(params=_db_backends(), autouse=True)
def isolated_db(request, tmp_path, monkeypatch):
    """Provide each test with an isolated database (SQLite by default; also
    Postgres when DATABASE_URL is a postgres URL — 26-01).

    Suppresses 'no such table' warnings from daemon threads that may attempt
    DB access during fixture teardown after the temp database is removed.
    These warnings do not affect test correctness since assertions happen
    before teardown.
    """
    warnings.filterwarnings("ignore", message=".*no such table.*")
    warnings.filterwarnings("ignore", message=".*database is locked.*")
    warnings.filterwarnings("ignore", category=pytest.PytestUnhandledThreadExceptionWarning)

    backend = getattr(request, "param", "sqlite")

    if backend == "postgres":
        import psycopg

        pg_url = os.environ["DATABASE_URL"]
        # Fresh schema per test: drop and recreate the public schema.
        with psycopg.connect(pg_url, autocommit=True) as c:
            c.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
        monkeypatch.setattr("app.config.DATABASE_URL", pg_url)
        monkeypatch.setattr("app.config.SYMLINK_DIR", str(tmp_path / "project_links"))

        from app.database import init_db, seed_predefined_triggers

        init_db()
        seed_predefined_triggers()
        yield pg_url
        return

    # SQLite path — the original zero-config default, unchanged.
    monkeypatch.setattr("app.config.DATABASE_URL", "")
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
