# Phase B Forge Design: Materialized, Git-Traceable Artifacts

## Scope

Phase B makes successful harness evolution rounds produce real project artifacts, not only database rows. When a round is applied, Agented should:

1. Persist the proposed primitive CRUD changes to the Forge DB, as it does today.
2. Materialize the affected project-bound primitives into the project's filesystem under `.claude/`.
3. Create one git commit in the project repository that references the `harness_evolution_rounds.id` and the applied asset ids.
4. Allow `skill` to become a writable Forge kind by mapping DB skill rows to `.claude/skills/<name>/SKILL.md`.

The design intentionally keeps the DB as the source of truth for session compilation. The filesystem becomes the auditable projection of that source of truth, and git becomes the reversible history Phase C can evaluate and roll back.

## Cross-Phase Contract

Phase B must introduce a reusable materialization interface that Phase C can call without running Codex or mutating the canonical DB.

Recommended module:

```python
# backend/app/services/forge_materialization_service.py

@dataclass
class MaterializedFile:
    kind: str
    asset_id: str
    path: str
    action: Literal["written", "deleted", "unchanged"]
    content_hash: str | None = None

@dataclass
class MaterializationResult:
    project_id: str
    workspace_path: str
    kinds: list[str]
    files: list[MaterializedFile]
    changed_paths: list[str]
    deleted_paths: list[str]
    skipped: list[dict[str, str]]
    git_commit_sha: str | None = None
    git_dirty_before: bool = False

def materialize_primitives(
    project: Mapping[str, Any],
    kinds: Collection[str],
    workspace_path: Path | str,
) -> MaterializationResult:
    """Write selected bound Forge primitives into workspace_path/.claude."""
```

This exact three-argument function is the stable contract. It reads currently bound primitives for `project["id"]`, writes the selected `kinds` into `workspace_path/.claude`, and returns deterministic file-level results. It must not create git commits itself. A separate commit helper should consume `MaterializationResult` so Phase C can materialize into a sandbox without committing.

The function must also maintain `.claude/agented-forge/manifest.json`. The manifest records every Agented-generated file by `{kind, asset_id, path, content_hash}`. Deletes depend on this manifest: after a DB primitive is removed, the row may no longer be fetchable, so the materializer must compare the previous manifest with the currently bound primitive set and delete stale Agented-owned files for the requested `kinds`.

Phase C uses this contract in two ways:

- Eval gate: call `materialize_primitives(project, kinds, sandbox_path)` to build a disposable harness projection before running checks.
- Rollback: use the Phase B git commit SHA recorded on the evolution round as the revertible snapshot, via `git revert <sha>` or equivalent operator-controlled rollback.

## Gap 1: DB-Only Forged Primitives

### Current State

- `backend/app/services/harness_evolver.py:1-19` says the evolver reads bound Forge primitives, lets Codex edit a scratch workspace, and applies changes through DB repositories. It also says skills are deferred.
- `backend/app/services/harness_evolver.py:62-65` defines `WRITABLE_KINDS = ("rule", "hook", "command", "mcp_server")` and `READABLE_KINDS = ("rule", "skill", "hook", "command", "mcp_server")`.
- `backend/app/services/harness_evolver.py:516-595` builds a scratch-only workspace under `forge/<kind>s/*.json`.
- `backend/app/services/harness_evolver.py:782-851` diffs only `WRITABLE_KINDS` from the scratch workspace.
- `backend/app/services/harness_evolver.py:911-952` applies patches only through DB CRUD calls and returns `[{kind, op, asset_id}]`.
- `backend/app/services/harness_evolver.py:1145-1151` marks the round applied immediately after DB writes. No filesystem projection or git operation happens.
- `backend/app/db/project_forge_bindings.py:24` already allows `rule`, `skill`, `hook`, `command`, `mcp_server`, and `plugin` bindings.
- `backend/app/db/schema/_harness_evolution.py:24-43` stores the round, patch, applied asset ids, notes, and scratch dir, but no materialization result or git commit SHA.
- Project path resolution already exists: `ProjectWorkspaceService.resolve_working_directory()` prefers `project.local_path`, then clones/uses `github_repo` under `workspace_root/projects/{safe_name}` (`backend/app/services/project_workspace_service.py:74-134`). `projects.local_path`, `github_repo`, `github_host`, `clone_status`, and `last_synced_at` are defined in `backend/app/db/schema/_orgs.py:85-112` and populated through `create_project()` / `update_project()` in `backend/app/db/projects.py:18-116`.

