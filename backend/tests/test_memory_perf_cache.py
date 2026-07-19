"""Perf regression: memory/observability endpoints must not spawn a tesserae
subprocess on every page load."""

import app_litestar.routes.memory_system as ms


def test_tesserae_cli_status_caches_version(monkeypatch):
    """`tesserae --version` is spawned once and cached process-wide — not on every
    memory-systems page load (was a visible navigation delay)."""
    ms._cli_status_cache.clear()
    monkeypatch.setattr(ms.shutil, "which", lambda _: "/usr/bin/tesserae")

    calls = []

    class _R:
        returncode = 0
        stdout = "tesserae 0.20.0"
        stderr = ""

    def _fake_run(*a, **k):
        calls.append(1)
        return _R()

    monkeypatch.setattr(ms.subprocess, "run", _fake_run)
    try:
        r1 = ms._tesserae_cli_status()
        r2 = ms._tesserae_cli_status()
        assert r1 == r2 == {
            "installed": True,
            "version": "tesserae 0.20.0",
            "path": "/usr/bin/tesserae",
        }
        assert len(calls) == 1  # spawned once, not per call
    finally:
        ms._cli_status_cache.clear()


def test_tesserae_cli_status_not_installed_is_not_cached(monkeypatch):
    """A 'not installed' result is NOT cached, so a later install is picked up."""
    ms._cli_status_cache.clear()
    monkeypatch.setattr(ms.shutil, "which", lambda _: None)
    assert ms._tesserae_cli_status() == {"installed": False, "version": None, "path": None}
    assert ms._cli_status_cache == {}  # nothing cached
