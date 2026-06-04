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


def test_global_cap_gate_uses_conservative_sum_not_max(monkeypatch):
    # Round-3 (round-2 of codex on round-3) HIGH: the gate must add in_flight +
    # db_running, never max(). With max(), fresh in-memory reservations stack
    # invisibly under a large db_running and blow past the cap. The dispatcher
    # must defer once the SUM reaches the cap.
    import app.services.execution_queue_service as eqs

    Q = eqs.ExecutionQueueService
    monkeypatch.setattr(Q, "_GLOBAL_CONCURRENCY_CAP", 20, raising=False)
    monkeypatch.setattr(Q, "_active_global", 3, raising=False)
    # db has 18 running across the three tables.
    monkeypatch.setattr(Q, "_count_running_work", staticmethod(lambda: 18))

    dispatched = []
    monkeypatch.setattr(
        eqs, "get_pending_entries", lambda limit=10: [{"id": "q1", "trigger_id": "t1"}]
    )
    monkeypatch.setattr(
        Q, "_dispatch_entry", classmethod(lambda cls, entry: dispatched.append(entry))
    )

    Q._dispatch_batch()
    # 3 + 18 = 21 >= 20 → deferred. max(3,18)=18 < 20 would have WRONGLY dispatched.
    assert dispatched == []


def test_scheduled_team_overlap_skips_when_already_running(monkeypatch):
    # Round-3 (codex re-review) MEDIUM: the scheduled-team path _execute_team()
    # must coalesce overlapping cron ticks via count_running_for_team(), like the
    # trigger path does.
    import app.services.scheduler_service as ss

    monkeypatch.setattr(ss, "get_team", lambda tid: {"id": tid, "enabled": 1})
    monkeypatch.setattr(
        "app.db.team_executions.count_running_for_team", lambda tid: 1, raising=False
    )
    logged = {}
    monkeypatch.setattr(
        "app.services.audit_log_service.AuditLogService.log",
        lambda **kw: logged.update(kw),
        raising=False,
    )
    started = []

    class _TES:
        @staticmethod
        def execute_team(**kw):
            started.append(kw)

    import sys

    monkeypatch.setitem(
        sys.modules,
        "app.services.team_execution_service",
        type("M", (), {"TeamExecutionService": _TES}),
    )

    ss.SchedulerService._execute_team("team-1")
    assert started == []  # overlap → not started
    assert logged.get("action") == "scheduler.skip_overlap"
    assert logged.get("entity_type") == "team"


def test_scheduled_super_agent_log_marked_terminal(monkeypatch):
    # Round-4 MEDIUM: the scheduled super-agent branch logs its dispatch as
    # 'running' and nothing ever updates that row — so the overlap guard would
    # skip every future tick of the trigger and the global cap would count a
    # phantom execution forever. The dispatch must be recorded terminal.
    import sys

    import app.services.scheduler_service as ss

    trigger = {
        "id": "trg-sa",
        "enabled": 1,
        "dispatch_type": "super_agent",
        "super_agent_id": "sa-1",
        "prompt_template": "do it: {message}",
        "backend_type": "claude",
    }
    monkeypatch.setattr(ss, "get_trigger", lambda tid: trigger)
    monkeypatch.setattr(ss, "update_trigger_last_run", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.services.execution_service.ExecutionService.get_status",
        staticmethod(lambda tid: {"status": "idle"}),
        raising=False,
    )

    created, updated = [], []
    # The scheduler imports these via app.db.triggers' re-export binding, so
    # patch THAT module's attributes (patching execution_logs wouldn't take).
    monkeypatch.setattr(
        "app.db.triggers.create_execution_log",
        lambda **kw: created.append(kw) or True,
    )
    monkeypatch.setattr(
        "app.db.triggers.update_execution_log",
        lambda eid, **kw: updated.append((eid, kw)) or True,
    )

    class _SLE(Exception):
        pass

    class _SAS:
        @staticmethod
        def get_or_create_session(said):
            return "sess-1"

        @staticmethod
        def send_message(sid, msg):
            return None

    monkeypatch.setitem(
        sys.modules,
        "app.services.super_agent_session_service",
        type("M", (), {"SuperAgentSessionService": _SAS, "SessionLimitError": _SLE}),
    )

    ss.SchedulerService._execute_trigger("trg-sa")
    assert created, "dispatch log row was created"
    assert updated, "dispatch log row was marked terminal"
    eid, kw = updated[0]
    assert eid == created[0]["execution_id"]
    assert kw.get("status") == "success" and kw.get("finished_at")


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