### Recommended Approach

Add a materialization service that projects DB-bound Forge primitives into the project worktree after a successful apply.

Apply flow:

1. `apply_patch(patch, project_id)` continues to be responsible for DB CRUD and binding new assets.
2. `run_evolution_round()` and `apply_dry_run_round()` resolve the project workspace after DB apply:
   - `project = get_project(project_id)`
   - `workspace_path = ProjectWorkspaceService.resolve_working_directory(project_id)`
3. Call `materialize_primitives(project, _kinds_from_applied(applied), workspace_path)`.
4. If files changed, create a git commit in `workspace_path`.
5. Mark the round applied with the existing `applied_asset_ids_json` plus materialization and git metadata.

The commit should land in the resolved project repository, not Agented's own repo:

- For local projects, commit in `project.local_path`.
- For GitHub projects without `local_path`, commit in the clone returned by `ProjectWorkspaceService.resolve_working_directory()`, which is the workspace clone under `workspace_root/projects/{safe_name}`.
- Do not create a secondary worktree by default. Operator workflows already happen in the project checkout; committing in the same repo makes git history match what the operator sees. If future UI needs review branches, that can be a separate mode.

Commit only Agented-owned projection files. Use `git add -- <changed-paths>` with repo-relative paths from `MaterializationResult`, not `git add .`. This avoids sweeping in operator edits.

Commit message format:

```text
forge: apply harness evolution <round_id>

Round: <round_id>
Project: <project_id>
Applied-Assets: <compact-json-list>
Materialized-Paths:
- .claude/commands/<name>.md
- .claude/hooks/<name>.sh
- .claude/settings.json
- .claude/mcp.json
```

`Applied-Assets` should be compact JSON using the existing shape from `apply_patch()`, for example:

```json
[{"kind":"rule","op":"update","asset_id":12},{"kind":"skill","op":"create","asset_id":45}]
```

Recommended file projection:

- `command`: `.claude/commands/<safe-name>.md`
  - Body from `commands.content`.
  - YAML frontmatter should include `name`, `description`, `arguments` when present, `agented-kind`, `agented-asset-id`, and `agented-source: forge`.
  - Existing runtime overlay uses `commands/<safe>.md` (`context_compiler_service.py:213-218`), so this mirrors the session overlay.
- `hook`: `.claude/hooks/<safe-name>.sh` plus `.claude/settings.json`
  - Script body from `hooks.content`.
  - Add a shebang when missing, matching the overlay behavior in `claude_config_overlay.py:284-320`.
  - Register the hook command under `settings.json["hooks"][event]`, matching the overlay schema at `claude_config_overlay.py:326-340`.
  - Use relative command paths such as `.claude/hooks/<safe-name>.sh` in committed settings so the repository is portable.
- `mcp_server`: `.claude/mcp.json`
  - Merge into `mcpServers` by server name, matching `claude_config_overlay.py:263-281`.
  - Render only command/args/env/url/type-compatible keys, matching `_render_mcp_server()` in `context_compiler_service.py:221-227`, but fix the existing `env_json` mismatch by decoding `env_json` to `env` when possible.
  - Store `agented_asset_id` and `agented_source` inside generated server objects so stale entries can be removed safely.
- `rule`: `.claude/agented-forge/rules/<safe-name>.md`
  - Rules have no native `.claude` runtime file in the current code. Keep them as auditable artifacts in an Agented-owned subtree rather than pretending they are first-class Claude Code config.
  - Include YAML frontmatter with `name`, `description`, `rule_type`, `enabled`, `agented-kind`, `agented-asset-id`, and optional `condition`.
  - Body should be the rule action text, or description if action is empty.

