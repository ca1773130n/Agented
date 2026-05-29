# Phase A — Complete the Evidence — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the three *real* Phase A evidence gaps (per the codex-verified re-baseline): fix the workflow session-capture id mismatch, enrich the existing `detect_h2/h3/h4` failure detectors with confidence/severity + wider Environment-Contract / Trajectory coverage, and make the already-working LLM takeaway extractor provider-kind agnostic instead of codex-only.

**Architecture:** All three gaps are *modifications* to existing, working code — not greenfield builds. The detectors, the LLM extraction path (ON by default), and four of five session fetchers already exist and are correct. We change the one broken emit argument, add a uniform scoring + wider patterns to the detector layer, and introduce a small `provider_cli_map` util that the LLM path consumes (Phase A owns it; it cedes to Phase C's `harness_evolution_eval.py` per spine reconciliation #3). No DB schema changes — incident `confidence`/`severity` ride inside the existing `evidence_json` blob.

**Tech Stack:** Python 3.10, raw SQLite (`get_connection`), Pydantic v2, pytest with the `isolated_db` fixture, `unittest.mock` for subprocess/LLM patching, ruff line-length=100.

---

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `backend/app/services/workflow_execution_service.py` | **Modify** (line 666) | Emit the execution-row id, not the workflow-template id |
| `backend/app/services/harness_failure_annotator.py` | **Modify** (detectors + `_apply_priority_protocol`) | Add `_score_incident`, wider H2/H3/H4 patterns, uniform confidence/severity enrichment |
| `backend/app/services/provider_cli_map.py` | **Create** | provider-kind → LLM CLI argv template (Phase A owner; cedes to Phase C) |
| `backend/app/services/harness_takeaway_extractor.py` | **Modify** (`_extract_llm`, `extract_for_session`, run helper) | Provider-kind aware LLM extraction |
| `backend/tests/test_harness_workflow_capture.py` | **Create** | Workflow fetcher-contract + emit-arg regression |
| `backend/tests/test_harness_detectors_enrichment.py` | **Create** | Scoring + wider-pattern detector tests |
| `backend/tests/test_provider_cli_map.py` | **Create** | provider-kind → argv resolution |
| `backend/tests/test_takeaway_provider_kind.py` | **Create** | Provider-kind threading through extraction |

---

## Task 1: Fix the workflow session-capture id mismatch

**Files:**
- Modify: `backend/app/services/workflow_execution_service.py:666`
- Test: `backend/tests/test_harness_workflow_capture.py` (create)

**Context:** `_fetch_workflow(session_id)` (`harness_failure_annotator.py:215`) queries `workflow_executions WHERE id = ?` and `workflow_node_executions WHERE execution_id = ?` — both keyed on the **execution-row** id. But the completion emit at `workflow_execution_service.py:666` passes `workflow_id` (the **template** id), so both queries return empty and the workflow scope never produces evidence. `execution_id` is already in scope at that call site (used at lines 635-649).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_harness_workflow_capture.py
"""Regression: workflow session capture must key on the execution-row id."""
from __future__ import annotations

import pytest

from app.database import get_connection
from app.services.harness_failure_annotator import _fetch_workflow


@pytest.fixture()
def _wf_rows(isolated_db):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO workflow_executions (id, workflow_id, status) "
            "VALUES ('wfex-1', 'wf-tmpl-1', 'completed')"
        )
        conn.execute(
            "INSERT INTO workflow_node_executions (execution_id, output_json, error) "
            "VALUES ('wfex-1', '{\"result\": \"ok\"}', NULL)"
        )
        conn.commit()


def test_fetch_workflow_resolves_by_execution_row_id(_wf_rows):
    """Given the execution-row id, the fetcher returns the aggregated payload."""
    payload = _fetch_workflow("wfex-1")
    assert payload is not None
    assert "ok" in payload.text


def test_fetch_workflow_returns_none_for_template_id(_wf_rows):
    """Given the workflow TEMPLATE id (the current bug), nothing matches."""
    payload = _fetch_workflow("wf-tmpl-1")
    assert payload is None
