# Phase E: Make It Collective + Self-Feeding

Date: 2026-05-29

Scope: design only. No source behavior is changed by this document.

## Gap 1: Collective Propagation For Forged Primitives

### Current State

`project_forge_bindings` is explicitly project-scoped. Its CRUD module describes "per-project sticky Forge context defaults" consumed by `ContextCompilerService` and enforces `UNIQUE(project_id, kind, asset_id)` idempotency on add (`backend/app/db/project_forge_bindings.py:1`, `backend/app/db/project_forge_bindings.py:10`, `backend/app/db/project_forge_bindings.py:62`). The table itself has `project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE`, `kind`, `asset_id`, `role`, `enabled`, and `position`, with the same unique constraint (`backend/app/db/migrations/v07_features.py:187`, `backend/app/db/migrations/v07_features.py:197`).

The context compiler reads only `list_project_forge_bindings(project_id, enabled_only=True)` before merging session overrides (`backend/app/services/context_compiler_service.py:337`, `backend/app/services/context_compiler_service.py:339`). The evolver also reads only enabled bindings for one `project_id` in `gather_inputs()` (`backend/app/services/harness_evolver.py:369`, `backend/app/services/harness_evolver.py:377`) and creates new rule/hook/command rows with that same project id (`backend/app/services/harness_evolver.py:955`, `backend/app/services/harness_evolver.py:985`). New primitives are immediately bound back to the originating project via `bindings_repo.add_binding(project_id, kind, str(asset_id))` (`backend/app/services/harness_evolver.py:911`, `backend/app/services/harness_evolver.py:928`).

Rules, hooks, and commands already have a weak global layer in their own tables: `project_id` is nullable in schema and repository list calls include `project_id = ? OR project_id IS NULL` when scoped to a project (`backend/app/db/schema/_plugins.py:69`, `backend/app/db/schema/_plugins.py:89`, `backend/app/db/schema/_plugins.py:108`, `backend/app/db/rules.py:112`, `backend/app/db/hooks.py:98`, `backend/app/db/commands.py:108`). MCP servers are globally registered, with a separate `project_mcp_servers` assignment table (`backend/app/db/migrations/v04_initial.py:1994`, `backend/app/db/migrations/v04_initial.py:2013`), and the Forge binding layer can bind `mcp_server` by asset id (`backend/app/db/project_forge_bindings.py:24`).

HarnessSync exists as installed harness tooling, not as a current Forge propagation engine. Setup bundles `harness-sync` as the harness plugin (`backend/app/services/setup_service.py:24`, `backend/app/services/setup_service.py:100`), stores the selected harness plugin in settings (`backend/app_litestar/routes/admin_tooling.py:61`, `backend/app_litestar/routes/admin_tooling.py:77`), and exposes plugin sync status through `/admin/plugin-exports/{plugin_id}/sync-status` (`backend/app_litestar/routes/leaf_crud_g.py:487`, `backend/app_litestar/routes/leaf_crud_g.py:493`). The sync service can sync entity types `agent`, `skill`, `command`, `hook`, and `rule` to plugin disk, uses content hashes to skip unchanged writes, and guards its own writes with `_syncing_paths` (`backend/app/services/sync_persistence_service.py:56`, `backend/app/services/sync_persistence_service.py:89`, `backend/app/services/sync_persistence_service.py:101`). It does not currently sync MCP servers or Forge binding rows (`backend/app/services/sync_persistence_service.py:61`, `backend/app/services/sync_persistence_service.py:76`).

Memory decay already uses `HALF_LIFE_DAYS = 30` and `BASE_LAMBDA = log(2) / HALF_LIFE_DAYS`, then dampens decay by mention count (`backend/app/services/memory_evolution.py:11`, `backend/app/services/memory_evolution.py:13`, `backend/app/services/memory_evolution.py:153`, `backend/app/services/memory_evolution.py:197`). Reuse this weighting shape for promotion evidence so old wins fade unless they recur.

### Recommended Approach

Add an explicit shared-scope layer above project bindings:

1. Keep asset tables as the source of primitive payloads.
2. Promote proven project-local primitives into shared asset rows by setting `project_id = NULL` for rules/hooks/commands or by reusing the global `mcp_servers` registry.
3. Represent propagation intent in new shared binding tables instead of overloading `project_forge_bindings`.
4. Materialize project adoption as ordinary `project_forge_bindings` rows with provenance fields, so existing compiler/evolver code can keep consuming bindings through one read path after the repository is widened.

