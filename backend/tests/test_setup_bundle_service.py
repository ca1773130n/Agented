"""SetupBundleService: bundled harness plugins + self-healing CLI install.

Covers the v0.6 changes: Tesserae/GRD/HarnessSync are always bundled, and the
per-account CLI plugin install retries on later boots until a Claude account
exists (separate ``cli_plugins_installed`` flag, decoupled from
``bundle_installed``).
"""

from app.database import get_setting, set_setting
from app.services.setup_service import (
    BUNDLE_HARNESS_CLI_PLUGINS,
    BUNDLE_PLUGINS,
    SetupBundleService,
)


class _SyncThread:
    """Drop-in for threading.Thread that runs the target synchronously so the
    background install logic is testable without real concurrency."""

    def __init__(self, target=None, daemon=None, **kwargs):
        self._target = target

    def start(self):
        if self._target:
            self._target()


def test_bundle_includes_three_harness_plugins():
    names = {p["remote_name"] for p in BUNDLE_PLUGINS}
    assert {"grd", "tesserae", "harness-sync"} <= names
    assert set(BUNDLE_HARNESS_CLI_PLUGINS) == {"grd", "tesserae", "harness-sync"}


def test_maybe_schedule_skips_when_already_installed(isolated_db, monkeypatch):
    set_setting("cli_plugins_installed", "true")
    constructed = []
    monkeypatch.setattr(
        "threading.Thread",
        lambda *a, **k: constructed.append(1) or _SyncThread(*a, **k),
    )
    assert SetupBundleService._maybe_schedule_cli_install() is False
    assert constructed == []  # nothing scheduled


def test_maybe_schedule_sets_flag_on_success(isolated_db, monkeypatch):
    monkeypatch.setattr("threading.Thread", _SyncThread)
    monkeypatch.setattr(
        SetupBundleService,
        "_install_cli_plugins_all_accounts",
        staticmethod(lambda: {"accounts": 1, "results": [{"installed": ["grd@..."]}]}),
    )
    assert SetupBundleService._maybe_schedule_cli_install() is True
    assert get_setting("cli_plugins_installed") == "true"


def test_maybe_schedule_keeps_retrying_when_no_accounts(isolated_db, monkeypatch):
    monkeypatch.setattr("threading.Thread", _SyncThread)
    monkeypatch.setattr(
        SetupBundleService,
        "_install_cli_plugins_all_accounts",
        staticmethod(lambda: {"accounts": 0, "installed": []}),
    )
    # Scheduled, ran, but found no Claude account → flag stays unset so the
    # next boot retries (the bug: CLI plugins never installed after onboarding).
    assert SetupBundleService._maybe_schedule_cli_install() is True
    assert get_setting("cli_plugins_installed") != "true"


def test_install_cli_plugins_no_accounts_returns_zero(isolated_db):
    # Real guard, empty DB: no Claude accounts → accounts=0, nothing shelled out.
    res = SetupBundleService._install_cli_plugins_all_accounts()
    assert res["accounts"] == 0


def test_install_cli_plugins_env_is_scoped(isolated_db, monkeypatch):
    """The `claude plugins install` subprocess must NOT inherit the full
    operator/CI process env (remote-code surface). It gets a scoped env:
    PATH + the per-account CLAUDE_CONFIG_DIR (plus the fork-safety toggle),
    but never arbitrary secrets like AWS_SECRET_ACCESS_KEY."""
    import app.services.setup_service as setup_mod

    # Plant a secret that must NOT leak to the installer subprocess.
    monkeypatch.setenv("AGENTED_PLANTED_SECRET", "leak-me-not")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "super-secret")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    monkeypatch.setattr(
        "app.db.backends.get_backend_accounts",
        lambda backend_id: [{"account_name": "acct", "config_path": "/tmp/claude-acct-config"}],
    )

    captured_envs = []

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(cmd, env=None, **kwargs):
        captured_envs.append(env or {})
        return _Result()

    monkeypatch.setattr(setup_mod.subprocess, "run", _fake_run)

    SetupBundleService._install_cli_plugins_all_accounts()

    assert captured_envs, "expected subprocess.run to be invoked"
    for env in captured_envs:
        # Secrets from the parent process are NOT handed to the installer.
        assert "AGENTED_PLANTED_SECRET" not in env
        assert "AWS_SECRET_ACCESS_KEY" not in env
        # But the install still has what it genuinely needs.
        assert env.get("PATH") == "/usr/bin:/bin"
        assert env.get("CLAUDE_CONFIG_DIR") == "/tmp/claude-acct-config"