```

- [ ] **Step 2: Run test to verify it fails / documents the contract**

Run: `cd backend && uv run pytest tests/test_harness_workflow_capture.py -v`
Expected: both tests PASS (they lock the fetcher contract — the fetcher is already correct). If `workflow_node_executions`/`workflow_executions` column names differ, the test errors on the INSERT — fix the column names to match the real schema (`uv run python -c "import sqlite3,app.database as d; ..."`) before proceeding. This test exists to lock the contract the emit must satisfy.

- [ ] **Step 3: Fix the emit argument**

In `backend/app/services/workflow_execution_service.py`, line 666, change:

```python
        emit_execution_complete("workflow", workflow_id, final_status, output_data)
```

to:

```python
        # Capture keys on the execution-row id (workflow_executions.id), NOT the
        # workflow template id — see _fetch_workflow in harness_failure_annotator.
        emit_execution_complete("workflow", execution_id, final_status, output_data)
```

- [ ] **Step 4: Add the emit-argument regression test**

```python
# Append to backend/tests/test_harness_workflow_capture.py
import inspect
from app.services import workflow_execution_service as wes


def test_workflow_emit_passes_execution_id_not_template_id():
    """Guard: the completion emit must pass execution_id, not workflow_id."""
    src = inspect.getsource(wes)
    assert 'emit_execution_complete("workflow", execution_id' in src, (
        "workflow completion must emit the execution-row id"
    )
    assert 'emit_execution_complete("workflow", workflow_id' not in src
```

- [ ] **Step 5: Run + commit**

Run: `cd backend && uv run pytest tests/test_harness_workflow_capture.py -v`
Expected: all three PASS.

```bash
git add backend/app/services/workflow_execution_service.py backend/tests/test_harness_workflow_capture.py
git commit -m "fix(life-harness): workflow capture emits execution-row id, not template id"
```

---

## Task 2: Add uniform confidence/severity scoring to incidents

**Files:**
- Modify: `backend/app/services/harness_failure_annotator.py` (add `_score_incident`, call it in `_apply_priority_protocol`)
- Test: `backend/tests/test_harness_detectors_enrichment.py` (create)

**Context:** Detectors emit `{layer, kind, event_index, evidence}` dicts with no confidence/severity. We attach both inside `evidence` (no DB migration — `evidence_json` already stores arbitrary structure). Scoring is keyed by `kind`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_harness_detectors_enrichment.py
"""Detector enrichment: confidence + severity, wider H2/H3/H4 coverage."""
from __future__ import annotations

from app.services.harness_failure_annotator import (
    TurnEvent,
    _apply_priority_protocol,
)


def _tool_result(idx: int, error: str) -> TurnEvent:
    return TurnEvent(index=idx, role="tool_result", tool_error=error)


def test_incidents_carry_confidence_and_severity():
    events = [_tool_result(0, "missing required argument: path")]
    out = _apply_priority_protocol(events, outcome="failed")
    assert out, "expected an h2_invalid_tool_call incident"
    ev = out[0]["evidence"]
    assert 0.0 <= ev["confidence"] <= 1.0
    assert ev["severity"] in ("low", "medium", "high", "critical")


def test_invalid_tool_call_scored_high():
    out = _apply_priority_protocol(
        [_tool_result(0, "unknown argument: foo")], outcome="failed",
    )
    ev = out[0]["evidence"]
    assert ev["confidence"] >= 0.9
    assert ev["severity"] == "high"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_harness_detectors_enrichment.py::test_incidents_carry_confidence_and_severity tests/test_harness_detectors_enrichment.py::test_invalid_tool_call_scored_high -v`
Expected: FAIL with `KeyError: 'confidence'`.

- [ ] **Step 3: Write minimal implementation**

Add to `backend/app/services/harness_failure_annotator.py` (above `_apply_priority_protocol`):