Use deterministic writers. Re-running materialization for the same DB state should be a no-op at the git level.

The materializer should write `.claude/agented-forge/manifest.json` on every successful run. The manifest is the ownership boundary for cleanup: if a generated path is not in the current bound set but appears in the previous manifest for the same project/kind/asset id, delete it. Never delete files outside the manifest unless the file frontmatter contains a matching `agented-asset-id`.

### Alternatives

1. Commit DB export JSON under `.agented/forge/*.json`.
   - Pro: simple and lossless.
   - Con: does not make the forge real as harness artifacts; skills, commands, hooks, and MCP servers remain detached from their real layout.

2. Commit in a generated branch/worktree per round.
   - Pro: isolates operator changes and makes review easier.
   - Con: increases branch management and does not match the project's normal working tree. Better as a future review mode.

3. Make filesystem the source of truth and re-import DB from files.
   - Pro: git becomes canonical.
   - Con: too large for Phase B; current compiler, UI bindings, and DB repos all assume DB ownership.

Recommendation: DB remains canonical; `.claude` is a deterministic projection; one project-repo commit records each applied round.

### Files To Create Or Modify

- Create `backend/app/services/forge_materialization_service.py`
  - `MaterializedFile`
  - `MaterializationResult`
  - `materialize_primitives(project, kinds, workspace_path)`
  - per-kind render helpers
  - path-safety helpers
- Create `backend/app/services/forge_git_trace_service.py`
  - `is_git_repo(path) -> bool`
  - `commit_materialization(workspace_path, result, round_id, applied_asset_ids) -> str | None`
- Modify `backend/app/services/harness_evolver.py`
  - Import materialization and git trace helpers.
  - Extend `EvolutionResult` with `materialization` and `git_commit_sha`.
  - Call materialization + commit in both `run_evolution_round()` and `apply_dry_run_round()` after DB apply.
  - Keep dry-run behavior unchanged until explicit apply.
- Modify `backend/app/db/harness_evolution.py`
  - Let `mark_applied()` accept optional `materialization_result` and `git_commit_sha`.
  - Decode those fields in `_row_to_dict()`.
- Modify `backend/app/db/schema/_harness_evolution.py` and add a migration in `backend/app/db/migrations/v07_features.py`
  - Add `materialization_result_json TEXT`
  - Add `git_commit_sha TEXT`
- Optional later cleanup: make `context_compiler_service._render_mcp_server()` understand `env_json` when rendering MCP servers.

### Schema Changes

Add two nullable fields to `harness_evolution_rounds`:

```sql
ALTER TABLE harness_evolution_rounds ADD COLUMN materialization_result_json TEXT;
ALTER TABLE harness_evolution_rounds ADD COLUMN git_commit_sha TEXT;
```

No schema change is required for rules/hooks/commands because they already have `source_path` (`backend/app/db/schema/_plugins.py:69-127`). MCP servers do not have `source_path`; do not add it for Phase B because one MCP server can be globally bound to many projects and materialize to different repos. The per-round materialization result is the correct place for repo-specific paths.

### Key Signatures

```python
def _kinds_from_applied(applied: Sequence[Mapping[str, Any]]) -> set[str]:
    return {str(a["kind"]) for a in applied if a.get("kind")}

def commit_materialization(
    workspace_path: Path | str,
    result: MaterializationResult,
    *,
    round_id: str,
    project_id: str,
    applied_asset_ids: Sequence[Mapping[str, Any]],
) -> str | None:
    """Commit materialized paths and return the new commit SHA when one is created."""

def apply_patch(patch: EvolutionPatch, project_id: str) -> list[dict]:
    """Apply Forge DB CRUD and return applied asset descriptors."""
```

Keep `apply_patch()` focused on DB writes. Do not make it resolve workspaces or run git; that keeps DB application testable and lets Phase C use materialization independently.

### Edge Cases

