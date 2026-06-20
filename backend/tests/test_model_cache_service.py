"""v0.7.8: model_cache_service — get/refresh/invalidate/list_stale."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.db.connection import get_connection
from app.services import model_cache_service


@pytest.fixture
def mock_discover():
    """Replace ModelDiscoveryService._discover_with_source with a controllable
    mock. The fixture exposes the underlying ``return_value``/``side_effect``
    interface tests have used since v0.7.8 (a bare list[str]) and adapts it
    into the new ``(models, source)`` tuple under the hood.
    """
    with patch("app.services.model_cache_service.ModelDiscoveryService._discover_with_source") as m:

        class _Adapter:
            """Maintains the legacy ``return_value`` / ``side_effect`` API
            (a bare list) while feeding ``_discover_with_source`` a tuple."""

            def __init__(self, mock):
                self._mock = mock
                self._call_count = 0

            @property
            def call_count(self):
                return self._mock.call_count

            @property
            def return_value(self):
                rv = self._mock.return_value
                return rv[0] if isinstance(rv, tuple) else rv

            @return_value.setter
            def return_value(self, value):
                self._mock.return_value = (value, "mixed")

            @property
            def side_effect(self):
                return self._mock.side_effect

            @side_effect.setter
            def side_effect(self, value):
                self._mock.side_effect = value

        yield _Adapter(m)


def test_first_call_populates_cache_and_returns_models(isolated_db, mock_discover):
    mock_discover.return_value = ["gpt-5", "gpt-5.1", "gpt-5.1-codex-mini"]
    models, meta = model_cache_service.get_models(backend_kind="codex", auth_method="api_key")
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
    models, meta = model_cache_service.get_models(backend_kind="codex", auth_method="api_key")
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
    models, meta = model_cache_service.get_models(backend_kind="codex", auth_method="api_key")
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
            "UPDATE model_discovery_cache SET expires_at = ? WHERE backend_kind = ?",
            (past, "codex"),
        )
        conn.commit()
    stale = model_cache_service.list_stale()
    assert len(stale) == 1
    assert stale[0]["backend_kind"] == "codex"


def test_filter_applied_codex_oauth_drops_gpt51(isolated_db, mock_discover):
    mock_discover.return_value = ["gpt-5", "gpt-5.1", "gpt-5.1-codex-mini"]
    models, _meta = model_cache_service.get_models(backend_kind="codex", auth_method="chatgpt")
    assert "gpt-5.1" not in models
    assert "gpt-5.1-codex-mini" not in models
    assert "gpt-5" in models


def test_discovery_failure_records_error_message_and_empty_list(isolated_db, mock_discover):
    mock_discover.side_effect = RuntimeError("subprocess died")
    models, meta = model_cache_service.get_models(backend_kind="codex", auth_method="api_key")
    assert models == []
    assert meta["error_message"] is not None
    assert "RuntimeError" in meta["error_message"]
    assert "subprocess died" in meta["error_message"]


def test_failed_discovery_uses_short_ttl(isolated_db, mock_discover):
    """A subprocess failure should expire in ~1 hour, NOT 7 days."""
    mock_discover.side_effect = RuntimeError("subprocess died")
    model_cache_service.get_models(backend_kind="codex", auth_method="api_key")
    with get_connection() as conn:
        row = conn.execute(
            "SELECT discovered_at, expires_at FROM model_discovery_cache "
            "WHERE backend_kind = ? AND auth_method = ?",
            ("codex", "api_key"),
        ).fetchone()
    assert row is not None
    discovered_at = datetime.fromisoformat(row["discovered_at"])
    expires_at = datetime.fromisoformat(row["expires_at"])
    delta = expires_at - discovered_at
    # Should be exactly ERROR_TTL_SECONDS (1 hour), not 7 days.
    assert delta == timedelta(seconds=model_cache_service.ERROR_TTL_SECONDS)
    assert delta < timedelta(days=1)


def test_empty_discovery_uses_short_ttl(isolated_db, mock_discover):
    """Empty discovery (no models found) should also use the short TTL."""
    mock_discover.return_value = []
    model_cache_service.get_models(backend_kind="codex", auth_method="api_key")
    with get_connection() as conn:
        row = conn.execute(
            "SELECT discovered_at, expires_at FROM model_discovery_cache "
            "WHERE backend_kind = ? AND auth_method = ?",
            ("codex", "api_key"),
        ).fetchone()
    assert row is not None
    discovered_at = datetime.fromisoformat(row["discovered_at"])
    expires_at = datetime.fromisoformat(row["expires_at"])
    delta = expires_at - discovered_at
    assert delta == timedelta(seconds=model_cache_service.ERROR_TTL_SECONDS)
    assert delta < timedelta(days=1)


def test_refresh_returns_models_alongside_metadata(isolated_db, mock_discover):
    """refresh() should include the filtered model list in its response dict."""
    mock_discover.return_value = ["gpt-5", "gpt-5.1"]
    result = model_cache_service.refresh("codex", "api_key")
    assert "models" in result
    assert result["models"] == ["gpt-5", "gpt-5.1"]
    assert result["backend_kind"] == "codex"
    assert result["auth_method"] == "api_key"
    assert result["fresh"] is True


def test_successful_discovery_uses_full_ttl(isolated_db, mock_discover):
    """Successful discovery keeps the configured 7-day TTL."""
    mock_discover.return_value = ["gpt-5"]
    model_cache_service.get_models(backend_kind="codex", auth_method="api_key")
    with get_connection() as conn:
        row = conn.execute(
            "SELECT discovered_at, expires_at FROM model_discovery_cache "
            "WHERE backend_kind = ? AND auth_method = ?",
            ("codex", "api_key"),
        ).fetchone()
    assert row is not None
    discovered_at = datetime.fromisoformat(row["discovered_at"])
    expires_at = datetime.fromisoformat(row["expires_at"])
    delta = expires_at - discovered_at
    assert delta == timedelta(days=7)


# v0.7.9: discovery_method now reflects the actual source, not "mixed".


def test_sidecar_path_records_method_sidecar(isolated_db):
    """When the sidecar returns models, discovery_method == "sidecar"."""
    with patch(
        "app.services.model_cache_service.ModelDiscoveryService._discover_with_source",
        return_value=(["claude-opus-4-7", "claude-sonnet-4-7"], "sidecar"),
    ):
        models, meta = model_cache_service.get_models(
            backend_kind="claude", auth_method="cli_browser", force_refresh=True
        )
    assert "claude-opus-4-7" in models
    assert meta["discovery_method"] == "sidecar"


def test_fallback_to_local_records_method_local(isolated_db):
    """When sidecar returns nothing and local stats-cache returns models,
    discovery_method == "local"."""
    with patch(
        "app.services.model_cache_service.ModelDiscoveryService._discover_with_source",
        return_value=(["claude-opus-4-6"], "local"),
    ):
        models, meta = model_cache_service.get_models(
            backend_kind="claude", auth_method="cli_browser", force_refresh=True
        )
    assert models == ["claude-opus-4-6"]
    assert meta["discovery_method"] == "local"


def test_empty_discovery_records_method_empty(isolated_db):
    """No models found → discovery_method == "empty"."""
    with patch(
        "app.services.model_cache_service.ModelDiscoveryService._discover_with_source",
        return_value=([], "empty"),
    ):
        _models, meta = model_cache_service.get_models(
            backend_kind="claude", auth_method="cli_browser", force_refresh=True
        )
    assert meta["discovery_method"] == "empty"