```python
# (confidence, severity) keyed by incident kind. Unknown kinds fall back to
# a low-confidence general score.
_INCIDENT_SCORES: dict[str, tuple[float, str]] = {
    "h2_invalid_tool_call": (0.95, "high"),
    "h2_tool_in_content": (0.55, "low"),
    "h2_repeated_tool_failure": (0.90, "high"),
    "h3_contract_violation": (0.80, "medium"),
    "h3_setup_failure": (0.90, "high"),
    "h3_missing_file": (0.70, "medium"),
    "h3_permission_denied": (0.90, "high"),
    "h4_repeat_action": (0.75, "medium"),
    "h4_stagnation": (0.55, "low"),
    "h4_budget_exhausted": (0.85, "high"),
    "h4_abandoned_goal": (0.60, "medium"),
    "general_unclassified": (0.40, "low"),
}


def _score_incident(incident: dict) -> dict:
    """Attach confidence + severity into the incident's evidence blob."""
    conf, sev = _INCIDENT_SCORES.get(incident.get("kind", ""), (0.40, "low"))
    evidence = dict(incident.get("evidence") or {})
    evidence.setdefault("confidence", conf)
    evidence.setdefault("severity", sev)
    incident["evidence"] = evidence
    return incident
```

Then, in `_apply_priority_protocol`, change the final `return out` to score every incident first:

```python
    return [_score_incident(inc) for inc in out]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_harness_detectors_enrichment.py -v`
Expected: the two scoring tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/harness_failure_annotator.py backend/tests/test_harness_detectors_enrichment.py
git commit -m "feat(annotator): uniform confidence/severity scoring on incidents"
```

---

## Task 3: Widen H3 to cover Environment-Contract failures

**Files:**
- Modify: `backend/app/services/harness_failure_annotator.py` (`detect_h3`)
- Test: `backend/tests/test_harness_detectors_enrichment.py`

**Context:** `detect_h3` today only catches `h3_contract_violation` + `h3_setup_failure`. The design's H3 (Environment Contract) also covers missing files and permission errors.

- [ ] **Step 1: Write the failing test**

```python
# Append to backend/tests/test_harness_detectors_enrichment.py

def test_h3_missing_file_detected():
    out = _apply_priority_protocol(
        [_tool_result(0, "ENOENT: no such file or directory, open '/tmp/x'")],
        outcome="failed",
    )
    kinds = {i["kind"] for i in out}
    assert "h3_missing_file" in kinds


def test_h3_permission_denied_detected():
    out = _apply_priority_protocol(
        [_tool_result(0, "EACCES: permission denied, open '/etc/shadow'")],
        outcome="failed",
    )
    kinds = {i["kind"] for i in out}
    assert "h3_permission_denied" in kinds
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_harness_detectors_enrichment.py::test_h3_missing_file_detected tests/test_harness_detectors_enrichment.py::test_h3_permission_denied_detected -v`
Expected: FAIL (kinds not present).

- [ ] **Step 3: Write minimal implementation**

In `detect_h3`, inside the `if ev.role == "tool_result" and ev.tool_error:` block, after the existing `elif ... h3_setup_failure` branch, add:

```python
            elif "permission denied" in err or "eacces" in err:
                incidents.append({
                    "layer": "h3",
                    "kind": "h3_permission_denied",
                    "event_index": ev.index,
                    "evidence": {"error": ev.tool_error[:240]},
                })
            elif (
                "no such file or directory" in err
                or "enoent" in err
                or "file not found" in err
            ):
                incidents.append({
                    "layer": "h3",
                    "kind": "h3_missing_file",
                    "event_index": ev.index,
                    "evidence": {"error": ev.tool_error[:240]},
                })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_harness_detectors_enrichment.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/harness_failure_annotator.py backend/tests/test_harness_detectors_enrichment.py
git commit -m "feat(annotator): H3 Environment-Contract detectors (missing file, permission denied)"
```

---

## Task 4: Add H2 repeated-tool-failure and H4 abandoned-goal detectors

**Files:**
- Modify: `backend/app/services/harness_failure_annotator.py` (`detect_h2`, `detect_h4`)
- Test: `backend/tests/test_harness_detectors_enrichment.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to backend/tests/test_harness_detectors_enrichment.py

def _assistant(idx: int, text: str = "", tool: str | None = None) -> TurnEvent:
    return TurnEvent(index=idx, role="assistant", content_text=text, tool_name=tool)


