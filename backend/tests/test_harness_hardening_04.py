"""Regression tests for the 04.* harness-evolution hardening items.

Covers: H1 (path traversal in deploy materialization), H2 (conditional
mark_applied / double-apply guard), H3 (scratch cleanup), H4 (plugin install
exit-code), H5 (skill fs containment), M1 (executable-kind opt-in gate),
M3 (git revert guards), M4 (create-reversal identity check), M5 (round
budget), M6 (codex output cap), L1 (kill-switch re-check), L2 (loader
not-found vs error).
"""

from __future__ import annotations

from http import HTTPStatus
from unittest.mock import MagicMock

import pytest

from app.db import harness_evolution as evo_repo
from app.db.connection import get_connection


def _seed_project(project_id: str, name: str = "Hardening Project", local_path: str | None = None):
    with get_connection() as conn:
        cols = "id, name"
        vals = [project_id, name]
        ph = "?, ?"
        if local_path is not None:
            cols += ", local_path"
            vals.append(local_path)
            ph += ", ?"
        conn.execute(f"INSERT OR IGNORE INTO projects ({cols}) VALUES ({ph})", vals)
        conn.commit()


def _start_round(project_id: str) -> str:
    return evo_repo.start_round(
        project_id=project_id,
        input_window_since=None,
        input_window_until=None,
        input_execution_count=0,
        input_forge={},
    )


# --------------------------------------------------------------------------
# [04.H1] deploy materialization path traversal
# --------------------------------------------------------------------------


def test_h1_safe_segment_rejects_traversal():
    from app.services.harness_deploy_service import HarnessDeployService as H

    for bad in ("..", ".", "", "/"):
        with pytest.raises(ValueError):
            H._safe_segment(bad)
    # A path-like name is sanitized (collapsed to safe segment), not escaped.
    assert "/" not in H._safe_segment("../../etc")


def test_h1_safe_segment_sanitizes():
    from app.services.harness_deploy_service import HarnessDeployService as H

    assert H._safe_segment("My Skill/../evil") not in ("..", "")
    assert "/" not in H._safe_segment("a/b/c")
    assert H._safe_segment("good-name_1.2") == "good-name_1.2"


def test_h1_assert_within_blocks_escape(tmp_path):
    from app.services.harness_deploy_service import HarnessDeployService as H

    base = tmp_path / "base"
    base.mkdir()
    H._assert_within(str(base), str(base / "child"))  # ok
    with pytest.raises(ValueError):
        H._assert_within(str(base), str(tmp_path / "outside"))


# --------------------------------------------------------------------------
# [04.H2] conditional mark_applied (double-apply guard)
# --------------------------------------------------------------------------


def test_h2_mark_applied_is_conditional(isolated_db):
    _seed_project("proj-h2")
    rid = _start_round("proj-h2")
    first = evo_repo.mark_applied(
        rid, output_patch={"entries": []}, applied_asset_ids=[], notes="n"
    )
    assert first is True
    # Second call must NOT re-transition an already-applied round.
    second = evo_repo.mark_applied(
        rid, output_patch={"entries": []}, applied_asset_ids=[], notes="n2"
    )
    assert second is False


def test_h2_project_lock_is_per_project():
    from app.services import harness_evolver as ev

    la = ev._project_lock("p1")
    lb = ev._project_lock("p1")
    lc = ev._project_lock("p2")
    assert la is lb
    assert la is not lc


# --------------------------------------------------------------------------
# [04.H3] scratch cleanup default + budget helpers
# --------------------------------------------------------------------------


