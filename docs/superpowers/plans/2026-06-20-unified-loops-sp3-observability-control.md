# Unified Loops — Sub-project #3: Observability + Control — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-iteration trace + enriched live status (observe) and true pause/resume, mid-loop intervene, and configurable human-gate checkpoints (control) to the unified loop executor.

**Architecture:** Extend `goal_loop_runner` with a `pause_event` + control state on `_RunnerState`, blocking ONLY at the iteration boundary (line ~639) and the met-terminal (line ~508) via short-poll loops that always re-check `stop_event` (never an unbounded wait; gate waits bounded by `max_wall_seconds`). Add `LoopGate` to `LoopSpec`. Surface new SSE events + control routes; render trace/control/gate UI on the existing session panel. No migration (gate config in JSON; control state is runtime).

**Tech Stack:** Python 3.10 (msgspec + dataclass + threading.Event, Ruff line-length=100), Litestar routes, pytest (`isolated_db`). Frontend: Vue 3 + TS, Vitest, vue-i18n (en/ko/ja/zh).

**Spec:** `docs/superpowers/specs/2026-06-20-unified-loops-sp3-observability-control-design.md`

---

## File structure

| File | Responsibility | Action |
|---|---|---|
| `backend/app/models/loop_spec.py` | `LoopGate` struct; `LoopState.human_gate`; legacy mapping | **Modify** |
| `backend/app/services/goal_loop_runner.py` | `_RunnerState` control fields; control fns; pause/gate/intervene wiring; enriched `get_runner_state` | **Modify** |
| `backend/app_litestar/routes/grd_routes.py` | pause/resume→runner; `loop/intervene` + `loop/gate-decision` routes; register | **Modify** |
| `frontend/src/services/api/grd.ts` | `LoopGate` type + `human_gate` on config; control client methods | **Modify** |
| `frontend/src/composables/useProjectSession.ts` | dispatch new SSE events (paused/resumed/awaiting_human/gate_resolved/intervened) | **Modify** |
| `frontend/src/components/grd/LoopTracePanel.vue` | per-iteration trace + control bar + gate card | **Create** |
| `frontend/src/components/sessions/ProjectSessionPanel.vue` | host `LoopTracePanel` | **Modify** |
| `frontend/src/locales/{en,ko,ja,zh}.json` | `loopControl.*` | **Modify** |
| Tests | per task | **Create** |

---

## Task 1: `LoopGate` + `LoopState.human_gate`

**Files:** Modify `backend/app/models/loop_spec.py`; Test `backend/tests/test_loop_spec_human_gate.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_loop_spec_human_gate.py
from app.models.loop_spec import LoopSpec, LoopGate


def test_human_gate_defaults_off():
    spec = LoopSpec.from_legacy_config({"goal": "g"}, execution_type="goal_loop")
    assert spec.state.human_gate is None


def test_human_gate_every_n_parses():
    spec = LoopSpec.from_legacy_config(
        {"goal": "g", "human_gate": {"mode": "every_n", "n": 3}}, execution_type="goal_loop")
    assert spec.state.human_gate == LoopGate(mode="every_n", n=3)


def test_human_gate_on_exit_parses_for_ralph():
    spec = LoopSpec.from_legacy_config(
        {"task_description": "t", "human_gate": {"mode": "on_exit"}}, execution_type="ralph")
    assert spec.state.human_gate.mode == "on_exit"
    assert spec.state.human_gate.n == 1  # default
```

- [ ] **Step 2: Run → FAIL** — `cd backend && uv run pytest tests/test_loop_spec_human_gate.py -q` (ImportError: LoopGate)

- [ ] **Step 3: Implement**

Add `GateMode = Literal["off", "every_n", "on_exit"]` near the other Literals, the struct after `QualityGate`:

```python
class LoopGate(msgspec.Struct, frozen=True):
    mode: GateMode = "off"
    n: int = 1
```

