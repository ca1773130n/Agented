"""Data-safety tests for ProjectInstallService settings.json handling."""

import json

import pytest

from app.services.project_install_service import ProjectInstallService

_HOOK = {"name": "my-hook", "event": "PreToolUse", "description": "d"}


def _settings(tmp_path):
    d = tmp_path / ".claude"
    d.mkdir()
    return d / "settings.json"


def test_refuses_to_clobber_unparseable_settings(tmp_path):
    """Regression: an existing-but-unparseable settings.json must NOT be silently
    reset to {} and overwritten — that destroyed the operator's whole file. Abort
    with a surfaced error and leave the file byte-for-byte untouched."""
    sp = _settings(tmp_path)
    corrupt = '{ "hooks": { ,,, truncated'
    sp.write_text(corrupt)

    with pytest.raises(ValueError):
        ProjectInstallService._update_settings_json_hooks(str(tmp_path), _HOOK, "add")

    assert sp.read_text() == corrupt  # untouched, not clobbered


def test_add_hook_preserves_unrelated_keys_atomically(tmp_path):
    """A normal add must preserve the operator's other settings and write valid
    JSON (atomic temp+replace leaves no stray .tmp)."""
    sp = _settings(tmp_path)
    sp.write_text(json.dumps({"model": "opus", "permissions": {"allow": ["x"]}}))

    ProjectInstallService._update_settings_json_hooks(str(tmp_path), _HOOK, "add")

    out = json.loads(sp.read_text())
    assert out["model"] == "opus"  # unrelated keys survive
    assert out["permissions"] == {"allow": ["x"]}
    names = [h["name"] for h in out["hooks"]["PreToolUse"]]
    assert "my-hook" in names
    assert not (tmp_path / ".claude" / "settings.json.tmp").exists()  # no stray temp