- No git repository: DB apply and filesystem materialization should still succeed. Mark the round `applied`, set `git_commit_sha = None`, and include a skipped entry like `{"stage": "git", "reason": "workspace is not a git repository"}` in `materialization_result_json`. Do not fail the evolution round solely because git is absent.
- Dirty operator worktree: do not fail if unrelated files are dirty. Stage only materialized paths. If one of the materialized paths has pre-existing uncommitted changes, fail the git commit step with a clear skipped/error entry and leave DB + files applied. This prevents silently committing operator edits to the same harness file.
- No materialized diff: if DB changes render to identical files, do not create an empty commit. Record `changed_paths=[]` and `git_commit_sha=None`.
- Missing workspace: if neither `local_path` nor resolvable `github_repo` exists, DB apply should remain applied, materialization should be skipped with a clear reason, and the round should surface the warning.
- Path traversal: all filenames must pass through one slug/safe-name function; every resolved target must remain under `workspace_path/.claude`.
- Settings merge: hook materialization must update only Agented-owned hook entries, not delete operator-defined hooks. Add markers such as `agented_asset_id` in each hook entry so updates/deletes can target prior generated entries.
- MCP merge: preserve existing `mcpServers` entries not owned by the applied assets. For delete, remove the named server only if its entry is marked `agented_asset_id` matching the deleted asset.
- Stale generated files: delete only paths present in `.claude/agented-forge/manifest.json` for the current project and requested kinds. This is what makes DB deletes observable after the DB row is gone.
- Commit author: rely on repo git config by default. If git reports missing author identity, skip commit and record the git stderr; do not invent global identity.

### Verification

- Unit tests for `materialize_primitives()` with temp directories:
  - command writes `.claude/commands/<safe>.md`
  - hook writes script and merges `.claude/settings.json`
  - MCP merges `.claude/mcp.json`
  - rule writes `.claude/agented-forge/rules/<safe>.md`
  - stale manifest entries are deleted when a primitive is no longer bound
  - path traversal names are sanitized
  - second run is idempotent
- Unit tests for `commit_materialization()`:
  - commits only materialized paths
  - returns SHA on a git repo
  - skips with reason outside git
  - refuses to include pre-existing uncommitted changes on the same path
- Evolver tests:
  - `run_evolution_round(dry_run=False)` records `materialization_result` and `git_commit_sha`
  - `apply_dry_run_round()` performs materialization and commit only at approval time
  - missing workspace does not turn a DB-applied round into failed
- Full verification before implementation completion remains the repo standard: `just build`, `cd backend && uv run pytest`, and `cd frontend && npm run test:run`.

## Gap 2: Skills Deferred / Not Materialized

### Current State

- `backend/app/services/harness_evolver.py:16-19` says skill create/update is deferred because `.claude/skills/<name>/SKILL.md` needs filesystem materialization.
- `backend/app/services/harness_evolver.py:62-65` makes `skill` readable but not writable.
- `backend/app/services/harness_evolver.py:267-269` and `:330-331` tell Codex not to edit skills and to propose them in notes only.
- `backend/app/services/harness_evolver.py:440-455` fetches bound skills from `app.db.skills.get_user_skill()`.
- `backend/app/services/harness_evolver.py:508-512` projects skills as read-only payloads with `description` and `content`.
- `parse_patch()` explicitly skips skills by iterating only `WRITABLE_KINDS` (`backend/app/services/harness_evolver.py:790-808`).
- `project_forge_bindings.VALID_KINDS` already includes `skill` (`backend/app/db/project_forge_bindings.py:24`).
- Two skill tables exist:
  - `user_skills`: global registry with `skill_name`, `skill_path`, `description`, `enabled`, `selected_for_harness`, `metadata` (`backend/app/db/schema/_skills.py:6-18`).
  - `project_skills`: per-project association by `skill_name`, `skill_path`, `source` (`backend/app/db/schema/_skills.py:24-35`).
- Current imports from `.claude/skills/<name>/SKILL.md` only add `project_skills` entries and do not parse skill content into `user_skills` (`backend/app/services/harness_loader_service.py:299-322`).
- There is already precedent for rendering skill packages:
  - plugin export writes `skills/<slug>/SKILL.md` (`backend/app/services/plugin_export_service.py:88-96`).
  - skill conversation renders `name` and `description` frontmatter in `SKILL.md` (`backend/app/services/skill_conversation_service.py:1188-1212`).
  - takeaway extraction materializes generated skills below `.claude/skills/.agented-takeaways/` and registers `project_skills` (`backend/app/services/harness_takeaway_extractor.py:778-829`).