Add to `LoopState`: `human_gate: Optional[LoopGate] = None`. Add a builder + wire into BOTH branches of `from_legacy_config`:

```python
def _gate_cfg(c: dict) -> Optional[LoopGate]:
    hg = c.get("human_gate")
    if isinstance(hg, dict) and hg.get("mode") and hg.get("mode") != "off":
        return LoopGate(mode=hg["mode"], n=int(hg.get("n") or 1))
    return None
```

In each branch set `state = LoopState(..., human_gate=_gate_cfg(c))` (ralph branch keeps `context_policy`/`sandbox` args; goal_loop branch likewise).

- [ ] **Step 4: Run → PASS** — `cd backend && uv run pytest tests/test_loop_spec_human_gate.py tests/test_loop_spec.py tests/test_loop_spec_quality_gate.py -q`

- [ ] **Step 5: Commit** — `git commit -m "feat(loops): LoopGate human-gate on LoopState"`

---

## Task 2: `_RunnerState` control fields + control fns + enriched status

**Files:** Modify `backend/app/services/goal_loop_runner.py`; Test `backend/tests/test_goal_loop_control_api.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_goal_loop_control_api.py
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
```

- [ ] **Step 2: Run → FAIL** — `cd backend && uv run pytest tests/test_goal_loop_control_api.py -q`

- [ ] **Step 3: Implement**

Add to `_RunnerState` (after `last_commit`):

```python
    pause_event: threading.Event = field(default_factory=threading.Event)
    pending_note: Optional[str] = None
    awaiting_human: bool = False
    gate_decision: Optional[tuple] = None  # (decision, message)
```

Add a private getter + control fns (near `stop_runner`):

```python
def _get_state(session_id: str) -> Optional[_RunnerState]:
    with _runners_lock:
        return _runners.get(session_id)


def pause_runner(session_id: str) -> bool:
    st = _get_state(session_id)
    if st: st.pause_event.set()
    return st is not None


def resume_runner(session_id: str) -> bool:
    st = _get_state(session_id)
    if st: st.pause_event.clear()
    return st is not None


def intervene_runner(session_id: str, message: str) -> bool:
    st = _get_state(session_id)
    if st: st.pending_note = message
    return st is not None


def submit_gate_decision(session_id: str, decision: str, message: Optional[str] = None) -> bool:
    st = _get_state(session_id)
    if st: st.gate_decision = (decision, message)
    return st is not None
```

Enrich `get_runner_state` return with `total_cost_usd`, `total_tokens`, `max_cost_usd`, `max_tokens`, `paused: state.pause_event.is_set()`, `awaiting_human: state.awaiting_human`.

- [ ] **Step 4: Run → PASS** — `cd backend && uv run pytest tests/test_goal_loop_control_api.py -q`

- [ ] **Step 5: Commit** — `git commit -m "feat(loops): runner control API (pause/resume/intervene/gate) + enriched status"`

---

## Task 3: Pause hold + paused/resumed events

**Files:** Modify `backend/app/services/goal_loop_runner.py`; Test `backend/tests/test_goal_loop_pause_hold.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_goal_loop_pause_hold.py
import threading, time
from app.services import goal_loop_runner as glr


class _State:
    def __init__(self):
        self.pause_event = threading.Event()
        self.stop_event = threading.Event()
        self.iteration = 1


def test_returns_immediately_when_not_paused(monkeypatch):
    monkeypatch.setattr(glr.ProjectSessionManager, "_broadcast", lambda *a, **k: None)
    glr._wait_if_paused(_State(), "s")  # no hang


def test_blocks_until_resumed_then_returns(monkeypatch):
    monkeypatch.setattr(glr, "_PAUSE_POLL_SECONDS", 0.01)
    monkeypatch.setattr(glr.ProjectSessionManager, "_broadcast", lambda *a, **k: None)
    st = _State(); st.pause_event.set()
    t = threading.Thread(target=lambda: glr._wait_if_paused(st, "s")); t.start()
    time.sleep(0.05); assert t.is_alive()       # still held
    st.pause_event.clear(); t.join(timeout=2); assert not t.is_alive()


def test_breaks_out_on_stop(monkeypatch):
    monkeypatch.setattr(glr, "_PAUSE_POLL_SECONDS", 0.01)
    monkeypatch.setattr(glr.ProjectSessionManager, "_broadcast", lambda *a, **k: None)
    st = _State(); st.pause_event.set()
    t = threading.Thread(target=lambda: glr._wait_if_paused(st, "s")); t.start()
    time.sleep(0.05); st.stop_event.set(); t.join(timeout=2); assert not t.is_alive()
```

