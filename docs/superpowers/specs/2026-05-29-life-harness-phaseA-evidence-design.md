# 2026-05-29 Life-Harness Phase A Evidence Design

Design-only plan for completing the "signal in" side of the self-improvement loop. This document is based on the current implementation in `/Users/neo/Developer/Projects/Agented` as of 2026-05-29 and names only buildable backend changes.

## Gap 1: Session Capture For Workflow And Team Session Scopes

### (a) Current state with verified evidence

The session-completion channel is wired during Litestar startup. `backend/app_litestar/lifecycle.py:365-368` imports `register_session_handler` and `harness_failure_annotator.on_session_complete`, then registers the annotator. `backend/app_litestar/lifecycle.py:377-382` registers `harness_takeaway_extractor.on_session_complete` on the same channel.

The channel contract is session-scoped: `backend/app/services/execution_events.py:48-54` defines `emit_session_complete(session_kind, session_id, project_id, status, output)`. The legacy bridge maps `entity_type="workflow"` to `session_kind="workflow"` at `backend/app/services/execution_events.py:81-84` and emits with `project_id=None` at `backend/app/services/execution_events.py:111-122`.

The annotator fetcher registry already contains all five expected scopes:

```python
_FETCHERS: dict[str, SessionFetcher] = {
    "trigger_execution": _fetch_trigger_execution,
    "super_agent": _fetch_super_agent_session,
    "project_session": _fetch_project_session,
    "workflow": _fetch_workflow,
    "team_session": _fetch_team_session,
}
```

This is verified at `backend/app/services/harness_failure_annotator.py:293-299`.

The workflow scope is registered but broken by an identifier mismatch. `backend/app/services/workflow_execution_service.py:332-338` receives both `execution_id` and `workflow_id` in `_run_workflow`. Node rows are written with `execution_id` at `backend/app/services/workflow_execution_service.py:471-476`, and the final workflow execution row is updated with `execution_id` at `backend/app/services/workflow_execution_service.py:635-650`. However, completion emits `workflow_id` instead of `execution_id` at `backend/app/services/workflow_execution_service.py:666`:

```python
emit_execution_complete("workflow", workflow_id, final_status, output_data)
```

The current workflow fetcher queries `workflow_executions.id = ?` and `workflow_node_executions.execution_id = ?` at `backend/app/services/harness_failure_annotator.py:219-227`. Because the emitted `session_id` is `workflow_id`, `_fetch_workflow()` usually returns `None` unless a workflow id accidentally equals a workflow execution id.

The workflow DB schema confirms the correct execution key is `workflow_executions.id`, while the parent workflow key is `workflow_executions.workflow_id`: `backend/app/db/schema/_workflows.py:35-46`. Node transcript material lives in `workflow_node_executions.output_json` and `workflow_node_executions.error`, keyed by `workflow_node_executions.execution_id`: `backend/app/db/schema/_workflows.py:50-62`.

The team-session scope is registered and has a durable backing table. `backend/app/db/schema/_team_executions.py:18-30` defines `team_executions.id`, `team_id`, `topology`, `trigger_type`, `project_id`, `message`, `status`, `error`, and `execution_ids`. `backend/app/services/team_execution_service.py:235-241` emits `session_kind="team_session"` with `session_id=team_exec_id` and `output={"execution_ids": execution_ids or []}`. `backend/app/db/team_executions.py:108-126` decodes `execution_ids` from JSON for callers.

The current team fetcher at `backend/app/services/harness_failure_annotator.py:244-288` reads `team_executions` through `get_team_execution()`, then fetches component `execution_logs.stdout_log` rows with `execution_id IN (...)` at `backend/app/services/harness_failure_annotator.py:269-275`. The execution-log schema confirms `execution_logs.execution_id`, `backend_type`, `stdout_log`, `stderr_log`, and `status` at `backend/app/db/schema/_core.py:60-84`.

The team fetcher has two issues:

1. It concatenates raw `stdout_log` strings without normalizing JSON arrays to JSONL. Existing trigger fetcher uses `_to_claude_jsonl()` at `backend/app/services/harness_failure_annotator.py:82-87`, and `_to_claude_jsonl()` explicitly handles `execution_logs.stdout_log` arrays at `backend/app/services/harness_failure_annotator.py:90-172`.
2. It returns `backend_type` from the last component row with a non-empty backend. If a mixed-backend team runs, `annotate_from_text()` only parses when `backend_type == "claude"` at `backend/app/services/harness_failure_annotator.py:579-583`, so one codex/gemini/opencode component can suppress Claude-parsable logs from other components.

### (b) Recommended approach and alternatives

Recommended approach:

1. Fix workflow emission to use the workflow execution id as the session id:

```python
emit_session_complete(
    "workflow",
    execution_id,
    None,
    final_status,
    output_data,
)
```

