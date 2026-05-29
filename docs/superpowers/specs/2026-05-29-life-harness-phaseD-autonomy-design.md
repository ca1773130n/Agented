## 1. Current State

- The admin evolution routes expose project-scoped dry-run and live-run entry points: `POST /admin/projects/{project_id}/evolution/dry-run` calls `run_evolution_round(..., dry_run=True)`, while `POST /admin/projects/{project_id}/evolution/apply` calls the same service with `dry_run=False` ([backend/app_litestar/routes/harness_evolution.py:13](../../backend/app_litestar/routes/harness_evolution.py), [backend/app_litestar/routes/harness_evolution.py:30](../../backend/app_litestar/routes/harness_evolution.py)).
- Existing operator approval is a separate route, `POST /admin/evolution/rounds/{round_id}/apply`, which delegates to `apply_dry_run_round(round_id)` ([backend/app_litestar/routes/harness_evolution.py:79](../../backend/app_litestar/routes/harness_evolution.py)).
- Existing operator rejection is `POST /admin/evolution/rounds/{round_id}/abort`, which delegates to `abort_dry_run_round(round_id, reason=...)` ([backend/app_litestar/routes/harness_evolution.py:85](../../backend/app_litestar/routes/harness_evolution.py)).
- Round listing and detail routes return rows directly from `app.db.harness_evolution` (`list_for_project`, `list_all`, `get_round`) ([backend/app_litestar/routes/harness_evolution.py:47](../../backend/app_litestar/routes/harness_evolution.py), [backend/app_litestar/routes/harness_evolution.py:56](../../backend/app_litestar/routes/harness_evolution.py), [backend/app_litestar/routes/harness_evolution.py:64](../../backend/app_litestar/routes/harness_evolution.py)).
- The writable Forge kinds today are `rule`, `hook`, `command`, and `mcp_server`; `skill` is readable but not writable by the evolver ([backend/app/services/harness_evolver.py:62](../../backend/app/services/harness_evolver.py)).
- The evolver has a project-level rate limiter before it starts a round; it blocks existing `pending` / `running` rounds and recent successful rounds with status `applied` or `awaiting_approval` ([backend/app/services/harness_evolver.py:107](../../backend/app/services/harness_evolver.py), [backend/app/services/harness_evolver.py:134](../../backend/app/services/harness_evolver.py), [backend/app/services/harness_evolver.py:179](../../backend/app/services/harness_evolver.py)).
- `run_evolution_round` starts a DB row, marks it running, builds a scratch workspace, invokes Codex, reads `NOTES.md`, parses and validates the patch, then either marks the row `awaiting_approval` for dry runs or applies the patch and marks the row `applied` for live runs ([backend/app/services/harness_evolver.py:1072](../../backend/app/services/harness_evolver.py), [backend/app/services/harness_evolver.py:1102](../../backend/app/services/harness_evolver.py), [backend/app/services/harness_evolver.py:1112](../../backend/app/services/harness_evolver.py), [backend/app/services/harness_evolver.py:1119](../../backend/app/services/harness_evolver.py), [backend/app/services/harness_evolver.py:1134](../../backend/app/services/harness_evolver.py), [backend/app/services/harness_evolver.py:1145](../../backend/app/services/harness_evolver.py)).
- `apply_dry_run_round` only applies rows whose status is exactly `awaiting_approval`; other statuses return a failed `EvolutionResult` ([backend/app/services/harness_evolver.py:1169](../../backend/app/services/harness_evolver.py), [backend/app/services/harness_evolver.py:1176](../../backend/app/services/harness_evolver.py)).
- The patch applier directly calls the Forge create/update/delete repos and binds created primitives back to the project ([backend/app/services/harness_evolver.py:911](../../backend/app/services/harness_evolver.py), [backend/app/services/harness_evolver.py:919](../../backend/app/services/harness_evolver.py), [backend/app/services/harness_evolver.py:936](../../backend/app/services/harness_evolver.py), [backend/app/services/harness_evolver.py:945](../../backend/app/services/harness_evolver.py)).
- The `harness_evolution_rounds` schema currently stores `id`, `project_id`, timestamps, status, input window/count, `input_forge_json`, `output_patch_json`, `applied_asset_ids_json`, `error_message`, `notes`, and `scratch_dir`; it has no auto-apply audit columns today ([backend/app/db/schema/_harness_evolution.py:24](../../backend/app/db/schema/_harness_evolution.py)).
- The round status check allows only `pending`, `running`, `awaiting_approval`, `applied`, `failed`, and `aborted` ([backend/app/db/schema/_harness_evolution.py:29](../../backend/app/db/schema/_harness_evolution.py)).
- Repository helpers implement `mark_applied`, `mark_awaiting_approval`, and `mark_aborted` as state updates on `harness_evolution_rounds` ([backend/app/db/harness_evolution.py:53](../../backend/app/db/harness_evolution.py), [backend/app/db/harness_evolution.py:79](../../backend/app/db/harness_evolution.py), [backend/app/db/harness_evolution.py:126](../../backend/app/db/harness_evolution.py)).
- `get_round`, `list_for_project`, and `list_all` deserialize `input_forge_json`, `output_patch_json`, and `applied_asset_ids_json` into `input_forge`, `output_patch`, and `applied_asset_ids` ([backend/app/db/harness_evolution.py:139](../../backend/app/db/harness_evolution.py), [backend/app/db/harness_evolution.py:150](../../backend/app/db/harness_evolution.py), [backend/app/db/harness_evolution.py:160](../../backend/app/db/harness_evolution.py), [backend/app/db/harness_evolution.py:173](../../backend/app/db/harness_evolution.py)).
- The frontend API type currently has no autonomy fields on `EvolutionRound`; it includes status, timestamps, patch, applied assets, error, notes, and scratch dir ([frontend/src/services/api/harness-evolution.ts:43](../../frontend/src/services/api/harness-evolution.ts)).
- The frontend API exposes `dryRun`, `liveRun`, `approve`, `abort`, and `getImpact`; it does not expose config, autonomous apply, or revert methods today ([frontend/src/services/api/harness-evolution.ts:121](../../frontend/src/services/api/harness-evolution.ts), [frontend/src/services/api/harness-evolution.ts:127](../../frontend/src/services/api/harness-evolution.ts), [frontend/src/services/api/harness-evolution.ts:133](../../frontend/src/services/api/harness-evolution.ts), [frontend/src/services/api/harness-evolution.ts:139](../../frontend/src/services/api/harness-evolution.ts), [frontend/src/services/api/harness-evolution.ts:148](../../frontend/src/services/api/harness-evolution.ts)).
- `HarnessEvolutionCard` loads recent rounds and projects, runs dry-runs, and provides inline Approve/Abort only for `awaiting_approval` rounds ([frontend/src/views/dashboards/cards/HarnessEvolutionCard.vue:52](../../frontend/src/views/dashboards/cards/HarnessEvolutionCard.vue), [frontend/src/views/dashboards/cards/HarnessEvolutionCard.vue:89](../../frontend/src/views/dashboards/cards/HarnessEvolutionCard.vue), [frontend/src/views/dashboards/cards/HarnessEvolutionCard.vue:113](../../frontend/src/views/dashboards/cards/HarnessEvolutionCard.vue), [frontend/src/views/dashboards/cards/HarnessEvolutionCard.vue:130](../../frontend/src/views/dashboards/cards/HarnessEvolutionCard.vue), [frontend/src/views/dashboards/cards/HarnessEvolutionCard.vue:278](../../frontend/src/views/dashboards/cards/HarnessEvolutionCard.vue)).
- Lifecycle startup registers session-completion handlers for failure annotation, takeaway extraction, and Tesserae export, then starts scheduler setup; it does not register an evolution handler in this file today ([backend/app_litestar/lifecycle.py:364](../../backend/app_litestar/lifecycle.py), [backend/app_litestar/lifecycle.py:376](../../backend/app_litestar/lifecycle.py), [backend/app_litestar/lifecycle.py:392](../../backend/app_litestar/lifecycle.py), [backend/app_litestar/lifecycle.py:415](../../backend/app_litestar/lifecycle.py)).
- The session event channel supports `register_session_handler` and `emit_session_complete`, and swallows/logs per-handler exceptions so one handler cannot block the rest ([backend/app/services/execution_events.py:38](../../backend/app/services/execution_events.py), [backend/app/services/execution_events.py:48](../../backend/app/services/execution_events.py), [backend/app/services/execution_events.py:55](../../backend/app/services/execution_events.py)).
- The scheduler setup uses a `periodic_jobs` list and registers each item with APScheduler using `add_job(..., trigger="interval", id=..., replace_existing=True)` ([backend/app_litestar/lifecycle.py:186](../../backend/app_litestar/lifecycle.py), [backend/app_litestar/lifecycle.py:213](../../backend/app_litestar/lifecycle.py), [backend/app_litestar/lifecycle.py:245](../../backend/app_litestar/lifecycle.py)).
- The CLI script is still a manual operator path: it imports `run_evolution_round`, passes `--dry-run` through to `dry_run`, and exits success for `applied` or `awaiting_approval` ([backend/scripts/run_harness_evolution.py:21](../../backend/scripts/run_harness_evolution.py), [backend/scripts/run_harness_evolution.py:43](../../backend/scripts/run_harness_evolution.py), [backend/scripts/run_harness_evolution.py:45](../../backend/scripts/run_harness_evolution.py), [backend/scripts/run_harness_evolution.py:66](../../backend/scripts/run_harness_evolution.py)).