def test_h3_round_budget_reads_env(monkeypatch):
    from app.services import harness_evolver as ev

    monkeypatch.delenv("AGENTED_EVOLUTION_MAX_ROUND_COST_USD", raising=False)
    monkeypatch.delenv("AGENTED_EVOLUTION_MAX_ROUND_ITERATIONS", raising=False)
    assert ev._round_budget() == (None, None)
    monkeypatch.setenv("AGENTED_EVOLUTION_MAX_ROUND_COST_USD", "1.5")
    monkeypatch.setenv("AGENTED_EVOLUTION_MAX_ROUND_ITERATIONS", "7")
    assert ev._round_budget() == (1.5, 7)
    # non-positive / malformed => None
    monkeypatch.setenv("AGENTED_EVOLUTION_MAX_ROUND_ITERATIONS", "0")
    monkeypatch.setenv("AGENTED_EVOLUTION_MAX_ROUND_COST_USD", "x")
    assert ev._round_budget() == (None, None)


def test_h3_default_keep_scratch_is_false():
    import inspect

    from app.services import harness_evolver as ev

    sig = inspect.signature(ev.run_evolution_round)
    assert sig.parameters["keep_scratch_on_failure"].default is False


# --------------------------------------------------------------------------
# [04.H5] skill filesystem containment
# --------------------------------------------------------------------------


def test_h5_create_skill_rejects_traversal_name(isolated_db, tmp_path):
    from app.services import harness_evolver as ev

    _seed_project("proj-h5", local_path=str(tmp_path))
    # A name resolving to "" after sanitization is rejected (returns None).
    out = ev._create_skill(
        name="../../../../etc/evil", payload={"content": "x"}, project_id="proj-h5"
    )
    # Either rejected (None) or contained under .claude/skills.
    skills_root = (tmp_path / ".claude" / "skills").resolve()
    for created in skills_root.rglob("SKILL.md") if skills_root.exists() else []:
        assert created.resolve().is_relative_to(skills_root)
    # Crucially nothing was written outside the project root.
    assert not (tmp_path.parent / "etc").exists()
    _ = out


def test_h5_delete_skill_refuses_uncontained_path(isolated_db, tmp_path):
    from app.db import skills as skills_repo
    from app.services import harness_evolver as ev

    # A skill row pointing at a path OUTSIDE any .claude/skills dir.
    rogue = tmp_path / "important.txt"
    rogue.write_text("keep me", encoding="utf-8")
    sid = skills_repo.add_user_skill(
        skill_name="rogue", skill_path=str(rogue), description=None, enabled=1
    )
    ev._delete_skill(asset_id=sid)
    # The file must NOT have been unlinked (uncontained path refused).
    assert rogue.exists()


# --------------------------------------------------------------------------
# [04.H4] plugin install exit code
# --------------------------------------------------------------------------


def test_h4_plugin_install_reports_failures(monkeypatch):
    from app.services.harness_plugin_installer import HarnessPluginInstaller

    calls = {"n": 0}

    def fake_run(cmd, **kw):
        calls["n"] += 1
        m = MagicMock()
        # marketplace add + list succeed; installs: first fails, rest ok
        if cmd[:3] == ["claude", "plugin", "install"]:
            plugin = cmd[3]
            m.returncode = 1 if plugin == "HarnessSync" else 0
            m.stderr = "boom" if m.returncode else ""
            m.stdout = ""
        else:
            m.returncode = 0
            m.stdout = ""  # nothing pre-installed
            m.stderr = ""
        return m

    monkeypatch.setattr("app.services.harness_plugin_installer.subprocess.run", fake_run)
    out = HarnessPluginInstaller.ensure_plugins_installed("/tmp/cfg-x")
    assert "HarnessSync" in out["failed"]
    assert "grd" in out["installed"]


# --------------------------------------------------------------------------
# [04.M1] executable-kind opt-in gate
# --------------------------------------------------------------------------


def _passing_round(kinds):
    return {
        "output_patch": {"entries": [{"kind": k, "op": "create"} for k in kinds]},
        "eval_verdict": {"passed": True, "score": 0.99},
    }