Use direct `emit_session_complete()` rather than the legacy `emit_execution_complete()` bridge because `_run_workflow()` has the execution id and the five-argument API is the canonical contract.

2. Rename `_fetch_workflow()` to `_fetch_workflow_execution()` and keep a compatibility alias only if needed by tests. The fetcher should continue to key by `workflow_executions.id`, not `workflow_id`.

3. Normalize workflow node output into Claude-compatible JSONL when possible. For each node row, add a text event containing `node_id`, `node_type`, `status`, `output_json`, and `error`. If `output_json` decodes to a `WorkflowMessage` with `text`, preserve that text as assistant content. If the node has `error`, create a synthetic `tool_result` with `is_error=true` so H2/H3/H4 detectors can classify it.

4. Normalize each team component log independently with `_to_claude_jsonl()` before concatenation. If multiple backends appear, parse supported Claude-shaped logs instead of dropping all events because the last backend was not `claude`.

Alternative 1: Make `_fetch_workflow_execution()` accept either `workflow_executions.id` or `workflow_id` and, when given a parent workflow id, select the latest execution. Trade-off: this hides the event-contract bug and can annotate the wrong execution if multiple runs complete close together.

Alternative 2: Add an explicit `session_source_refs` table that maps every emitted `(session_kind, session_id)` to underlying execution rows. Trade-off: stronger long-term observability model, but overkill for Phase A because the current tables already contain the required transcript/log columns.

### (c) Specific files to create or modify

Modify:

- `backend/app/services/workflow_execution_service.py`: emit `"workflow"` with `execution_id`, not `workflow_id`.
- `backend/app/services/harness_failure_annotator.py`: replace `_fetch_workflow()` with `_fetch_workflow_execution()`, update `_FETCHERS["workflow"]`, normalize workflow and team-session logs.
- `backend/app/services/harness_takeaway_extractor.py`: consume the improved fetchers; no separate workflow/team fetcher should be duplicated here because it imports `_FETCHERS` at `backend/app/services/harness_takeaway_extractor.py:41-46`.

Tests to add or modify:

- `backend/tests/.../test_harness_failure_annotator.py`
- `backend/tests/.../test_harness_takeaway_extractor.py`
- `backend/tests/.../test_workflow_execution_events.py`
- `backend/tests/.../test_team_execution_session_capture.py`

No DB migration is required for Gap 1.

### (d) Data-model/schema changes

No schema change is required.

Verified existing tables and columns:

- `workflow_executions.id`, `workflow_executions.workflow_id`, `workflow_executions.status`, `workflow_executions.output_json`, `workflow_executions.error`: `backend/app/db/schema/_workflows.py:35-46`.
- `workflow_node_executions.execution_id`, `node_id`, `node_type`, `status`, `input_json`, `output_json`, `error`: `backend/app/db/schema/_workflows.py:50-62`.
- `team_executions.id`, `project_id`, `status`, `error`, `execution_ids`: `backend/app/db/schema/_team_executions.py:18-30`.
- `execution_logs.execution_id`, `backend_type`, `status`, `stdout_log`, `stderr_log`: `backend/app/db/schema/_core.py:60-84`.

### (e) Key function signatures

```python
from typing import Any, Optional

def _fetch_workflow_execution(session_id: str) -> Optional[SessionPayload]:
    ...

def _workflow_rows_to_claude_jsonl(
    workflow_row: Any,
    node_rows: list[Any],
) -> str:
    ...

def _workflow_node_row_to_events(row: Any) -> list[dict[str, Any]]:
    ...

def _fetch_team_session(session_id: str) -> Optional[SessionPayload]:
    ...

def _normalize_component_stdout(stdout_log: str, backend_type: str) -> str:
    ...
```

Implementation notes:

- `_fetch_workflow_execution()` returns `SessionPayload(text=..., backend_type="claude", project_id=None, outcome=workflow_row["status"])`.
- `_workflow_rows_to_claude_jsonl()` should include `workflow_executions.error` and each node `error`.
- `_normalize_component_stdout()` should call `_to_claude_jsonl()` for Claude-shaped logs and return plain text wrapped as assistant text for non-Claude logs only after parser support exists. Until backend-specific parsers exist, mixed teams should retain a `backend_type="claude"` payload when at least one component is Claude-shaped.

### (f) Edge cases

