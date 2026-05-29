# Phase C - Trust the Changes: Eval Gate + Rollback

Date: 2026-05-29

Scope: design only. No implementation in this phase.

Phase C consumes Phase B's materialization contract and commit audit, and provides an eval verdict plus rollback capability for Phase D autonomy gating.

```python
@dataclass(frozen=True)
class MaterializationResult:
    round_id: str
    workspace_dir: Path
    written_files: list[Path]
    primitive_files: dict[str, list[Path]]
    git_commit_sha: str | None

def materialize_primitives(round_id: str, workspace_dir: Path) -> MaterializationResult: ...
```

```python
class CheckResult(BaseModel):
    name: str
    passed: bool
    severity: Literal["error", "warning", "info"] = "error"
    primitive_kind: str | None = None
    primitive_name: str | None = None
    asset_id: str | int | None = None
    details: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)

class EvalVerdict(BaseModel):
    passed: bool
    per_check: list[CheckResult]
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
```

```python
class RevertResult(BaseModel):
    round_id: str
    status: Literal["reverted", "conflict", "failed"]
    reverted_asset_ids: list[dict[str, Any]] = Field(default_factory=list)
    git_revert_sha: str | None = None
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
```

## Gap 1 - Eval Gate Before Apply

### 1. Current State

`backend/app/services/harness_evolver.py` currently validates only patch shape. `validate_patch()` iterates entries, rejects non-writable kinds, checks payload object shape, validates hook event/content, rule description/action, command content, MCP command/url, and required `existing_asset_id` for update/delete at lines 858-875. `_validate_payload()` is field-presence validation only at lines 878-904.

The orchestration path has no functional verification after validation. `run_evolution_round()` starts a DB row at lines 1102-1109, marks it `running` at line 1112, builds the scratch workspace and runs Codex at lines 1113-1114, parses and validates the patch at lines 1119-1120, then either marks dry runs `awaiting_approval` at lines 1134-1143 or applies immediately at lines 1145-1159.

The current DB status set is `pending`, `running`, `awaiting_approval`, `applied`, `failed`, `aborted` in `backend/app/db/schema/_harness_evolution.py:29-33`. The repo helper `mark_running()` only transitions `pending -> running` at `backend/app/db/harness_evolution.py:43-50`. `mark_awaiting_approval()` and `mark_applied()` finish the round directly at `backend/app/db/harness_evolution.py:53-100`.

The input window already contains the material needed for replay. `gather_inputs()` reads bound primitives at `backend/app/services/harness_evolver.py:377-394`, snapshots at lines 396-401, annotations/incidents at lines 407-419, and returns `trajectories` plus `takeaways` at lines 432-437. Incident shape comes from `harness_failure_annotator`: detectors emit `{layer, kind, event_index, evidence}` at lines 414-419, 426-431, 442-447, 454-459, 475-480, 505-510, and 516-520. The priority protocol emits a fallback `general_unclassified` incident at lines 554-560.

### 2. Recommended Approach + Alternatives Considered

Recommended: add a new `backend/app/services/harness_evolution_eval.py` service and call it after `validate_patch()` passes and before either `mark_awaiting_approval()` or `apply_patch()`. The service creates a temporary eval workspace, calls Phase B's `materialize_primitives(round_id, workspace_dir)`, runs static checks against the materialized files, runs replay checks against sampled input-window trajectories, writes an `EvalVerdict` to the round, and returns failure early as `eval_failed` when verdict fails.

The gate should run for both dry-run and live apply. Dry-run should become `awaiting_approval` only after eval passes, so human approval sees a patch that is already syntactically and behaviorally screened. Live apply should call `apply_patch()` only after eval passes.

Alternatives considered:

1. Put static checks inside `validate_patch()`. Rejected because `validate_patch()` operates on `EvolutionPatch` objects and has no materialized files, so it cannot parse hook scripts, frontmatter, or MCP config exactly as the harness will consume them.
2. Run eval only after DB apply. Rejected because the gap is specifically "before apply"; a failed eval after apply still needs rollback.
3. Use the existing `GoalJudgeService` directly. Rejected as the public eval contract must accept provider-level `{backend_kind, model_override?}` and support `anthropic`, `openai`, `gemini`, and `ollama`, while current judge routing is harness-oriented (`claude`, `codex`, `gemini`, `opencode`) in `backend/app/services/goal_judge_service.py:140-166`.

### 3. Files to Create / Modify

Create:

- `backend/app/services/harness_evolution_eval.py` - eval orchestration, static checks, replay sampling, LLM judge adapter, verdict models.
- `backend/app/models/harness_evolution.py` - shared Pydantic v2 models for `CheckResult`, `EvalVerdict`, `ReplaySample`, `ReplayJudgeRequest`, `RevertResult`.