Promotion earns shared status through either:

1. Operator promotion: a direct admin action promotes an existing project primitive.
2. Phase C evidence: at least `min_success_sessions` distinct successful sessions across `min_project_count` projects, with an exponentially decayed score above `min_score`. Suggested default: `min_success_sessions = 5`, `min_project_count = 2`, `min_score = 0.72`, `half_life_days = 30`.

Promotion score:

```python
score = sum(eval_score * exp(-(ln(2) / half_life_days) * age_days) for eval in evidence)
normalized = min(1.0, score / min_success_sessions)
```

Phase C should provide the eval outcome, score, reason, session id, project id, primitive fingerprint, and primitive asset reference. Phase E does not rejudge sessions.

Binding policy:

1. `auto`: bind into matching projects automatically unless they have an explicit block or conflict.
2. `opt_in`: surface as recommended shared primitives; operator accepts per project or by project group.
3. `manual`: shared registry only; never auto-bind.

Default policy should be `opt_in` for hooks and MCP servers, `auto` for non-destructive rules and commands only when the primitive declares compatible harnesses and no conflict is detected.

### Alternatives

Alternative A: make `project_forge_bindings.project_id` nullable and use `NULL` as "global". This is small but creates ambiguous precedence and conflicts with the current `NOT NULL` FK and `UNIQUE(project_id, kind, asset_id)` model.

Alternative B: copy promoted assets into every project as project-local primitives. This is operationally simple but loses lineage, makes HarnessSync noisy, and creates propagation loops when copied primitives are later re-promoted.

Alternative C: rely only on `project_id IS NULL` rows in rules/hooks/commands. This already exists for listing, but it does not bind assets into runtime context, does not handle mcp_server/project assignment uniformly, and gives no adoption/audit trail.

### Files To Create Or Modify

Create:

1. `backend/app/db/shared_forge_bindings.py`
2. `backend/app/services/forge_promotion_service.py`
3. `backend/app/services/forge_propagation_service.py`
4. `backend/app/models/forge_propagation.py`
5. `backend/tests/test_shared_forge_bindings.py`
6. `backend/tests/test_forge_propagation_service.py`

Modify:

1. `backend/app/db/migrations/v07_features.py` or the next migration module: add shared propagation tables.
2. `backend/app/db/project_forge_bindings.py`: add optional provenance columns and query helpers; preserve existing public shape for current callers.
3. `backend/app/services/context_compiler_service.py`: consume resolved effective bindings from the binding repo, not raw project rows.
4. `backend/app/services/harness_evolver.py`: emit promotion candidates after apply and include shared-origin metadata in `gather_inputs()`.
5. `backend/app/services/sync_persistence_service.py`: sync shared rules/hooks/commands to the harness plugin and add support for shared binding manifests.
6. `backend/app_litestar/routes/project_forge_bindings.py`: add endpoints to list/adopt/block shared primitives.
7. Frontend settings/forge binding UI: show source, conflict state, and adoption policy.

### Schema Changes