- Workflow cancellation currently returns early at `backend/app/services/workflow_execution_service.py:420-428` without emitting session completion. Add emission before cleanup for cancelled workflows so the `"workflow"` scope emits in all terminal paths.
- Workflow cycle detection returns at `backend/app/services/workflow_execution_service.py:371-378` without emitting session completion. Add emission after `update_workflow_execution(...)`.
- Workflow timeout sets `workflow_failed=True` at `backend/app/services/workflow_execution_service.py:408-417`; final emission should use `"failed"` unless a future status value `"timeout"` is persisted.
- Team rows may exist with no `execution_ids`; current behavior should persist an empty annotation summary, not crash.
- Team rows may have component execution ids whose logs are missing or still running; include available logs and append `team_executions.error` if present.
- `execution_ids` order is stored in `team_executions.execution_ids`, but the current SQL orders by `execution_logs.id`. Preserve the stored order by sorting fetched rows against the decoded `execution_ids` list.
- Workflow `output_json` can contain JSON that is not a `WorkflowMessage`; stringify it and include it as evidence rather than dropping it.

### (g) Verification

Use the backend `isolated_db` fixture.

Tests:

- Insert a `workflow_executions` row with `id="wf-exec-1"` and `workflow_id="wf-1"`, plus two `workflow_node_executions` rows. Assert `_fetch_workflow_execution("wf-exec-1")` returns text containing both node outputs and outcome from `workflow_executions.status`.
- Insert only `workflow_id="wf-1"` and assert `_fetch_workflow_execution("wf-1")` returns `None`; this guards against reintroducing ambiguous parent-id lookup.
- Unit test `_run_workflow()` completion emission with a monkeypatched `emit_session_complete` spy; assert the session id is `execution_id`.
- Insert a `team_executions` row with `execution_ids='["exec-a","exec-b"]'` and two `execution_logs.stdout_log` values stored as JSON arrays. Assert `_fetch_team_session()` returns JSONL, in stored execution-id order.
- Run `annotate_session("workflow", "wf-exec-1")` and assert `session_annotations.session_kind="workflow"` and `session_annotations.session_id="wf-exec-1"` are persisted.
- Run `extract_for_session("team_session", "team-exec-1")` with a monkeypatched LLM-disabled environment and assert no exception when component logs are missing.

## Gap 2: Failure Annotator Classification

### (a) Current state with verified evidence

Current typed representation is partial. `TurnEvent` is a dataclass with `index`, `role`, `content_text`, `tool_name`, `tool_args`, `tool_error`, and `raw` at `backend/app/services/harness_failure_annotator.py:45-55`. `SessionPayload` contains `text`, `backend_type`, `project_id`, and `outcome` at `backend/app/services/harness_failure_annotator.py:61-67`.

The parser only handles Claude JSONL. `annotate_from_text()` calls `parse_claude_stream()` only when `backend_type == "claude"` and otherwise uses an empty event list at `backend/app/services/harness_failure_annotator.py:579-583`.

Current H2 detection:

- Assistant text that looks like a tool invocation or fenced tool block: `backend/app/services/harness_failure_annotator.py:408-419`.
- Tool-result errors containing `"json"`, `"missing required"`, `"unknown argument"`, `"invalid"`, `"no such tool"`, or `"not found"`: `backend/app/services/harness_failure_annotator.py:420-431`.

Current H3 detection:

- Contract wording like `"unknown parameter"`, `"unsupported"`, `"must be called after"`, `"out of order"`: `backend/app/services/harness_failure_annotator.py:435-447`.
- Setup failures from result events: `"unknown command"`, `"command not found"`, or `"zero turns"`: `backend/app/services/harness_failure_annotator.py:448-459`.

Current H4 detection:

- Same assistant tool call and args repeated at least three times: `backend/app/services/harness_failure_annotator.py:466-480`.
- Five consecutive assistant text turns during failed outcomes when the session has at least one tool call: `backend/app/services/harness_failure_annotator.py:492-514`.
- `outcome == "timeout"` maps to `h4_budget_exhausted`: `backend/app/services/harness_failure_annotator.py:515-521`.

Priority protocol:

- H2 incidents claim event indexes first.
- H3 incidents are skipped if their event index is already claimed.
- H4 incidents are skipped if their event index is already claimed.
- Failed outcomes with no incidents get `general_unclassified`.

This is implemented at `backend/app/services/harness_failure_annotator.py:526-562`.

Persistence stores one row per incident in `session_layer_incidents` and a roll-up in `session_annotations`. `repo.replace_incidents()` writes `layer`, `priority`, `kind`, `evidence_json`, `event_index`, and `detector_version` at `backend/app/db/harness_annotations.py:21-72`, then upserts the session summary at `backend/app/db/harness_annotations.py:73-104`. The schema columns are defined at `backend/app/db/schema/_harness_annotations.py:31-44` and `backend/app/db/schema/_harness_annotations.py:63-79`.

There is no first-class incident type, no confidence, and no severity column. Confidence and severity can be stored inside `evidence_json` without a migration.

### (b) Recommended approach and alternatives

Recommended approach:

Introduce a typed incident object in the service layer and keep the existing DB schema. Convert typed incidents to dicts immediately before `repo.replace_incidents()`.

Add detector families:

- H2 Action Realization:
  - Tool-call syntax emitted as plain text.
  - Malformed JSON/tool args.
  - Missing required tool args.
  - Unknown tool name.
  - Tool result explicitly reports invalid invocation.
  - Same failed tool call repeated at least two times.
- H3 Environment Contract:
  - Missing files or directories: `"No such file or directory"`, `"ENOENT"`, `"file not found"`.
  - Missing environment variables or credentials: `"missing env"`, `"environment variable"`, `"API key not found"`, `"not authenticated"`.
  - Permissions and sandbox: `"permission denied"`, `"operation not permitted"`, `"read-only file system"`, `"outside writable root"`.
  - Wrong paths: `"not a directory"`, `"cannot access"`, `"path does not exist"`.
  - Commands unavailable: `"command not found"`, `"executable file not found"`, `"No such file or directory: 'cmd'"`.
- H4 Trajectory:
  - Repeated identical actions, already present, but include failed-repeat evidence.
  - Looping assistant language: `"try again"` / `"retrying"` / `"same error"` repeated across turns.
  - Abandoned goals: `"I can't continue"`, `"unable to proceed"`, `"giving up"`, `"cannot complete"` near final turns.
  - Contradictory steps: assistant says it will do X, then later says it did not or cannot do X without intervening evidence.
  - Budget exhaustion and timeout.
- General:
  - Failed, cancelled, interrupted, or timeout outcomes with no layer-specific detector hit.

Alternative 1: Add `confidence` and `severity` columns to `session_layer_incidents`. Trade-off: cleaner analytics, but this requires migration and UI/model updates; not necessary for Phase A because `evidence_json` already persists arbitrary structured metadata.

Alternative 2: Move detectors to separate classes per layer. Trade-off: cleaner long-term organization, but a module-level typed function set is faster to implement and matches the current file style.

### (c) Specific files to create or modify

Modify:

- `backend/app/services/harness_failure_annotator.py`: add `HarnessIncident`, detector result helpers, expanded regex detectors, severity/confidence assignment, and backend-specific parser routing hooks.
- `backend/app/db/harness_annotations.py`: no required schema change; optionally validate typed incident dict keys before insert.

Tests:

- Add focused tests in the existing harness annotator test module or create `backend/tests/test_harness_failure_annotator_classification.py`.

### (d) Data-model/schema changes

No required schema migration.

Persist incident fields this way:

- `session_layer_incidents.layer`: incident `layer`.
- `session_layer_incidents.kind`: incident `kind`.
- `session_layer_incidents.event_index`: incident `event_index`.
- `session_layer_incidents.evidence_json`: full evidence object including `snippet`, `error`, `confidence`, `severity`, `detector`, `backend_type`, `tool_name`, `repeat_count`, and optional `normalized_message`.
- `session_layer_incidents.detector_version`: bumped detector version.

Existing schema verified at `backend/app/db/schema/_harness_annotations.py:31-44`.

### (e) Key function signatures

```python
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, TypedDict

HarnessLayer = Literal["h2", "h3", "h4", "general"]
IncidentSeverity = Literal["low", "medium", "high", "critical"]

class IncidentEvidence(TypedDict, total=False):
    snippet: str
    error: str
    normalized_message: str
    detector: str
    confidence: float
    severity: IncidentSeverity
    backend_type: str
    tool_name: str
    repeat_count: int
    event_indexes: list[int]
    outcome: str

@dataclass(frozen=True)
class HarnessIncident:
    layer: HarnessLayer
    kind: str
    event_index: Optional[int]
    evidence: IncidentEvidence = field(default_factory=dict)

def detect_h2(events: list[TurnEvent], *, backend_type: str) -> list[HarnessIncident]:
    ...

def detect_h3(events: list[TurnEvent], *, backend_type: str) -> list[HarnessIncident]:
    ...

def detect_h4(
    events: list[TurnEvent],
    *,
    outcome: Optional[str],
    backend_type: str,
) -> list[HarnessIncident]:
    ...

def detect_general(
    events: list[TurnEvent],
    *,
    outcome: Optional[str],
    backend_type: str,
) -> list[HarnessIncident]:
    ...

def _apply_priority_protocol(
    events: list[TurnEvent],
    *,
    outcome: Optional[str],
    backend_type: str,
) -> list[dict[str, Any]]:
    ...

def _incident_to_repo_dict(incident: HarnessIncident) -> dict[str, Any]:
    ...

def _severity_for(
    layer: HarnessLayer,
    *,
    outcome: Optional[str],
    repeat_count: int = 1,
) -> IncidentSeverity:
    ...

def _confidence_for(kind: str, *, exact_pattern: bool, repeat_count: int = 1) -> float:
    ...
```

Severity assignment:

- `critical`: failed/timeout session with H2/H3 incident and no later success evidence.
- `high`: repeated failed tool invocation, missing credentials, permission denied, command not found, timeout.
- `medium`: single malformed tool args, missing file/path, unsupported parameter, abandoned goal.
- `low`: weak trajectory wording or plain-text tool-like syntax without a tool error.

Confidence assignment:

- `0.95`: exact machine error (`is_error=true`, JSON parse/tool schema failure, command not found, permission denied).
- `0.85`: repeated identical failed action or timeout.
- `0.70`: missing file/env/path text pattern.
- `0.55`: trajectory-language pattern without explicit tool/error evidence.
- `0.40`: general catch-all.

### (f) Edge cases

- `"not found"` is ambiguous. In H2 it can mean unknown tool; in H3 it can mean missing file/command. Prefer H3 when the error contains path-like text, `ENOENT`, `command`, `file`, or directory terms. Prefer H2 when the error contains `tool`, `argument`, `schema`, `json`, or `parameter`.
- Successful sessions should not get H4 stagnation from chat-only text, preserving the current guard at `backend/app/services/harness_failure_annotator.py:482-495`.
- A failed event index should only be claimed by the highest-priority layer. Keep H2 before H3 before H4.
- Incidents with `event_index=None` must still persist and sort after indexed incidents; current query already orders `event_index ASC NULLS LAST` at `backend/app/db/harness_annotations.py:121-127`.
- Non-Claude backends currently produce no parsed events. Until parsers exist, classify raw-text environment failures by wrapping plain transcript lines into coarse `TurnEvent(role="tool_result", tool_error=...)` events for failed outcomes.

### (g) Verification

Use `isolated_db`.

Tests:

- H2: assistant text `take_action(...)` emits `h2_tool_in_content` with low/medium confidence.
- H2: tool error `"missing required argument: path"` emits `h2_invalid_tool_call`.
- H2: same failed tool call appears twice and emits `h2_repeated_tool_failure`.
- H3: `"No such file or directory: /tmp/missing"` emits `h3_missing_file`.
- H3: `"permission denied"` emits `h3_permission_denied`.
- H3: `"command not found: rg"` emits `h3_command_not_found`.
- H4: three identical tool calls emit `h4_repeat_action`.
- H4: final assistant says `"I cannot continue"` on failed outcome emits `h4_abandoned_goal`.
- General: failed outcome with unrelated text emits one `general_unclassified`.
- Persistence: after `annotate_from_text(...)`, assert `session_layer_incidents.evidence_json` contains `confidence` and `severity`, and `session_annotations.primary_layer` follows H2/H3/H4/general priority.

## Gap 3: Takeaway Extractor LLM Path Is Not Backend-Agnostic

### (a) Current state with verified evidence

The extractor advertises two modes. The file docstring says the LLM mode calls Codex at `backend/app/services/harness_takeaway_extractor.py:14-17`.

Current LLM path is codex-only:

- `_llm_codex_cmd()` reads `AGENTED_TAKEAWAY_CODEX_CMD` or `AGENTED_CODEX_CMD`, then defaults to `["codex", "exec", "--skip-git-repo-check", "{PROMPT}"]`: `backend/app/services/harness_takeaway_extractor.py:468-480`.
- `_run_codex_for_extraction()` invokes that command with `subprocess.run(...)`: `backend/app/services/harness_takeaway_extractor.py:483-522`.
- `_extract_llm()` calls `_run_codex_for_extraction(prompt, timeout=_llm_timeout())`: `backend/app/services/harness_takeaway_extractor.py:535-559`.

This does not accept `{backend_kind, model_override}` and cannot route to claude, opencode, or gemini.

The backend-agnostic pattern already exists in `goal_judge_service.py`:

- It documents support for `claude`, `codex`, `gemini`, and `opencode` at `backend/app/services/goal_judge_service.py:13-19`.
- It defines per-backend default models at `backend/app/services/goal_judge_service.py:43-48`:

```python
DEFAULT_JUDGE_MODEL = {
    "claude": "claude-haiku-4-5",
    "codex": "o4-mini",
    "gemini": "gemini-2.5-flash",
    "opencode": "auto",
}
```

- `GoalJudgeService.judge()` accepts `backend_kind` and `model_override` at `backend/app/services/goal_judge_service.py:139-151`, then selects `model = model_override or DEFAULT_JUDGE_MODEL.get(backend_kind, "auto")` at `backend/app/services/goal_judge_service.py:159-166`.
- `_run_llm_judge()` uses `CLIProxyManager.get_url_and_key()` at `backend/app/services/goal_judge_service.py:222-229`, posts to `{base_url}/chat/completions` at `backend/app/services/goal_judge_service.py:249-258`, and passes `metadata={"backend_kind": backend_kind}` at `backend/app/services/goal_judge_service.py:231-248`.