- [ ] **Step 2: Run → FAIL** — `cd backend && uv run pytest tests/test_goal_loop_pause_hold.py -q`

- [ ] **Step 3: Implement**

Add `_PAUSE_POLL_SECONDS = 0.5` near the other module constants, the helper:

```python
def _wait_if_paused(state, session_id: str) -> None:
    """Block at the iteration boundary while paused. Always re-checks
    stop_event so a paused loop stays stoppable (never an unbounded wait)."""
    if not state.pause_event.is_set():
        return
    ProjectSessionManager._broadcast(session_id, "goal_loop_paused", {"iteration": state.iteration})
    while state.pause_event.is_set() and not state.stop_event.is_set():
        time.sleep(_PAUSE_POLL_SECONDS)
    if not state.stop_event.is_set():
        ProjectSessionManager._broadcast(session_id, "goal_loop_resumed", {"iteration": state.iteration})
```

Wire it in `_run` immediately before the `_next_iteration(...)` call (line ~639):

```python
            _wait_if_paused(state, session_id)
            if state.stop_event.is_set():
                break
```

- [ ] **Step 4: Run → PASS** — `cd backend && uv run pytest tests/test_goal_loop_pause_hold.py tests/services/test_goal_loop_runner.py -q`

- [ ] **Step 5: Commit** — `git commit -m "feat(loops): true pause hold at iteration boundary + paused/resumed events"`

---

## Task 4: Mid-loop intervene (note prepend)

**Files:** Modify `backend/app/services/goal_loop_runner.py`; Test `backend/tests/test_goal_loop_intervene.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_goal_loop_intervene.py
from app.services.goal_loop_runner import _apply_pending_note


def test_prepends_note_and_clears():
    class S: pending_note = "use the cache"
    s = S()
    reason = _apply_pending_note(s, "tests still failing")
    assert reason.startswith("Operator note: use the cache")
    assert "tests still failing" in reason
    assert s.pending_note is None


def test_no_note_returns_reason_unchanged():
    class S: pending_note = None
    assert _apply_pending_note(S(), "x") == "x"
```

- [ ] **Step 2: Run → FAIL** — `cd backend && uv run pytest tests/test_goal_loop_intervene.py -q`

- [ ] **Step 3: Implement**

Add the helper:

```python
def _apply_pending_note(state, reason: str) -> str:
    """Consume an operator intervene/modify note (if any), prepending it to the
    next iteration's prompt reason so both carry and reset policies pick it up."""
    note = getattr(state, "pending_note", None)
    if not note:
        return reason
    state.pending_note = None
    return f"Operator note: {note}\n\n{reason}"
```

In `_run`, change the `_next_iteration(...)` call's `reason=` (line ~644) to `reason=_apply_pending_note(state, verdict.reason)`.

- [ ] **Step 4: Run → PASS** — `cd backend && uv run pytest tests/test_goal_loop_intervene.py tests/services/test_goal_loop_runner.py -q`

- [ ] **Step 5: Commit** — `git commit -m "feat(loops): mid-loop intervene — operator note prepended to next iteration"`

---

## Task 5: Human-gate checkpoints (every_n + on_exit)