```sql
CREATE TABLE shared_forge_bindings (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    scope                 TEXT NOT NULL DEFAULT 'org'
                          CHECK (scope IN ('org', 'workspace')),
    kind                  TEXT NOT NULL
                          CHECK (kind IN ('rule', 'skill', 'hook', 'command',
                                          'mcp_server', 'plugin')),
    asset_id              TEXT NOT NULL,
    role                  TEXT,
    enabled               INTEGER NOT NULL DEFAULT 1,
    propagation_policy    TEXT NOT NULL DEFAULT 'opt_in'
                          CHECK (propagation_policy IN ('auto', 'opt_in', 'manual')),
    compatibility_json    TEXT NOT NULL DEFAULT '{}',
    fingerprint           TEXT NOT NULL,
    promoted_from_project_id TEXT,
    promoted_from_binding_id INTEGER,
    promoted_by           TEXT NOT NULL DEFAULT 'operator'
                          CHECK (promoted_by IN ('operator', 'phase_c_eval')),
    promotion_score       REAL NOT NULL DEFAULT 0,
    promotion_evidence_json TEXT NOT NULL DEFAULT '[]',
    created_at            TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at            TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(scope, kind, fingerprint)
);

CREATE INDEX idx_sfb_enabled_policy
ON shared_forge_bindings(enabled, propagation_policy);

CREATE TABLE project_shared_forge_adoptions (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id            TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    shared_binding_id     INTEGER NOT NULL REFERENCES shared_forge_bindings(id)
                          ON DELETE CASCADE,
    state                 TEXT NOT NULL DEFAULT 'recommended'
                          CHECK (state IN ('recommended', 'adopted', 'blocked',
                                           'conflicted', 'superseded')),
    local_binding_id      INTEGER REFERENCES project_forge_bindings(id)
                          ON DELETE SET NULL,
    conflict_reason       TEXT,
    decided_by            TEXT,
    decided_at            TEXT,
    created_at            TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(project_id, shared_binding_id)
);

CREATE INDEX idx_psfa_project_state
ON project_shared_forge_adoptions(project_id, state);

ALTER TABLE project_forge_bindings ADD COLUMN source_scope TEXT NOT NULL DEFAULT 'project'
    CHECK (source_scope IN ('project', 'shared'));
ALTER TABLE project_forge_bindings ADD COLUMN source_shared_binding_id INTEGER
    REFERENCES shared_forge_bindings(id) ON DELETE SET NULL;
ALTER TABLE project_forge_bindings ADD COLUMN conflict_policy TEXT NOT NULL DEFAULT 'local_wins'
    CHECK (conflict_policy IN ('local_wins', 'shared_wins', 'manual'));
ALTER TABLE project_forge_bindings ADD COLUMN fingerprint TEXT;

CREATE UNIQUE INDEX idx_pfb_project_shared_source
ON project_forge_bindings(project_id, source_shared_binding_id)
WHERE source_shared_binding_id IS NOT NULL;
```

Do not change the existing `UNIQUE(project_id, kind, asset_id)` in place. It still protects duplicate materialized project bindings. Shared adoption gets its own idempotency through `project_shared_forge_adoptions`.

### Key Signatures

```python
from typing import Any, Literal, Optional, TypedDict

ForgeKind = Literal["rule", "skill", "hook", "command", "mcp_server", "plugin"]
PropagationPolicy = Literal["auto", "opt_in", "manual"]
AdoptionState = Literal["recommended", "adopted", "blocked", "conflicted", "superseded"]


class PromotionEvidence(TypedDict):
    project_id: str
    session_kind: str
    session_id: str
    eval_score: float
    eval_outcome: str
    observed_at: str
    round_id: Optional[str]


class SharedForgeBinding(TypedDict):
    id: int
    scope: str
    kind: ForgeKind
    asset_id: str
    role: Optional[str]
    enabled: bool
    propagation_policy: PropagationPolicy
    compatibility: dict[str, Any]
    fingerprint: str
    promotion_score: float
    promotion_evidence: list[PromotionEvidence]


def fingerprint_primitive(kind: ForgeKind, asset: dict[str, Any]) -> str: ...


def promote_primitive(
    *,
    project_id: str,
    kind: ForgeKind,
    asset_id: str,
    promoted_by: Literal["operator", "phase_c_eval"],
    evidence: list[PromotionEvidence],
    propagation_policy: PropagationPolicy = "opt_in",
) -> SharedForgeBinding: ...


def list_effective_bindings(
    project_id: str,
    *,
    enabled_only: bool = False,
    include_recommended: bool = False,
) -> list[dict[str, Any]]: ...


def compute_propagation_plan(
    shared_binding_id: int,
    *,
    target_project_ids: Optional[list[str]] = None,
) -> list[dict[str, Any]]: ...


def apply_propagation_plan(
    plan: list[dict[str, Any]],
    *,
    actor: str = "system",
) -> dict[str, int]: ...


def sync_shared_primitives_to_harnesses(
    *,
    plugin_id: str,
    plugin_dir: str,
    harnesses: list[Literal["claude", "codex", "gemini", "opencode"]],
) -> dict[str, Any]: ...
```

### Conflict Handling

Conflict fingerprint is computed from normalized payload fields, not display names alone. A collision is:

1. Same `kind` and same normalized `name`, but different fingerprint.
2. Same behavior fingerprint but different asset ids.
3. Hook same `event` and same trigger matcher but materially different content.
4. MCP same `name` but different command/url/env shape.

Resolution order:

1. Explicit project-local binding wins by default.
2. Existing `project_shared_forge_adoptions.state = blocked` suppresses propagation.
3. Identical fingerprint becomes `adopted` and links to the shared binding without duplicating asset payload.
4. Different fingerprint becomes `conflicted`; no runtime binding is added.
5. Operator can set `shared_wins` to replace the materialized local binding, or `manual` to keep both with ordered positions.

### HarnessSync Design

HarnessSync should distribute the shared layer as a generated plugin manifest, then rely on existing plugin disk sync for concrete rule/hook/command payloads:

1. Extend `SyncService.sync_entity_to_disk()` for entity type `shared_binding_manifest` and `mcp_server`.
2. Write `shared-forge/bindings.json` containing shared binding ids, fingerprints, compatibility, propagation policy, source asset references, and adoption defaults.
3. Continue writing commands to `commands/*.md`, skills to `skills/*/SKILL.md`, and hooks/rules to `hooks/hooks.json` using existing paths (`backend/app/services/sync_persistence_service.py:339`, `backend/app/services/sync_persistence_service.py:354`).
4. For Codex/Gemini/OpenCode, HarnessSync adapters should translate the manifest into their native rule, command, hook, and MCP config locations. Agented remains the source of truth; file watchers may report drift but must not auto-promote file-only edits.
5. After sync completes, write/update `app_meta.harness_synced_at`, matching the existing setup-status marker read by health (`backend/app_litestar/routes/health.py:157`, `backend/app_litestar/routes/health.py:159`).

### Edge Cases

Propagation loops: a materialized shared binding must set `source_scope = 'shared'` and `source_shared_binding_id`. The promotion service must ignore these rows as promotion sources unless the local project explicitly forks them, producing a new fingerprint and lineage.

Cross-project conflicts: conflicts stay local to `project_shared_forge_adoptions`; one project's block or override must not mutate the shared binding or other projects' adoption rows.

Harness drift: HarnessSync file watcher updates to generated files should update the underlying asset only when a sync_state row maps the file to a known entity. Shared binding manifests should be one-way from DB to disk unless a future signed import format is added.

Deleted shared primitives: soft-disable shared binding first, mark all adoption rows `superseded`, and leave materialized project bindings disabled rather than deleting them.

Credential-bearing MCP servers: never auto-propagate `env_json` secrets. Compatibility metadata can declare required env keys; project adoption supplies overrides locally.

## Gap 2: Tesserae KG As Evolution Source

### Current State

`tesserae_integration.py` is producer-side plumbing: it pushes Agented session history into Tesserae's `HarnessSession` import surface (`backend/app/services/tesserae_integration.py:1`, `backend/app/services/tesserae_integration.py:8`). The integration is opt-in by `projects.tesserae_project_root` (`backend/app/services/tesserae_integration.py:12`, `backend/app/services/tesserae_integration.py:15`). On successful session completion, it exports all sessions and may auto-compile the graph (`backend/app/services/tesserae_integration.py:896`, `backend/app/services/tesserae_integration.py:922`, `backend/app/services/tesserae_integration.py:933`, `backend/app/services/tesserae_integration.py:936`).

The import path is full-batch and destructive from Tesserae's perspective (`backend/app/services/tesserae_integration.py:17`, `backend/app/services/tesserae_integration.py:25`). `export_sessions_to_tesserae()` gathers project sessions and decisions, writes a temporary JSON payload, then runs `tesserae project sessions import` (`backend/app/services/tesserae_integration.py:489`, `backend/app/services/tesserae_integration.py:508`, `backend/app/services/tesserae_integration.py:529`, `backend/app/services/tesserae_integration.py:535`).

The only query helper today is `ask_tesserae(project_id, question, top_k=5)`, which shells out to `tesserae ask` and returns markdown or `None` (`backend/app/services/tesserae_integration.py:948`, `backend/app/services/tesserae_integration.py:975`). The evolver uses Tesserae only in `build_workspace()`, not `gather_inputs()`: it creates `tesserae_context.md` by asking one question per top-five takeaway and treats failures as a no-op (`backend/app/services/harness_evolver.py:569`, `backend/app/services/harness_evolver.py:586`, `backend/app/services/harness_evolver.py:600`, `backend/app/services/harness_evolver.py:663`). `gather_inputs()` currently returns only primitives, trajectories, and unapplied takeaways (`backend/app/services/harness_evolver.py:421`, `backend/app/services/harness_evolver.py:437`).

### Recommended Approach

