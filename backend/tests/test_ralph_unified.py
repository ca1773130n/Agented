# backend/tests/test_ralph_unified.py
from app.models.loop_spec import LoopSpec
from app.services.execution_type_handler import RalphSessionHandler


def test_ralph_start_config_becomes_agent_task_reset_loopspec(monkeypatch, isolated_db):
    seen = {}
    monkeypatch.setattr(RalphSessionHandler, "_check_ralph_plugin", staticmethod(lambda: None))
    import app.services.execution_type_handler as eth

    monkeypatch.setattr(
        eth.ProjectSessionManager,
        "create_session",
        lambda **kw: seen.update(create=kw) or "sess-r",
    )
    monkeypatch.setattr(
        eth.ProjectSessionManager,
        "get_session_info",
        lambda sid: {"pid": 1, "status": "active"},
    )
    started = {}
    monkeypatch.setattr(
        eth, "start_runner", lambda sid, cfg, cwd: started.update(sid=sid, cfg=cfg), raising=False
    )

    RalphSessionHandler().start(
        {
            "project_id": "p",
            "cwd": "/tmp",
            "ralph_config": {
                "task_description": "do it",
                "max_iterations": 40,
                "no_progress_threshold": 3,
            },
        }
    )
    spec = LoopSpec.from_legacy_config(
        started["cfg"], execution_type=started["cfg"]["_execution_type"]
    )
    assert spec.body.kind == "agent_task"
    assert spec.state.context_policy == "reset"
    assert spec.exit.max_iterations == 40
    assert seen["create"]["execution_type"] == "ralph"
