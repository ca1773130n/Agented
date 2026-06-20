# backend/tests/services/test_sandbox_eval.py
import os
from pathlib import Path
from app.services.sandbox_eval import run_isolated_check


def test_runs_check_against_a_snapshot_not_the_live_dir(tmp_path):
    (tmp_path / "marker.txt").write_text("hi")
    # check verifies the file exists in the snapshot cwd (proves the copy happened)
    res = run_isolated_check("test -f marker.txt", str(tmp_path), timeout=10)
    assert res.returncode == 0
    # the snapshot temp dir is cleaned up (no stray agented-eval-* dir leaked into
    # the live workspace; the autouse isolated_db fixture also writes test.db here)
    leaked = [p.name for p in tmp_path.iterdir() if p.name.startswith("agented-eval-")]
    assert leaked == []
    assert "marker.txt" in {p.name for p in tmp_path.iterdir()}


def test_env_is_scrubbed(tmp_path):
    os.environ["SECRET_TOKEN_XYZ"] = "leak"
    try:
        res = run_isolated_check('test -z "$SECRET_TOKEN_XYZ"', str(tmp_path), timeout=10)
        assert res.returncode == 0  # secret NOT present in the scrubbed env
    finally:
        os.environ.pop("SECRET_TOKEN_XYZ", None)


def test_nonzero_exit_propagates(tmp_path):
    res = run_isolated_check("exit 3", str(tmp_path), timeout=10)
    assert res.returncode == 3


def test_oversize_workspace_falls_back_to_inherit(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.sandbox_eval._MAX_SNAPSHOT_BYTES", 1)  # force fallback
    (tmp_path / "big.txt").write_text("xxxxxxxxxx")
    res = run_isolated_check("test -f big.txt", str(tmp_path), timeout=10)
    assert res.returncode == 0  # ran in-place (fallback), still works
    assert res.sandboxed is False


def test_escaping_symlink_is_neutralized(tmp_path):
    """A pre-planted symlink pointing OUTSIDE the workspace must not be readable
    from inside the snapshot (it's dropped during neutralization)."""
    import os
    secret = tmp_path.parent / "outside_secret.txt"
    secret.write_text("TOPSECRET")
    ws = tmp_path / "ws"
    ws.mkdir()
    os.symlink(str(secret), str(ws / "leak"))
    # cat the symlink target from inside the snapshot — should NOT find the secret.
    res = run_isolated_check("cat leak 2>/dev/null; true", str(ws), timeout=10)
    assert "TOPSECRET" not in res.stdout


def test_run_check_inplace_scrubs_env(tmp_path):
    import os
    os.environ["SECRET_TOKEN_INPLACE"] = "leak"
    try:
        from app.services.sandbox_eval import run_check_inplace
        res = run_check_inplace('test -z "$SECRET_TOKEN_INPLACE"', str(tmp_path), timeout=10)
        assert res.returncode == 0 and res.sandboxed is False
    finally:
        os.environ.pop("SECRET_TOKEN_INPLACE", None)


def test_timeout_returns_124(tmp_path):
    res = run_isolated_check("sleep 5", str(tmp_path), timeout=1)
    assert res.returncode == 124