Add optional KG signal ingestion inside `gather_inputs()`, before workspace build. The KG signal should be structured evidence, not only prose context. `build_workspace()` can still write markdown for Codex, but the round audit and dedup logic need typed rows.

Use these Tesserae queries:

1. `fresh_insights`: source for recent discoveries, regressions, and high-signal new takeaways. Map to `signal_type = 'fresh_insight'`.
2. `search_facts`: source for recurring decisions, constraints, and established project facts. Run targeted queries derived from top takeaways, incident summaries, and changed primitive names. Map to `signal_type = 'fact'` or `decision`.
3. `tesserae_ask`: source for synthesized answers when the evolver needs a bounded explanation of why a pattern recurs. Map to `signal_type = 'synthesis'`.
4. `graph_ppr`: source for cluster context around primitive names, rule concepts, session ids, and file paths. Map to `signal_type = 'cluster'`.
5. `list_communities`: source for stable community/cluster labels. Map to `signal_type = 'community_pattern'`, useful when several sessions point at the same subsystem.

Ingress should be feature-flagged:

```text
AGENTED_EVOLUTION_KG_SIGNALS=1
AGENTED_EVOLUTION_KG_SIGNAL_LIMIT=20
AGENTED_EVOLUTION_KG_MIN_WEIGHT=0.25
```

`gather_inputs()` should add:

```python
{
    "kg_signals": [
        {
            "source": "tesserae",
            "query_kind": "fresh_insights",
            "signal_type": "fresh_insight",
            "content": "...",
            "node_ids": ["..."],
            "fingerprint": "...",
            "weight": 0.81,
            "observed_at": "...",
            "expires_at": "...",
            "dedup_state": "new",
        }
    ]
}
```

The workspace builder should write these to `kg_signals/*.json` and a concise `kg_signals/SUMMARY.md`. Codex sees KG evidence alongside trajectories and takeaways, but patch validation remains unchanged.

### Alternatives

Alternative A: continue only writing `tesserae_context.md`. This is cheap and already works, but cannot dedup, weight, audit, or promote KG-driven changes reliably.

Alternative B: import all Tesserae graph nodes into Agented SQLite. This enables rich local queries but duplicates Tesserae and risks stale graph copies.

Alternative C: ask one broad `tesserae_ask` question per evolution round. This bounds cost but misses structured recurring facts and makes weighting opaque.

### Schema Changes

```sql
CREATE TABLE harness_kg_signals (
    id                  TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source              TEXT NOT NULL DEFAULT 'tesserae',
    query_kind          TEXT NOT NULL
                        CHECK (query_kind IN ('tesserae_ask', 'search_facts',
                                              'fresh_insights', 'graph_ppr',
                                              'list_communities')),
    signal_type         TEXT NOT NULL
                        CHECK (signal_type IN ('decision', 'takeaway', 'fresh_insight',
                                               'community_pattern', 'cluster',
                                               'fact', 'synthesis')),
    content             TEXT NOT NULL,
    node_ids_json       TEXT NOT NULL DEFAULT '[]',
    related_assets_json TEXT NOT NULL DEFAULT '[]',
    fingerprint         TEXT NOT NULL,
    weight              REAL NOT NULL DEFAULT 0,
    observed_at         TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at          TEXT,
    dedup_state         TEXT NOT NULL DEFAULT 'new'
                        CHECK (dedup_state IN ('new', 'duplicate_primitive',
                                               'duplicate_signal', 'dismissed',
                                               'promoted')),
    consumed_round_id   TEXT REFERENCES harness_evolution_rounds(id)
                        ON DELETE SET NULL,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(project_id, source, fingerprint)
);

CREATE INDEX idx_hkg_project_weight
ON harness_kg_signals(project_id, dedup_state, weight DESC);

ALTER TABLE harness_evolution_rounds ADD COLUMN input_kg_signals_json TEXT
    NOT NULL DEFAULT '[]';
```

### Key Signatures

