"""Auto-implement seam gating tests (26-04 — the DEFERRED, INERT auto-code stub).

``CompetitorStrategyService.start_autoimplement`` is the would-be entry point into
the autonomy stack. It is the headline-safety seam: it must be INERT in this MVP
and triple-gated, and EVEN with all three gates passed it spawns NO session and
mutates NO repo (returns ``not_implemented``). These tests pin every gate state:

* ``AGENTED_STRATEGY_AUTOIMPLEMENT`` unset → ``disabled`` (the default).
* flag set but strategy uncleared → ``legal_gate_not_cleared``.
* flag set + cleared but no ``confirm_token`` → ``confirmation_required``.
* flag set + cleared + confirm → ``not_implemented`` / ``deferred`` AND
  ``goal_loop_runner.start_runner`` / ``ProjectSessionManager.create_session`` are
  asserted NOT called (the MVP must never auto-execute).

There is deliberately NO HTTP route exercising this — it is a code seam only.
"""

from app.db import competitor_strategies as dao
from app.db.competitor_strategies import LEGAL_CHECKLIST_ITEMS
from app.db.projects import create_project
from app.services.competitor_strategy_service import (
    AGENTED_STRATEGY_AUTOIMPLEMENT,
    CompetitorStrategyService,
)


def _seed_strategy(project_id, *, cleared=False):
    strat = dao.create_strategy(
        project_id,
        title="Auto-implement seam strategy",
        body="behavior-only response",
        backend_kind="claude",
        model="claude-haiku-4-5-20251001",
    )
    sid = strat["id"]
    if cleared:
        for item in LEGAL_CHECKLIST_ITEMS:
            dao.record_legal_item(sid, item, True, project_id=project_id)
    dao.set_status(sid, "approved", project_id=project_id)
    return sid


def _spy_session_seams(monkeypatch):
    """Spy the session-spawn seams; return the call list (must stay empty)."""
    calls = []
    import app.services.goal_loop_runner as glr

    monkeypatch.setattr(glr, "start_runner", lambda *a, **k: calls.append(("start_runner", a, k)))
    from app.services import project_session_manager as psm

    monkeypatch.setattr(
        psm.ProjectSessionManager,
        "create_session",
        lambda *a, **k: calls.append(("create_session", a, k)),
    )
    return calls


def test_autoimplement_disabled_by_default(isolated_db, monkeypatch):
    monkeypatch.delenv(AGENTED_STRATEGY_AUTOIMPLEMENT, raising=False)
    project_id = create_project(name="ai-off-proj")
    sid = _seed_strategy(project_id, cleared=True)

    result = CompetitorStrategyService.start_autoimplement(project_id, sid, confirm_token="yes")
    assert result["status"] == "disabled"


def test_autoimplement_flag_on_but_uncleared(isolated_db, monkeypatch):
    monkeypatch.setenv(AGENTED_STRATEGY_AUTOIMPLEMENT, "1")
    project_id = create_project(name="ai-uncleared-proj")
    sid = _seed_strategy(project_id, cleared=False)

    result = CompetitorStrategyService.start_autoimplement(project_id, sid, confirm_token="yes")
    assert result["status"] == "legal_gate_not_cleared"


def test_autoimplement_flag_on_cleared_no_confirm(isolated_db, monkeypatch):
    monkeypatch.setenv(AGENTED_STRATEGY_AUTOIMPLEMENT, "1")
    project_id = create_project(name="ai-noconfirm-proj")
    sid = _seed_strategy(project_id, cleared=True)

    result = CompetitorStrategyService.start_autoimplement(project_id, sid)
    assert result["status"] == "confirmation_required"


def test_autoimplement_all_gates_pass_is_inert(isolated_db, monkeypatch):
    monkeypatch.setenv(AGENTED_STRATEGY_AUTOIMPLEMENT, "1")
    project_id = create_project(name="ai-inert-proj")
    sid = _seed_strategy(project_id, cleared=True)
    calls = _spy_session_seams(monkeypatch)

    result = CompetitorStrategyService.start_autoimplement(
        project_id, sid, confirm_token="confirm-please"
    )

    # All three gates passed — but the MVP stub is INERT.
    assert result["status"] == "not_implemented"
    assert result["deferred"] is True
    # Crucially: NO session/runner was spawned.
    assert calls == [], f"auto-implement MVP must NOT spawn a session: {calls}"
