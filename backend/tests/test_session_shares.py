"""Tests for live-share tokens + two-client attach (Phase 25, 25-01).

Also covers the Codex security fixes: mint ownership gate (#1), token hashing
(#6), and co-drive CSRF / cross-site protection (#5).
"""

import hashlib
import threading
import time
from collections import deque
from datetime import datetime
from types import SimpleNamespace

import pytest
from litestar.exceptions import PermissionDeniedException

from app.db.connection import get_connection
from app.db.session_shares import (
    _hash_token,
    list_shares_for_session,
    mint_share_token,
    resolve_share_token,
    revoke_share_token,
)
from app.services.project_session_manager import ProjectSessionManager, SessionInfo
from app.services.session_sharing_service import SessionSharingService
from app_litestar.auth import Caller
from app_litestar.routes.session_shares import co_drive_send, mint_share, revoke_share


@pytest.fixture(autouse=True)
def _reset_psm():
    ProjectSessionManager._sessions.clear()
    ProjectSessionManager._subscribers.clear()
    yield
    ProjectSessionManager._sessions.clear()
    ProjectSessionManager._subscribers.clear()


def _active_session(session_id="psess-share1"):
    from unittest.mock import MagicMock

    now = datetime.now()
    si = SessionInfo(
        session_id=session_id,
        pid=1234,
        pgid=1234,
        master_fd=99,
        ring_buffer=deque(maxlen=10000),
        reader_thread=MagicMock(spec=threading.Thread),
        status="active",
        created_at=now,
        last_activity_at=now,
    )
    ProjectSessionManager._sessions[session_id] = si
    return si


# ---------------------------------------------------------------------------
# mint / resolve / expire / revoke round-trip (Level 1)
# ---------------------------------------------------------------------------


class TestTokenRoundTrip:
    def test_mint_resolve_returns_scope(self, isolated_db):
        token = mint_share_token("psess-abc", scope="chat", created_by="u1")
        row = resolve_share_token(token)
        assert row is not None
        assert row["session_id"] == "psess-abc"
        assert row["scope"] == "chat"
        assert row["created_by"] == "u1"

    def test_expired_token_resolves_none(self, isolated_db):
        token = mint_share_token("psess-abc", scope="read", ttl_seconds=-5)
        assert resolve_share_token(token) is None

    def test_revoked_token_resolves_none(self, isolated_db):
        token = mint_share_token("psess-abc", scope="read")
        assert resolve_share_token(token) is not None
        assert revoke_share_token(token) is True
        assert resolve_share_token(token) is None
        # A second revoke is a no-op (already revoked).
        assert revoke_share_token(token) is False

    def test_unknown_token_resolves_none(self, isolated_db):
        assert resolve_share_token("does-not-exist") is None
        assert resolve_share_token("") is None

    def test_invalid_scope_rejected(self, isolated_db):
        with pytest.raises(ValueError):
            mint_share_token("psess-abc", scope="admin")

    def test_list_returns_minted_rows(self, isolated_db):
        mint_share_token("psess-list", scope="read")
        mint_share_token("psess-list", scope="chat")
        rows = list_shares_for_session("psess-list")
        assert len(rows) == 2
        assert {r["scope"] for r in rows} == {"read", "chat"}


# ---------------------------------------------------------------------------
# can_attach — token bound to exactly one session
# ---------------------------------------------------------------------------


class TestCanAttach:
    def test_can_attach_returns_scope_for_bound_session(self, isolated_db):
        token = mint_share_token("psess-bound", scope="chat")
        assert SessionSharingService.can_attach(token, "psess-bound") == "chat"

    def test_can_attach_rejects_wrong_session(self, isolated_db):
        token = mint_share_token("psess-bound", scope="chat")
        # A token minted for one session must not attach a DIFFERENT session.
        assert SessionSharingService.can_attach(token, "psess-other") is None

    def test_can_attach_rejects_revoked(self, isolated_db):
        token = mint_share_token("psess-bound", scope="read")
        revoke_share_token(token)
        assert SessionSharingService.can_attach(token, "psess-bound") is None


# ---------------------------------------------------------------------------
# Two-client attach — a second (token) subscriber receives a broadcast delta
# over the EXISTING fan-out (Level 2 proxy, criterion 1)
# ---------------------------------------------------------------------------