```python
from datetime import datetime
from typing import Any, Literal, Optional, TypedDict

KGQueryKind = Literal[
    "tesserae_ask",
    "search_facts",
    "fresh_insights",
    "graph_ppr",
    "list_communities",
]

KGSignalType = Literal[
    "decision",
    "takeaway",
    "fresh_insight",
    "community_pattern",
    "cluster",
    "fact",
    "synthesis",
]


class KGSignal(TypedDict):
    id: str
    project_id: str
    source: Literal["tesserae"]
    query_kind: KGQueryKind
    signal_type: KGSignalType
    content: str
    node_ids: list[str]
    related_assets: list[dict[str, Any]]
    fingerprint: str
    weight: float
    observed_at: str
    expires_at: Optional[str]
    dedup_state: str


def gather_inputs(
    project_id: str,
    *,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 25,
    include_kg_signals: bool = False,
) -> dict[str, Any]: ...


def query_tesserae_signals(
    project_id: str,
    *,
    primitives: dict[str, list[dict]],
    trajectories: list[dict[str, Any]],
    takeaways: list[dict[str, Any]],
    limit: int = 20,
) -> list[KGSignal]: ...


def run_tesserae_query(
    project_id: str,
    query_kind: KGQueryKind,
    payload: dict[str, Any],
    *,
    timeout_seconds: int = 60,
) -> list[dict[str, Any]]: ...


def dedup_kg_signals(
    project_id: str,
    signals: list[KGSignal],
    primitives: dict[str, list[dict]],
) -> list[KGSignal]: ...


def weight_kg_signal(
    signal: KGSignal,
    *,
    now: datetime,
    half_life_days: int = 30,
) -> float: ...
```

### Dedup And Weighting

Dedup KG-derived signal against already-forged primitives using the same primitive fingerprinting from Gap 1. A KG signal is `duplicate_primitive` when its normalized content matches an existing primitive payload or when Tesserae node ids are already recorded in `promotion_evidence_json`. A signal is `duplicate_signal` when `(project_id, source, fingerprint)` already exists in `harness_kg_signals`.

Weight formula:

```python
base = {
    "decision": 0.85,
    "fresh_insight": 0.75,
    "community_pattern": 0.65,
    "cluster": 0.55,
    "fact": 0.50,
    "synthesis": 0.45,
    "takeaway": 0.70,
}[signal_type]
recurrence_boost = min(0.25, 0.05 * len(node_ids))
age_decay = exp(-(log(2) / half_life_days) * age_days)
weight = min(1.0, (base + recurrence_boost) * age_decay)
```

Signals below `AGENTED_EVOLUTION_KG_MIN_WEIGHT` are persisted for audit but excluded from `gather_inputs()` output.

### Edge Cases

KG noise: require either `weight >= min_weight` or at least two independent node ids for auto-fed signals. Single-node low-confidence facts should only appear in `kg_signals/SUMMARY.md` under ignored evidence.

Stale signal: apply the same 30-day half-life shape as `memory_evolution.py`; also set `expires_at` for fresh insights after 60 days unless re-observed.

Compiled graph lag: `on_session_complete()` imports sessions and may schedule compile asynchronously (`backend/app/services/tesserae_integration.py:933`, `backend/app/services/tesserae_integration.py:936`). If the compile is stale or a query fails, `gather_inputs()` should return an empty `kg_signals` list and include a diagnostic, never fail the evolution round.

Prompt injection from KG content: KG content came from sessions and docs, so serialize it as evidence JSON, not executable instructions. The evolver prompt should say KG signals are observations, not commands.

Circular evidence: a primitive forged from KG signal should record the KG signal id in notes/evidence. Future KG imports from sessions that mention that primitive must dedup against `related_assets_json` and `source_shared_binding_id`.

## Cross-Phase Contracts

Phase E consumes Phase B's binding model as the runtime materialization layer: `project_forge_bindings(project_id, kind, asset_id, role, enabled, position)` remains the concrete project context surface. Phase E adds shared provenance and adoption tables around it, but `ContextCompilerService` should still compile effective project bindings through the binding repo.

Phase E consumes Phase C eval as promotion evidence, not as raw session text. Required Phase C record shape:

```python
class PrimitiveEvalEvidence(TypedDict):
    project_id: str
    session_kind: str
    session_id: str
    primitive_kind: ForgeKind
    primitive_asset_id: str
    primitive_fingerprint: str
    eval_outcome: Literal["positive", "neutral", "negative"]
    eval_score: float
    reason: str
    evaluated_at: str
    round_id: Optional[str]
```

Phase E must not promote from failed, aborted, or unresolved evals. It may use `awaiting_approval` evolution rounds as candidate evidence only after operator approval; `harness_evolution_rounds` already distinguishes `awaiting_approval` and `applied` (`backend/app/db/schema/_harness_evolution.py:29`, `backend/app/db/schema/_harness_evolution.py:39`).