def test_m1_hook_blocked_without_opt_in(monkeypatch):
    from app.models.autonomy_policy import AutonomyPolicy
    from app.services import harness_autonomy as autonomy

    monkeypatch.delenv("AGENTED_AUTONOMY_ALLOW_EXECUTABLE_KINDS", raising=False)
    policy = AutonomyPolicy(enabled=True, allowed_kinds=["rule", "hook"], confidence_threshold=0.5)
    decision = autonomy.autonomous_apply_eligible(
        _passing_round(["hook"]), policy, recent_auto_applies=0, recent_within_cooldown=False
    )
    gate = next(g for g in decision.gates if g.name == "executable_kinds_opt_in")
    assert gate.passed is False
    assert decision.eligible is False


def test_m1_hook_allowed_with_opt_in(monkeypatch):
    from app.models.autonomy_policy import AutonomyPolicy
    from app.services import harness_autonomy as autonomy

    monkeypatch.setenv("AGENTED_AUTONOMY_ALLOW_EXECUTABLE_KINDS", "1")
    policy = AutonomyPolicy(enabled=True, allowed_kinds=["rule", "hook"], confidence_threshold=0.5)
    decision = autonomy.autonomous_apply_eligible(
        _passing_round(["hook"]), policy, recent_auto_applies=0, recent_within_cooldown=False
    )
    gate = next(g for g in decision.gates if g.name == "executable_kinds_opt_in")
    assert gate.passed is True


# --------------------------------------------------------------------------
# [04.L1] kill-switch re-check before apply
# --------------------------------------------------------------------------


def test_l1_kill_switch_rechecked_before_apply(isolated_db, monkeypatch):
    from app.db import project_autonomy_config as autonomy_cfg
    from app.models.autonomy_policy import AutonomyPolicy
    from app.services import harness_autonomy as autonomy

    _seed_project("proj-l1")
    autonomy_cfg.upsert_policy(
        "proj-l1",
        AutonomyPolicy(enabled=True, allowed_kinds=["rule"], confidence_threshold=0.1),
    )

    rnd = {
        "id": "her-l1",
        "status": "awaiting_approval",
        "output_patch": {"entries": [{"kind": "rule", "op": "create"}]},
        "eval_verdict": {"passed": True, "score": 0.99},
    }
    monkeypatch.setattr(autonomy.evo_repo, "list_for_project", lambda *a, **k: [rnd])
    monkeypatch.setattr(autonomy.evo_repo, "count_recent_auto_applies", lambda *a, **k: 0)
    blocked = {}
    monkeypatch.setattr(
        autonomy.evo_repo,
        "mark_auto_apply_blocked",
        lambda rid, reason: blocked.update({rid: reason}),
    )
    applied = []
    monkeypatch.setattr(autonomy, "apply_dry_run_round", lambda *a, **k: applied.append(a))
    # Kill switch ON => decision computes (kill_switch gate fails => not
    # eligible), but even if eligible, the pre-apply re-check must block.
    monkeypatch.setenv("AGENTED_AUTONOMY", "0")
    autonomy.process_project_autonomy("proj-l1")
    assert applied == []


# --------------------------------------------------------------------------
# [04.M3] git revert guards
# --------------------------------------------------------------------------


def test_m3_git_revert_refuses_dirty_tree(isolated_db, tmp_path, monkeypatch):
    from app.services import harness_evolution_rollback as rb

    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    _seed_project("proj-m3", local_path=str(root))

    runs = []

    def fake_run(cmd, **kw):
        runs.append(cmd)
        m = MagicMock()
        m.returncode = 0
        # dirty status
        m.stdout = " M file.py\n" if cmd[:2] == ["git", "status"] else ""
        m.stderr = ""
        return m

    monkeypatch.setattr(rb.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError):
        rb._git_revert("proj-m3", "deadbeef")
    # The actual `git revert --no-edit <sha>` must never have run.
    assert ["git", "revert", "--no-edit", "deadbeef"] not in runs


def test_m3_git_revert_only_aborts_when_revert_head_exists(isolated_db, tmp_path, monkeypatch):
    from app.services import harness_evolution_rollback as rb

    root = tmp_path / "repo2"
    (root / ".git").mkdir(parents=True)
    _seed_project("proj-m3b", local_path=str(root))

    runs = []

    def fake_run(cmd, **kw):
        runs.append(cmd)
        m = MagicMock()
        m.returncode = 0
        m.stdout = ""  # clean tree
        m.stderr = ""
        return m

    monkeypatch.setattr(rb.subprocess, "run", fake_run)
    assert rb._git_revert("proj-m3b", "abc123") is True
    # No REVERT_HEAD => no abort call.
    assert ["git", "revert", "--abort"] not in runs


