# Project Discovery & Import — design

**Date:** 2026-06-14
**Status:** approved (design)
**Surface:** `/projects` page (frontend) + `/admin/projects/*` (backend)

## Summary

Add a **Discovery & Import** feature to the `/projects` page so the operator
doesn't have to hand-create a project for every repo that already exists on
disk. The operator points it at a folder; the backend scans subfolders for git
repos, de-duplicates against existing projects, and imports the selected new
ones as projects — optionally assigning an owner **Team** ("template") and
auto-running the existing one-click **harness-setup** on each, so every imported
repo lands ready to be driven by agents.

## Goals

- Scan a server-side folder for git repos and list them (new vs. already-imported).
- Bulk-import selected repos as projects, auto-filling `name`, `github_repo`
  (git remote), and `local_path`.
- Optionally assign an owner Team and run the existing harness-setup on each
  imported project, with per-project progress.
- Reuse existing machinery (`create_project`, `TeamHarnessSetupService`, the
  `harness-setup/status` endpoint) rather than reinventing setup.

## Non-goals (v1 / YAGNI)

- **No cloning** of remote repos — import is for repos already on disk under the
  scanned folder.
- **No named-template catalog / editor** and **no explicit bundle picker** — the
  "template" is the owner Team; bundles are auto-selected by detected stack
  (see Grounding). A richer template system is a future extension.
- **No streaming/async scan job** — the scan is synchronous and bounded. If
  deep scans of huge trees prove slow, async streaming is a future extension.

## Grounding (why "template" = owner Team)

The existing per-project harness-setup is the anchor for "template harness
environment". Confirmed from the code:

- `TeamHarnessSetupService.setup(project_id)` runs 6 ordered steps
  (`HARNESS_SETUP_STEP_KEYS`): `grd_init`, `team_topology`, `bundle_binding`,
  `tesserae_enable`, `default_policies`, `materialize_compile`
  (`backend/app/services/team_harness_setup_service.py`).
- `_step_team_topology` **requires** the project's `owner_team_id` (it raises
  without one) and builds SA instances from that team.
- `_step_bundle_binding` **auto-selects** bundles from the repo's detected stack
  via `_select_bundles_for_stack` (`forge-creator` floor + `forge-python` /
  `forge-typescript` from `STACK.md`) — there is no bundle parameter.
- The HTTP trigger `POST /api/projects/{project_id}/harness-setup`
  (`grd_routes.py:751`, mounted on `grd_router` at base path `/api/projects`)
  takes no template/bundle args; status is polled via
  `GET /api/projects/{project_id}/harness-setup/status` (`grd_routes.py:777`).

Therefore the meaningful, user-chosen "template" for an imported project is the
**owner Team** (+ a "run setup" toggle). Bundles are automatic.

`create_project(name, product_id=None, owner_team_id=None, github_repo=None,
local_path=None, ...)` (`backend/app/db/projects.py:18`) already accepts exactly
the fields import needs; all are optional except `name`.

## Architecture

### Backend

**New service — `app/services/project_discovery_service.py`**