### Recommended Approach

Make `skill` writable as a first-class Forge primitive, backed by `user_skills` and projected to `.claude/skills/<safe-name>/SKILL.md`.

Add `skill` to:

```python
WRITABLE_KINDS = ("rule", "skill", "hook", "command", "mcp_server")
```

Update the guide and prompt to describe editable skill JSON:

```json
{
  "id": 123,
  "name": "review-pr-test-coverage",
  "payload": {
    "description": "Use when reviewing whether a PR has enough test coverage.",
    "content": "## When to use\nUse this skill when reviewing PR test coverage.\n\n## Steps\nInspect changed behavior and recommend focused tests.",
    "enabled": true
  }
}
```

DB behavior:

- Create:
  - Render the `SKILL.md` content into the project worktree path `.claude/skills/<safe-name>/SKILL.md`.
  - Create a `user_skills` row with `skill_name`, `skill_path`, `description`, `enabled=1`, `selected_for_harness=1`, and metadata containing `source`, `project_id`, and `round_id` when available.
  - Add a `project_forge_bindings` row with `kind="skill"` and `asset_id=<user_skills.id>`.
  - Also add or upsert a `project_skills` row for project-scoped discovery with `source="harness_evolver"`.
- Update:
  - Update `user_skills.skill_name`, `description`, `enabled`, and `metadata` as needed.
  - Rewrite `.claude/skills/<safe-name>/SKILL.md` during materialization.
  - If the skill name changes, delete the old generated directory only when it is Agented-owned and empty except generated files; otherwise leave it and record a skipped cleanup.
- Delete:
  - Delete the `user_skills` row through `delete_user_skill()`.
  - Remove the `project_forge_bindings` row by relying on DB cleanup if available, or explicitly remove the binding before/after delete.
  - Delete the `project_skills` row using `delete_project_skill(project_id, skill_name)`.
  - Remove `.claude/skills/<safe-name>/SKILL.md` and its empty generated directory during materialization.

Skill `SKILL.md` layout:

```markdown
---
name: review-pr-test-coverage
description: Use when reviewing whether a PR has enough test coverage.
agented-kind: skill
agented-asset-id: "123"
agented-source: forge
---

## When to use

Use this skill when reviewing whether a PR has enough test coverage.

## Steps

1. Inspect changed files and tests.
2. Identify uncovered behavior.
3. Recommend focused test additions.
```

Only `name` and `description` are required by this design. Extra Agented frontmatter is allowed and makes updates/deletes safe. Keep helper-file support out of Phase B; forge-evolved skills are `SKILL.md` only. The existing full skill wizard can continue to handle multi-file packages.

### Alternatives

1. Store skill content only in `project_skills`.
   - Pro: project-scoped table already exists.
   - Con: no content column; would require larger schema change and would not fit current `get_user_skill()` path in `harness_evolver.py:454-455`.

2. Store skill only as filesystem with no DB row.
   - Pro: closer to Claude Code package format.
   - Con: breaks Forge binding and context preview because `project_forge_bindings` needs an `asset_id`.

3. Keep skills as notes-only and let the operator use the skill wizard.
   - Pro: safest.
   - Con: does not close Phase B; the audit gap remains.

Recommendation: use `user_skills` as the Forge asset row, bind it to the project, mirror it into `project_skills`, and materialize `SKILL.md` deterministically.

### Files To Create Or Modify

- Modify `backend/app/services/harness_evolver.py`
  - Add `skill` to `WRITABLE_KINDS`.
  - Remove read-only prompt language for skills.
  - Update `_payload_for_kind("skill", asset)` to include `enabled`.
  - Add skill validation in `_validate_payload()`.
  - Add `_create_skill`, `_update_skill`, `_delete_skill` dispatchers.
