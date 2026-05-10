"""v0.7.13: tests for CLIProxyManager.ensure_min_version + upgrade.

Covers:
- _version_lt semver-ish ordering
- detect_version parses `cliproxyapi -V` output
- ensure_min_version is a no-op when current >= target
- ensure_min_version triggers upgrade when current < target
- ensure_min_version returns False when upgrade fails
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.services.cliproxy_manager import CLIProxyManager


# ---------------------------------------------------------------------------
# _version_lt
# ---------------------------------------------------------------------------


class TestVersionLt:
    def test_old_is_less_than_new(self):
        assert CLIProxyManager._version_lt("6.8.30", "7.0.0") is True

    def test_equal_is_not_less_than(self):
        assert CLIProxyManager._version_lt("7.0.0", "7.0.0") is False

    def test_newer_patch_is_not_less_than(self):
        assert CLIProxyManager._version_lt("7.0.1", "7.0.0") is False

    def test_newer_major_is_not_less_than(self):
        assert CLIProxyManager._version_lt("8.0.0", "7.0.0") is False

    def test_pads_short_versions(self):
        # "7" should be treated as 7.0.0, not less than 7.0.0
        assert CLIProxyManager._version_lt("7", "7.0.0") is False
        # "6" < "7.0.0"
        assert CLIProxyManager._version_lt("6", "7.0.0") is True


# ---------------------------------------------------------------------------
# detect_version
# ---------------------------------------------------------------------------


class TestDetectVersion:
    def test_returns_none_when_binary_missing(self):
        with patch("app.services.cliproxy_manager.shutil.which", return_value=None):
            assert CLIProxyManager.detect_version() is None

    def test_parses_version_from_stdout(self):
        mock_result = MagicMock()
        mock_result.stdout = "CLIProxyAPI Version: 6.8.30, Commit: abc123\n"
        mock_result.stderr = ""
        with (
            patch(
                "app.services.cliproxy_manager.shutil.which",
                return_value="/usr/local/bin/cliproxyapi",
            ),
            patch(
                "app.services.cliproxy_manager.subprocess.run",
                return_value=mock_result,
            ),
        ):
            assert CLIProxyManager.detect_version() == "6.8.30"

    def test_parses_version_from_stderr(self):
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "CLIProxyAPI Version: 7.0.0\n"
        with (
            patch(
                "app.services.cliproxy_manager.shutil.which",
                return_value="/usr/local/bin/cliproxyapi",
            ),
            patch(
                "app.services.cliproxy_manager.subprocess.run",
                return_value=mock_result,
            ),
        ):
            assert CLIProxyManager.detect_version() == "7.0.0"

    def test_returns_none_on_unparseable_output(self):
        mock_result = MagicMock()
        mock_result.stdout = "garbage output\n"
        mock_result.stderr = ""
        with (
            patch(
                "app.services.cliproxy_manager.shutil.which",
                return_value="/usr/local/bin/cliproxyapi",
            ),
            patch(
                "app.services.cliproxy_manager.subprocess.run",
                return_value=mock_result,
            ),
        ):
            assert CLIProxyManager.detect_version() is None

    def test_returns_none_on_timeout(self):
        with (
            patch(
                "app.services.cliproxy_manager.shutil.which",
                return_value="/usr/local/bin/cliproxyapi",
            ),
            patch(
                "app.services.cliproxy_manager.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="cliproxyapi", timeout=5),
            ),
        ):
            assert CLIProxyManager.detect_version() is None


# ---------------------------------------------------------------------------
# ensure_min_version
# ---------------------------------------------------------------------------


class TestEnsureMinVersion:
    def test_no_op_when_already_current(self):
        with (
            patch.object(CLIProxyManager, "detect_version", return_value="7.0.0"),
            patch.object(CLIProxyManager, "upgrade") as mock_upgrade,
        ):
            ok, msg = CLIProxyManager.ensure_min_version()
        assert ok is True
        assert "already at 7.0.0" in msg
        mock_upgrade.assert_not_called()

    def test_no_op_when_newer_than_minimum(self):
        with (
            patch.object(CLIProxyManager, "detect_version", return_value="7.5.1"),
            patch.object(CLIProxyManager, "upgrade") as mock_upgrade,
        ):
            ok, msg = CLIProxyManager.ensure_min_version()
        assert ok is True
        mock_upgrade.assert_not_called()

    def test_triggers_upgrade_on_old_version(self):
        # detect_version called twice: before upgrade -> 6.8.30, after -> 7.0.0
        with (
            patch.object(
                CLIProxyManager,
                "detect_version",
                side_effect=["6.8.30", "7.0.0"],
            ),
            patch.object(
                CLIProxyManager,
                "upgrade",
                return_value=(True, "upgraded to 7.0.0"),
            ) as mock_upgrade,
        ):
            ok, msg = CLIProxyManager.ensure_min_version()
        assert ok is True
        assert "6.8.30 -> 7.0.0" in msg
        mock_upgrade.assert_called_once()

    def test_returns_false_when_upgrade_fails(self):
        with (
            patch.object(CLIProxyManager, "detect_version", return_value="6.8.30"),
            patch.object(
                CLIProxyManager,
                "upgrade",
                return_value=(False, "brew upgrade failed: network"),
            ),
        ):
            ok, msg = CLIProxyManager.ensure_min_version()
        assert ok is False
        assert "brew upgrade failed" in msg

    def test_returns_false_when_upgrade_succeeds_but_version_still_old(self):
        # Pathological: brew exits 0 but version probe still returns old.
        with (
            patch.object(
                CLIProxyManager,
                "detect_version",
                side_effect=["6.8.30", "6.8.30"],
            ),
            patch.object(
                CLIProxyManager,
                "upgrade",
                return_value=(True, "upgraded"),
            ),
        ):
            ok, msg = CLIProxyManager.ensure_min_version()
        assert ok is False
        assert "still 6.8.30" in msg

    def test_calls_install_when_not_installed(self):
        with (
            patch.object(
                CLIProxyManager,
                "detect_version",
                side_effect=[None, "7.0.0"],
            ),
            patch.object(
                CLIProxyManager, "install_if_needed", return_value=True
            ) as mock_install,
            patch.object(CLIProxyManager, "upgrade") as mock_upgrade,
        ):
            ok, msg = CLIProxyManager.ensure_min_version()
        assert ok is True
        mock_install.assert_called_once()
        mock_upgrade.assert_not_called()

    def test_returns_false_when_install_fails(self):
        with (
            patch.object(CLIProxyManager, "detect_version", return_value=None),
            patch.object(
                CLIProxyManager, "install_if_needed", return_value=False
            ),
        ):
            ok, msg = CLIProxyManager.ensure_min_version()
        assert ok is False
        assert "not installed" in msg


# ---------------------------------------------------------------------------
# upgrade dispatch
# ---------------------------------------------------------------------------


class TestUpgradeDispatch:
    def test_uses_brew_on_macos(self):
        with (
            patch("app.services.cliproxy_manager.platform.system", return_value="Darwin"),
            patch(
                "app.services.cliproxy_manager.shutil.which",
                return_value="/usr/local/bin/brew",
            ),
            patch.object(
                CLIProxyManager,
                "_brew_upgrade",
                return_value=(True, "upgraded to 7.0.0"),
            ) as mock_brew,
        ):
            ok, _ = CLIProxyManager.upgrade()
        assert ok is True
        mock_brew.assert_called_once()

    def test_uses_release_binary_on_linux(self):
        with (
            patch("app.services.cliproxy_manager.platform.system", return_value="Linux"),
            patch.object(
                CLIProxyManager,
                "_linux_upgrade_release_binary",
                return_value=(True, "installed v7.0.0"),
            ) as mock_linux,
        ):
            ok, _ = CLIProxyManager.upgrade()
        assert ok is True
        mock_linux.assert_called_once()

    def test_unsupported_platform_returns_false(self):
        with patch(
            "app.services.cliproxy_manager.platform.system", return_value="Windows"
        ):
            ok, msg = CLIProxyManager.upgrade()
        assert ok is False
        assert "Unsupported platform" in msg


class TestBrewUpgrade:
    def test_success_returns_new_version(self):
        result = MagicMock(returncode=0, stdout="", stderr="")
        with (
            patch(
                "app.services.cliproxy_manager.subprocess.run",
                return_value=result,
            ),
            patch.object(CLIProxyManager, "detect_version", return_value="7.0.0"),
        ):
            ok, msg = CLIProxyManager._brew_upgrade()
        assert ok is True
        assert "7.0.0" in msg

    def test_already_current_treated_as_success(self):
        result = MagicMock(
            returncode=1,
            stdout="cliproxyapi 7.0.0 already installed",
            stderr="",
        )
        with patch(
            "app.services.cliproxy_manager.subprocess.run",
            return_value=result,
        ):
            ok, msg = CLIProxyManager._brew_upgrade()
        assert ok is True
        assert "already" in msg.lower()

    def test_failure_returns_false_with_stderr(self):
        result = MagicMock(returncode=1, stdout="", stderr="some brew error\n")
        with patch(
            "app.services.cliproxy_manager.subprocess.run",
            return_value=result,
        ):
            ok, msg = CLIProxyManager._brew_upgrade()
        assert ok is False
        assert "brew upgrade failed" in msg

    def test_timeout_returns_false(self):
        with patch(
            "app.services.cliproxy_manager.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="brew", timeout=180),
        ):
            ok, msg = CLIProxyManager._brew_upgrade()
        assert ok is False
        assert "brew upgrade error" in msg