The project supports four backend kinds in command construction: `backend/app/services/command_builder.py:1-4` documents `claude`, `opencode`, `gemini`, and `codex`; `CommandBuilder.build()` branches on `opencode` at `backend/app/services/command_builder.py:41-45`, `gemini` at `backend/app/services/command_builder.py:46-53`, `codex` at `backend/app/services/command_builder.py:54-63`, and defaults to `claude` at `backend/app/services/command_builder.py:64-80`.

Takeaway persistence schema is already sufficient. `session_takeaways` includes `kind`, `content`, `confidence`, `evidence_json`, `suggested_target`, `suggested_payload_json`, and `extractor_version` at `backend/app/db/schema/_harness_takeaways.py:21-54`. Valid kinds and targets are defined in `backend/app/db/harness_takeaways.py:12-24`.

### (b) Recommended approach and alternatives

Recommended approach:

Replace the codex subprocess path with a CLIProxyAPI chat-completions path modeled directly on `GoalJudgeService`.

Add `DEFAULT_TAKEAWAY_MODEL` with the same per-kind defaults as the judge unless product wants different extraction models:

```python
DEFAULT_TAKEAWAY_MODEL = {
    "claude": "claude-haiku-4-5",
    "codex": "o4-mini",
    "gemini": "gemini-2.5-flash",
    "opencode": "auto",
}
```

Add a public extraction call that accepts backend routing:

```python
def _extract_llm(
    session_kind: str,
    session_id: str,
    project_id: Optional[str],
    payload: SessionPayload,
    *,
    backend_kind: Optional[str] = None,
    model_override: Optional[str] = None,
) -> list[dict[str, Any]]:
    ...
```

Default `backend_kind` to `payload.backend_type` when it is one of the four supported kinds, else `"claude"` or `"opencode"` based on operator config. Do not default to codex.

Alternative 1: Reuse `CommandBuilder` and spawn each backend CLI directly. Trade-off: this would support all four backends but duplicates timeout, auth, and model routing logic already centralized by CLIProxyAPI.

Alternative 2: Add a generic `LLMRouterService` and migrate both goal judge and takeaway extractor to it. Trade-off: best long-term shape, but higher blast radius. Phase A can copy the proven goal-judge pattern first, then refactor later.

### (c) Specific files to create or modify

Modify:

- `backend/app/services/harness_takeaway_extractor.py`: remove codex-only command construction from the active path, add `CLIProxyManager` + `httpx` route, backend/model arguments, chunking, JSON parsing, merge/dedup improvements, and tests.

Optional later refactor:

- `backend/app/services/llm_router_service.py`: shared backend-agnostic chat-completion helper for goal judge and takeaway extraction.

Tests:

- `backend/tests/test_harness_takeaway_extractor_llm.py` or equivalent.

### (d) Data-model/schema changes

No required schema migration.

The current takeaway row supports all output:

- `session_kind`, `session_id`, `project_id`: source scope.
- `kind`: one of `user_preference`, `discovered_procedure`, `tool_pattern`, `constraint`, `domain_fact`, `failure_root_cause`, `success_pattern`.
- `content`: 500-char implementation cap today at `backend/app/services/harness_takeaway_extractor.py:594`.
- `confidence`: existing real column.
- `evidence_json`: store extractor backend/model/chunk/rationale/source quotes.
- `suggested_target`: one of `memory`, `rule`, `skill`, `knowledge_graph`, `claude_md`.
- `suggested_payload_json`: existing target payload.
- `extractor_version`: bump from `llm-0.1.0` to `llm-0.2.0-backend-agnostic`.

Schema verified at `backend/app/db/schema/_harness_takeaways.py:21-54`; valid kinds/targets verified at `backend/app/db/harness_takeaways.py:12-24`.

### (e) Key function signatures