class TestTwoClientAttach:
    def test_second_subscriber_receives_broadcast(self, isolated_db):
        si = _active_session("psess-live1")
        token = mint_share_token(si.session_id, scope="chat")
        # The teammate's token is bound to the live session.
        assert SessionSharingService.can_attach(token, si.session_id) == "chat"

        received: list[str] = []

        def _teammate():
            # Attach via the SAME generator the token route joins — one more Queue
            # in _subscribers, no second fan-out. Stop after the first live event.
            for event in ProjectSessionManager.subscribe(si.session_id):
                received.append(event)
                break

        t = threading.Thread(target=_teammate, daemon=True)
        t.start()

        # Wait for the teammate's queue to register before broadcasting.
        deadline = time.time() + 5
        while time.time() < deadline and not ProjectSessionManager._subscribers.get(si.session_id):
            time.sleep(0.01)
        assert ProjectSessionManager._subscribers.get(si.session_id), "subscriber never registered"

        ProjectSessionManager._broadcast(
            si.session_id, "output", {"line": "hello teammate", "timestamp": "t"}
        )
        t.join(timeout=5)

        assert any("hello teammate" in ev for ev in received), received


# ---------------------------------------------------------------------------
# #6 — the stored column is a sha256 hash, not the raw token (no timing/enum)
# ---------------------------------------------------------------------------


class TestTokenHashing:
    def test_stored_column_is_hash_not_raw(self, isolated_db):
        token = mint_share_token("psess-hash", scope="read")
        with get_connection() as conn:
            rows = [r[0] for r in conn.execute("SELECT token FROM session_share_tokens").fetchall()]
        assert token not in rows, "raw token must NOT be persisted"
        assert hashlib.sha256(token.encode()).hexdigest() in rows
        assert _hash_token(token) in rows

    def test_lookup_by_correct_token_succeeds(self, isolated_db):
        token = mint_share_token("psess-hash", scope="chat")
        row = resolve_share_token(token)
        assert row is not None and row["scope"] == "chat"

    def test_lookup_by_wrong_token_fails(self, isolated_db):
        mint_share_token("psess-hash", scope="chat")
        assert resolve_share_token("not-the-token") is None

    def test_revoke_by_correct_token(self, isolated_db):
        token = mint_share_token("psess-hash", scope="read")
        assert revoke_share_token(token) is True
        assert resolve_share_token(token) is None


# ---------------------------------------------------------------------------
# #1 — mint requires session ownership (or admin); non-owner → 403
# ---------------------------------------------------------------------------


def _seed_owned_session_row(session_id, owner):
    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO projects (id, name) VALUES ('proj-mint', 'M')")
        cols = "id, project_id, status"
        vals = [session_id, "proj-mint", "active"]
        if owner is not None:
            cols += ", created_by"
            vals.append(owner)
        conn.execute(
            f"INSERT INTO project_sessions ({cols}) VALUES ({', '.join(['?'] * len(vals))})",
            vals,
        )
        conn.commit()


def _caller(user_id, role="member"):
    return Caller(api_key="k", role=role, user_id=user_id, auth_method="api_key")


class TestMintOwnershipGate:
    def test_owner_mints_ok(self, isolated_db):
        _seed_owned_session_row("psess-mine", owner="owner-1")
        result = mint_share.fn("proj-mint", "psess-mine", {"scope": "read"}, _caller("owner-1"))
        assert result["token"]
        assert result["scope"] == "read"

    def test_non_owner_mint_forbidden(self, isolated_db):
        _seed_owned_session_row("psess-mine", owner="owner-1")
        with pytest.raises(PermissionDeniedException):
            mint_share.fn("proj-mint", "psess-mine", {"scope": "chat"}, _caller("intruder"))

    def test_admin_can_mint_any(self, isolated_db):
        _seed_owned_session_row("psess-mine", owner="owner-1")
        result = mint_share.fn(
            "proj-mint", "psess-mine", {"scope": "read"}, _caller("root", role="admin")
        )
        assert result["token"]

    def test_unowned_session_mint_forbidden_for_non_admin(self, isolated_db):
        # Fail CLOSED: an unattributed (NULL created_by) session cannot be shared
        # by a non-admin, even one that "knows" the session id.
        _seed_owned_session_row("psess-orphan", owner=None)
        with pytest.raises(PermissionDeniedException):
            mint_share.fn("proj-mint", "psess-orphan", {"scope": "read"}, _caller("anyone"))


# ---------------------------------------------------------------------------
# ITEM 7 — revoke is scoped to the session at the DB layer (no cross-session
# revoke even if the higher-level owner check were bypassed)
# ---------------------------------------------------------------------------