- Modify `backend/app/db/skills.py`
  - No table change required.
  - Add helper `get_or_create_user_skill_by_name()` or make create/upsert explicit if duplicate names should update instead of fail.
- Modify `backend/app/db/projects.py`
  - Add an upsert helper for `project_skills` because `add_project_skill()` currently returns `None` on uniqueness conflicts (`backend/app/db/projects.py:244-264`).
- Use the new `backend/app/services/forge_materialization_service.py`
  - Add skill renderer and delete handling.

### Schema Changes

No required schema change for skill CRUD.

Optional but useful:

```sql
ALTER TABLE user_skills ADD COLUMN content TEXT;
```

Do not make that optional field a Phase B dependency. Existing code currently treats `content` as present in some dict renderers (`plugin_format.generate_skill_md()` reads `skill.get("content")`), but the `user_skills` schema does not define it. Phase B can keep skill content in `metadata` or reconstruct content from the `SKILL.md` file during materialization. The cleaner follow-up is a real `content` column, but it expands migration and UI implications.

For Phase B, recommended DB representation without schema change:

- `user_skills.skill_name`: skill name
- `user_skills.skill_path`: `.claude/skills/<safe-name>/SKILL.md` when project-local, or absolute path if already stored that way elsewhere
- `user_skills.description`: frontmatter description
- `user_skills.enabled`: boolean
- `user_skills.selected_for_harness`: `1`
- `user_skills.metadata`: JSON containing `content`, `agented_source`, `project_id`, and latest `round_id`

### Key Signatures

```python
def _create_skill(*, name: str, payload: dict, project_id: str) -> int | None:
    """Create or upsert a Forge-owned user skill and project binding."""

def _update_skill(*, asset_id: int, payload: dict) -> bool:
    """Update a Forge-owned user skill."""

def _delete_skill(*, asset_id: int, project_id: str | None = None) -> bool:
    """Delete a Forge-owned user skill and project association."""

def render_skill_md(skill: Mapping[str, Any]) -> str:
    """Render one skill row as .claude/skills/<name>/SKILL.md."""
```

The skill delete dispatcher needs `project_id` if it is responsible for `project_skills` cleanup. If keeping the current `_delete_dispatch[kind](asset_id=<id>)` shape is important, do DB asset deletion there and let materialization remove files from the post-apply result. The better implementation is to make dispatchers accept `project_id` for all kinds, even if only skill uses it.

### Edge Cases

- Duplicate skill name: prefer update/upsert for an existing `user_skills.skill_name` when metadata indicates `agented_source=harness_evolver`; otherwise fail validation with a clear duplicate-name error.
- Missing skill content: validation should require either `payload.content` or a non-empty description. If only description exists, render it as the body.
- Existing operator skill directory: do not overwrite `.claude/skills/<name>/SKILL.md` unless its frontmatter has `agented-source: forge` or matching `agented-asset-id`. On conflict, fail materialization for that skill and record the conflict.
- Multi-file skill packages: out of scope for Phase B. Leave existing non-`SKILL.md` files untouched.
- Name changes: render the new path, remove the old generated path only when owned by the same asset id.
- Global skill used by multiple projects: if a `user_skills` row is bound to more than one project, updating it changes all bindings. Validation should prevent auto-updating a skill with multiple project bindings unless the skill metadata says it is project-scoped to this project.

### Verification

- Patch parser detects create/update/delete for `forge/skills/*.json` after adding `skill` to `WRITABLE_KINDS`.
- Validation rejects skill payloads with no description and no content.
- Create skill:
  - writes/updates `user_skills`
  - binds `project_forge_bindings(kind="skill")`
  - upserts `project_skills`
  - materializes `.claude/skills/<name>/SKILL.md`
  - commits the file with the round id
- Update skill:
  - changes DB metadata/description
  - rewrites only the generated `SKILL.md`
  - creates exactly one round commit
- Delete skill:
  - removes DB binding and project skill association
  - deletes only Agented-owned generated files
  - commits the deletion
- Regression tests confirm existing rule/hook/command/MCP evolution still behaves as before when no skill entries are present.
