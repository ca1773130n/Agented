"""v0.7.8: refresh_stale_model_caches_job — daily background refresh."""

from unittest.mock import patch

from app_litestar.lifecycle import refresh_stale_model_caches_job


def test_no_stale_rows_no_refresh_calls():
    with (
        patch(
            "app.services.model_cache_service.list_stale", return_value=[]
        ) as list_stale_mock,
        patch("app.services.model_cache_service.refresh") as refresh_mock,
    ):
        refresh_stale_model_caches_job()
        list_stale_mock.assert_called_once_with(grace_seconds=86400)
        refresh_mock.assert_not_called()


def test_refreshes_each_stale_entry():
    stale_rows = [
        {"backend_kind": "codex", "auth_method": "api_key"},
        {"backend_kind": "claude", "auth_method": "chatgpt"},
    ]
    with (
        patch(
            "app.services.model_cache_service.list_stale", return_value=stale_rows
        ),
        patch("app.services.model_cache_service.refresh") as refresh_mock,
    ):
        refresh_stale_model_caches_job()
    assert refresh_mock.call_count == 2
    refresh_mock.assert_any_call("codex", "api_key")
    refresh_mock.assert_any_call("claude", "chatgpt")


def test_one_failing_refresh_does_not_block_others():
    stale_rows = [
        {"backend_kind": "codex", "auth_method": "api_key"},
        {"backend_kind": "claude", "auth_method": "chatgpt"},
    ]

    def side_effect(backend_kind, auth_method):
        if backend_kind == "codex":
            raise RuntimeError("subprocess died")
        return {"ok": True}

    with (
        patch(
            "app.services.model_cache_service.list_stale", return_value=stale_rows
        ),
        patch(
            "app.services.model_cache_service.refresh", side_effect=side_effect
        ) as refresh_mock,
    ):
        refresh_stale_model_caches_job()
    assert refresh_mock.call_count == 2


def test_list_stale_failure_is_swallowed():
    with patch(
        "app.services.model_cache_service.list_stale",
        side_effect=RuntimeError("db down"),
    ):
        # Must not raise.
        refresh_stale_model_caches_job()