class TestRevokeScoping:
    def test_revoke_wrong_session_is_noop(self, isolated_db):
        token = mint_share_token("psess-A", scope="read")
        # A revoke scoped to a DIFFERENT session must NOT flip this token.
        assert revoke_share_token(token, session_id="psess-OTHER") is False
        assert resolve_share_token(token) is not None  # still live
        # The token's own session revokes it.
        assert revoke_share_token(token, session_id="psess-A") is True
        assert resolve_share_token(token) is None

    def test_revoke_without_session_still_works(self, isolated_db):
        # Back-compat: internal/test callers may revoke by token alone.
        token = mint_share_token("psess-A", scope="read")
        assert revoke_share_token(token) is True
        assert resolve_share_token(token) is None


# ---------------------------------------------------------------------------
# ITEM 7 — revoke_share route requires session ownership (or admin); a non-owner
# who merely knows a token can no longer revoke it cross-session
# ---------------------------------------------------------------------------


class TestRevokeOwnershipGate:
    def test_owner_revokes_ok(self, isolated_db):
        _seed_owned_session_row("psess-mine", owner="owner-1")
        token = mint_share_token("psess-mine", scope="read", created_by="owner-1")
        result = revoke_share.fn("proj-mint", "psess-mine", token, _caller("owner-1"))
        assert result == {"revoked": True}
        assert resolve_share_token(token) is None

    def test_non_owner_revoke_forbidden_and_share_still_resolves(self, isolated_db):
        _seed_owned_session_row("psess-mine", owner="owner-1")
        token = mint_share_token("psess-mine", scope="read", created_by="owner-1")
        with pytest.raises(PermissionDeniedException):
            revoke_share.fn("proj-mint", "psess-mine", token, _caller("intruder"))
        # The intruder did NOT revoke it — the share is still live.
        assert resolve_share_token(token) is not None

    def test_admin_revokes_any(self, isolated_db):
        _seed_owned_session_row("psess-mine", owner="owner-1")
        token = mint_share_token("psess-mine", scope="read", created_by="owner-1")
        result = revoke_share.fn("proj-mint", "psess-mine", token, _caller("root", role="admin"))
        assert result == {"revoked": True}

    def test_unowned_session_revoke_forbidden_for_non_admin(self, isolated_db):
        # Fail CLOSED: an unattributed (NULL created_by) session's token cannot be
        # revoked by a non-admin, even one that "knows" the token.
        _seed_owned_session_row("psess-orphan", owner=None)
        token = mint_share_token("psess-orphan", scope="read")
        with pytest.raises(PermissionDeniedException):
            revoke_share.fn("proj-mint", "psess-orphan", token, _caller("anyone"))
        assert resolve_share_token(token) is not None


# ---------------------------------------------------------------------------
# #5 — co-drive SEND requires the X-Share-Token header + rejects cross-site
# ---------------------------------------------------------------------------


def _req(headers=None):
    """A minimal request stub with case-insensitive header lookup."""
    low = {k.lower(): v for k, v in (headers or {}).items()}

    class _H:
        def get(self, key, default=None):
            return low.get(key.lower(), default)

    return SimpleNamespace(headers=_H())


class TestCoDriveCsrf:
    def test_token_only_in_url_rejected(self, isolated_db):
        # No X-Share-Token header (token only in the URL path) → rejected.
        token = mint_share_token("psess-csrf", scope="chat")
        with pytest.raises(PermissionDeniedException):
            co_drive_send.fn(token, {"text": "hi"}, _req())

    def test_wrong_header_token_rejected(self, isolated_db):
        token = mint_share_token("psess-csrf", scope="chat")
        with pytest.raises(PermissionDeniedException):
            co_drive_send.fn(token, {"text": "hi"}, _req({"X-Share-Token": "mismatch"}))

    def test_cross_site_origin_rejected(self, isolated_db):
        token = mint_share_token("psess-csrf", scope="chat")
        req = _req(
            {"X-Share-Token": token, "Origin": "https://evil.example", "Host": "agented.app"}
        )
        with pytest.raises(PermissionDeniedException):
            co_drive_send.fn(token, {"text": "hi"}, req)

    def test_same_origin_header_carrying_post_accepted(self, isolated_db, monkeypatch):
        token = mint_share_token("psess-csrf", scope="chat")
        # Stub co_drive so we isolate the CSRF gate (the accept path).
        monkeypatch.setattr(SessionSharingService, "co_drive", staticmethod(lambda *a, **k: True))
        req = _req({"X-Share-Token": token, "Origin": "https://agented.app", "Host": "agented.app"})
        result = co_drive_send.fn(token, {"text": "go"}, req)
        assert result["sent"] is True