# --------------------------------------------------------------------------
# [04.M4] create-reversal identity check
# --------------------------------------------------------------------------


def test_m4_create_reversal_identity_mismatch_refuses_delete(isolated_db, monkeypatch):
    from app.services import harness_evolution_rollback as rb
    from app.services import harness_evolver as ev

    journal = [
        {
            "kind": "rule",
            "op": "create",
            "asset_id": "5",
            "before": None,
            "created_identity": "orig",
        }
    ]
    # Current asset at id 5 is a DIFFERENT rule (id reuse). reverse_apply_journal
    # imports _fetch_primitive from harness_evolver locally, so patch it there.
    monkeypatch.setattr(ev, "_fetch_primitive", lambda kind, aid: {"name": "someone-else"})
    deleted = []
    monkeypatch.setitem(ev._delete_dispatch, "rule", lambda *, asset_id: deleted.append(asset_id))
    n, failures = rb.reverse_apply_journal("proj-m4", journal)
    assert deleted == []
    assert failures and "identity mismatch" in failures[0]["error"]


def test_m4_create_reversal_identity_match_deletes(isolated_db, monkeypatch):
    from app.services import harness_evolution_rollback as rb
    from app.services import harness_evolver as ev

    journal = [
        {
            "kind": "rule",
            "op": "create",
            "asset_id": "9",
            "before": None,
            "created_identity": "orig",
        }
    ]
    monkeypatch.setattr(ev, "_fetch_primitive", lambda kind, aid: {"name": "orig"})
    deleted = []
    monkeypatch.setitem(ev._delete_dispatch, "rule", lambda *, asset_id: deleted.append(asset_id))
    monkeypatch.setattr(rb, "_unbind", lambda *a, **k: None)
    n, failures = rb.reverse_apply_journal("proj-m4b", journal)
    assert deleted == ["9"]
    assert failures == []


# --------------------------------------------------------------------------
# [04.M6] codex output cap (smoke: streams to temp files, checks exit code)
# --------------------------------------------------------------------------


def test_m6_codex_runner_checks_returncode(tmp_path, monkeypatch):
    from app.services import harness_evolver as ev

    (tmp_path / "PROMPT.md").write_text("hello", encoding="utf-8")

    def fake_run(cmd, **kw):
        # Write a big stderr to the provided temp file handle, then fail.
        kw["stderr"].write(b"E" * (2 * 1_000_000))
        m = MagicMock()
        m.returncode = 3
        return m

    monkeypatch.setattr(ev, "_default_codex_cmd", lambda: ["codex", "exec", ev._PROMPT_TOKEN])
    monkeypatch.setattr(ev.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError) as exc:
        ev._run_codex_in_workspace(tmp_path)
    assert "exited 3" in str(exc.value)


# --------------------------------------------------------------------------
# [04.L2] loader distinguishes not-found from error
# --------------------------------------------------------------------------


def test_l2_check_harness_exists_clone_error_is_500(isolated_db, monkeypatch):
    from app.services.harness_loader_service import HarnessLoaderService

    _seed_project("proj-l2")
    with get_connection() as conn:
        conn.execute("UPDATE projects SET github_repo = ? WHERE id = ?", ("owner/repo", "proj-l2"))
        conn.commit()

    monkeypatch.setattr(
        "app.services.harness_loader_service.GitHubService.clone_repo",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("token leak: ghp_secret")),
    )
    body, status = HarnessLoaderService.check_harness_exists("proj-l2")
    assert status == HTTPStatus.INTERNAL_SERVER_ERROR
    # Raw exception (token) must not leak.
    assert "ghp_secret" not in str(body)