def test_h2_repeated_tool_failure_detected():
    # Same tool errors twice → repeated-failure signal.
    events = [
        _tool_result(0, "bash: boom: command failed"),
        _tool_result(1, "bash: boom: command failed"),
    ]
    out = _apply_priority_protocol(events, outcome="failed")
    assert "h2_repeated_tool_failure" in {i["kind"] for i in out}


def test_h4_abandoned_goal_detected():
    events = [
        _assistant(0, "I can't continue, giving up on this task."),
    ]
    out = _apply_priority_protocol(events, outcome="failed")
    assert "h4_abandoned_goal" in {i["kind"] for i in out}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_harness_detectors_enrichment.py::test_h2_repeated_tool_failure_detected tests/test_harness_detectors_enrichment.py::test_h4_abandoned_goal_detected -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

In `detect_h2`, before `return incidents`, add a repeated-failure pass:

```python
    # Repeated identical tool errors → systemic failure, not a one-off.
    err_counts: dict[str, int] = {}
    err_first: dict[str, int] = {}
    for ev in events:
        if ev.role == "tool_result" and ev.tool_error:
            key = ev.tool_error.strip().lower()[:120]
            err_counts[key] = err_counts.get(key, 0) + 1
            err_first.setdefault(key, ev.index)
    for key, count in err_counts.items():
        if count >= 2:
            incidents.append({
                "layer": "h2",
                "kind": "h2_repeated_tool_failure",
                "event_index": err_first[key],
                "evidence": {"error": key, "count": count},
            })
```

In `detect_h4`, before `return incidents`, add abandoned-goal detection:

```python
    _ABANDON_PHRASES = (
        "i can't continue", "i cannot continue", "unable to proceed",
        "giving up", "cannot complete", "i give up",
    )
    for ev in events:
        if ev.role == "assistant" and ev.content_text:
            low = ev.content_text.lower()
            if any(p in low for p in _ABANDON_PHRASES):
                incidents.append({
                    "layer": "h4",
                    "kind": "h4_abandoned_goal",
                    "event_index": ev.index,
                    "evidence": {"snippet": ev.content_text[:240]},
                })
                break
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_harness_detectors_enrichment.py -v`
Expected: all enrichment tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/harness_failure_annotator.py backend/tests/test_harness_detectors_enrichment.py
git commit -m "feat(annotator): H2 repeated-tool-failure + H4 abandoned-goal detectors"
```

---

## Task 5: Create the provider-kind → LLM CLI map

**Files:**
- Create: `backend/app/services/provider_cli_map.py`
- Test: `backend/tests/test_provider_cli_map.py` (create)

**Context:** Spine reconciliation #3 — canonical taxonomy is **provider-kind** (`anthropic/openai/gemini/ollama`). This util returns an argv template with a `{PROMPT}` placeholder, matching the existing `_llm_codex_cmd()` convention. Phase A owns it; it cedes to Phase C's `harness_evolution_eval.py` later (the function signature is kept stable so the migration is a one-line import change).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_provider_cli_map.py
import pytest

from app.services.provider_cli_map import (
    SUPPORTED_PROVIDER_KINDS,
    resolve_llm_cmd,
)


def test_supported_kinds_are_the_four_providers():
    assert set(SUPPORTED_PROVIDER_KINDS) == {"anthropic", "openai", "gemini", "ollama"}


@pytest.mark.parametrize(
    "kind, head",
    [("anthropic", "claude"), ("openai", "codex"), ("gemini", "gemini"), ("ollama", "ollama")],
)
def test_resolve_llm_cmd_head(kind, head):
    cmd = resolve_llm_cmd(kind)
    assert cmd[0] == head
    assert "{PROMPT}" in cmd


def test_resolve_llm_cmd_env_override(monkeypatch):
    monkeypatch.setenv("AGENTED_TAKEAWAY_ANTHROPIC_CMD", "claude --model opus -p {PROMPT}")
    cmd = resolve_llm_cmd("anthropic")
    assert cmd == ["claude", "--model", "opus", "-p", "{PROMPT}"]


def test_resolve_llm_cmd_unknown_raises():
    with pytest.raises(ValueError, match="unknown provider_kind"):
        resolve_llm_cmd("deepseek")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_provider_cli_map.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.provider_cli_map`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/provider_cli_map.py