Modify:

- `backend/app/services/harness_evolver.py` - insert eval between `validate_patch()` at lines 1119-1120 and the dry-run/apply branches at lines 1134-1151; extend `EvolutionResult.status` comment at lines 235-240.
- `backend/app/db/harness_evolution.py` - add `mark_evaluating()`, `mark_eval_failed()`, `store_eval_verdict()`, and include `eval_verdict_json`, `phase_b_commit_sha`, `reverted_at`, `revert_error`, `revert_conflicts_json` in `_row_to_dict()`.
- `backend/app/db/schema/_harness_evolution.py` and the active migration file - add columns and rebuild the status check to include new states.
- `backend/app_litestar/routes/harness_evolution.py` - include `eval_verdict` in `_result_payload()` at lines 94-101 or rely on detail route at lines 64-69; no new eval route is required.

### 4. Schema Changes

Add columns:

```sql
ALTER TABLE harness_evolution_rounds
ADD COLUMN eval_verdict_json TEXT;

ALTER TABLE harness_evolution_rounds
ADD COLUMN eval_started_at TEXT;

ALTER TABLE harness_evolution_rounds
ADD COLUMN eval_finished_at TEXT;

ALTER TABLE harness_evolution_rounds
ADD COLUMN phase_b_commit_sha TEXT;
```

The existing `status` check at `backend/app/db/schema/_harness_evolution.py:29-33` must be rebuilt because SQLite cannot alter a `CHECK` constraint in place. New status definition:

```sql
status TEXT NOT NULL DEFAULT 'pending'
       CHECK (status IN (
           'pending', 'running', 'evaluating', 'awaiting_approval',
           'applied', 'eval_failed', 'failed', 'aborted', 'reverted'
       ))
```

Before transition diagram:

```text
pending -> running -> failed
pending -> running -> awaiting_approval -> applied
pending -> running -> applied
awaiting_approval -> aborted
```

After transition diagram:

```text
pending -> running -> failed
pending -> running -> evaluating -> eval_failed
pending -> running -> evaluating -> awaiting_approval -> applied
pending -> running -> evaluating -> applied
awaiting_approval -> aborted
applied -> reverted
```

`eval_failed` is terminal for that round. It differs from `failed`: `failed` means the generation/parser/apply machinery broke; `eval_failed` means the patch was well-formed but did not meet the trust gate.

### 5. Key Signatures

```python
def run_evolution_round(
    project_id: str,
    *,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 25,
    keep_scratch_on_failure: bool = True,
    dry_run: bool = False,
    min_interval_hours: Optional[int] = None,
    force: bool = False,
    eval_backend_kind: str = "anthropic",
    eval_model_override: Optional[str] = None,
) -> EvolutionResult: ...
```

```python
def evaluate_patch(
    *,
    round_id: str,
    project_id: str,
    patch: EvolutionPatch,
    inputs: dict[str, Any],
    backend_kind: Literal["anthropic", "openai", "gemini", "ollama"],
    model_override: Optional[str] = None,
    workspace_root: Optional[Path] = None,
) -> EvalVerdict: ...
```

```python
def run_static_checks(
    *,
    materialization: MaterializationResult,
    patch: EvolutionPatch,
) -> list[CheckResult]: ...
```

```python
def run_regression_replay(
    *,
    materialization: MaterializationResult,
    inputs: dict[str, Any],
    patch: EvolutionPatch,
    backend_kind: Literal["anthropic", "openai", "gemini", "ollama"],
    model_override: Optional[str] = None,
    sample_size: int = 8,
) -> list[CheckResult]: ...
```

```python
def judge_replay_sample(
    *,
    sample: ReplaySample,
    patched_workspace_dir: Path,
    targeted_incidents: list[dict[str, Any]],
    backend_kind: Literal["anthropic", "openai", "gemini", "ollama"],
    model_override: Optional[str] = None,
) -> CheckResult: ...
```

```python
def mark_evaluating(round_id: str) -> None: ...

def store_eval_verdict(round_id: str, verdict: EvalVerdict) -> None: ...

def mark_eval_failed(
    round_id: str,
    *,
    verdict: EvalVerdict,
    error_message: Optional[str] = None,
) -> None: ...
```

### 6. Edge Cases and Failure Modes

Static checks:

- Hook scripts are stored as `content` in `hooks` payloads. The materialized hook file should be checked by content type: `bash -n` for shell hooks, `python -c "import py_compile; py_compile.compile(..., doraise=True)"` for Python hooks, and a warning for unknown shebang/extensions. Current hook payload requirements are only `event` and `content` at `backend/app/services/harness_evolver.py:880-890`.
- Rule and command frontmatter should be parsed with PyYAML for YAML and `tomli` for TOML. `backend/pyproject.toml:12` includes `pyyaml`; `backend/uv.lock` contains `tomli`, which is needed for py310 compatibility.
- MCP server config should validate required `server_type`, `command`/`url`, `args`, `env_json`, and transport-specific fields. Current validation only checks command-or-url at `backend/app/services/harness_evolver.py:899-903`; the eval check should parse `env_json` and `headers_json` as JSON when present.

Replay checks:

- The replay sample should prefer trajectories with incidents targeted by the patch, then include at least one unrelated recent trajectory as a regression sentinel. `gather_inputs()` already carries `incidents`, `primary_layer`, and `active_bindings` at `backend/app/services/harness_evolver.py:409-418`.
- The LLM judge prompt must include the old incident list, patched materialized primitive summaries, and the original transcript or trajectory. The judge returns JSON matching `CheckResult`; malformed judge output is a failed check with low confidence.
- The LLM judge must be provider-routed by `backend_kind in {"anthropic", "openai", "gemini", "ollama"}`. A compatibility layer may map `anthropic -> claude`, `openai -> codex`, and `gemini -> gemini` for local CLI execution, but the public eval function must not expose a claude-only contract.
- If the evaluator cannot reach the selected backend, the verdict should fail closed unless the caller explicitly adds a future `eval_allow_unavailable=True` escape hatch. Phase C should not include that escape hatch by default.

State handling:

- `_check_rate_limit()` currently treats only `pending` and `running` as in-flight at `backend/app/services/harness_evolver.py:134-136`, and only `applied`/`awaiting_approval` as recent successes at lines 179-182. It must include `evaluating` as in-flight and keep `eval_failed` out of recent-success rate limiting.
- If static checks fail, skip replay and mark `eval_failed` with a verdict containing only static results.
- If replay produces mixed results, `passed=False`; `confidence` should be the mean of per-check confidences, capped at `0.6` when any required check is unavailable.

### 7. Verification / Test Strategy

Backend unit tests:

- `validate_patch()` remains shape-only; add tests that eval is called after `validate_patch()` and before `apply_patch()` by monkeypatching both functions and asserting call order.
- Static check tests cover bash syntax failure, Python compile failure, YAML/TOML frontmatter parse failure, invalid `env_json`, and valid MCP stdio/http configs.
- Replay tests use a fake LLM judge and input trajectories shaped like `harness_failure_annotator` incidents (`layer`, `kind`, `event_index`, `evidence`) from `backend/app/services/harness_failure_annotator.py:414-419`.
- State tests assert `pending -> running -> evaluating -> eval_failed`, `pending -> running -> evaluating -> awaiting_approval`, and `pending -> running -> evaluating -> applied`.

Route tests:

- `POST /admin/projects/{project_id}/evolution/dry-run` at `backend/app_litestar/routes/harness_evolution.py:13-27` returns `awaiting_approval` only after eval passes.
- `GET /admin/evolution/rounds/{round_id}` at lines 64-69 exposes `eval_verdict`.

Migration tests:

- Fresh schema includes the new columns and status values.
- Upgrade from the current table preserves existing rows and allows `evaluating`, `eval_failed`, and `reverted`.

Full verification after implementation:

```bash
just build
cd backend && uv run pytest
cd frontend && npm run test:run
```

## Gap 2 - Rollback

### 1. Current State

`apply_patch()` applies primitive CRUD directly through repo helpers at `backend/app/services/harness_evolver.py:911-952`. Creates also call `bindings_repo.add_binding()` at lines 925-928. Updates call the per-kind update repo at lines 936-943. Deletes call the per-kind delete repo at lines 945-950.

`mark_applied()` persists `status='applied'`, `finished_at`, `output_patch_json`, and `applied_asset_ids_json` at `backend/app/db/harness_evolution.py:53-76`, but it does not store before-images. `_row_to_dict()` decodes only `input_forge_json`, `output_patch_json`, and `applied_asset_ids_json` at lines 173-185.

Primitive deletes are hard deletes: rules at `backend/app/db/rules.py:88-93`, hooks at `backend/app/db/hooks.py:74-79`, commands at `backend/app/db/commands.py:84-89`, and MCP servers at `backend/app/db/mcp_servers.py:153-158`. Binding creation is idempotent and may update an existing binding position/enabled state at `backend/app/db/project_forge_bindings.py:62-100`. Binding deletion by id exists at lines 103-110, and whole-project replacement is atomic at lines 113-149.

