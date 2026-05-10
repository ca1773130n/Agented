"""Sidecar → backend_accounts mirror coverage.

The monitoring pipeline (rate-limit gauges, polling job, dashboard
status) all read from local ``backend_accounts``. Post-wave-80 that
table is empty until accounts are mirrored from the sidecar. The sync
service is the single seam that closes that gap; these tests pin its
contract:

* HTTP shape coming back from the sidecar gets mapped onto the local
  ``backend_accounts`` columns the monitoring code expects.
* Re-running the sync upserts in place (no duplicate rows).
* HTTP and auth failures degrade silently to 0 — monitoring callers
  rely on this so a sidecar outage doesn't break the polling loop.
"""

from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from app.services import sidecar_account_sync_service as svc


def _sample_payload() -> dict[str, Any]:
    return {
        "items": [
            {
                "id": "bkd-aaaaaaaaaaaa",
                "kind": "claude",
                "display_name": "Personal1",
                "status": "ready",
                "config": {
                    "email": "alice@example.com",
                    "config_path": "~/.claude-personal1",
                    "plan": "max",
                    "is_default": True,
                },
            },
            {
                "id": "bkd-bbbbbbbbbbbb",
                "kind": "codex",
                "display_name": "Codex-Pro",
                "status": "ready",
                "config": {
                    "email": "alice@example.com",
                    "config_path": "~/.codex",
                    "plan": "pro",
                    "is_default": False,
                },
            },
        ]
    }


class _FakeResp:
    def __init__(self, status: int, body: Any) -> None:
        self.status_code = status
        self._body = body

    def json(self) -> Any:
        return self._body


class _FakeClient:
    """Minimal httpx.Client stand-in used as a context manager."""

    def __init__(self, resp: _FakeResp | Exception) -> None:
        self._resp = resp

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def get(self, url: str, headers: dict[str, str] | None = None) -> _FakeResp:
        if isinstance(self._resp, Exception):
            raise self._resp
        return self._resp


def _patch_httpx(monkeypatch: pytest.MonkeyPatch, resp: _FakeResp | Exception) -> None:
    import httpx

    monkeypatch.setattr(httpx, "Client", lambda **_kw: _FakeClient(resp))


def _seed_admin_key(db_path: str, key: str = "test-admin-key") -> None:
    """Insert a row into user_roles so the sync resolver finds a key."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO user_roles (api_key, role) VALUES (?, 'admin')", (key,)
        )
        conn.commit()
    finally:
        conn.close()


def test_sync_inserts_sidecar_accounts(monkeypatch, isolated_db):
    _seed_admin_key(isolated_db)
    _patch_httpx(monkeypatch, _FakeResp(200, _sample_payload()))

    n = svc.sync_sidecar_accounts()
    assert n == 2

    conn = sqlite3.connect(isolated_db)
    rows = conn.execute(
        "SELECT backend_id, account_name, email, config_path, plan, is_default "
        "FROM backend_accounts ORDER BY backend_id, account_name"
    ).fetchall()
    assert rows == [
        ("backend-claude", "Personal1", "alice@example.com", "~/.claude-personal1", "max", 1),
        ("backend-codex", "Codex-Pro", "alice@example.com", "~/.codex", "pro", 0),
    ]


def test_sync_is_idempotent(monkeypatch, isolated_db):
    """Re-running the sync upserts in place — no duplicates."""
    _seed_admin_key(isolated_db)
    _patch_httpx(monkeypatch, _FakeResp(200, _sample_payload()))

    svc.sync_sidecar_accounts()
    svc.sync_sidecar_accounts()
    svc.sync_sidecar_accounts()

    conn = sqlite3.connect(isolated_db)
    count = conn.execute("SELECT COUNT(*) FROM backend_accounts").fetchone()[0]
    assert count == 2


def test_sync_updates_existing_rows_on_rename(monkeypatch, isolated_db):
    """Display-name change on the same config_path updates the existing row."""
    _seed_admin_key(isolated_db)
    _patch_httpx(monkeypatch, _FakeResp(200, _sample_payload()))
    svc.sync_sidecar_accounts()

    # Sidecar renames Personal1 → Primary; same config_path
    renamed = _sample_payload()
    renamed["items"][0]["display_name"] = "Primary"
    _patch_httpx(monkeypatch, _FakeResp(200, renamed))
    svc.sync_sidecar_accounts()

    conn = sqlite3.connect(isolated_db)
    names = sorted(
        r[0] for r in conn.execute("SELECT account_name FROM backend_accounts").fetchall()
    )
    assert names == ["Codex-Pro", "Primary"]


def test_sync_returns_zero_when_no_admin_key(monkeypatch, isolated_db):
    """No env key, no user_roles row → silent skip."""
    monkeypatch.delenv("AI_ACCOUNTS_API_KEY", raising=False)
    monkeypatch.delenv("AGENTED_API_KEY", raising=False)
    # don't seed user_roles

    # Should never even open the HTTP client.
    def _fail(**_kw):
        raise AssertionError("HTTP client must not be constructed without a key")

    import httpx

    monkeypatch.setattr(httpx, "Client", _fail)

    assert svc.sync_sidecar_accounts() == 0


def test_sync_returns_zero_on_http_error(monkeypatch, isolated_db):
    _seed_admin_key(isolated_db)
    import httpx

    _patch_httpx(monkeypatch, httpx.ConnectError("connection refused"))

    assert svc.sync_sidecar_accounts() == 0
    conn = sqlite3.connect(isolated_db)
    assert conn.execute("SELECT COUNT(*) FROM backend_accounts").fetchone()[0] == 0


def test_sync_returns_zero_on_non_200(monkeypatch, isolated_db):
    _seed_admin_key(isolated_db)
    _patch_httpx(monkeypatch, _FakeResp(401, {"error": "unauthorized"}))

    assert svc.sync_sidecar_accounts() == 0


def test_sync_skips_unknown_kinds(monkeypatch, isolated_db):
    """An unknown backend kind in the sidecar response is dropped silently."""
    _seed_admin_key(isolated_db)
    payload = {
        "items": [
            {
                "id": "bkd-future",
                "kind": "future-llm",
                "display_name": "Mystery",
                "status": "ready",
                "config": {},
            }
        ]
    }
    _patch_httpx(monkeypatch, _FakeResp(200, payload))

    assert svc.sync_sidecar_accounts() == 0
    conn = sqlite3.connect(isolated_db)
    assert conn.execute("SELECT COUNT(*) FROM backend_accounts").fetchone()[0] == 0


def test_sync_falls_back_when_display_name_missing(monkeypatch, isolated_db):
    """Sidecar id is a stable fallback when display_name is null."""
    _seed_admin_key(isolated_db)
    payload = {
        "items": [
            {
                "id": "bkd-noname",
                "kind": "claude",
                "display_name": None,
                "status": "ready",
                "config": {"config_path": "~/.claude-noname"},
            }
        ]
    }
    _patch_httpx(monkeypatch, _FakeResp(200, payload))

    assert svc.sync_sidecar_accounts() == 1
    conn = sqlite3.connect(isolated_db)
    name = conn.execute("SELECT account_name FROM backend_accounts").fetchone()[0]
    assert name == "bkd-noname"