"""provider-kind → LLM CLI argv template.

Canonical taxonomy: provider-kind (anthropic/openai/gemini/ollama) — see
docs/superpowers/specs/2026-05-29-life-harness-completion-design.md
reconciliation #3. Phase A owns this; when Phase C ships, the same
``resolve_llm_cmd`` moves to harness_evolution_eval.py and callers update
their import only. Templates carry a ``{PROMPT}`` placeholder substituted by
the caller (same convention as the existing _llm_codex_cmd()).
"""
from __future__ import annotations

import os
import shlex

SUPPORTED_PROVIDER_KINDS = ("anthropic", "openai", "gemini", "ollama")

_DEFAULT_TEMPLATES: dict[str, list[str]] = {
    "anthropic": ["claude", "-p", "{PROMPT}"],
    "openai": ["codex", "exec", "--skip-git-repo-check", "{PROMPT}"],
    "gemini": ["gemini", "-p", "{PROMPT}"],
    "ollama": ["ollama", "run", "{MODEL}", "{PROMPT}"],
}

_DEFAULT_MODELS: dict[str, str] = {"ollama": "llama3"}


def resolve_llm_cmd(provider_kind: str, model_override: str | None = None) -> list[str]:
    """Return the argv template (with ``{PROMPT}``) for a provider kind.

    Per-provider override via ``AGENTED_TAKEAWAY_<PROVIDER>_CMD`` (e.g.
    ``AGENTED_TAKEAWAY_ANTHROPIC_CMD``). ``{MODEL}`` in a template is filled
    from ``model_override`` or the provider default.
    """
    if provider_kind not in _DEFAULT_TEMPLATES:
        raise ValueError(f"unknown provider_kind: {provider_kind!r}")

    override = os.environ.get(f"AGENTED_TAKEAWAY_{provider_kind.upper()}_CMD")
    if override:
        try:
            template = shlex.split(override)
        except ValueError:
            template = list(_DEFAULT_TEMPLATES[provider_kind])
    else:
        template = list(_DEFAULT_TEMPLATES[provider_kind])

    model = model_override or _DEFAULT_MODELS.get(provider_kind)
    if model is not None:
        template = [model if part == "{MODEL}" else part for part in template]
    return template
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_provider_cli_map.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/provider_cli_map.py backend/tests/test_provider_cli_map.py
git commit -m "feat(provider-cli-map): provider-kind→LLM argv util (Phase A owner, cedes to Phase C)"
```

---

## Task 6: Make the LLM extraction path provider-kind aware

**Files:**
- Modify: `backend/app/services/harness_takeaway_extractor.py` (`_run_codex_for_extraction` → generalized runner; `_extract_llm` gains `provider_kind`)
- Test: `backend/tests/test_takeaway_provider_kind.py` (create)

**Context:** `_extract_llm` (line 535) builds its command via `_llm_codex_cmd()` (codex-only) and runs it via `_run_codex_for_extraction`. We generalize: `_extract_llm` accepts `provider_kind` (default `"anthropic"`) + `model_override`, builds the command via `resolve_llm_cmd`, and runs it via a renamed `_run_llm_for_extraction(prompt, *, cmd_template, timeout)`. Tests patch `_run_llm_for_extraction`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_takeaway_provider_kind.py
"""Provider-kind threading through LLM takeaway extraction."""
from __future__ import annotations

from unittest.mock import patch

from app.services import harness_takeaway_extractor as tx
from app.services.harness_failure_annotator import SessionPayload


def _payload(text: str) -> SessionPayload:
    return SessionPayload(text=text, backend_type="claude", project_id="proj-1", outcome="completed")


def test_extract_llm_uses_provider_cmd(monkeypatch):
    """_extract_llm builds its command from resolve_llm_cmd(provider_kind)."""
    monkeypatch.setenv("AGENTED_TAKEAWAY_LLM", "1")
    captured = {}

    def _fake_run(prompt, *, cmd_template, timeout):
        captured["cmd_template"] = cmd_template
        return "[]"

    big_text = "x" * 5000  # exceed _llm_min_text_bytes
    with patch.object(tx, "_run_llm_for_extraction", _fake_run):
        tx._extract_llm("super_agent", "s-1", "proj-1", _payload(big_text),
                        provider_kind="gemini")

    assert captured["cmd_template"][0] == "gemini"


def test_extract_llm_disabled_returns_empty(monkeypatch):
    monkeypatch.setenv("AGENTED_TAKEAWAY_LLM", "0")
    with patch.object(tx, "_run_llm_for_extraction") as m:
        out = tx._extract_llm("super_agent", "s-1", "proj-1", _payload("x" * 5000),
                              provider_kind="anthropic")
    assert out == []
    m.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_takeaway_provider_kind.py -v`
