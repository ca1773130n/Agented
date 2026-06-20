from app.services import goal_loop_runner as glr
from app.models.loop_spec import LoopSpec


def _mk(session_id="s"):
    spec = LoopSpec.from_legacy_config({"goal": "g", "max_iterations": 9, "max_tokens": 1000, "max_cost_usd": 2.0}, execution_type="goal_loop")
    st = glr._RunnerState(session_id=session_id, config={"goal": "g"}, started_at=0.0, spec=spec)
    glr._runners[session_id] = st
    return st


def test_pause_resume_toggle_event():
    st = _mk("s-pr")
    glr.pause_runner("s-pr"); assert st.pause_event.is_set()
    glr.resume_runner("s-pr"); assert not st.pause_event.is_set()
    glr._runners.pop("s-pr", None)


def test_intervene_sets_pending_note():
    st = _mk("s-iv")
    glr.intervene_runner("s-iv", "focus on the parser")
    assert st.pending_note == "focus on the parser"
    glr._runners.pop("s-iv", None)


def test_gate_decision_recorded():
    st = _mk("s-gd")
    glr.submit_gate_decision("s-gd", "modify", "add a test first")
    assert st.gate_decision == ("modify", "add a test first")
    glr._runners.pop("s-gd", None)


def test_get_runner_state_enriched():
    st = _mk("s-st"); st.total_cost_usd = 0.5; st.total_tokens = 120
    snap = glr.get_runner_state("s-st")
    assert snap["total_cost_usd"] == 0.5 and snap["total_tokens"] == 120
    assert snap["max_cost_usd"] == 2.0 and snap["max_tokens"] == 1000
    assert snap["paused"] is False and snap["awaiting_human"] is False
    glr._runners.pop("s-st", None)