Phase B assumption: Phase B records the git commit SHA produced by materialization on `harness_evolution_rounds.phase_b_commit_sha`. Rollback uses that SHA for `git revert`.

### 2. Recommended Approach + Alternatives Considered

Recommended: make apply auditable before adding `revert_round(round_id)`. Store per-entry before/after images and binding snapshots in `applied_asset_ids_json` or a new `apply_journal_json` column. Then `revert_round()` can reverse create/update/delete operations transactionally and run `git revert <phase_b_commit_sha>` only after DB conflict checks pass.

The apply journal should be captured inside `apply_patch()` before each mutation. For updates and deletes, fetch the current primitive row using the existing `get_*` helpers before mutation. For creates, record the inserted asset id and the binding row returned by `bindings_repo.add_binding()`. For delete, record all project bindings for the asset before deletion because hard deletes can cascade or orphan depending on table constraints.

Alternatives considered:

1. Infer rollback from `output_patch_json`. Rejected because updates/deletes lose prior values; current patch entries only store new payload and `existing_asset_id` at `backend/app/services/harness_evolver.py:1250-1261`.
2. Re-run Phase B materialization from old inputs. Rejected because DB state and bindings may have changed since the round.
3. Always force-revert by overwriting current rows. Rejected because a later evolution round or operator edit may have intentionally modified the same asset.

### 3. Files to Create / Modify

Create:

- `backend/app/services/harness_evolution_revert.py` - conflict detection, DB reverse operations, git revert orchestration.

Modify:

- `backend/app/services/harness_evolver.py` - have `apply_patch()` return apply journal entries, not only `{kind, op, asset_id}`; use a DB transaction or a compensating transaction helper.
- `backend/app/db/harness_evolution.py` - add `mark_reverted()`, `mark_revert_failed()`, and JSON decoding for apply/revert fields.
- `backend/app_litestar/routes/harness_evolution.py` - add `POST /admin/evolution/rounds/{round_id}/revert`.
- `backend/app/db/schema/_harness_evolution.py` and migration - add rollback columns and `reverted` state.

### 4. Schema Changes

Add columns:

```sql
ALTER TABLE harness_evolution_rounds
ADD COLUMN apply_journal_json TEXT NOT NULL DEFAULT '[]';

ALTER TABLE harness_evolution_rounds
ADD COLUMN reverted_at TEXT;

ALTER TABLE harness_evolution_rounds
ADD COLUMN revert_error TEXT;

ALTER TABLE harness_evolution_rounds
ADD COLUMN revert_conflicts_json TEXT NOT NULL DEFAULT '[]';

ALTER TABLE harness_evolution_rounds
ADD COLUMN revert_git_sha TEXT;
```

State check must include `reverted` as shown in Gap 1. If implementation wants to avoid overloading the round status, an alternative is `revert_status TEXT CHECK (...)`; however, the recommended model sets round `status='reverted'` after a successful rollback so `list_all(status=...)` in `backend/app/db/harness_evolution.py:160-170` works without a new filter.

Apply journal entry shape:

```python
class ApplyJournalEntry(BaseModel):
    op: Literal["create", "update", "delete"]
    kind: Literal["rule", "hook", "command", "mcp_server"]
    asset_id: str | int
    name: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    bindings_before: list[dict[str, Any]] = Field(default_factory=list)
    bindings_after: list[dict[str, Any]] = Field(default_factory=list)
```

### 5. Key Signatures

```python
def apply_patch(
    patch: EvolutionPatch,
    project_id: str,
    *,
    capture_journal: bool = True,
) -> list[ApplyJournalEntry]: ...
```

```python
def revert_round(
    round_id: str,
    *,
    force: bool = False,
    revert_git: bool = True,
) -> RevertResult: ...
```

```python
def detect_revert_conflicts(
    *,
    round_id: str,
    journal: list[ApplyJournalEntry],
    force: bool = False,
) -> list[dict[str, Any]]: ...
```

```python
def reverse_apply_journal(
    *,
    project_id: str,
    journal: list[ApplyJournalEntry],
    force: bool = False,
) -> list[dict[str, Any]]: ...
```

```python
def revert_phase_b_commit(
    *,
    repo_dir: Path,
    commit_sha: str,
) -> str: ...
```

```python
def mark_reverted(
    round_id: str,
    *,
    revert_git_sha: Optional[str],
    reverted_asset_ids: list[dict[str, Any]],
) -> None: ...

def mark_revert_failed(
    round_id: str,
    *,
    error_message: str,
    conflicts: Optional[list[dict[str, Any]]] = None,
) -> None: ...
```