**Files:** Modify `backend/app/services/goal_loop_runner.py`; Test `backend/tests/test_goal_loop_human_gate.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_goal_loop_human_gate.py
import threading, time
from app.services import goal_loop_runner as glr


class _State:
    def __init__(self):
        self.stop_event = threading.Event()
        self.gate_decision = None
        self.awaiting_human = False
        self.iteration = 2


def test_await_gate_returns_decision(monkeypatch):
    monkeypatch.setattr(glr, "_PAUSE_POLL_SECONDS", 0.01)
    monkeypatch.setattr(glr.ProjectSessionManager, "_broadcast", lambda *a, **k: None)
    st = _State()
    out = {}
    t = threading.Thread(target=lambda: out.update(r=glr._await_gate(st, "s", 2, "every 2", max_wall_seconds=999)))
    t.start(); time.sleep(0.05)
    assert st.awaiting_human is True
    st.gate_decision = ("modify", "add a test")
    t.join(timeout=2)
    assert out["r"] == ("modify", "add a test")
    assert st.awaiting_human is False


def test_await_gate_times_out_to_abort(monkeypatch):
    monkeypatch.setattr(glr, "_PAUSE_POLL_SECONDS", 0.01)
    monkeypatch.setattr(glr.ProjectSessionManager, "_broadcast", lambda *a, **k: None)
    st = _State()
    decision, _ = glr._await_gate(st, "s", 2, "x", max_wall_seconds=0)  # immediate timeout
    assert decision == "abort"


def test_gate_due_helper():
    from app.models.loop_spec import LoopGate
    assert glr._gate_due(LoopGate(mode="every_n", n=3), iteration_no=3) is True
    assert glr._gate_due(LoopGate(mode="every_n", n=3), iteration_no=4) is False
    assert glr._gate_due(None, iteration_no=3) is False
```

- [ ] **Step 2: Run → FAIL** — `cd backend && uv run pytest tests/test_goal_loop_human_gate.py -q`

- [ ] **Step 3: Implement**

Add helpers:

```python
def _gate_due(gate, iteration_no: int) -> bool:
    return bool(gate) and gate.mode == "every_n" and gate.n > 0 and iteration_no % gate.n == 0


def _await_gate(state, session_id: str, iteration_no: int, gate_reason: str, *, max_wall_seconds: int):
    """Hold for a human decision. Returns (decision, message). Bounded by
    max_wall_seconds (→ abort) and always responsive to stop_event."""
    import time as _t
    state.awaiting_human = True
    state.gate_decision = None
    entered = _t.time()
    ProjectSessionManager._broadcast(
        session_id, "goal_loop_awaiting_human", {"iteration": iteration_no, "gate_reason": gate_reason})
    while state.gate_decision is None and not state.stop_event.is_set():
        if _t.time() - entered > max_wall_seconds:
            state.awaiting_human = False
            return ("abort", "gate wait exceeded max_wall_seconds")
        _t.sleep(_PAUSE_POLL_SECONDS)
    state.awaiting_human = False
    decision, message = state.gate_decision or ("abort", "stopped")
    ProjectSessionManager._broadcast(session_id, "goal_loop_gate_resolved", {"decision": decision})
    return (decision, message)
```

Wire `every_n` at the advance boundary (after `_wait_if_paused`, before the note/advance):

```python
            hg = state.spec.state.human_gate
            if _gate_due(hg, iteration_no):
                decision, message = _await_gate(state, session_id, iteration_no,
                    gate_reason=f"every {hg.n} iterations", max_wall_seconds=max_wall_seconds)
                if decision == "abort":
                    _broadcast_end(session_id, reason="human_abort", detail=message or "operator aborted")
                    ProjectSessionManager.stop_session(session_id); break
                if decision == "modify" and message:
                    state.pending_note = message
```

Wire `on_exit` at the met-terminal (replace the `if _met_terminates(...)` block, line ~508):

