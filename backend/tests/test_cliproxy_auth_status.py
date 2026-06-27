"""CLIProxy auth-status derivation + keepalive job.

The access token auto-refreshes from the refresh token ON USE, so the state
ladder is: ok → expiring (within window) → expired (past, still refreshable) →
needs_relogin (refresh token dead). gemini tracks no expiry → always ok.
"""

from datetime import datetime, timedelta, timezone

from app.services import cliproxy_manager as cm
from app.services.cliproxy_manager import CLIProxyManager, _auth_state, _redact_email


def test_redact_email():
    assert _redact_email("ca1773130n@gmail.com") == "c***@gmail.com"
    assert _redact_email("") == "<none>"
    assert _redact_email(None) == "<none>"
    assert _redact_email("nodomain") == "<none>"


NOW = datetime(2026, 6, 27, 12, 0, 0, tzinfo=timezone.utc)


def _iso(delta_seconds: float) -> str:
    return (NOW + timedelta(seconds=delta_seconds)).isoformat()


def test_auth_state_ladder():
    assert _auth_state({}, now=NOW, healthy=False) == "unreachable"
    assert _auth_state({"disabled": True}, now=NOW, healthy=True) == "disabled"
    assert _auth_state({"expired": None}, now=NOW, healthy=True) == "ok"  # gemini
    assert _auth_state({"expired": _iso(3600)}, now=NOW, healthy=True) == "ok"
    assert _auth_state({"expired": _iso(600)}, now=NOW, healthy=True) == "expiring"
    assert _auth_state({"expired": _iso(-600)}, now=NOW, healthy=True) == "expired"
    # 9 days past expiry → dead refresh token → needs interactive re-login.
    assert _auth_state({"expired": _iso(-9 * 86400)}, now=NOW, healthy=True) == "needs_relogin"
    assert _auth_state({"expired": "not-a-date"}, now=NOW, healthy=True) == "unknown"


def test_auth_status_summary_worst_first(monkeypatch):
    monkeypatch.setattr(CLIProxyManager, "is_healthy", classmethod(lambda cls: True))
    monkeypatch.setattr(
        CLIProxyManager,
        "list_accounts",
        classmethod(
            lambda cls: [
                {"email": "ok@x", "type": "gemini", "expired": None},
                {"email": "fresh@x", "type": "claude", "expired": _iso(99999)},
                {"email": "dead@x", "type": "codex", "expired": _iso(-9 * 86400)},
            ]
        ),
    )
    st = CLIProxyManager.auth_status()
    assert st["available"] is True
    assert st["summary"]["worst_state"] == "needs_relogin"  # worst wins the badge
    assert st["summary"]["total"] == 3
    assert {a["email"]: a["auth_state"] for a in st["accounts"]}["dead@x"] == "needs_relogin"


def test_keepalive_job_probes_when_expiring_and_flags_relogin(monkeypatch):
    monkeypatch.setattr(CLIProxyManager, "is_healthy", classmethod(lambda cls: True))
    monkeypatch.setattr(
        CLIProxyManager,
        "list_accounts",
        classmethod(
            lambda cls: [
                {"email": "soon@x", "type": "claude", "expired": _iso(600)},  # expiring
                {"email": "dead@x", "type": "codex", "expired": _iso(-9 * 86400)},
            ]
        ),
    )
    probed_flag = {"called": False}

    def fake_probe(cls):
        probed_flag["called"] = True
        return True

    monkeypatch.setattr(CLIProxyManager, "keepalive_probe", classmethod(fake_probe))
    # Pin "now" so the expiring account is genuinely within the window.
    real_dt = cm.datetime

    class _DT(real_dt):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(cm, "datetime", _DT)

    res = CLIProxyManager.keepalive_job()
    assert probed_flag["called"] is True  # expiring → probe fired
    assert res["probed"] is True
    assert [r["email"] for r in res["needs_relogin"]] == ["dead@x"]


def test_keepalive_job_noop_when_proxy_down(monkeypatch):
    monkeypatch.setattr(CLIProxyManager, "is_healthy", classmethod(lambda cls: False))
    monkeypatch.setattr(CLIProxyManager, "list_accounts", classmethod(lambda cls: []))
    res = CLIProxyManager.keepalive_job()
    assert res == {"available": False, "probed": False, "needs_relogin": []}
