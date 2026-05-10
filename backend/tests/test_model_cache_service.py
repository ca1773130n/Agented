"""v0.7.8: model_cache_service — get/refresh/invalidate/list_stale."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.db.connection import get_connection
from app.services import model_cache_service


@pytest.fixture
def mock_discover():
    """Replace ModelDiscoveryService._discover_raw with a controllable mock."""
    with patch(
        "app.services.model_cache_service.ModelDiscoveryService._discover_raw"
    ) as m:
        yield m


def test_first_call_populates_cache_and_returns_models(isolated_db, mock_discover):
    mock_discover.return_value = ["gpt-5", "gpt-5.1", "gpt-5.1-codex-mini"]
    models, meta = model_cache_service.get_models(
        backend_kind="codex", auth_method="api_key"
    )
    assert models == ["gpt-5", "gpt-5.1", "gpt-5.1-codex-mini"]
    assert meta["fresh"] is True
    assert meta["backend_kind"] == "codex"
    assert meta["auth_method"] == "api_key"
    with get_connection() as conn:
        rows = list(conn.execute("SELECT * FROM model_discovery_cache"))
    assert len(rows) == 1


def test_second_call_within_ttl_returns_cache_no_redicovery(isolated_db, mock_discover):
    mock_discover.return_value = ["gpt-5"]
    model_cache_service.get_models(backend_kind="codex", auth_method="api_key")
    assert mock_discover.call_count == 1
    models, meta = model_cache_service.get_models(
        backend_kind="codex", auth_method="api_key"
    )
    assert models == ["gpt-5"]
    assert meta["fresh"] is False
    assert mock_discover.call_count == 1  # not re-called


def test_force_refresh_redicovers_even_within_ttl(isolated_db, mock_discover):
    mock_discover.return_value = ["gpt-5"]
    model_cache_service.get_models(backend_kind="codex", auth_method="api_key")
    mock_discover.return_value = ["gpt-5", "o1"]
    models, meta = model_cache_service.get_models(
        backend_kind="codex", auth_method="api_key", force_refresh=True
    )
    assert models == ["gpt-5", "o1"]
    assert meta["fresh"] is True
    assert mock_discover.call_count == 2


def test_expired_cache_redicovers(isolated_db, mock_discover):
    mock_discover.return_value = ["gpt-5"]
    model_cache_service.get_models(backend_kind="codex", auth_method="api_key")
    # Force-expire by rewriting expires_at to the past
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE model_discovery_cache SET expires_at = ? "
            "WHERE backend_kind = ? AND auth_method = ?",
            (past, "codex", "api_key"),
        )
        conn.commit()
    mock_discover.return_value = ["gpt-5", "o1"]
    models, meta = model_cache_service.get_models(
        backend_kind="codex", auth_method="api_key"
    )
    assert models == ["gpt-5", "o1"]
    assert meta["fresh"] is True
    assert mock_discover.call_count == 2


def test_invalidate_specific_auth(isolated_db, mock_discover):
    mock_discover.return_value = ["gpt-5"]
    model_cache_service.get_models(backend_kind="codex", auth_method="api_key")
    model_cache_service.get_models(backend_kind="codex", auth_method="chatgpt")
    deleted = model_cache_service.invalidate("codex", "api_key")
    assert deleted == 1
    with get_connection() as conn:
        rows = list(conn.execute("SELECT auth_method FROM model_discovery_cache"))
    assert {r["auth_method"] for r in rows} == {"chatgpt"}


def test_invalidate_all_auth_methods(isolated_db, mock_discover):
    mock_discover.return_value = ["gpt-5"]
    model_cache_service.get_models(backend_kind="codex", auth_method="api_key")
    model_cache_service.get_models(backend_kind="codex", auth_method="chatgpt")
    deleted = model_cache_service.invalidate("codex")
    assert deleted == 2
    with get_connection() as conn:
        rows = list(conn.execute("SELECT * FROM model_discovery_cache"))
    assert rows == []


def test_list_stale_returns_only_expired(isolated_db, mock_discover):
    mock_discover.return_value = ["gpt-5"]
    model_cache_service.get_models(backend_kind="codex", auth_method="api_key")
    model_cache_service.get_models(backend_kind="claude", auth_method="api_key")
    # Expire only the codex row
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE model_discovery_cache SET expires_at = ? "
            "WHERE backend_kind = ?",
            (past, "codex"),
        )
        conn.commit()
    stale = model_cache_service.list_stale()
    assert len(stale) == 1
    assert stale[0]["backend_kind"] == "codex"


def test_filter_applied_codex_oauth_drops_gpt51(isolated_db, mock_discover):
    mock_discover.return_value = ["gpt-5", "gpt-5.1", "gpt-5.1-codex-mini"]
    models, _meta = model_cache_service.get_models(
        backend_kind="codex", auth_method="chatgpt"
    )
    assert "gpt-5.1" not in models
    assert "gpt-5.1-codex-mini" not in models
    assert "gpt-5" in models


def test_discovery_failure_records_error_message_and_empty_list(
    isolated_db, mock_discover
):
    mock_discover.side_effect = RuntimeError("subprocess died")
    models, meta = model_cache_service.get_models(
        backend_kind="codex", auth_method="api_key"
    )
    assert models == []
    assert meta["error_message"] is not None
    assert "RuntimeError" in meta["error_message"]
    assert "subprocess died" in meta["error_message"]