Expected: FAIL — `_run_llm_for_extraction` doesn't exist and `_extract_llm` has no `provider_kind` kwarg.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/services/harness_takeaway_extractor.py`:

(a) Add the import near the top with the other service imports:

```python
from app.services.provider_cli_map import resolve_llm_cmd
```

(b) Rename `_run_codex_for_extraction` to `_run_llm_for_extraction` and have it take the command template as a parameter (replaces the internal `_llm_codex_cmd()` call):

```python
def _run_llm_for_extraction(prompt: str, *, cmd_template: list[str], timeout: int) -> str:
    """Invoke the provider CLI with the extraction prompt; return stdout.

    Mockable: tests patch this function to return canned JSON.
    """
    if "{PROMPT}" in cmd_template:
        cmd = [prompt if part == "{PROMPT}" else part for part in cmd_template]
        stdin_input = None
    else:
        cmd = list(cmd_template)
        stdin_input = prompt

    try:
        result = subprocess.run(
            cmd,
            cwd=tempfile.gettempdir(),
            input=stdin_input,
            timeout=timeout,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"LLM CLI not found ({cmd_template[0]})") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"LLM extraction timed out after {timeout}s") from exc
    if result.returncode != 0:
        err = (result.stderr or "").strip()
        raise RuntimeError(f"LLM extraction exited {result.returncode}: {err[:300]}")
    return result.stdout or ""
```

(c) Update `_extract_llm`'s signature and the run call:

```python
def _extract_llm(
    session_kind: str,
    session_id: str,
    project_id: Optional[str],
    payload: SessionPayload,
    *,
    provider_kind: str = "anthropic",
    model_override: Optional[str] = None,
) -> list[dict[str, Any]]:
```

Inside it, replace the `raw_output = _run_codex_for_extraction(prompt, timeout=_llm_timeout())` line with:

```python
    cmd_template = resolve_llm_cmd(provider_kind, model_override)
    try:
        raw_output = _run_llm_for_extraction(
            prompt, cmd_template=cmd_template, timeout=_llm_timeout(),
        )
    except RuntimeError as exc:
        logger.warning("takeaway LLM: %s", exc)
        return []
```

(d) Delete the now-unused `_llm_codex_cmd()` function (and its `AGENTED_TAKEAWAY_CODEX_CMD` reference) — the `openai` provider template preserves the old codex default, and `AGENTED_TAKEAWAY_OPENAI_CMD` is the override path.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_takeaway_provider_kind.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/harness_takeaway_extractor.py backend/tests/test_takeaway_provider_kind.py
git commit -m "feat(takeaway): provider-kind aware LLM extraction (was codex-only)"
```

---

## Task 7: Thread provider-kind through `extract_for_session`

**Files:**
- Modify: `backend/app/services/harness_takeaway_extractor.py` (`extract_for_session`, `on_session_complete`, add `_default_provider_kind`)
- Test: `backend/tests/test_takeaway_provider_kind.py`

**Context:** `extract_for_session` (line 1009) calls `_extract_llm(...)` with no provider. Add a `provider_kind` parameter defaulting to a resolver: env `AGENTED_TAKEAWAY_PROVIDER` else `"anthropic"`. (Per-project backend resolution is a deliberate follow-up — keep this bounded; the resolver is the single seam to extend later.)

- [ ] **Step 1: Write the failing test**

```python
# Append to backend/tests/test_takeaway_provider_kind.py
from unittest.mock import patch