## 2. Policy Object Design

Create `backend/app/models/autonomy_policy.py` with a Pydantic v2 model:

```python
from pydantic import BaseModel, Field

class AutonomyPolicy(BaseModel):
    enabled: bool = False
    confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    max_ops_per_round: int = Field(default=5, ge=1)
    allowed_kinds: list[str] = Field(default_factory=lambda: ["rule", "memory"])
    denied_ops: list[str] = Field(default_factory=lambda: ["delete"])
    no_delete_operator_authored: bool = True
    cooldown_seconds: int = Field(default=3600, ge=0)
    rate_limit_per_day: int = Field(default=5, ge=0)
```

Notes:

- `enabled=False` preserves review-mode as the default.
- `allowed_kinds` should initially ship as `["rule"]` unless Phase C proves `memory` can be represented as a supported evolver patch kind. The requested example includes `memory`, but current `WRITABLE_KINDS` does not.
- Add a companion `AutonomousApplyDecision` model or typed dict for audit output: `eligible`, `gates`, `policy_snapshot`, `eval_verdict`, `round_id`, `project_id`, `timestamp`, `triggering_session_id`.

## 3. Decision Logic

Design `autonomous_apply_eligible(round, policy, eval_verdict) -> bool` as a thin wrapper over a richer evaluator:

```python
def evaluate_autonomous_apply(
    round_row: dict,
    policy: AutonomyPolicy,
    eval_verdict: EvalVerdict | None,
    *,
    triggering_session_id: str | None,
    now: datetime,
) -> AutonomousApplyDecision:
    ...

def autonomous_apply_eligible(round_row, policy, eval_verdict) -> bool:
    return evaluate_autonomous_apply(...).eligible
```

Required gates:

- `global_enabled`: block when `AGENTED_AUTONOMY=0`.
- `policy_enabled`: block when `policy.enabled` is false.
- `round_status`: require `awaiting_approval`; autonomous apply must reuse the dry-run approval path and never double-apply an `applied` row.
- `eval_present`: block if Phase C verdict is missing.
- `eval_passed`: require `eval_verdict.passed is True`.
- `confidence`: require `eval_verdict.confidence >= policy.confidence_threshold`.
- `blast_radius`: require `len(round.output_patch.entries) <= policy.max_ops_per_round`.
- `allowed_kinds`: require every entry kind in `policy.allowed_kinds` and in current service `WRITABLE_KINDS`.
- `denied_ops`: block any entry whose `op` is in `policy.denied_ops`.
- `operator_delete_guard`: when `no_delete_operator_authored` is true, block deletes of primitives whose source/author metadata indicates operator-authored content. If the relevant Forge tables lack author/source metadata, the gate must fail closed for deletes.
- `cooldown`: require no successful autonomous apply for the same project within `policy.cooldown_seconds`.
- `daily_rate_limit`: require count of autonomous applies in the previous 24h to be below `policy.rate_limit_per_day`.
- `concurrency`: require acquisition of a per-project autonomy lock before applying.
- `idempotency`: require the Phase C eval verdict idempotency key to match the round patch hash.

The decision function returns all gate results for observability. `True` is returned only when every gate passes.

## 4. Schema Changes

Modify `harness_evolution_rounds`:

```sql
ALTER TABLE harness_evolution_rounds ADD COLUMN auto_applied INTEGER NOT NULL DEFAULT 0;
ALTER TABLE harness_evolution_rounds ADD COLUMN auto_apply_reason TEXT;
ALTER TABLE harness_evolution_rounds ADD COLUMN auto_apply_blocked_reason TEXT;
```