```python
from dataclasses import dataclass
from typing import Any, Optional, TypedDict

SUPPORTED_LLM_BACKENDS: frozenset[str] = frozenset({
    "claude",
    "codex",
    "gemini",
    "opencode",
})

DEFAULT_TAKEAWAY_MODEL: dict[str, str] = {
    "claude": "claude-haiku-4-5",
    "codex": "o4-mini",
    "gemini": "gemini-2.5-flash",
    "opencode": "auto",
}

class RawLLMTakeaway(TypedDict, total=False):
    kind: str
    content: str
    confidence: float
    suggested_target: Optional[str]
    rationale: str
    source_quote: str

@dataclass(frozen=True)
class LLMExtractionConfig:
    backend_kind: str
    model: str
    timeout_seconds: int
    transcript_cap_chars: int
    chunk_chars: int
    chunk_overlap_chars: int

def _resolve_llm_config(
    payload: SessionPayload,
    *,
    backend_kind: Optional[str] = None,
    model_override: Optional[str] = None,
) -> LLMExtractionConfig:
    ...

def _run_llm_for_extraction(
    prompt: str,
    *,
    backend_kind: str,
    model: str,
    timeout: int,
) -> str:
    ...

def _build_takeaway_prompt(
    *,
    session_kind: str,
    session_id: str,
    project_id: Optional[str],
    chunk_index: int,
    chunk_count: int,
    transcript_chunk: str,
) -> str:
    ...

def _chunk_transcript(
    text: str,
    *,
    chunk_chars: int,
    overlap_chars: int,
    max_chars: int,
) -> list[str]:
    ...

def _parse_llm_takeaways(raw_output: str) -> list[RawLLMTakeaway]:
    ...

def _map_llm_takeaway(
    raw: RawLLMTakeaway,
    *,
    session_kind: str,
    session_id: str,
    project_id: Optional[str],
    backend_kind: str,
    model: str,
    chunk_index: int,
) -> Optional[dict[str, Any]]:
    ...

def _merge_takeaways(
    heuristic: list[dict[str, Any]],
    llm: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ...

def _takeaway_dedupe_key(item: dict[str, Any]) -> tuple[str, str]:
    ...
```

`_run_llm_for_extraction()` should match the judge's request shape:

```python
payload = {
    "model": model,
    "messages": [
        {"role": "system", "content": _TAKEAWAY_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ],
    "stream": False,
    "metadata": {"backend_kind": backend_kind},
}
```

The function should call `CLIProxyManager.get_url_and_key()`, then `httpx.post(f"{base_url}/chat/completions", ...)`, as `goal_judge_service.py` does at `backend/app/services/goal_judge_service.py:222-258`.

Extraction prompt:

```text
Extract reusable takeaways from one AI-agent session transcript chunk.

Return only a JSON array. Each object must have:
- kind: user_preference | discovered_procedure | tool_pattern | constraint | domain_fact | failure_root_cause | success_pattern
- content: one concise sentence, max 500 chars
- confidence: number from 0.0 to 1.0
- suggested_target: memory | rule | skill | knowledge_graph | claude_md | null
- rationale: short reason grounded in the transcript
- source_quote: shortest relevant quote or paraphrase from this chunk

Rules:
- Extract only information useful to future sessions.
- Do not restate the user task.
- Do not invent facts not supported by the transcript.
- Prefer 0-5 high-signal items per chunk.
- Use failure_root_cause for diagnosed causes of failed runs.
- Use success_pattern for reusable behaviors that worked.
```

Chunking:

- Cap total transcript at `_TAKEAWAY_LLM_TRANSCRIPT_CAP`.
- Split into chunks of 16,000 chars with 1,000-char overlap.
- Run the LLM per chunk.
- Include `chunk_index` and `chunk_count` in the prompt and evidence.
- Deduplicate across chunks with normalized `(kind, content)` keys.

Confidence mapping:

- Clamp model confidence to `[0.0, 1.0]`.
- Reduce by `0.10` when `source_quote`/`rationale` is empty.
- Reduce by `0.15` when content is generic, e.g. less than 20 chars or starts with `"the agent should"` without concrete object.
- Increase max to at least `0.80` only when the source is explicit user preference or exact environment constraint.
- Auto-apply threshold remains `HIGH_CONFIDENCE = 0.85` at `backend/app/services/harness_takeaway_extractor.py:52`.

Heuristic + LLM merge/dedup:

- Keep heuristic items first when exact `(kind, normalized_content)` matches, preserving current deterministic tie behavior at `backend/app/services/harness_takeaway_extractor.py:1037-1040`.
- If LLM and heuristic overlap semantically but differ in wording, keep the higher-confidence item and merge evidence under `evidence["merged_sources"]`.
- Use path-aware dedupe for `domain_fact`: if both payloads name the same path, keep one.
- Use target-aware dedupe for `user_preference`: if both write the same memory key, keep one.

### (f) Edge cases

- CLIProxyAPI unavailable: return `[]` and log a warning, same non-blocking behavior as the current codex path.
- Unsupported `backend_kind`: coerce to `"opencode"` with model `"auto"` or to `"claude"` with `claude-haiku-4-5`; record the original in evidence if a request was made. Do not coerce to codex.
- LLM returns fenced JSON or prose: keep `_slice_json_array()` behavior from `backend/app/services/harness_takeaway_extractor.py:525-532`.
- LLM returns one object instead of an array: reject or wrap only if all required fields are present; tests should define the accepted behavior.
- Multiple chunks return conflicting target suggestions: choose the higher-confidence target; if tied, prefer `memory`, then `rule`, then `knowledge_graph`, then `skill`, then `claude_md` only when the content is instruction-like.
- Short transcripts below `_llm_min_text_bytes()` should continue to skip LLM extraction.
- Team-session transcripts may contain mixed backends; use the configured extraction backend for the LLM call, not the transcript producer backend, when `model_override` or `backend_kind` is provided.

