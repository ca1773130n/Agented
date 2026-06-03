"""Regression tests for the Codex review fixes on PR #193."""


def test_oauth_callback_subpaths_bypass_auth():
    # BLOCKER: /api/oauth-callback/{rest:path} — provider redirects hit subpaths,
    # which must still bypass app auth (the proxy is state-gated).
    from app_litestar.middleware import _path_requires_auth

    assert _path_requires_auth("/api/oauth-callback") is False
    assert _path_requires_auth("/api/oauth-callback/google?code=x&state=y") is False
    # github webhook stays exact (no subpaths) and other /api still requires auth.
    assert _path_requires_auth("/api/webhooks/github") is False
    assert _path_requires_auth("/api/projects") is True


def test_issue_comment_dedup_allows_distinct_edits():
    import app_litestar.routes.webhooks as wh

    wh._seen_delivery_keys.clear()
    # Same comment id, two different updated_at (two edits) → both allowed.
    k1 = f"comment:o/r:5:{'2026-06-04T00:00:00Z'}"
    k2 = f"comment:o/r:5:{'2026-06-04T00:05:00Z'}"
    assert wh._is_duplicate_key(k1) is False
    assert wh._is_duplicate_key(k2) is False  # distinct edit not suppressed
    assert wh._is_duplicate_key(k1) is True  # identical redelivery suppressed


def test_skill_md_path_containment():
    from pathlib import Path

    from app.services.harness_evolver import _is_skill_md_path

    assert _is_skill_md_path(Path("/proj/.claude/skills/my-skill/SKILL.md")) is True
    # Wrong filename / not under .claude/skills / traversal → rejected.
    assert _is_skill_md_path(Path("/proj/.claude/skills/my-skill/evil.sh")) is False
    assert _is_skill_md_path(Path("/etc/passwd")) is False
    assert _is_skill_md_path(Path("/proj/.claude/skills/../../../etc/SKILL.md")) is False


def test_process_manager_signal_group_respects_pgid_valid(monkeypatch):
    import signal

    from app.services.process_manager import ProcessInfo, ProcessManager

    class _P:
        pid = 4242

    calls = {"killpg": [], "kill": []}
    monkeypatch.setattr(
        "app.services.process_manager.os.killpg", lambda pg, s: calls["killpg"].append((pg, s))
    )
    monkeypatch.setattr(
        "app.services.process_manager.os.kill", lambda p, s: calls["kill"].append((p, s))
    )

    valid = ProcessInfo(process=_P(), pgid=999, execution_id="e", trigger_id="t", pgid_valid=True)
    ProcessManager._signal_group(valid, signal.SIGSTOP)
    assert calls["killpg"] == [(999, signal.SIGSTOP)] and calls["kill"] == []

    invalid = ProcessInfo(
        process=_P(), pgid=4242, execution_id="e", trigger_id="t", pgid_valid=False
    )
    ProcessManager._signal_group(invalid, signal.SIGCONT)
    # pgid unknown → signal the pid only, never killpg.
    assert calls["kill"] == [(4242, signal.SIGCONT)] and len(calls["killpg"]) == 1


def test_count_running_work_sums_all_three_tables(monkeypatch):
    # Round-3 HIGH: global cap (01 H6) must count team_executions /
    # workflow_executions, not just execution_logs — else team/workflow
    # strategies that fork their own daemons slip past the host cap.
    import app.services.execution_queue_service as eqs

    monkeypatch.setattr(
        "app.db.execution_logs.get_active_execution_count", lambda: 2, raising=False
    )

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql):
            # team_executions → 3 running, workflow_executions → 1 running.
            count = 3 if "team_executions" in sql else 1
            return type("R", (), {"fetchone": lambda _self: [count]})()

    monkeypatch.setattr(eqs, "get_connection", lambda: _Conn(), raising=False)
    monkeypatch.setattr("app.db.connection.get_connection", lambda: _Conn(), raising=False)

    assert eqs.ExecutionQueueService._count_running_work() == 2 + 3 + 1


def test_skill_write_anchored_to_owning_project(monkeypatch, tmp_path):
    # Round-3 HIGH: the skill UPDATE write must be contained to the OWNING
    # project's skills root, not merely a skills-shaped path. A SKILL.md that is
    # shape-valid but lives outside the bound project's root is refused.
    import app.services.harness_evolver as he

    proj_root = tmp_path / "proj"
    inside = proj_root / ".claude" / "skills" / "s" / "SKILL.md"
    outside = tmp_path / "other" / ".claude" / "skills" / "s" / "SKILL.md"

    monkeypatch.setattr(he, "_owning_project_id_for_skill", lambda _aid: "proj-1")
    monkeypatch.setattr(he, "_project_root", lambda _pid: proj_root)

    assert he._skill_write_allowed("42", inside) is True
    assert he._skill_write_allowed("42", outside) is False
