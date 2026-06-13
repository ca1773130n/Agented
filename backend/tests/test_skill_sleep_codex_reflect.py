"""Codex-subprocess Reflect — an alternative to the in-process seam, used ONLY
when the multi-vendor scheduler reports an available codex account.

The subprocess runner is monkeypatched (no real CLI); these verify the
SELECTION logic (auto prefers codex when available, falls back otherwise), the
availability gate, and the LLMCall-seam adapter.
"""

from __future__ import annotations

import json


def _seed_corpus(project_id: str, n: int = 14) -> None:
    from app.db import harness_kg_signals

    for i in range(n):
        harness_kg_signals.record_signal(
            signal_id=f"sig-{project_id}-{i}",
            project_id=project_id,
            question=f"How is concern {i} handled?",
            content=f"By mechanism {i}.",
            round_id="r1",
            already_forged=False,
            weight=1.0,
            now="2026-01-01T00:00:00",
        )


def test_codex_available_reads_rotation_candidates(isolated_db, monkeypatch):
    from app.services import skill_sleep_service as svc
    from app.services.account_rotation_service import RotationCandidate

    monkeypatch.setattr(
        "app.services.account_rotation_service.rotation_candidates",
        lambda backend, **kw: [
            RotationCandidate(
                account_id=1, backend="codex", config_dir="/home/neo/.codex-x", display_name="c"
            )
        ],
    )
    assert svc._codex_available() == "/home/neo/.codex-x"


def test_codex_unavailable_returns_none(isolated_db, monkeypatch):
    from app.services import skill_sleep_service as svc

    monkeypatch.setattr(
        "app.services.account_rotation_service.rotation_candidates", lambda backend, **kw: []
    )
    assert svc._codex_available() is None


def test_select_reflect_auto_prefers_codex_when_available(isolated_db, monkeypatch):
    from app.services import skill_sleep_service as svc

    monkeypatch.setattr(svc, "_codex_available", lambda: "/cfg")
    sentinel = object()
    monkeypatch.setattr(svc, "_build_codex_reflect_call", lambda cfg: sentinel)
    assert svc._select_reflect_call("auto", "claude") is sentinel


def test_select_reflect_auto_falls_back_when_codex_absent(isolated_db, monkeypatch):
    from app.services import skill_sleep_service as svc

    monkeypatch.setattr(svc, "_codex_available", lambda: None)
    monkeypatch.setattr(
        svc, "_build_codex_reflect_call", lambda cfg: (_ for _ in ()).throw(AssertionError("no"))
    )
    # Falls back to the in-process seam (a real callable, not the codex one).
    call = svc._select_reflect_call("auto", "claude")
    assert callable(call)


def test_select_reflect_in_process_when_forced(isolated_db, monkeypatch):
    from app.services import skill_sleep_service as svc

    # A non-auto/non-codex value never touches codex availability.
    monkeypatch.setattr(
        svc, "_codex_available", lambda: (_ for _ in ()).throw(AssertionError("should not check"))
    )
    assert callable(svc._select_reflect_call("in_process", "claude"))


def test_codex_reflect_call_returns_body(isolated_db, monkeypatch):
    from app.services import skill_sleep_service as svc

    monkeypatch.setattr(
        svc, "_run_codex_reflect", lambda prompt, *, config_dir, timeout=600: "CODEX BODY"
    )
    call = svc._build_codex_reflect_call("/cfg")
    out = call([{"role": "user", "content": "improve the skill"}])
    assert out == "CODEX BODY"


def test_round_uses_codex_reflect_when_available(isolated_db, monkeypatch):
    """End-to-end: reflect_backend='auto' + codex available → the round's
    candidate comes from the codex subprocess (monkeypatched)."""
    from app.db.skills import add_user_skill
    from app.services import skill_sleep_service as svc

    _seed_corpus("proj-cx", n=16)
    add_user_skill("deploy", "", "d", 1)
    monkeypatch.setattr(
        "app.services.harness_evolver._owning_project_id_for_skill", lambda sid: "proj-cx"
    )
    monkeypatch.setattr(svc, "_codex_available", lambda: "/cfg")
    monkeypatch.setattr(
        svc, "_run_codex_reflect", lambda prompt, *, config_dir, timeout=600: "CAND from codex"
    )

    def _answer(messages):
        sysmsg = next((m["content"] for m in messages if m.get("role") == "system"), "")
        return "WIN" if "CAND from codex" in sysmsg else "MEH"

    def _judge(messages):
        s = 0.9 if "WIN" in messages[0]["content"] else 0.4
        return json.dumps({"groundedness": s, "sufficiency": s, "quality": s, "reason": "x"})

    v = svc.SkillSleepGate.run_skill_sleep_round(
        "proj-cx",
        "deploy",
        answer_call=_answer,
        judge_call=_judge,
        n=8,
        seed=3,
        reflect_backend="auto",
    )
    assert v["status"] == "accepted"
    from app.db import skill_sleep

    assert skill_sleep.get_run(v["run_id"])["candidate_body"] == "CAND from codex"