- `scan(root, *, nested=False, max_depth=3) -> list[DiscoveredRepo]`
  - Validate `root`: must be an absolute, existing directory → else `ValueError`
    (surfaced as 400).
  - **Immediate mode** (default): each direct child directory containing a
    `.git` entry is a repo.
  - **Nested mode**: bounded `os.walk` capped at `max_depth`; skip an ignore set
    (`node_modules`, `.venv`, `venv`, `dist`, `build`, `.git`, `__pycache__`,
    `.cache`); once a directory is identified as a repo, do **not** descend into
    it (a repo's own subdirs/submodules are not separately imported in v1).
  - Per repo, collect: `name` (folder basename), `local_path` (abs),
    `remote_url` (`git -C <path> remote get-url origin`, best-effort →
    `None` for local-only), and dedup fields.
  - **Caps**: hard limits `max_depth <= 8` and `<= 500` repos returned;
    unreadable dirs are skipped and counted (`unreadable`).
- **Dedup**: `_mark_existing(repos)` lists current projects once and marks each
  discovered repo `already_imported=True` + `existing_project_id` when its
  `local_path` matches an existing project's `local_path` **or** its normalized
  remote URL matches an existing project's `github_repo`
  (normalize: strip scheme/`git@`/trailing `.git`/`/`, lowercase host+path).

`DiscoveredRepo` shape: `{ name, local_path, remote_url, already_imported,
existing_project_id }`.

**New routes (in the projects router, `/admin/projects`)**

- `POST /admin/projects/discover`
  - body `{ root: str, nested?: bool, max_depth?: int }`
  - returns `{ repos: DiscoveredRepo[], scanned: int, found: int,
    new_count: int, unreadable: int }`
  - synchronous; bounded by the caps above.
- `POST /admin/projects/import`
  - body `{ repos: { name, local_path, github_repo? }[], product_id?: str,
    owner_team_id?: str, run_harness_setup?: bool }`
  - For each repo: skip if it dedups to an existing project (defensive
    re-check); else `create_project(...)`. Per-repo failures are isolated.
  - If `run_harness_setup` **and** `owner_team_id` is set, spawn
    `TeamHarnessSetupService.setup` per created project on a daemon thread
    (mirrors `grd_routes.py:751`), flipping each to `running` first.
  - returns `{ imported: { project_id, name }[],
    skipped: { name, reason }[], setup_started: bool }`.
- Reuse existing `GET /api/projects/{id}/harness-setup/status` for progress
  (note the `/api/projects` base — distinct from the `/admin/projects`
  discover/import routes).

### Frontend

- **`src/services/api/projects.ts`** — add `discover(root, nested, maxDepth)` and
  `importRepos(payload)`; export types for `DiscoveredRepo` and the
  import response.
- **`src/components/projects/ProjectDiscoveryModal.vue`** (new):
  1. Folder path input + "only direct subfolders" (default) / "scan nested"
     toggle + max-depth field → **Scan** (calls `discover`).
  2. Results table: checkbox · name · `NEW`/`imported` badge · remote URL or
     "local only" · path. "Select all new" pre-checked; imported rows disabled.
  3. Target controls: **Product** dropdown (optional), **Team** dropdown
     (the template), "Run harness setup after import" toggle (default on;
     disabled with a hint when no Team is chosen).
  4. **Import N & set up** → calls `importRepos`; then renders per-project rows
     polling `harness-setup/status` (when setup ran), with links to each new
     project. Emits an event so the page refreshes its list.
- **`src/views/ProjectsPage.vue`** — add a "Discover repos" button beside
  "Create Project"; mount the modal; refresh project list on import success.
- **i18n** — new `projectsDiscovery.*` namespace in `en/ko/ja/zh` (key-identical).

## Data flow

Discover button → modal → enter folder → `POST /discover` (scan + dedup) →
operator selects repos + Product/Team + setup toggle → `POST /import`
(create projects + optionally spawn harness-setups) → frontend polls each new
project's `harness-setup/status` → on completion, `/projects` list refreshes.

## Error handling

- **Scan**: missing/non-absolute/non-dir `root` → 400 with a clear message;
  per-directory permission errors are skipped and counted (`unreadable`);
  depth/result caps prevent runaway walks.
- **Import**: each repo is created independently — one failure (bad path,
  duplicate, DB error) is captured in `skipped[]` with a reason and does not
  abort the batch. Repos that dedup to an existing project are skipped.
- **Harness-setup**: reuses the existing idempotent, no-rollback orchestrator
  (per-step failure handling already built in). The setup toggle is disabled
  unless a Team is selected, since `team_topology` requires `owner_team_id`.
- **git remote read failure**: `remote_url=None` (local-only repo) — still
  importable; dedup falls back to `local_path` only for that repo.

## Edge cases

- Repo with no remote → imported as local-only (`github_repo` unset).
- Same remote cloned to two paths → both shown; dedup is path-OR-remote, so the
  second is marked already-imported once the first is imported.
- Folder with zero git repos → empty results + "no repos found" message.
- Nested mode hitting the ignore set / depth cap → those branches are pruned
  (documented in the result counts).
- Re-scanning after an import → previously-imported repos show the `imported`
  badge (disabled).

## Testing

- **Backend**: `project_discovery_service` over a tmp tree of fake repos
  (create `.git` dirs / `git init`): immediate vs. nested, depth cap, ignore
  set, remote read, dedup (path + normalized remote). Import route: creates
  projects, isolates per-repo failure, dedups, spawns setup (mocked
  `TeamHarnessSetupService.setup`). Bad-root → 400.
- **Frontend**: `ProjectDiscoveryModal` (scan renders results, selection,
  import call, progress polling stub), `projectApi.discover/importRepos`,
  ProjectsPage button wiring. Stub network via the existing test patterns.
- **Verification**: `just build` (vue-tsc + vite) + targeted backend suite
  (new discovery/import tests + projects regressions) + frontend `test:run`
  (no new failures vs. the 7-failure baseline).

## Files

**New**
- `backend/app/services/project_discovery_service.py`
- `backend/tests/test_project_discovery_service.py` (+ import-route test, in an
  existing projects route test file or a new one)
- `frontend/src/components/projects/ProjectDiscoveryModal.vue`
- `frontend/src/components/projects/__tests__/ProjectDiscoveryModal.test.ts`

**Modified**
- `backend/app_litestar/routes/projects.py` — add `discover` + `import` handlers
  to `projects_router` (base `/admin/projects`; existing `create_project` is at
  line 95, router registration at line 655).
- `frontend/src/services/api/projects.ts` — `discover` / `importRepos` + types.
- `frontend/src/views/ProjectsPage.vue` — Discover button + modal mount + refresh.
- `frontend/src/locales/{en,ko,ja,zh}.json` — `projectsDiscovery.*`.