Recommended indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_her_auto_project_started
ON harness_evolution_rounds(project_id, auto_applied, started_at DESC);
```

`auto_apply_reason` JSON shape:

```json
{
  "eligible": true,
  "timestamp": "2026-05-29T00:00:00Z",
  "triggering_session_id": "session-id",
  "eval": {"passed": true, "confidence": 0.91, "verdict": "pass"},
  "policy": {"confidence_threshold": 0.85, "max_ops_per_round": 5},
  "gates": [{"name": "confidence", "passed": true, "detail": "0.91 >= 0.85"}]
}
```

`auto_apply_blocked_reason` uses the same shape with `eligible=false` and failed gate details. Store only one of the two fields for a given decision attempt, with later evaluations allowed to update `auto_apply_blocked_reason` until the row is applied/aborted.

Update `mark_applied` to accept `auto_applied: bool = False` and `auto_apply_reason: dict | None = None`. Add `mark_auto_apply_blocked(round_id, reason: dict)` for failed gates.

## 5. Autonomy Config Storage

Option 1: JSON column on `projects`.

- Add `projects.autonomy_policy_json TEXT`.
- Pros: simple lookup, no join, mirrors existing JSON config fields such as `team_topology_config` and `grd_config`.
- Cons: harder to index by `enabled`, worse auditability for future policy history, grows the already broad `projects` row.

Option 2: new `project_autonomy_config` table.

```sql
CREATE TABLE IF NOT EXISTS project_autonomy_config (
    project_id TEXT PRIMARY KEY,
    policy_json TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_by TEXT,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_project_autonomy_enabled
ON project_autonomy_config(enabled);
```

- Pros: clean ownership, easy scheduler polling for enabled projects, future policy history/audit can be added without widening `projects`, avoids mixing operational autonomy state into product metadata.
- Cons: requires a join or second query.

Recommendation: use `project_autonomy_config`. The scheduler needs to poll enabled policies, and autonomy has operational safety/audit semantics distinct from the project profile.

Global kill switch:

- `AGENTED_AUTONOMY=0` disables all autonomous apply attempts, regardless of per-project policy.
- Any value other than exact `"0"` leaves per-project opt-in policy in control.
- This should be checked at every decision point, not only startup, so operators can stop autonomy with a process env restart and avoid stale in-memory policy.

## 6. Scheduler / Trigger Integration

Option A: session-complete hook.

- Add `app.services.harness_autonomy.on_session_complete(session_kind, session_id, project_id, status, output)`.
- Register it in `backend/app_litestar/lifecycle.py` after failure annotation and takeaway extraction.
- Handler behavior: if `project_id` exists, status is terminal/successful enough for Phase C to evaluate, and policy enabled, run a dry-run round (`dry_run=True`) or inspect the just-created round if Phase C owns round creation, fetch Phase C eval verdict, evaluate policy, then call an internal autonomous approval wrapper.
- Strength: fastest loop closure.
- Risk: session completion path already fans out to annotator/takeaway/Tesserae; Codex evolution is expensive and should run in a background thread/job, not inline.

Option B: periodic scheduler job.

- Add `process_autonomy_candidates_job()` in `harness_autonomy.py`.
- Register with APScheduler in lifecycle `periodic_jobs`, e.g. every 5 minutes with `max_instances=1`.
- Poll enabled projects, find `awaiting_approval` rounds with Phase C verdicts and no `auto_apply_reason`, evaluate policy, and apply or record blocked reason.
- Strength: catch-up, easier concurrency control, does not lengthen session-complete latency.
- Risk: slower feedback and does not create new rounds unless paired with a separate producer.

Option C: both.

- Session-complete handler enqueues/starts a dry-run round quickly after new evidence arrives.
- Scheduler job catches missed events, reevaluates rounds whose Phase C verdict arrived late, and enforces blocked-reason observability.

Recommendation: Option C. Use the session-complete hook for speed and the scheduler as a safety net. The handler should not apply inline; it should enqueue or spawn bounded background work. The scheduler should be the canonical catch-up path for eligible `awaiting_approval` rows.

Important correction to the prompt context: current code registers annotator, takeaway, and Tesserae session-complete handlers, but no visible session-complete call to `run_evolution_round` exists in the inspected files. Phase D should add this trigger path explicitly rather than assume it exists.

## 7. Operator UX Design

Settings:

- Add a per-project Settings section, `Harness Autonomy`.
- Controls: checkbox/toggle `Autonomous apply`, threshold slider/input for `confidence_threshold`, numeric input for `max_ops_per_round`, multi-select checkboxes for `allowed_kinds`, checkbox for `Block deletes`, checkbox for `Never delete operator-authored primitives`, numeric cooldown, numeric daily limit.
- Show global disabled state when backend reports `AGENTED_AUTONOMY=0`; disable controls with a concise status line.

HarnessEvolutionCard:

- Extend `EvolutionRound` type with `auto_applied`, `auto_apply_reason`, and `auto_apply_blocked_reason`.
- For `status === "applied" && auto_applied`, show a badge `Auto-applied` beside the existing status pill and show confidence if present, e.g. `0.91`.
- For blocked rows, show a subtle `Auto blocked` badge and a one-line reason from the failed gate.
- Keep manual Approve/Abort for `awaiting_approval` rows.
- Add `Revert` action for auto-applied rows, assuming Phase C exposes `POST /admin/evolution/rounds/{id}/revert`.

Audit log drawer:

- In the detail modal or a drawer launched from the card, render `auto_apply_reason.gates` as human-readable rows:
  - `Applied because: confidence 0.91 >= 0.85`
  - `3 ops <= max 5`
  - `Kinds rule, memory all allowed`
  - `No denied delete ops`
- Provide raw JSON behind a disclosure for support/debugging.

## 8. Files to Create / Modify

- Create `backend/app/models/autonomy_policy.py`: Pydantic v2 `AutonomyPolicy`, `EvalVerdict`, and decision/audit models.
- Create `backend/app/db/project_autonomy_config.py`: repository helpers for per-project policy get/upsert/list-enabled.
- Create `backend/app/services/harness_autonomy.py`: decision logic, scheduler job, session-complete handler, concurrency lock, autonomous approval wrapper.
- Create DB migration in `backend/app/db/migrations/v07_features.py` or next migration module: add round audit columns and create `project_autonomy_config`.
- Modify `backend/app/db/schema/_harness_evolution.py`: include new columns for fresh DBs.
- Modify `backend/app/db/schema/_orgs.py` only if the JSON-column option is selected; recommended design avoids this.
- Modify `backend/app/db/harness_evolution.py`: serialize/deserialize new audit fields, extend `mark_applied`, add `mark_auto_apply_blocked`, add helper queries for recent auto-applies.
- Modify `backend/app/services/harness_evolver.py`: expose an internal apply path that can mark `auto_applied=True`; keep manual `apply_dry_run_round` behavior unchanged.
- Modify `backend/app_litestar/routes/harness_evolution.py`: add config get/update routes and wire revert proxy only if Phase C endpoint exists.
- Modify `backend/app_litestar/lifecycle.py`: register autonomy session handler and scheduler job.
- Modify `frontend/src/services/api/harness-evolution.ts`: add autonomy fields, config API, and assumed revert method.
- Create `frontend/src/components/settings/HarnessAutonomySettings.vue`: project-level settings controls.
- Modify the relevant project settings view to mount `HarnessAutonomySettings.vue`.
- Modify `frontend/src/views/dashboards/cards/HarnessEvolutionCard.vue`: badges, confidence display, blocked reason, revert action.
- Modify `frontend/src/views/dashboards/cards/HarnessEvolutionDetailModal.vue`: audit log drawer/section and revert affordance.
- Add backend tests in `backend/tests/test_harness_autonomy.py`: policy gates, kill switch, cooldown/rate limit, delete guard, missing eval, concurrency.
- Add frontend tests for config controls and card badges/actions.

## 9. Edge Cases

Eval flaky:

- Phase C must write verdicts with an idempotency key derived from `round_id + patch_hash + evaluator_version`.
- Phase D should consume only the latest stable verdict for the exact patch hash.
- If multiple verdicts conflict for the same idempotency key, block autonomous apply and store `auto_apply_blocked_reason` with `gate="eval_stability"`.

Threshold gaming:

- Do not trust model self-reported confidence from the evolved patch prompt.
- Confidence must come from Phase C evaluator output, not from `NOTES.md` or Codex patch text.
- Add provenance to eval verdicts: evaluator name/version, input patch hash, and whether the verdict came from deterministic checks, LLM judge, or consensus.
- For high-risk kinds (`hook`, `mcp_server`, `command`) require manual approval initially or require a higher threshold plus mechanical validation.

Runaway loop:

- Add circuit breakers:
  - `rate_limit_per_day` and `cooldown_seconds` per policy.
  - global max autonomous applies per project per week.
  - no autonomous apply when the only evidence window is a session triggered by a previous autonomous apply unless enough independent sessions have occurred.
  - stop autonomy for the project after any revert of an auto-applied round until an operator re-enables it.

Conflicting concurrent rounds:

- Use a DB-backed per-project mutex table or transactional lock row: `project_autonomy_locks(project_id PRIMARY KEY, locked_at, holder)`.
- Acquire before policy evaluation and keep through `apply_patch` + `mark_applied`.
- Also enforce only one in-flight `pending`/`running`/autonomy-applying candidate per project.

Phase C eval not yet run:

- Missing verdict is a hard block.
- Store `auto_apply_blocked_reason` with `gate="eval_present"`.
- Scheduler may reevaluate after verdict appears, but must verify patch hash/idempotency key before applying.

## 10. Cross-Phase Contracts

Phase C assumptions:

- Eval verdict shape assumed by Phase D:

```json
{
  "passed": true,
  "confidence": 0.91,
  "verdict": "pass",
  "idempotency_key": "round:patch:evaluator",
  "patch_hash": "sha256...",
  "evaluator_version": "phase-c-v1",
  "created_at": "2026-05-29T00:00:00Z"
}
```

- Revert endpoint assumed by Phase D:
  - `POST /admin/evolution/rounds/{id}/revert`
  - Response mirrors `EvolutionRunResult` or returns `{round_id, status, reverted_asset_ids, error, notes}`.
  - Revert must be idempotent and must record a reversible audit row.

What Phase D must not do if Phase C is not shipped:

- Must not auto-apply without a Phase C verdict.
- Must not invent confidence from model output, notes, patch size, or status.
- Must not expose enabled autonomy controls as functional unless backend can persist policy and fetch trusted verdicts.
- Must not show revert controls unless the backend route exists and is wired to a real revert implementation.

## 11. Alternatives Considered

Simple threshold vs. multi-signal policy:

- Option 1: simple threshold gates (`passed` and `confidence >= threshold`) plus hard safety gates.
- Option 2: weighted composite score across confidence, patch size, kind risk, historical revert rate, mechanical checks, and evaluator agreement.
- Recommendation: start with simple threshold plus hard gates. It is auditable, easy to explain in the UI, and matches the Phase D scope. Add composite scoring later after collecting real false-positive/false-negative data.

JSON column vs. new table for autonomy config:

- Option 1: `projects.autonomy_policy_json`.
- Option 2: `project_autonomy_config`.
- Recommendation: new table. Autonomy is operational safety policy, not descriptive project metadata, and the scheduler benefits from an indexed `enabled` column.

Session-complete trigger vs. scheduler trigger vs. both:

- Option 1: session-complete only. Fast but risks doing expensive work in an event handler and misses late Phase C verdicts.
- Option 2: scheduler only. Simple and robust but slower and does not naturally tie to fresh evidence.
- Option 3: both. Session-complete creates timely candidates; scheduler catches missed/late candidates and records blocked reasons.
- Recommendation: both, with the scheduler as canonical catch-up and the session handler doing bounded enqueue/background work.

## 12. Verification Checklist

- `AutonomyPolicy` validates defaults and bounds.
- `AGENTED_AUTONOMY=0` blocks all autonomous applies.
- Disabled policy blocks and records an observable reason.
- Missing Phase C verdict blocks.
- Failed eval blocks.
- Confidence below threshold blocks.
- Patch with too many ops blocks.
- Disallowed kind blocks.
- Denied op blocks.
- Delete of operator-authored primitive blocks or fails closed if authorship cannot be determined.
- Cooldown and daily rate limit block.
- Concurrent eligible rounds for one project result in only one apply.
- Applying autonomous round sets `auto_applied=1` and stores `auto_apply_reason`.
- Blocked candidate stores `auto_apply_blocked_reason`.
- Manual approve/abort behavior remains unchanged.
- Frontend settings can fetch/update policy and respect global kill switch.
- HarnessEvolutionCard shows `Auto-applied`, confidence, blocked reason, and revert action only when applicable.
- Revert button is hidden or disabled until Phase C revert contract is available.