### (g) Verification

Use `isolated_db` and monkeypatch `CLIProxyManager.get_url_and_key()` plus `httpx.post`.

Tests:

- For each backend kind `claude`, `codex`, `gemini`, and `opencode`, call `_extract_llm(..., backend_kind=kind)` and assert the posted payload includes `metadata.backend_kind == kind`.
- Assert default models match the judge pattern: `claude-haiku-4-5`, `o4-mini`, `gemini-2.5-flash`, and `auto`.
- Assert `model_override="custom-model"` replaces the per-kind default.
- Assert malformed JSON returns `[]` and does not call `repo.insert_many`.
- Assert two chunks produce deduped takeaways with evidence containing chunk indexes.
- Assert LLM output maps to valid `session_takeaways` rows through `repo.insert_many()` with `evidence_json.extractor == "llm"` and `evidence_json.backend_kind`.
- Assert heuristic and LLM duplicates collapse to one item in `extract_for_session()`.

## Cross-phase Contracts

### Typed incident shape consumed by the evolver

The evolver currently reads annotations with `annotations_repo.get_annotation(session_kind, session_id)` and `annotations_repo.list_incidents(session_kind, session_id)` at `backend/app/services/harness_evolver.py:405-408`. Preserve that repository contract.

Incident row shape exposed by `list_incidents()`:

```python
class EvolverIncident(TypedDict, total=False):
    id: str
    layer: Literal["h2", "h3", "h4", "general"]
    priority: int
    kind: str
    evidence: IncidentEvidence
    event_index: Optional[int]
    detector_version: str
    created_at: str
```

Required evidence keys for Phase A:

```python
class IncidentEvidence(TypedDict, total=False):
    snippet: str
    error: str
    normalized_message: str
    detector: str
    confidence: float
    severity: Literal["low", "medium", "high", "critical"]
    backend_type: str
    tool_name: str
    repeat_count: int
    event_indexes: list[int]
    outcome: str
```

The session summary shape remains `session_annotations`: `session_kind`, `session_id`, `project_id`, `annotator_version`, `primary_layer`, `incident_count`, `h2_count`, `h3_count`, `h4_count`, `general_count`, `outcome`, `annotated_at`.

### Takeaway shape

Repository input shape for `repo.insert_many()`:

```python
class TakeawayInput(TypedDict, total=False):
    session_kind: str
    session_id: str
    project_id: Optional[str]
    kind: Literal[
        "user_preference",
        "discovered_procedure",
        "tool_pattern",
        "constraint",
        "domain_fact",
        "failure_root_cause",
        "success_pattern",
    ]
    content: str
    confidence: float
    evidence: dict[str, Any]
    suggested_target: Optional[
        Literal["memory", "rule", "skill", "knowledge_graph", "claude_md"]
    ]
    suggested_payload: dict[str, Any]
    extractor_version: str
```

Required LLM evidence keys:

```python
class TakeawayEvidence(TypedDict, total=False):
    extractor: Literal["heuristic", "llm"]
    backend_kind: Literal["claude", "codex", "gemini", "opencode"]
    model: str
    chunk_index: int
    chunk_count: int
    rationale: str
    source_quote: str
    merged_sources: list[str]
```

### Confirmation all five scopes now emit

After Gap 1 implementation, all five scopes should emit and fetch:

1. `trigger_execution`: emitted from `backend/app/services/execution_service.py:758-764`; fetched from `execution_logs.stdout_log` by `_fetch_trigger_execution()` at `backend/app/services/harness_failure_annotator.py:69-87`.
2. `super_agent`: emitted from `backend/app/services/super_agent_session_service.py:335-341`; fetched from `super_agent_sessions.conversation_log` by `_fetch_super_agent_session()` at `backend/app/services/harness_failure_annotator.py:179-195`.
3. `project_session`: emitted from `backend/app/services/project_session_manager.py:1393-1399`; fetched from `project_sessions.log_json` by `_fetch_project_session()` at `backend/app/services/harness_failure_annotator.py:198-212`.
4. `workflow`: emit must be corrected to use `workflow_executions.id` (`execution_id`) from `backend/app/services/workflow_execution_service.py:332-338`; fetch from `workflow_executions` and `workflow_node_executions` by `_fetch_workflow_execution()`.
5. `team_session`: emitted from `backend/app/services/team_execution_service.py:235-241`; fetched from `team_executions.execution_ids` plus component `execution_logs.stdout_log` by `_fetch_team_session()`.

Completion criterion for Phase A: every terminal session in these five scopes produces either a `session_annotations` row, zero-or-more `session_layer_incidents`, and zero-or-more `session_takeaways`, or an explicit logged fetch failure. Silent no-op because of scope mismatch or codex-only LLM routing is not acceptable.
