"""Tests for GRD 0.4.x binary detection + exec-vs-node invocation."""

from app.services.grd_cli_service import GrdCliService


def test_detect_prefers_path_executable(monkeypatch, isolated_db):
    """gd / grd-tools resolvable on PATH (npm @jokerized/getresearchdone
    symlinks) are preferred and marked as direct executables."""
    def fake_which(name):
        return {"gd": "/usr/local/bin/gd", "grd-tools": "/usr/local/bin/grd-tools"}.get(name)

    monkeypatch.setattr("app.services.grd_cli_service.shutil.which", fake_which)
    GrdCliService.detect_binaries()

    assert GrdCliService.gd_path() == "/usr/local/bin/gd"
    assert GrdCliService._gd_is_exec is True
    assert GrdCliService.binary_path() == "/usr/local/bin/grd-tools"
    assert GrdCliService._binary_is_exec is True


def test_run_gd_invokes_executable_directly_vs_node(monkeypatch):
    """A PATH executable runs as `gd …`; a `.js` path runs as `node …/gd.js …`."""
    captured = {}

    class _Result:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        return _Result()

    monkeypatch.setattr("app.services.grd_cli_service.subprocess.run", fake_run)

    # Direct executable → no "node" prefix.
    GrdCliService._gd_path = "/usr/local/bin/gd"
    GrdCliService._gd_is_exec = True
    GrdCliService.run_gd("/tmp", "harness", "status")
    assert captured["cmd"][:3] == ["/usr/local/bin/gd", "harness", "status"]

    # `.js` path → node-invoked.
    GrdCliService._gd_path = "/x/grd/0.4.4/bin/gd.js"
    GrdCliService._gd_is_exec = False
    GrdCliService.run_gd("/tmp", "harness", "status")
    assert captured["cmd"][:2] == ["node", "/x/grd/0.4.4/bin/gd.js"]