Route signature:

```python
@post("/evolution/rounds/{round_id:str}/revert", sync_to_thread=True)
def revert_evolution_round(
    round_id: str,
    data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]: ...
```

### 6. Edge Cases and Failure Modes

Round state:

- If `round.status != "applied"`, `revert_round()` returns `RevertResult(status="failed", error=...)` and does not mutate DB or git. This includes `awaiting_approval`, `eval_failed`, `failed`, `aborted`, and already `reverted`.
- If `apply_journal_json` is missing for older applied rounds, refuse rollback with a clear error. Do not try best-effort inference from `output_patch_json`.

Conflict detection:

- Update rollback conflicts if current primitive row does not match journal `after`. Example: a later round or operator changed `rules.action`; refusing protects newer edits.
- Delete rollback conflicts if the asset id has been recreated since deletion. For integer IDs this is unlikely but should be checked; for MCP text IDs it is plausible.
- Create rollback conflicts if the created asset has been modified since journal `after`, or if other projects now bind that created global MCP server. Default behavior refuses. `force=True` may delete only the project binding and leave the global MCP server when it is shared.
- Later round conflict: scan later `applied` rounds for matching `{kind, asset_id}` in `apply_journal_json`. If found, refuse unless `force=True`.

Compensating transactions:

- Preferred implementation is one SQLite transaction for all DB reverse operations using direct SQL through `get_connection()`, because existing repo helpers each commit independently (`rules.py:23-42`, `hooks.py:22-32`, `commands.py:22-40`, `mcp_servers.py:39-74`). If implementation reuses repo helpers, wrap each reverse step with a compensating stack and roll forward/back explicitly on failure.
- Reverse order must be the inverse of apply order. If apply created A then updated B, rollback restores B then deletes A.
- DB rollback should run before git revert. If DB conflicts, do not touch git. If DB succeeds but git revert fails, mark `revert_failed` fields while leaving status `applied` plus `revert_error`; manual recovery can rerun with `revert_git=False` after resolving git.

Binding restoration:

- Create rollback deletes the project binding created by `bindings_repo.add_binding()` at `backend/app/services/harness_evolver.py:925-928`, then deletes the created primitive if it is not shared.
- Update rollback restores the primitive `before` row and restores binding fields from `bindings_before` if they changed.
- Delete rollback recreates the primitive from `before` and restores `bindings_before`. For integer IDs, direct SQL insert with explicit `id` is required; the public `create_rule/create_hook/create_command` helpers allocate new IDs and are unsuitable for exact restoration.
- MCP rollback must restore text id rows exactly, because `mcp_servers.id` is `TEXT PRIMARY KEY` at `backend/app/db/schema/_triggers_infra.py:9-29`.

Git rollback:

- Use Phase B's `phase_b_commit_sha`; if missing and `revert_git=True`, fail before DB mutation.
- Run `git -C <project_root> revert --no-edit <sha>` and return the new revert commit SHA from `git rev-parse HEAD`.
- If the working tree is dirty, refuse unless future implementation adds an explicit `force_git=True`. Phase C should not hide unrelated operator edits.

### 7. Verification / Test Strategy

Backend unit tests:

- `revert_round()` rejects non-`applied` states.
- Create rollback deletes the created primitive and removes the binding created by `add_binding()`.
- Update rollback restores all mutable fields: rules (`name`, `description`, `rule_type`, `condition`, `action`, `enabled`), hooks (`name`, `event`, `description`, `content`, `enabled`), commands (`name`, `description`, `content`, `arguments`, `enabled`), and MCP servers (`name`, `description`, `server_type`, `command`, `args`, `env_json`, `url`, `enabled`).
- Delete rollback reinserts the original row with the same id and restores prior project bindings.
- Conflict tests mutate the asset after apply and assert rollback refuses without `force=True`.
- Later-round tests create a second applied journal touching the same `{kind, asset_id}` and assert rollback refuses.
- Git tests monkeypatch `subprocess.run` to verify dirty-tree refusal, commit-sha requirement, successful `git revert`, and git-failure reporting.

Route tests:

- `POST /admin/evolution/rounds/{round_id}/revert` returns `reverted` on success and `conflict` with conflict details on later modification.
- `GET /admin/evolution/rounds/{round_id}` exposes `reverted_at`, `revert_error`, and `revert_conflicts`.

Migration tests:

- Existing applied rows still decode through `_row_to_dict()`.
- New rows can store and retrieve `apply_journal_json`, `eval_verdict_json`, and revert metadata.

Full verification after implementation:

```bash
just build
cd backend && uv run pytest
cd frontend && npm run test:run
```