```python
            if _met_terminates(met=verdict.met, confidence=verdict.confidence, gate=gate):
                hg = state.spec.state.human_gate
                if hg and hg.mode == "on_exit":
                    decision, message = _await_gate(state, session_id, iteration_no,
                        gate_reason="completion (met)", max_wall_seconds=max_wall_seconds)
                    if decision == "modify":
                        if message: state.pending_note = message
                        # human rejects 'done' → fall through and keep iterating
                    else:
                        end_reason = "human_abort" if decision == "abort" else "met"
                        _broadcast_end(session_id, reason=end_reason, detail=verdict.reason)
                        ProjectSessionManager.stop_session(session_id); break
                else:
                    _broadcast_end(session_id, reason="met", detail=verdict.reason)
                    ProjectSessionManager.stop_session(session_id); break
```

- [ ] **Step 4: Run → PASS** — `cd backend && uv run pytest tests/test_goal_loop_human_gate.py tests/services/test_goal_loop_runner.py tests/test_goal_loop_min_confidence.py -q`

- [ ] **Step 5: Commit** — `git commit -m "feat(loops): human-gate checkpoints (every_n + on_exit) with continue/modify/abort"`

---

## Task 6: Routes — pause/resume→runner, intervene, gate-decision

**Files:** Modify `backend/app_litestar/routes/grd_routes.py`; Test `backend/tests/test_loop_control_routes.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_loop_control_routes.py
from unittest.mock import patch
from app_litestar.routes import grd_routes as gr


def test_intervene_route_calls_runner():
    with patch.object(gr, "_ensure_project", lambda pid: {"id": pid}), \
         patch("app.services.goal_loop_runner.intervene_runner", return_value=True) as m:
        out = gr.loop_intervene("p", "sess", {"message": "do X"})
    m.assert_called_once_with("sess", "do X")
    assert out["ok"] is True


def test_gate_decision_route_calls_runner():
    with patch.object(gr, "_ensure_project", lambda pid: {"id": pid}), \
         patch("app.services.goal_loop_runner.submit_gate_decision", return_value=True) as m:
        out = gr.loop_gate_decision("p", "sess", {"decision": "continue"})
    m.assert_called_once_with("sess", "continue", None)
    assert out["ok"] is True


def test_gate_decision_rejects_bad_decision():
    import pytest
    from litestar.exceptions import ClientException
    with patch.object(gr, "_ensure_project", lambda pid: {"id": pid}):
        with pytest.raises(ClientException):
            gr.loop_gate_decision("p", "sess", {"decision": "nope"})
```

