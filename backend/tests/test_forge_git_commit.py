"""commit_materialization git behavior + no-git fallback."""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.services.forge_materialization_service import (
    MaterializationResult,
    WrittenFile,
    commit_materialization,
)


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_commit_stages_only_claude_paths(tmp_path):
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "t@t.io")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "operator.txt").write_text("hand-edited")
    (tmp_path / ".claude" / "commands").mkdir(parents=True)
    (tmp_path / ".claude" / "commands" / "deploy.md").write_text("x")

    result = MaterializationResult(
        written=[WrittenFile(".claude/commands/deploy.md", "command", "c1")]
    )
    sha = commit_materialization({"id": "p", "local_path": str(tmp_path)}, result, "her-round-1")

    assert sha
    status = _git(tmp_path, "status", "--porcelain")
    assert "operator.txt" in status  # operator file NOT committed
    msg = _git(tmp_path, "log", "-1", "--pretty=%B")
    assert "her-round-1" in msg  # message references round id


def test_commit_returns_none_without_git(tmp_path):
    (tmp_path / ".claude").mkdir()
    result = MaterializationResult(written=[WrittenFile(".claude/x.md", "command", "c1")])
    sha = commit_materialization({"id": "p", "local_path": str(tmp_path)}, result, "her-round-2")
    assert sha is None


def test_commit_returns_none_when_no_local_path(tmp_path):
    result = MaterializationResult(written=[WrittenFile(".claude/x.md", "command", "c1")])
    assert commit_materialization({"id": "p"}, result, "r") is None


def test_materialize_round_resolves_project_and_kinds(isolated_db, tmp_path):
    from app.database import get_connection
    from app.db import commands as commands_repo
    from app.db import project_forge_bindings as bindings_repo
    from app.db import harness_evolution as evo_repo
    from app.services.forge_materialization_service import materialize_round

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, status, local_path) VALUES ('proj-r', 'P', 'active', ?)",
            (str(tmp_path),),
        )
        conn.commit()
    cid = commands_repo.create_command(
        name="deploy", description="d", content="x", project_id="proj-r"
    )
    bindings_repo.add_binding("proj-r", "command", str(cid))
    rid = evo_repo.start_round(
        project_id="proj-r",
        input_window_since=None,
        input_window_until=None,
        input_execution_count=0,
        input_forge={},
        scratch_dir="/tmp/x",
    )
    evo_repo.mark_applied(
        rid,
        output_patch={"entries": []},
        applied_asset_ids=[{"kind": "command", "op": "create", "asset_id": cid}],
        notes="",
    )
    materialize_round(rid, tmp_path)
    assert (tmp_path / ".claude" / "commands" / "deploy.md").exists()


def test_materialize_round_returns_empty_for_missing_round(isolated_db, tmp_path):
    from app.services.forge_materialization_service import materialize_round, MaterializationResult

    result = materialize_round("her-does-not-exist", tmp_path)
    assert isinstance(result, MaterializationResult)
    assert result.written == []