def test_extract_for_session_passes_provider_to_llm(monkeypatch, isolated_db):
    monkeypatch.setenv("AGENTED_TAKEAWAY_PROVIDER", "openai")
    seen = {}

    def _fake_llm(sk, sid, pid, payload, *, provider_kind="anthropic", model_override=None):
        seen["provider_kind"] = provider_kind
        return []

    fake_payload = SessionPayload(text="x" * 5000, backend_type="claude",
                                  project_id="proj-1", outcome="completed")
    with patch.object(tx, "_FETCHERS", {"super_agent": lambda _id: fake_payload}), \
         patch.object(tx, "_extract_heuristic", lambda *a, **k: []), \
         patch.object(tx, "_extract_llm", _fake_llm):
        tx.extract_for_session("super_agent", "s-1", project_id="proj-1")

    assert seen["provider_kind"] == "openai"


def test_default_provider_kind_falls_back_to_anthropic(monkeypatch):
    monkeypatch.delenv("AGENTED_TAKEAWAY_PROVIDER", raising=False)
    assert tx._default_provider_kind("proj-1") == "anthropic"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_takeaway_provider_kind.py::test_extract_for_session_passes_provider_to_llm tests/test_takeaway_provider_kind.py::test_default_provider_kind_falls_back_to_anthropic -v`
Expected: FAIL — `_default_provider_kind` missing; provider not threaded.

- [ ] **Step 3: Write minimal implementation**

Add the resolver and thread it through. In `harness_takeaway_extractor.py`:

```python
def _default_provider_kind(project_id: Optional[str]) -> str:
    """Resolve the provider kind for extraction. Single seam to extend with
    per-project backend lookup later; for now env override → anthropic."""
    return os.environ.get("AGENTED_TAKEAWAY_PROVIDER", "anthropic")
```

Update `extract_for_session` to accept and pass the provider kind:

```python
def extract_for_session(
    session_kind: str,
    session_id: str,
    *,
    project_id: Optional[str] = None,
    provider_kind: Optional[str] = None,
) -> list[str]:
```

and inside, after `resolved_project_id` is computed, replace the `_extract_llm(...)` call with:

```python
    resolved_provider = provider_kind or _default_provider_kind(resolved_project_id)
    llm = _extract_llm(
        session_kind, session_id, resolved_project_id, payload,
        provider_kind=resolved_provider,
    )
```

(`on_session_complete` needs no change — it calls `extract_for_session` without `provider_kind`, so the default resolver applies.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_takeaway_provider_kind.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/harness_takeaway_extractor.py backend/tests/test_takeaway_provider_kind.py
git commit -m "feat(takeaway): resolve provider-kind in extract_for_session (env→anthropic default)"
```

---

## Task 8: Full verification gate

**Files:** none — runs the three project gates.

- [ ] **Step 1: Full backend suite**

Run: `cd backend && uv run pytest`
Expected: all pass (0 failures/errors). In particular the pre-existing annotator + takeaway tests still pass (no regression from the detector enrichment or the `_run_codex_for_extraction`→`_run_llm_for_extraction` rename — grep the test suite for `_run_codex_for_extraction` and update any remaining references as part of this step if present).

- [ ] **Step 2: Ruff format**

Run: `cd backend && uv run ruff format --check .`
Expected: clean. If not: `uv run ruff format .` then `git commit -am "style: ruff format"`.

- [ ] **Step 3: Frontend suite (no frontend changes, but the gate is mandatory)**

Run: `cd frontend && npm run test:run`
Expected: all pass.

- [ ] **Step 4: Build**

Run: `just build`
Expected: vue-tsc + vite build succeed.

- [ ] **Step 5: Tag**

```bash
git tag life-harness-phaseA-complete
```
