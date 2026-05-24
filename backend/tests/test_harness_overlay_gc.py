"""Tests for periodic GC of orphan harness-overlay temp dirs."""

from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import patch

from app.services.harness_overlay import cleanup_stale_overlays


def _make_overlay(name: str, age_seconds: float) -> Path:
    """Create a fake overlay dir under /tmp and back-date its mtime."""
    path = Path(f"/tmp/agented-claude-overlay-{name}")
    if path.exists():
        import shutil
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    (path / "settings.json").write_text("{}")
    when = time.time() - age_seconds
    os.utime(path, (when, when))
    return path


def test_cleanup_removes_old_overlays_keeps_fresh_ones(tmp_path):
    """Overlays older than max_age_hours go away; fresh ones survive."""
    # max_age_hours = 1 -> 3600s cutoff
    old = _make_overlay(f"gc-old-{os.getpid()}", age_seconds=7200)   # 2h
    fresh = _make_overlay(f"gc-fresh-{os.getpid()}", age_seconds=600)  # 10m

    try:
        result = cleanup_stale_overlays(max_age_hours=1)
        assert not old.exists()
        assert fresh.exists()
        assert result["removed"] >= 1
        assert result["kept"] >= 1
    finally:
        import shutil
        for p in (old, fresh):
            shutil.rmtree(p, ignore_errors=True)


def test_cleanup_zero_dirs_returns_zero_counts():
    """Nothing to do is a clean no-op (don't conjure errors from an empty
    /tmp scan)."""
    # We can't guarantee /tmp is empty of overlays from parallel tests, so
    # at minimum verify the function returns and doesn't blow up.
    out = cleanup_stale_overlays(max_age_hours=24)
    assert "removed" in out
    assert "kept" in out
    assert "errors" in out


def test_cleanup_swallows_glob_failure(monkeypatch):
    """A hostile /tmp must not raise."""
    def _boom(*_args, **_kwargs):
        raise OSError("permission denied")
    with patch("pathlib.Path.glob", _boom):
        result = cleanup_stale_overlays(max_age_hours=1)
    assert result["errors"] >= 1
