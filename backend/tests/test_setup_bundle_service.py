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
