"""CLIProxyManager login now DELEGATES to ai-accounts (single source of truth for
the Antigravity-aware login flow). These checks pin the seam: the Agented "gemini"
backend maps to ai-accounts' "antigravity" login, the credential targets the global
auth dir, and the async result is bridged to the sync ``Popen`` API callers expect."""

from __future__ import annotations

import ai_accounts_core.cliproxy.manager as aam

from app.services.cliproxy_manager import _GLOBAL_AUTH_DIR, CLIProxyManager


def test_gemini_backend_logs_in_via_antigravity(monkeypatch):
    calls = []

    async def fake_start(kind, cfg=None):
        calls.append((kind, str(cfg)))
        return None, aam.CliproxyLoginInfo(oauth_url="https://accounts.google.com/o/oauth2/v2/auth")

    monkeypatch.setattr(aam, "start_cliproxy_login", fake_start)
    monkeypatch.setattr(CLIProxyManager, "_kill_stale_login_processes", classmethod(lambda cls: None))

    proc, info = CLIProxyManager.start_login(backend_type="gemini")

    # The obsolete `-login` is gone: "gemini" → Antigravity, cred to the global dir.
    assert calls == [("antigravity", str(_GLOBAL_AUTH_DIR))]
    assert info["url"].startswith("https://accounts.google.com")
    # No live proc (None) → no-op sync proc that won't blow up callers.
    assert proc.wait(timeout=1) == 0
    proc.kill()


def test_unknown_backend_rejected(monkeypatch):
    monkeypatch.setattr(CLIProxyManager, "_kill_stale_login_processes", classmethod(lambda cls: None))
    try:
        CLIProxyManager.start_login(backend_type="bogus")
    except ValueError as exc:
        assert "bogus" in str(exc)
    else:
        raise AssertionError("expected ValueError for unsupported backend")


def test_forward_callback_delegates(monkeypatch):
    async def fake_forward(url):
        return {"status": "completed", "url": url}

    monkeypatch.setattr(aam, "forward_cliproxy_callback", fake_forward)
    out = CLIProxyManager.forward_callback("http://localhost:51121/oauth-callback?code=x&state=y")
    assert out["status"] == "completed"