Note: route handlers are decorated; call the underlying function via `gr.loop_intervene.fn` if Litestar wraps it, else directly — the implementer confirms the call form against the existing `session_input` test in `test_litestar_grd.py`. (Sub-project #1/#2 verifiers hit the decorated-handler-not-directly-callable gotcha; if direct call fails, drive these via the TestClient like `test_litestar_grd.py` does.)

- [ ] **Step 2: Run → FAIL** — `cd backend && uv run pytest tests/test_loop_control_routes.py -q`

- [ ] **Step 3: Implement**

In `pause_session`/`resume_session` (lines 1398–1411), after the PSM call add best-effort runner control:

```python
    from app.services.goal_loop_runner import pause_runner  # resume_runner in resume_session
    pause_runner(session_id)
```

Add two routes (near `session_input`):

```python
@post("/{project_id:str}/sessions/{session_id:str}/loop/intervene", sync_to_thread=False)
def loop_intervene(project_id: str, session_id: str, data: dict) -> dict[str, Any]:
    _ensure_project(project_id)
    message = (data or {}).get("message")
    if not message:
        raise ClientException(detail="message is required")
    from app.services.goal_loop_runner import intervene_runner
    return {"ok": intervene_runner(session_id, str(message))}


@post("/{project_id:str}/sessions/{session_id:str}/loop/gate-decision", sync_to_thread=False)
def loop_gate_decision(project_id: str, session_id: str, data: dict) -> dict[str, Any]:
    _ensure_project(project_id)
    body = data or {}
    decision = body.get("decision")
    if decision not in ("continue", "modify", "abort"):
        raise ClientException(detail="decision must be continue|modify|abort")
    from app.services.goal_loop_runner import submit_gate_decision
    return {"ok": submit_gate_decision(session_id, decision, body.get("message"))}
```

Register `loop_intervene, loop_gate_decision` in `grd_router.route_handlers`.

- [ ] **Step 4: Run → PASS** — `cd backend && uv run pytest tests/test_loop_control_routes.py tests/test_litestar_grd.py -k "loop or session or pause" -q`

- [ ] **Step 5: Commit** — `git commit -m "feat(loops): control routes — pause/resume→runner, loop/intervene, loop/gate-decision"`

---

## Task 7: Frontend — grd.ts control client + types

**Files:** Modify `frontend/src/services/api/grd.ts`; Test `frontend/src/services/api/__tests__/grd.loopcontrol.test.ts`

- [ ] **Step 1: Failing test**

```typescript
// frontend/src/services/api/__tests__/grd.loopcontrol.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
vi.mock('../client', () => ({ apiFetch: vi.fn() }));
import { apiFetch } from '../client';
import { grdApi } from '../grd';
const mock = () => apiFetch as ReturnType<typeof vi.fn>;
beforeEach(() => { vi.clearAllMocks(); (apiFetch as ReturnType<typeof vi.fn>).mockResolvedValue({}); });

describe('loop control client', () => {
  it('interveneLoop POSTs message', async () => {
    await grdApi.interveneLoop('p', 's', 'do X');
    expect(mock()).toHaveBeenCalledWith('/api/projects/p/sessions/s/loop/intervene',
      { method: 'POST', body: JSON.stringify({ message: 'do X' }) });
  });
  it('gateDecision POSTs decision + message', async () => {
    await grdApi.gateDecision('p', 's', 'modify', 'add test');
    expect(mock()).toHaveBeenCalledWith('/api/projects/p/sessions/s/loop/gate-decision',
      { method: 'POST', body: JSON.stringify({ decision: 'modify', message: 'add test' }) });
  });
});
```

- [ ] **Step 2: Run → FAIL** — `cd frontend && npx vitest run src/services/api/__tests__/grd.loopcontrol.test.ts`

- [ ] **Step 3: Implement**

In `grd.ts`: add `export interface LoopGate { mode: 'off' | 'every_n' | 'on_exit'; n?: number }`, add `human_gate?: LoopGate` to `GoalLoopConfig`, and methods on `grdApi`:

```typescript
  interveneLoop: (projectId: string, sessionId: string, message: string) =>
    apiFetch(`/api/projects/${projectId}/sessions/${sessionId}/loop/intervene`,
      { method: 'POST', body: JSON.stringify({ message }) }),
  gateDecision: (projectId: string, sessionId: string, decision: 'continue'|'modify'|'abort', message?: string) =>
    apiFetch(`/api/projects/${projectId}/sessions/${sessionId}/loop/gate-decision`,
      { method: 'POST', body: JSON.stringify({ decision, message }) }),
```

(`pauseSession`/`resumeSession` already exist — reuse for pause/resume.)

- [ ] **Step 4: Run → PASS** — `cd frontend && npx vitest run src/services/api/__tests__/grd.loopcontrol.test.ts`

- [ ] **Step 5: Commit** — `git commit -m "feat(loops): grd.ts loop-control client + LoopGate type"`

---

## Task 8: Frontend — SSE event dispatch for new control events

**Files:** Modify `frontend/src/composables/useProjectSession.ts`; Test `frontend/src/composables/__tests__/useProjectSession.control.test.ts`

- [ ] **Step 1: Failing test** — assert the composable exposes reactive state for the new events. Mirror the existing goal-iteration handler test pattern in the file's test suite (the implementer reads the existing `useProjectSession` test for the exact harness). Minimum:

```typescript
// asserts onLoopAwaitingHuman / paused refs update when the mapped SSE event fires.
// Use the same fake-EventSource harness the existing goal_iteration tests use.
```

- [ ] **Step 2: Run → FAIL**

- [ ] **Step 3: Implement** — in the SSE event switch (the `goal_iteration_*` block, lines ~224–286), add cases for `goal_loop_paused`/`goal_loop_resumed` (set `paused` ref), `goal_loop_awaiting_human` (set `awaitingHuman` + `gateReason` refs), `goal_loop_gate_resolved` (clear `awaitingHuman`), `goal_loop_intervened` (optional toast). Expose the new refs from the composable's return.

- [ ] **Step 4: Run → PASS** — `cd frontend && npx vitest run src/composables/__tests__/useProjectSession.control.test.ts`

- [ ] **Step 5: Commit** — `git commit -m "feat(loops): dispatch pause/resume/awaiting-human/gate SSE events"`

---

## Task 9: Frontend — LoopTracePanel (trace + control bar + gate card) + i18n

**Files:** Create `frontend/src/components/grd/LoopTracePanel.vue`; Modify `frontend/src/components/sessions/ProjectSessionPanel.vue`, `frontend/src/locales/{en,ko,ja,zh}.json`; Test `frontend/src/components/grd/__tests__/LoopTracePanel.test.ts`

- [ ] **Step 1: Failing test**

```typescript
// frontend/src/components/grd/__tests__/LoopTracePanel.test.ts
import { describe, it, expect, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import en from '../../../locales/en.json';

const calls = vi.hoisted(() => ({
  listGoalIterations: vi.fn().mockResolvedValue({ iterations: [
    { iteration: 1, verdict: 'not_met', confidence: 0.4, judge_source: 'llm', cost_usd: 0.01, tokens_total: 100 },
    { iteration: 2, verdict: 'met', confidence: 0.9, judge_source: 'llm', cost_usd: 0.02, tokens_total: 200 },
  ] }),
  pauseSession: vi.fn().mockResolvedValue({}), resumeSession: vi.fn().mockResolvedValue({}),
  interveneLoop: vi.fn().mockResolvedValue({}), gateDecision: vi.fn().mockResolvedValue({}),
}));
vi.mock('../../../services/api', async (o) => ({ ...(await o<any>()), grdApi: calls }));
import LoopTracePanel from '../LoopTracePanel.vue';

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en: { loopControl: en.loopControl } } as never });
const mountP = (props = {}) => mount(LoopTracePanel, { props: { projectId: 'p', sessionId: 's', awaitingHuman: false, ...props }, global: { plugins: [i18n] } });

describe('LoopTracePanel', () => {
  it('renders the per-iteration trace rows', async () => {
    const w = mountP(); await flushPromises();
    expect(calls.listGoalIterations).toHaveBeenCalledWith('p', 's');
    expect(w.findAll('[data-testid="loop-iter-row"]').length).toBe(2);
  });
  it('pause calls grdApi.pauseSession', async () => {
    const w = mountP(); await flushPromises();
    await w.find('[data-testid="loop-pause"]').trigger('click');
    expect(calls.pauseSession).toHaveBeenCalledWith('p', 's');
  });
  it('shows the gate card and Continue calls gateDecision', async () => {
    const w = mountP({ awaitingHuman: true }); await flushPromises();
    await w.find('[data-testid="gate-continue"]').trigger('click');
    expect(calls.gateDecision).toHaveBeenCalledWith('p', 's', 'continue', undefined);
  });
});
```

- [ ] **Step 2: Run → FAIL**

- [ ] **Step 3: Implement** — `LoopTracePanel.vue` props `{ projectId, sessionId, awaitingHuman, gateReason? }`; on mount call `grdApi.listGoalIterations`; render a row per iteration (`data-testid="loop-iter-row"`) showing iteration #, verdict, confidence, source/version, tokens, cost. Control bar: Pause (`loop-pause`→`pauseSession`), Resume (`resumeSession`), Stop (`stopSession`), Intervene (textarea→`interveneLoop`). Gate card (`v-if="awaitingHuman"`): Continue (`gate-continue`), Modify (textarea→`gateDecision('modify', msg)`), Abort. Host `<LoopTracePanel>` in `ProjectSessionPanel.vue` for goal-loop/ralph sessions, passing the `awaitingHuman`/`gateReason` from `useProjectSession`. Add `loopControl.*` i18n (en/ko/ja/zh, key-identical): `pause`, `resume`, `stop`, `intervene`, `interveneSend`, `awaitingHuman`, `gateContinue`, `gateModify`, `gateAbort`, `iteration`, `confidence`, `cost`, `tokens`.

- [ ] **Step 4: Run → PASS** — `cd frontend && npx vitest run src/components/grd/__tests__/LoopTracePanel.test.ts && npm run build`

- [ ] **Step 5: Commit** — `git commit -m "feat(loops): LoopTracePanel — per-iteration trace + control bar + human-gate card"`

---

## Task 10: Full verification

- [ ] **Step 1: Backend** — `cd backend && uv run pytest -q tests/test_loop_spec_human_gate.py tests/test_goal_loop_control_api.py tests/test_goal_loop_pause_hold.py tests/test_goal_loop_intervene.py tests/test_goal_loop_human_gate.py tests/test_loop_control_routes.py tests/services/test_goal_loop_runner.py tests/test_goal_loop_min_confidence.py tests/test_goal_loop_ouroboros.py tests/test_ralph_unified.py tests/test_loop_spec.py tests/test_litestar_grd.py` → all PASS.
- [ ] **Step 2: Frontend** — `cd frontend && npm run build && npm run test:run` → build clean; suite at the 7-failure baseline, no new failures.
- [ ] **Step 3: Finish branch** (superpowers:finishing-a-development-branch).

---

## Self-review

**Spec coverage:** §2a pause/resume → T2 (api) + T3 (hold). §2b status enrichment → T2. §2c intervene → T2 (api) + T4 (wiring). §2d human gates → T1 (spec) + T2 (decision api) + T5 (wiring). §2e events → T3/T5 (backend) + T8 (frontend dispatch). §2f trace → T9. §2g control bar → T9. §2h gate UI → T9. §2i client+i18n → T7 + T9. Verify → T10. ✅

**Placeholder scan:** backend tasks carry literal code + commands. T8's test is described against "the existing harness" rather than fully written — flagged: the implementer must read the existing `useProjectSession` goal-iteration test and mirror its fake-EventSource setup (the exact harness isn't reproduced here to avoid guessing its internals). T9's Vue component body is specified by behavior + required `data-testid`s + i18n keys rather than full template — acceptable for a UI component, the test pins the contract.

**Type consistency:** `LoopGate.mode` ∈ {off, every_n, on_exit} (T1↔T7); decision ∈ {continue, modify, abort} (T2↔T5↔T6↔T9); `_await_gate` returns `(decision, message)` consistent T5↔T2; `get_runner_state` enriched keys consistent T2↔T9 (`total_cost_usd`/`total_tokens`/`max_*`/`paused`/`awaiting_human`); `_apply_pending_note`/`pending_note` consistent T2↔T4↔T5. ✅

**Concurrency review:** every blocking helper (`_wait_if_paused`, `_await_gate`) loops on a poll interval and re-checks `stop_event` each pass — no unbounded waits; gate waits are additionally bounded by `max_wall_seconds`→abort. Pause/gate blocks sit at the iteration boundary (line ~639) and the met-terminal (line ~508), where the agent process is idle — no mid-turn interruption. Control fns target the stable `registry_key`, so they work under `context_policy=reset`. ✅
