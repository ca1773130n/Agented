"""Tests for the v0.7.84 GRD CLI surface migration to GRD v0.3.24.

Covers the new ``gd.js`` binary detection, the ``run_gd*`` runners, and
each typed helper (health / think / dead-end / genome / verify
mechanical). Subprocess is mocked at the ``GrdCliService._run`` boundary
so tests don't depend on a real GRD install.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from app.services.grd_cli_service import GrdCliService


# Reset the cached binary paths between tests so detection order is
# observable and one test's stale path doesn't contaminate another.
def _reset_cli():
    GrdCliService._binary_path = None
    GrdCliService._gd_path = None
    GrdCliService._binary_available = False
    GrdCliService._gd_available = False


def _mock_runner(success: bool, output: str | None = None, error: str | None = None):
    return {"success": success, "output": output, "error": error}


# ---------------------------------------------------------------------
# detect_binaries
# ---------------------------------------------------------------------


def test_detect_binaries_no_install_marks_both_unavailable(monkeypatch):
    """Neither binary present → both ``*_available`` flags clear."""
    _reset_cli()
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    with patch("glob.glob", return_value=[]):
        GrdCliService.detect_binaries()
    avail = GrdCliService.available()
    assert avail["grd_tools_available"] is False
    assert avail["gd_available"] is False
    assert avail["grd_tools_path"] is None
    assert avail["gd_path"] is None


def test_detect_binaries_env_var(monkeypatch, tmp_path):
    """CLAUDE_PLUGIN_ROOT pointing at a dir with both binaries picks
    them up without touching the settings table or glob roots.
    """
    _reset_cli()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "grd-tools.js").write_text("// stub")
    (bin_dir / "gd.js").write_text("// stub")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    GrdCliService.detect_binaries()
    avail = GrdCliService.available()
    assert avail["grd_tools_available"] is True
    assert avail["gd_available"] is True
    assert avail["grd_tools_path"].endswith("/bin/grd-tools.js")
    assert avail["gd_path"].endswith("/bin/gd.js")


def test_detect_binary_back_compat_returns_grd_tools_path(monkeypatch, tmp_path):
    """Legacy ``detect_binary()`` callers still get the
    ``grd-tools.js`` path even after the v0.3.24 dual-detection.
    """
    _reset_cli()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "grd-tools.js").write_text("// stub")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    path = GrdCliService.detect_binary()
    assert path is not None
    assert path.endswith("/bin/grd-tools.js")


# ---------------------------------------------------------------------
# run_gd_json
# ---------------------------------------------------------------------


def test_run_gd_json_parses_payload():
    _reset_cli()
    GrdCliService._gd_path = "/fake/gd.js"
    GrdCliService._gd_available = True
    with patch.object(
        GrdCliService,
        "_run",
        return_value=_mock_runner(True, output=json.dumps({"foo": "bar"})),
    ):
        result = GrdCliService.run_gd_json("/proj", "health")
    assert result["success"] is True
    assert result["data"] == {"foo": "bar"}
    assert result["error"] is None


def test_run_gd_json_handles_non_json_output():
    _reset_cli()
    GrdCliService._gd_path = "/fake/gd.js"
    GrdCliService._gd_available = True
    with patch.object(
        GrdCliService, "_run", return_value=_mock_runner(True, output="not-json")
    ):
        result = GrdCliService.run_gd_json("/proj", "health")
    assert result["success"] is False
    assert result["data"] is None
    assert "non-JSON" in (result["error"] or "")


def test_run_gd_json_propagates_subprocess_error():
    _reset_cli()
    GrdCliService._gd_path = "/fake/gd.js"
    GrdCliService._gd_available = True
    with patch.object(
        GrdCliService,
        "_run",
        return_value=_mock_runner(False, error="exit 1"),
    ):
        result = GrdCliService.run_gd_json("/proj", "health")
    assert result["success"] is False
    assert result["error"] == "exit 1"


# ---------------------------------------------------------------------
# Typed helpers
# ---------------------------------------------------------------------


def test_get_health_prefers_gd_when_available():
    _reset_cli()
    GrdCliService._gd_path = "/fake/gd.js"
    GrdCliService._gd_available = True
    GrdCliService._binary_path = "/fake/grd-tools.js"
    GrdCliService._binary_available = True
    payload = {"drift_weighted": 0.5, "blocker_count": 0}
    with patch.object(
        GrdCliService, "_run", return_value=_mock_runner(True, output=json.dumps(payload))
    ) as run:
        result = GrdCliService.get_health("/proj")
    assert result["success"] is True
    assert result["data"] == payload
    # First arg of the _run call must be the gd path, not grd-tools.
    assert run.call_args[0][0] == "/fake/gd.js"


def test_get_health_falls_back_to_grd_tools_when_gd_missing():
    _reset_cli()
    GrdCliService._binary_path = "/fake/grd-tools.js"
    GrdCliService._binary_available = True
    # gd not installed
    with patch.object(
        GrdCliService,
        "_run",
        return_value=_mock_runner(True, output="# health text"),
    ) as run:
        result = GrdCliService.get_health("/proj")
    assert result["success"] is True
    # Plain-text fallback wraps under ``text`` so callers always get a dict.
    assert result["data"] == {"text": "# health text"}
    assert run.call_args[0][0] == "/fake/grd-tools.js"


def test_think_requires_gd_binary():
    _reset_cli()
    # gd not installed
    result = GrdCliService.think("/proj")
    assert result["success"] is False
    assert "v0.3.24" in (result["error"] or "")


def test_add_dead_end_validates_required_fields():
    _reset_cli()
    GrdCliService._binary_path = "/fake/grd-tools.js"
    GrdCliService._binary_available = True
    # Missing reason
    result = GrdCliService.add_dead_end("/proj", approach="x", reason="")
    assert result["success"] is False
    assert "required" in (result["error"] or "")


def test_add_dead_end_builds_correct_argv():
    _reset_cli()
    GrdCliService._binary_path = "/fake/grd-tools.js"
    GrdCliService._binary_available = True
    captured = {}

    def fake_run(binary, cwd, argv, *, raw):
        captured["binary"] = binary
        captured["argv"] = argv
        captured["raw"] = raw
        return _mock_runner(True, output="ok")

    with patch.object(GrdCliService, "_run", side_effect=fake_run):
        GrdCliService.add_dead_end(
            "/proj", approach="try X", reason="X failed because Y", phase="42"
        )
    assert captured["binary"] == "/fake/grd-tools.js"
    assert captured["argv"][:2] == ["dead-end", "add"]
    assert "--approach" in captured["argv"]
    assert "try X" in captured["argv"]
    assert "--reason" in captured["argv"]
    assert "--phase" in captured["argv"]
    assert "42" in captured["argv"]


def test_promote_dead_ends_requires_phase():
    _reset_cli()
    GrdCliService._binary_path = "/fake/grd-tools.js"
    GrdCliService._binary_available = True
    result = GrdCliService.promote_dead_ends_from_phase("/proj", "")
    assert result["success"] is False
    assert "phase" in (result["error"] or "").lower()


def test_genome_show_parses_json():
    _reset_cli()
    GrdCliService._binary_path = "/fake/grd-tools.js"
    GrdCliService._binary_available = True
    payload = {"exists": True, "content": "# GENOME"}
    with patch.object(
        GrdCliService, "_run", return_value=_mock_runner(True, output=json.dumps(payload))
    ):
        result = GrdCliService.genome_show("/proj")
    assert result["success"] is True
    assert result["data"] == payload


def test_verify_mechanical_requires_phase():
    _reset_cli()
    GrdCliService._binary_path = "/fake/grd-tools.js"
    GrdCliService._binary_available = True
    result = GrdCliService.verify_mechanical("/proj", "")
    assert result["success"] is False
    assert "phase" in (result["error"] or "").lower()
