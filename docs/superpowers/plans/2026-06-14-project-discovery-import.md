# Project Discovery & Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Discover & Import feature to `/projects` that scans a folder for git repos, de-duplicates against existing projects, bulk-imports the new ones, and optionally runs the existing harness-setup on each using a chosen owner Team as the "template".

**Architecture:** A new backend `ProjectDiscoveryService` does the filesystem scan + dedup + import (reusing `db_create_project` and `TeamHarnessSetupService`); two thin routes (`POST /admin/projects/discover`, `POST /admin/projects/import`) expose it on the existing `projects_router`. The frontend adds `projectApi.discover/importRepos`, a `ProjectDiscoveryModal.vue` wizard, and a "Discover repos" button on `ProjectsPage`. Setup progress reuses the existing `GET /api/projects/{id}/harness-setup/status`.

**Tech Stack:** Python / Litestar / SQLite (raw) / pytest; Vue 3 + TypeScript / Vitest + @vue/test-utils / vue-i18n.

**Spec:** `docs/superpowers/specs/2026-06-14-project-discovery-import-design.md`

---

## File Structure

**Backend**
- Create `backend/app/services/project_discovery_service.py` — scan + dedup + import orchestration.
- Modify `backend/app_litestar/routes/projects.py` — add `discover_repos` + `import_discovered_repos` handlers; register them.
- Create `backend/tests/test_project_discovery_service.py` — unit tests for scan/dedup/import.
- Modify `backend/tests/test_litestar_projects.py` — route tests for discover/import.

**Frontend**
- Modify `frontend/src/services/api/types/projects.ts` — `DiscoveredRepo`, `DiscoverResponse`, `ImportResponse`.
- Modify `frontend/src/services/api/projects.ts` — `discover` + `importRepos`.
- Create `frontend/src/components/projects/ProjectDiscoveryModal.vue` — the wizard.
- Create `frontend/src/components/projects/__tests__/ProjectDiscoveryModal.test.ts`.
- Modify `frontend/src/views/ProjectsPage.vue` — Discover button + modal mount + refresh.
- Modify `frontend/src/locales/{en,ko,ja,zh}.json` — `projectsDiscovery` namespace.

---

## Task 1: Discovery service — filesystem scan

**Files:**
- Create: `backend/app/services/project_discovery_service.py`
- Test: `backend/tests/test_project_discovery_service.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_project_discovery_service.py`:

```python
"""Tests for ProjectDiscoveryService: filesystem scan, dedup, import."""

import os
import subprocess

from app.services import project_discovery_service as pds


def _make_repo(root: str, name: str) -> str:
    """Create a directory with a .git marker so it scans as a repo."""
    path = os.path.join(root, name)
    os.makedirs(os.path.join(path, ".git"), exist_ok=True)
    return path


def test_scan_fs_finds_immediate_child_repos(tmp_path):
    root = str(tmp_path)
    _make_repo(root, "alpha")
    _make_repo(root, "beta")
    os.makedirs(os.path.join(root, "notes"))  # no .git -> skipped

    repos, unreadable = pds._scan_fs(root, nested=False, max_depth=3)

    names = sorted(r["name"] for r in repos)
    assert names == ["alpha", "beta"]
    assert unreadable == 0
    assert all(r["local_path"].startswith(root) for r in repos)


def test_scan_fs_nested_finds_deep_repos_and_skips_ignored(tmp_path):
    root = str(tmp_path)
    _make_repo(root, "top")
    _make_repo(os.path.join(root, "sub"), "deep")
    _make_repo(os.path.join(root, "node_modules"), "vendored")  # ignored dir

    immediate, _ = pds._scan_fs(root, nested=False, max_depth=3)
    nested, _ = pds._scan_fs(root, nested=True, max_depth=3)

    assert sorted(r["name"] for r in immediate) == ["top"]
    found = sorted(r["name"] for r in nested)
    assert "top" in found and "deep" in found
    assert "vendored" not in found  # node_modules pruned


def test_scan_fs_does_not_descend_into_a_found_repo(tmp_path):
    root = str(tmp_path)
    outer = _make_repo(root, "outer")
    _make_repo(outer, "inner")  # inner repo nested inside a repo

    nested, _ = pds._scan_fs(root, nested=True, max_depth=5)

    names = [r["name"] for r in nested]
    assert names == ["outer"]  # stops at outer, never reaches inner
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_project_discovery_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.project_discovery_service'` (or `AttributeError: _scan_fs`).

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/services/project_discovery_service.py`:

```python
"""ProjectDiscoveryService — scan a folder for git repos, dedup against
existing projects, and bulk-import them (optionally running harness-setup).

The backend runs on the operator's own machine, so scanning a server-side
folder path is the operator inspecting their own filesystem. Scans are bounded
(depth + result caps) and best-effort (unreadable dirs are skipped + counted).
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
from typing import Optional

from app.database import create_project as db_create_project
from app.database import get_all_projects

logger = logging.getLogger(__name__)

_IGNORE_DIRS = {
    "node_modules", ".venv", "venv", "dist", "build", ".git",
    "__pycache__", ".cache", ".tox", ".next", "target",
}
_MAX_DEPTH_CAP = 8
_MAX_REPOS = 500


def _is_repo(path: str) -> bool:
    """A directory is a repo when it has a ``.git`` entry (dir or file)."""
    return os.path.exists(os.path.join(path, ".git"))


def _git_remote_url(path: str) -> Optional[str]:
    """Best-effort ``git remote get-url origin``; None for local-only repos."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:
        logger.debug("git remote read failed for %s", path, exc_info=True)
    return None


def _scan_fs(root: str, nested: bool, max_depth: int) -> tuple[list[dict], int]:
    """Return ``(repos, unreadable_count)``.

    Each repo dict: ``{name, local_path, remote_url}``. ``nested=False`` lists
    direct child repos; ``nested=True`` walks (depth-capped, ignore-pruned) and
    stops descending once a repo is found (no submodule double-import).
    """
    repos: list[dict] = []
    unreadable = 0

    def _add(path: str) -> None:
        repos.append({
            "name": os.path.basename(path.rstrip("/")),
            "local_path": path,
            "remote_url": _git_remote_url(path),
        })

    if not nested:
        try:
            entries = sorted(os.scandir(root), key=lambda e: e.name)
        except OSError as e:
            raise ValueError(f"cannot read folder: {e}")
        for entry in entries:
            if len(repos) >= _MAX_REPOS:
                break
            try:
                if entry.is_dir(follow_symlinks=False) and _is_repo(entry.path):
                    _add(entry.path)
            except OSError:
                unreadable += 1
        return repos, unreadable

    depth_cap = min(max_depth, _MAX_DEPTH_CAP)
    base_depth = root.rstrip("/").count(os.sep)
    for dirpath, dirnames, _files in os.walk(root):
        if len(repos) >= _MAX_REPOS:
            break
        depth = dirpath.rstrip("/").count(os.sep) - base_depth
        if depth >= depth_cap:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS]
        if dirpath != root and _is_repo(dirpath):
            _add(dirpath)
            dirnames[:] = []  # don't descend into a found repo
    return repos, unreadable
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_project_discovery_service.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/project_discovery_service.py backend/tests/test_project_discovery_service.py
git commit -m "feat(discovery): filesystem scan for git repos (immediate + nested)"
```

---

## Task 2: Dedup + `scan()` entry point

**Files:**
- Modify: `backend/app/services/project_discovery_service.py`
- Test: `backend/tests/test_project_discovery_service.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_project_discovery_service.py`:

```python
def test_short_remote_normalizes_forms():
    assert pds._short_remote("git@github.com:org/repo.git") == "github.com/org/repo"
    assert pds._short_remote("https://github.com/org/repo") == "github.com/org/repo"
    assert pds._short_remote("https://github.com/org/repo.git") == "github.com/org/repo"
    assert pds._short_remote("ssh://git@gitlab.com/org/repo.git") == "gitlab.com/org/repo"
    assert pds._short_remote(None) is None
    assert pds._short_remote("") is None


def test_scan_marks_already_imported_by_path_and_remote(tmp_path, isolated_db):
    from app.database import create_project as db_create_project

    root = str(tmp_path)
    a = _make_repo(root, "alpha")   # will dedup by local_path
    b = _make_repo(root, "beta")    # will dedup by remote
    _make_repo(root, "gamma")       # new

    db_create_project(name="Alpha", local_path=a)
    db_create_project(name="Beta", github_repo="github.com/org/beta")

    # Real git remote so beta resolves to github.com/org/beta
    subprocess.run(["git", "init", "-q"], cwd=b, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:org/beta.git"],
        cwd=b, check=True,
    )

    result = pds.ProjectDiscoveryService.scan(root, nested=False, max_depth=3)

    by_name = {r["name"]: r for r in result["repos"]}
    assert by_name["alpha"]["already_imported"] is True
    assert by_name["beta"]["already_imported"] is True
    assert by_name["gamma"]["already_imported"] is False
    assert result["new_count"] == 1


def test_scan_rejects_missing_root():
    import pytest

    with pytest.raises(ValueError):
        pds.ProjectDiscoveryService.scan("/no/such/folder/xyz", nested=False, max_depth=3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_project_discovery_service.py -q`
Expected: FAIL — `AttributeError: module ... has no attribute '_short_remote'` / `ProjectDiscoveryService`.

- [ ] **Step 3: Write minimal implementation**

Append to `backend/app/services/project_discovery_service.py`:

```python
def _short_remote(url: Optional[str]) -> Optional[str]:
    """Normalize a git remote URL to ``host/owner/repo`` for display + dedup.

    ``git@github.com:org/repo.git`` and ``https://github.com/org/repo`` both
    collapse to ``github.com/org/repo``. Returns None for empty input.
    """
    if not url:
        return None
    s = url.strip()
    s = re.sub(r"^git@([^:]+):", r"\1/", s)          # scp-style ssh
    s = re.sub(r"^[a-z][a-z0-9+.-]*://", "", s, flags=re.IGNORECASE)  # scheme
    s = re.sub(r"^[^@/]+@", "", s)                    # user@ (ssh://user@host)
    s = re.sub(r"\.git$", "", s, flags=re.IGNORECASE)
    s = s.rstrip("/").lower()
    return s or None


class ProjectDiscoveryService:
    """Scan / dedup / import entry points for the discovery feature."""

    @classmethod
    def scan(cls, root: str, *, nested: bool = False, max_depth: int = 3) -> dict:
        if not root or not isinstance(root, str):
            raise ValueError("root folder is required")
        abs_root = os.path.abspath(os.path.expanduser(root))
        if not os.path.isdir(abs_root):
            raise ValueError(f"not a directory: {root}")
        repos, unreadable = _scan_fs(abs_root, nested, max_depth)
        cls._mark_existing(repos)
        new_count = sum(1 for r in repos if not r["already_imported"])
        return {
            "repos": repos,
            "scanned": len(repos),
            "found": len(repos),
            "new_count": new_count,
            "unreadable": unreadable,
        }

    @classmethod
    def _mark_existing(cls, repos: list[dict]) -> None:
        existing = get_all_projects()
        path_to_id = {
            os.path.abspath(p["local_path"]): p["id"]
            for p in existing
            if p.get("local_path")
        }
        remote_to_id = {}
        for p in existing:
            sr = _short_remote(p.get("github_repo"))
            if sr:
                remote_to_id[sr] = p["id"]
        for r in repos:
            ap = os.path.abspath(r["local_path"])
            sr = _short_remote(r.get("remote_url"))
            existing_id = path_to_id.get(ap) or (remote_to_id.get(sr) if sr else None)
            r["already_imported"] = existing_id is not None
            r["existing_project_id"] = existing_id
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_project_discovery_service.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/project_discovery_service.py backend/tests/test_project_discovery_service.py
git commit -m "feat(discovery): dedup vs existing projects + scan() entry point"
```

---

## Task 3: `import_repos()` — create projects + spawn harness-setup

**Files:**
- Modify: `backend/app/services/project_discovery_service.py`
- Test: `backend/tests/test_project_discovery_service.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_project_discovery_service.py`:

```python
def test_import_repos_creates_projects_and_skips_dupes(tmp_path, isolated_db):
    from app.database import create_project as db_create_project, get_all_projects

    existing_path = str(tmp_path / "already")
    db_create_project(name="Already", local_path=existing_path)

    repos = [
        {"name": "fresh", "local_path": str(tmp_path / "fresh"),
         "remote_url": "git@github.com:org/fresh.git"},
        {"name": "Already", "local_path": existing_path, "remote_url": None},
        {"name": "", "local_path": "", "remote_url": None},  # invalid
    ]

    result = pds.ProjectDiscoveryService.import_repos(repos, run_harness_setup=False)

    assert [i["name"] for i in result["imported"]] == ["fresh"]
    reasons = {s["name"]: s["reason"] for s in result["skipped"]}
    assert reasons["Already"] == "already imported"
    assert "(unknown)" in reasons
    assert result["setup_started"] is False
    # The fresh project is persisted with the normalized remote.
    created = [p for p in get_all_projects() if p["name"] == "fresh"][0]
    assert created["github_repo"] == "github.com/org/fresh"


def test_import_repos_spawns_harness_setup_when_team_given(tmp_path, isolated_db, monkeypatch):
    from app.db.teams import create_team

    team_id = create_team(name="Backend")  # owner_team_id has a FK to teams

    calls = []
    monkeypatch.setattr(
        pds.ProjectDiscoveryService, "_spawn_harness_setup",
        classmethod(lambda cls, pid: calls.append(pid)),
    )

    repos = [{"name": "fresh", "local_path": str(tmp_path / "fresh"), "remote_url": None}]
    result = pds.ProjectDiscoveryService.import_repos(
        repos, owner_team_id=team_id, run_harness_setup=True,
    )

    assert result["setup_started"] is True
    assert calls == [result["imported"][0]["project_id"]]


def test_import_repos_no_setup_without_team(tmp_path, isolated_db, monkeypatch):
    calls = []
    monkeypatch.setattr(
        pds.ProjectDiscoveryService, "_spawn_harness_setup",
        classmethod(lambda cls, pid: calls.append(pid)),
    )
    repos = [{"name": "fresh", "local_path": str(tmp_path / "fresh"), "remote_url": None}]
    result = pds.ProjectDiscoveryService.import_repos(
        repos, owner_team_id=None, run_harness_setup=True,
    )
    assert result["setup_started"] is False
    assert calls == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_project_discovery_service.py -q`
Expected: FAIL — `AttributeError: ... has no attribute 'import_repos'`.

- [ ] **Step 3: Write minimal implementation**

Append these methods inside the `ProjectDiscoveryService` class in `backend/app/services/project_discovery_service.py`:

```python
    @classmethod
    def import_repos(
        cls,
        repos: list[dict],
        *,
        product_id: Optional[str] = None,
        owner_team_id: Optional[str] = None,
        run_harness_setup: bool = False,
        user_id: Optional[str] = None,
    ) -> dict:
        existing = get_all_projects()
        path_ids = {
            os.path.abspath(p["local_path"]): p["id"]
            for p in existing
            if p.get("local_path")
        }
        remote_ids = {}
        for p in existing:
            sr = _short_remote(p.get("github_repo"))
            if sr:
                remote_ids[sr] = p["id"]

        imported: list[dict] = []
        skipped: list[dict] = []
        for r in repos:
            name = (r.get("name") or "").strip()
            local_path = (r.get("local_path") or "").strip()
            if not name or not local_path:
                skipped.append({"name": name or "(unknown)", "reason": "missing name or local_path"})
                continue
            ap = os.path.abspath(local_path)
            sr = _short_remote(r.get("github_repo") or r.get("remote_url"))
            if ap in path_ids or (sr and sr in remote_ids):
                skipped.append({"name": name, "reason": "already imported"})
                continue
            try:
                pid = db_create_project(
                    name=name,
                    github_repo=sr,
                    local_path=local_path,
                    owner_team_id=owner_team_id,
                    product_id=product_id,
                    user_id=user_id,
                )
            except Exception:
                logger.warning("import: create_project failed for %s", name, exc_info=True)
                pid = None
            if not pid:
                skipped.append({"name": name, "reason": "create failed"})
                continue
            imported.append({"project_id": pid, "name": name})
            path_ids[ap] = pid
            if sr:
                remote_ids[sr] = pid

        setup_started = False
        if run_harness_setup and owner_team_id and imported:
            for it in imported:
                cls._spawn_harness_setup(it["project_id"])
            setup_started = True
        return {"imported": imported, "skipped": skipped, "setup_started": setup_started}

    @classmethod
    def _spawn_harness_setup(cls, project_id: str) -> None:
        """Flip status to running + run the 6-step setup off-thread (mirrors
        grd_routes.trigger_harness_setup)."""
        try:
            from app.db.projects import set_harness_setup_status
            from app.services.team_harness_setup_service import TeamHarnessSetupService

            set_harness_setup_status(project_id, "running")
            threading.Thread(
                target=TeamHarnessSetupService.setup,
                args=(project_id,),
                daemon=True,
                name=f"harness-setup-{project_id}",
            ).start()
        except Exception:
            logger.warning("harness setup spawn failed for %s", project_id, exc_info=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_project_discovery_service.py -q`
Expected: PASS (9 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/project_discovery_service.py backend/tests/test_project_discovery_service.py
git commit -m "feat(discovery): import_repos creates projects + spawns harness-setup"
```

---

## Task 4: Routes — `/admin/projects/discover` + `/admin/projects/import`

**Files:**
- Modify: `backend/app_litestar/routes/projects.py` (add 2 handlers near `create_project`; register in `projects_router` ~line 655)
- Test: `backend/tests/test_litestar_projects.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_litestar_projects.py` (reuses the file's existing `_client`, `create_user_role`, `isolated_db`):

```python
def test_discover_lists_repos_with_new_flags(isolated_db, tmp_path):
    import os
    from app.database import create_project as db_create_project

    create_user_role("admin-key-disc", "Admin", "admin")
    root = str(tmp_path)
    for n in ("alpha", "beta"):
        os.makedirs(os.path.join(root, n, ".git"), exist_ok=True)
    db_create_project(name="Alpha", local_path=os.path.join(root, "alpha"))

    with _client() as c:
        resp = c.post(
            "/admin/projects/discover",
            headers={"X-API-Key": "admin-key-disc"},
            json={"root": root, "nested": False},
        )
    assert resp.status_code == 201
    body = resp.json()
    by_name = {r["name"]: r for r in body["repos"]}
    assert by_name["alpha"]["already_imported"] is True
    assert by_name["beta"]["already_imported"] is False
    assert body["new_count"] == 1


def test_discover_rejects_bad_root(isolated_db):
    create_user_role("admin-key-disc2", "Admin", "admin")
    with _client() as c:
        resp = c.post(
            "/admin/projects/discover",
            headers={"X-API-Key": "admin-key-disc2"},
            json={"root": "/no/such/dir/zzz"},
        )
    assert resp.status_code == 400


def test_import_creates_projects(isolated_db, tmp_path, monkeypatch):
    from app.services.project_discovery_service import ProjectDiscoveryService

    # Don't spawn real setup threads in the test.
    monkeypatch.setattr(
        ProjectDiscoveryService, "_spawn_harness_setup",
        classmethod(lambda cls, pid: None),
    )
    from app.db.teams import create_team

    create_user_role("admin-key-imp", "Admin", "admin")
    team_id = create_team(name="Backend")  # owner_team_id has a FK to teams
    with _client() as c:
        resp = c.post(
            "/admin/projects/import",
            headers={"X-API-Key": "admin-key-imp"},
            json={
                "repos": [{"name": "fresh", "local_path": str(tmp_path / "fresh")}],
                "owner_team_id": team_id,
                "run_harness_setup": True,
            },
        )
    assert resp.status_code == 201
    body = resp.json()
    assert [i["name"] for i in body["imported"]] == ["fresh"]
    assert body["setup_started"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_litestar_projects.py -q -k "discover or import_creates"`
Expected: FAIL — 404 (routes not registered).

- [ ] **Step 3: Write minimal implementation**

In `backend/app_litestar/routes/projects.py`, add the import near the top (after the other `from app.services...` imports):

```python
from app.services.project_discovery_service import ProjectDiscoveryService
```

Add the two handlers immediately after the `create_project` handler:

```python
@post("/discover", sync_to_thread=False)
def discover_repos(data: dict, caller: Caller) -> dict[str, Any]:
    del caller  # auth gate only; scan reads the operator's own filesystem
    if not data or not data.get("root"):
        raise ClientException(detail="root folder is required")
    try:
        return ProjectDiscoveryService.scan(
            data["root"],
            nested=bool(data.get("nested", False)),
            max_depth=int(data.get("max_depth", 3)),
        )
    except ValueError as e:
        raise ClientException(detail=str(e))


@post("/import", sync_to_thread=False)
def import_discovered_repos(data: dict, caller: Caller) -> dict[str, Any]:
    repos = (data or {}).get("repos") or []
    if not repos:
        raise ClientException(detail="repos is required")
    return ProjectDiscoveryService.import_repos(
        repos,
        product_id=(data.get("product_id") or None),
        owner_team_id=(data.get("owner_team_id") or None),
        run_harness_setup=bool(data.get("run_harness_setup", False)),
        user_id=caller.user_id,
    )
```

In the `projects_router = Router(...)` registration list (~line 655), add both handlers right after `create_project,`:

```python
        create_project,
        discover_repos,
        import_discovered_repos,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_litestar_projects.py -q -k "discover or import_creates"`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app_litestar/routes/projects.py backend/tests/test_litestar_projects.py
git commit -m "feat(discovery): POST /admin/projects/discover + /import routes"
```

---

## Task 5: Frontend API — types + `discover`/`importRepos`

**Files:**
- Modify: `frontend/src/services/api/types/projects.ts`
- Modify: `frontend/src/services/api/projects.ts`

- [ ] **Step 1: Add response types**

In `frontend/src/services/api/types/projects.ts`, append after the `Project` interface:

```typescript
export interface DiscoveredRepo {
  name: string;
  local_path: string;
  remote_url: string | null;
  already_imported: boolean;
  existing_project_id: string | null;
}

export interface DiscoverResponse {
  repos: DiscoveredRepo[];
  scanned: number;
  found: number;
  new_count: number;
  unreadable: number;
}

export interface ImportResponse {
  imported: { project_id: string; name: string }[];
  skipped: { name: string; reason: string }[];
  setup_started: boolean;
}
```

- [ ] **Step 2: Add the API methods**

In `frontend/src/services/api/projects.ts`, add the new types to the existing `import type { ... } from './types';` block:

```typescript
  DiscoverResponse,
  ImportResponse,
```

Then add these two methods to the `projectApi` object, right after the `create:` method:

```typescript
  discover: (data: { root: string; nested?: boolean; max_depth?: number }) =>
    apiFetch<DiscoverResponse>('/admin/projects/discover', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  importRepos: (data: {
    repos: { name: string; local_path: string; github_repo?: string }[];
    product_id?: string;
    owner_team_id?: string;
    run_harness_setup?: boolean;
  }) =>
    apiFetch<ImportResponse>('/admin/projects/import', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
```

- [ ] **Step 3: Verify it type-checks**

Run: `cd frontend && npx vue-tsc --noEmit -p tsconfig.json 2>&1 | head -20`
Expected: no errors referencing `projects.ts` / `DiscoverResponse` / `ImportResponse`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/services/api/types/projects.ts frontend/src/services/api/projects.ts
git commit -m "feat(discovery): projectApi.discover + importRepos + types"
```

---

## Task 6: i18n — `projectsDiscovery` namespace (4 locales)

**Files:**
- Modify: `frontend/src/locales/en.json`, `ko.json`, `ja.json`, `zh.json`

- [ ] **Step 1: Add the `projectsDiscovery` namespace**

Add this sibling key after the `"projects": { ... }` object in each locale file (keys identical across all four).

`en.json`:
```json
"projectsDiscovery": {
  "button": "Discover repos",
  "title": "Discover & import projects",
  "folderLabel": "Folder to scan",
  "folderPlaceholder": "e.g., /Users/you/Developer/Projects",
  "directOnly": "Only direct subfolders",
  "scanNested": "Scan nested",
  "maxDepth": "Max depth",
  "scan": "Scan",
  "scanning": "Scanning…",
  "foundSummary": "Found {found} ({count} new)",
  "noneFound": "No git repos found in that folder.",
  "selectAllNew": "Select all new",
  "newBadge": "NEW",
  "importedBadge": "imported",
  "localOnly": "local only",
  "productLabel": "Product (optional)",
  "noProduct": "No product",
  "teamLabel": "Owner team (template)",
  "noTeam": "Select a team…",
  "runSetup": "Run harness setup after import",
  "setupNeedsTeam": "Pick an owner team to enable harness setup",
  "import": "Import {count} & set up",
  "importNoSetup": "Import {count}",
  "importing": "Importing…",
  "importedSummary": "Imported {count} project(s)",
  "skippedSummary": "{count} skipped",
  "rootRequired": "Enter a folder to scan",
  "scanError": "Scan failed",
  "importError": "Import failed",
  "close": "Close"
}
```

`ko.json`:
```json
"projectsDiscovery": {
  "button": "리포지토리 검색",
  "title": "프로젝트 검색 및 가져오기",
  "folderLabel": "검색할 폴더",
  "folderPlaceholder": "예: /Users/you/Developer/Projects",
  "directOnly": "직속 하위 폴더만",
  "scanNested": "중첩 검색",
  "maxDepth": "최대 깊이",
  "scan": "검색",
  "scanning": "검색 중…",
  "foundSummary": "{found}개 발견 (신규 {count}개)",
  "noneFound": "해당 폴더에서 git 리포지토리를 찾지 못했습니다.",
  "selectAllNew": "신규 전체 선택",
  "newBadge": "신규",
  "importedBadge": "가져옴",
  "localOnly": "로컬 전용",
  "productLabel": "제품 (선택)",
  "noProduct": "제품 없음",
  "teamLabel": "소유 팀 (템플릿)",
  "noTeam": "팀 선택…",
  "runSetup": "가져온 후 하니스 설정 실행",
  "setupNeedsTeam": "하니스 설정을 사용하려면 소유 팀을 선택하세요",
  "import": "{count}개 가져오고 설정",
  "importNoSetup": "{count}개 가져오기",
  "importing": "가져오는 중…",
  "importedSummary": "{count}개 프로젝트를 가져왔습니다",
  "skippedSummary": "{count}개 건너뜀",
  "rootRequired": "검색할 폴더를 입력하세요",
  "scanError": "검색 실패",
  "importError": "가져오기 실패",
  "close": "닫기"
}
```

`ja.json`:
```json
"projectsDiscovery": {
  "button": "リポジトリを検出",
  "title": "プロジェクトの検出とインポート",
  "folderLabel": "スキャンするフォルダ",
  "folderPlaceholder": "例: /Users/you/Developer/Projects",
  "directOnly": "直下のサブフォルダのみ",
  "scanNested": "ネストもスキャン",
  "maxDepth": "最大深度",
  "scan": "スキャン",
  "scanning": "スキャン中…",
  "foundSummary": "{found} 件検出（新規 {count} 件）",
  "noneFound": "そのフォルダに git リポジトリが見つかりませんでした。",
  "selectAllNew": "新規をすべて選択",
  "newBadge": "新規",
  "importedBadge": "インポート済み",
  "localOnly": "ローカルのみ",
  "productLabel": "プロダクト（任意）",
  "noProduct": "プロダクトなし",
  "teamLabel": "オーナーチーム（テンプレート）",
  "noTeam": "チームを選択…",
  "runSetup": "インポート後にハーネスをセットアップ",
  "setupNeedsTeam": "ハーネスのセットアップにはオーナーチームを選択してください",
  "import": "{count} 件をインポートしてセットアップ",
  "importNoSetup": "{count} 件をインポート",
  "importing": "インポート中…",
  "importedSummary": "{count} 件のプロジェクトをインポートしました",
  "skippedSummary": "{count} 件スキップ",
  "rootRequired": "スキャンするフォルダを入力してください",
  "scanError": "スキャンに失敗しました",
  "importError": "インポートに失敗しました",
  "close": "閉じる"
}
```

`zh.json`:
```json
"projectsDiscovery": {
  "button": "发现仓库",
  "title": "发现并导入项目",
  "folderLabel": "要扫描的文件夹",
  "folderPlaceholder": "例如：/Users/you/Developer/Projects",
  "directOnly": "仅直接子文件夹",
  "scanNested": "扫描嵌套",
  "maxDepth": "最大深度",
  "scan": "扫描",
  "scanning": "扫描中…",
  "foundSummary": "发现 {found} 个（{count} 个新）",
  "noneFound": "该文件夹中未找到 git 仓库。",
  "selectAllNew": "全选新项",
  "newBadge": "新",
  "importedBadge": "已导入",
  "localOnly": "仅本地",
  "productLabel": "产品（可选）",
  "noProduct": "无产品",
  "teamLabel": "所属团队（模板）",
  "noTeam": "选择团队…",
  "runSetup": "导入后运行 harness 设置",
  "setupNeedsTeam": "请选择所属团队以启用 harness 设置",
  "import": "导入 {count} 个并设置",
  "importNoSetup": "导入 {count} 个",
  "importing": "导入中…",
  "importedSummary": "已导入 {count} 个项目",
  "skippedSummary": "{count} 个已跳过",
  "rootRequired": "请输入要扫描的文件夹",
  "scanError": "扫描失败",
  "importError": "导入失败",
  "close": "关闭"
}
```

- [ ] **Step 2: Verify JSON validity + key parity**

Run:
```bash
cd frontend && node -e "
const fs=require('fs');
const ls=['en','ko','ja','zh'].map(l=>Object.keys(JSON.parse(fs.readFileSync('src/locales/'+l+'.json')).projectsDiscovery).sort());
const base=JSON.stringify(ls[0]);
console.log(ls.every(k=>JSON.stringify(k)===base) ? 'PARITY OK ('+ls[0].length+' keys)' : 'KEY MISMATCH');
"
```
Expected: `PARITY OK (30 keys)`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/locales/en.json frontend/src/locales/ko.json frontend/src/locales/ja.json frontend/src/locales/zh.json
git commit -m "feat(discovery): projectsDiscovery i18n (en/ko/ja/zh)"
```

---

## Task 7: `ProjectDiscoveryModal.vue`

**Files:**
- Create: `frontend/src/components/projects/ProjectDiscoveryModal.vue`
- Test: `frontend/src/components/projects/__tests__/ProjectDiscoveryModal.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/projects/__tests__/ProjectDiscoveryModal.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import ProjectDiscoveryModal from '../ProjectDiscoveryModal.vue';
import { projectApi } from '../../../services/api';

vi.mock('../../../services/api', () => ({
  projectApi: { discover: vi.fn(), importRepos: vi.fn() },
  ApiError: class extends Error {
    status: number;
    constructor(status: number, message: string) { super(message); this.status = status; }
  },
}));

describe('ProjectDiscoveryModal', () => {
  const teams = [{ id: 'team-1', name: 'Backend', color: '#fff', member_count: 0 }] as any;
  const products = [{ id: 'prod-1', name: 'Core', status: 'active', project_count: 0 }] as any;

  function mountComponent() {
    return mount(ProjectDiscoveryModal, {
      props: { teams, products },
      global: { provide: { showToast: vi.fn() }, stubs: { teleport: true } },
    });
  }

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(projectApi.discover).mockResolvedValue({
      repos: [
        { name: 'alpha', local_path: '/p/alpha', remote_url: 'git@github.com:o/alpha.git', already_imported: false, existing_project_id: null },
        { name: 'beta', local_path: '/p/beta', remote_url: null, already_imported: true, existing_project_id: 'proj-x' },
      ],
      scanned: 2, found: 2, new_count: 1, unreadable: 0,
    });
    vi.mocked(projectApi.importRepos).mockResolvedValue({
      imported: [{ project_id: 'proj-new', name: 'alpha' }], skipped: [], setup_started: false,
    });
  });

  it('scans and lists repos with new/imported state', async () => {
    const wrapper = mountComponent();
    await wrapper.find('input[data-testid="discover-root"]').setValue('/p');
    await wrapper.find('[data-testid="discover-scan"]').trigger('click');
    await flushPromises();
    expect(projectApi.discover).toHaveBeenCalledWith({ root: '/p', nested: false, max_depth: 3 });
    expect(wrapper.text()).toContain('alpha');
    expect(wrapper.text()).toContain('beta');
    // Only the 1 new repo is pre-selected.
    const checked = wrapper.findAll('input[type="checkbox"]:checked');
    expect(checked.length).toBe(1);
  });

  it('imports the selected new repos with team + setup flag', async () => {
    const wrapper = mountComponent();
    await wrapper.find('input[data-testid="discover-root"]').setValue('/p');
    await wrapper.find('[data-testid="discover-scan"]').trigger('click');
    await flushPromises();

    await wrapper.find('[data-testid="discover-team"]').setValue('team-1');
    await wrapper.find('[data-testid="discover-import"]').trigger('click');
    await flushPromises();

    expect(projectApi.importRepos).toHaveBeenCalledWith({
      repos: [{ name: 'alpha', local_path: '/p/alpha', github_repo: 'git@github.com:o/alpha.git' }],
      product_id: undefined,
      owner_team_id: 'team-1',
      run_harness_setup: true,
    });
    expect(wrapper.emitted('imported')).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/projects/__tests__/ProjectDiscoveryModal.test.ts`
Expected: FAIL — cannot resolve `../ProjectDiscoveryModal.vue`.

- [ ] **Step 3: Write the component**

Create `frontend/src/components/projects/ProjectDiscoveryModal.vue`:

```vue
<script setup lang="ts">
import { ref, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { projectApi, ApiError } from '../../services/api';
import type { Team, Product, DiscoveredRepo } from '../../services/api';
import { useToast } from '../../composables/useToast';

const props = defineProps<{ teams: Team[]; products: Product[] }>();
const emit = defineEmits<{ close: []; imported: [] }>();

const { t } = useI18n();
const showToast = useToast();

const root = ref('');
const nested = ref(false);
const maxDepth = ref(3);
const repos = ref<DiscoveredRepo[]>([]);
const selected = ref<Set<string>>(new Set());
const productId = ref('');
const teamId = ref('');
const runSetup = ref(true);
const scanning = ref(false);
const importing = ref(false);
const scanned = ref(false);
const newCount = ref(0);

const canSetup = computed(() => teamId.value !== '');
const selectedRepos = computed(() => repos.value.filter((r) => selected.value.has(r.local_path)));
const importLabel = computed(() =>
  runSetup.value && canSetup.value
    ? t('projectsDiscovery.import', { count: selectedRepos.value.length })
    : t('projectsDiscovery.importNoSetup', { count: selectedRepos.value.length }),
);

async function scan() {
  if (!root.value.trim()) {
    showToast(t('projectsDiscovery.rootRequired'), 'error');
    return;
  }
  scanning.value = true;
  try {
    const res = await projectApi.discover({
      root: root.value.trim(),
      nested: nested.value,
      max_depth: maxDepth.value,
    });
    repos.value = res.repos;
    newCount.value = res.new_count;
    selected.value = new Set(res.repos.filter((r) => !r.already_imported).map((r) => r.local_path));
    scanned.value = true;
  } catch (e) {
    showToast(e instanceof ApiError ? e.message : t('projectsDiscovery.scanError'), 'error');
  } finally {
    scanning.value = false;
  }
}

function toggle(repo: DiscoveredRepo) {
  if (repo.already_imported) return;
  const next = new Set(selected.value);
  if (next.has(repo.local_path)) next.delete(repo.local_path);
  else next.add(repo.local_path);
  selected.value = next;
}

function selectAllNew() {
  selected.value = new Set(repos.value.filter((r) => !r.already_imported).map((r) => r.local_path));
}

async function runImport() {
  if (selectedRepos.value.length === 0) return;
  importing.value = true;
  try {
    const res = await projectApi.importRepos({
      repos: selectedRepos.value.map((r) => ({
        name: r.name,
        local_path: r.local_path,
        github_repo: r.remote_url ?? undefined,
      })),
      product_id: productId.value || undefined,
      owner_team_id: teamId.value || undefined,
      run_harness_setup: runSetup.value && canSetup.value,
    });
    showToast(
      t('projectsDiscovery.importedSummary', { count: res.imported.length }),
      'success',
    );
    emit('imported');
  } catch (e) {
    showToast(e instanceof ApiError ? e.message : t('projectsDiscovery.importError'), 'error');
  } finally {
    importing.value = false;
  }
}
</script>

<template>
  <Teleport to="body">
    <div
      class="modal-overlay"
      role="dialog"
      aria-modal="true"
      tabindex="-1"
      @click.self="emit('close')"
      @keydown.escape="emit('close')"
    >
      <div class="modal">
        <div class="modal-header">
          <h2>{{ t('projectsDiscovery.title') }}</h2>
          <button class="modal-close" @click="emit('close')">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>{{ t('projectsDiscovery.folderLabel') }}</label>
            <div class="scan-row">
              <input
                v-model="root"
                data-testid="discover-root"
                type="text"
                :placeholder="t('projectsDiscovery.folderPlaceholder')"
                @keydown.enter="scan"
              />
              <button class="btn btn-primary" data-testid="discover-scan" :disabled="scanning" @click="scan">
                {{ scanning ? t('projectsDiscovery.scanning') : t('projectsDiscovery.scan') }}
              </button>
            </div>
            <label class="inline">
              <input type="checkbox" :checked="!nested" @change="nested = false" />
              {{ t('projectsDiscovery.directOnly') }}
            </label>
            <label class="inline">
              <input type="checkbox" v-model="nested" />
              {{ t('projectsDiscovery.scanNested') }}
            </label>
            <label v-if="nested" class="inline">
              {{ t('projectsDiscovery.maxDepth') }}
              <input v-model.number="maxDepth" type="number" min="1" max="8" style="width: 4rem" />
            </label>
          </div>

          <div v-if="scanned" class="results">
            <div class="results-head">
              <span>{{ t('projectsDiscovery.foundSummary', { found: repos.length, count: newCount }) }}</span>
              <button class="link" @click="selectAllNew">{{ t('projectsDiscovery.selectAllNew') }}</button>
            </div>
            <p v-if="repos.length === 0" class="muted">{{ t('projectsDiscovery.noneFound') }}</p>
            <ul v-else class="repo-list">
              <li v-for="repo in repos" :key="repo.local_path" class="repo-row">
                <label>
                  <input
                    type="checkbox"
                    :checked="selected.has(repo.local_path)"
                    :disabled="repo.already_imported"
                    @change="toggle(repo)"
                  />
                  <span class="repo-name">{{ repo.name }}</span>
                  <span v-if="repo.already_imported" class="badge badge-muted">{{ t('projectsDiscovery.importedBadge') }}</span>
                  <span v-else class="badge badge-new">{{ t('projectsDiscovery.newBadge') }}</span>
                  <span class="repo-remote">{{ repo.remote_url || t('projectsDiscovery.localOnly') }}</span>
                </label>
              </li>
            </ul>

            <div class="form-group">
              <label>{{ t('projectsDiscovery.productLabel') }}</label>
              <select v-model="productId" data-testid="discover-product">
                <option value="">{{ t('projectsDiscovery.noProduct') }}</option>
                <option v-for="p in props.products" :key="p.id" :value="p.id">{{ p.name }}</option>
              </select>
            </div>
            <div class="form-group">
              <label>{{ t('projectsDiscovery.teamLabel') }}</label>
              <select v-model="teamId" data-testid="discover-team">
                <option value="">{{ t('projectsDiscovery.noTeam') }}</option>
                <option v-for="tm in props.teams" :key="tm.id" :value="tm.id">{{ tm.name }}</option>
              </select>
            </div>
            <label class="inline">
              <input type="checkbox" v-model="runSetup" :disabled="!canSetup" />
              {{ t('projectsDiscovery.runSetup') }}
            </label>
            <p v-if="!canSetup" class="muted">{{ t('projectsDiscovery.setupNeedsTeam') }}</p>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="emit('close')">{{ t('projectsDiscovery.close') }}</button>
          <button
            v-if="scanned"
            class="btn btn-primary"
            data-testid="discover-import"
            :disabled="importing || selectedRepos.length === 0"
            @click="runImport"
          >
            {{ importing ? t('projectsDiscovery.importing') : importLabel }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.scan-row { display: flex; gap: 0.5rem; }
.scan-row input { flex: 1; }
.inline { display: inline-flex; align-items: center; gap: 0.4rem; margin-right: 1rem; font-size: 0.85rem; }
.results-head { display: flex; justify-content: space-between; align-items: center; margin: 0.75rem 0 0.25rem; }
.repo-list { list-style: none; padding: 0; margin: 0 0 1rem; max-height: 260px; overflow-y: auto; }
.repo-row { padding: 0.25rem 0; }
.repo-row label { display: flex; align-items: center; gap: 0.5rem; }
.repo-name { font-weight: 600; }
.repo-remote { color: var(--text-tertiary, #888); font-size: 0.8rem; margin-left: auto; }
.badge { font-size: 0.65rem; padding: 1px 6px; border-radius: 4px; }
.badge-new { background: rgba(34,197,94,0.15); color: #22c55e; }
.badge-muted { background: var(--bg-tertiary, rgba(255,255,255,0.06)); color: var(--text-tertiary, #888); }
.link { background: none; border: none; color: var(--accent-cyan, #60a5fa); cursor: pointer; font-size: 0.8rem; }
.muted { color: var(--text-tertiary, #888); font-size: 0.8rem; }
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/projects/__tests__/ProjectDiscoveryModal.test.ts`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/projects/ProjectDiscoveryModal.vue frontend/src/components/projects/__tests__/ProjectDiscoveryModal.test.ts
git commit -m "feat(discovery): ProjectDiscoveryModal wizard"
```

---

## Task 8: Wire into `ProjectsPage.vue`

**Files:**
- Modify: `frontend/src/views/ProjectsPage.vue`
- Test: `frontend/src/views/__tests__/ProjectsPage.test.ts`

- [ ] **Step 1: Write the failing test**

Append to `frontend/src/views/__tests__/ProjectsPage.test.ts` inside the `describe('ProjectsPage', ...)` block:

```typescript
  it('opens the discovery modal from the Discover button', async () => {
    const wrapper = mountComponent();
    await flushPromises();
    const btn = wrapper.find('[data-testid="discover-repos-btn"]');
    expect(btn.exists()).toBe(true);
    await btn.trigger('click');
    // The modal Teleports to body; with stubs:{teleport:true} its content
    // renders inline, so its root-folder input becomes findable.
    expect(wrapper.find('[data-testid="discover-root"]').exists()).toBe(true);
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/views/__tests__/ProjectsPage.test.ts -t "discovery modal"`
Expected: FAIL — button `[data-testid="discover-repos-btn"]` not found.

- [ ] **Step 3: Wire the button + modal**

In `frontend/src/views/ProjectsPage.vue`:

(a) Add the import after the other component imports (near line 11):
```typescript
import ProjectDiscoveryModal from '../components/projects/ProjectDiscoveryModal.vue';
```

(b) Add a state ref next to `showCreateModal` (near line 28):
```typescript
const showDiscoverModal = ref(false);
```

(c) Add the Discover button inside the `<template #actions>` of `PageHeader`, before the existing Create button:
```html
      <button class="btn btn-secondary" data-testid="discover-repos-btn" @click="showDiscoverModal = true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="7" /><path d="M21 21l-4.35-4.35" />
        </svg>
        {{ t('projectsDiscovery.button') }}
      </button>
```

(d) Mount the modal next to the Create modal block (e.g. right after the create-modal `</Teleport>` near line 350):
```html
  <ProjectDiscoveryModal
    v-if="showDiscoverModal"
    :teams="teams"
    :products="products"
    @close="showDiscoverModal = false"
    @imported="onReposImported"
  />
```

(e) Add the handler near `createProject` (the modal owns its own Teleport, so just close + refresh):
```typescript
async function onReposImported() {
  showDiscoverModal.value = false;
  await loadProjects();
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/views/__tests__/ProjectsPage.test.ts`
Expected: PASS (existing tests + the new one).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/ProjectsPage.vue frontend/src/views/__tests__/ProjectsPage.test.ts
git commit -m "feat(discovery): Discover button + modal on ProjectsPage"
```

---

## Task 9: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Backend — targeted suite**

Run:
```bash
cd backend && uv run pytest -q \
  tests/test_project_discovery_service.py \
  tests/test_litestar_projects.py
```
Expected: all PASS.

- [ ] **Step 2: Frontend — type-check + build**

Run: `just build`
Expected: `✓ built` (vue-tsc clean, vite build succeeds).

- [ ] **Step 3: Frontend — full test suite**

Run: `cd frontend && npm run test:run`
Expected: the new modal + ProjectsPage tests PASS; no NEW failures beyond the documented 7-failure baseline (RateLimitGauge, MarkdownContent, WorkingMemoryView, useTourMachine).

- [ ] **Step 4: Manual smoke (optional)**

Start the app (`just deploy` or dev servers), open `/projects`, click **Discover repos**, enter a folder containing git repos, Scan, pick a Team, **Import & set up**, and confirm new project cards appear and each shows harness-setup progress via `GET /api/projects/{id}/harness-setup/status`.

---

## Notes for the implementer

- **Imported `github_repo`** is stored as the normalized short remote (`github.com/owner/repo`); local-only repos store `null`. Import calls `db_create_project` directly (no clone/network validation) because the repos are already on disk.
- **Harness-setup** needs `owner_team_id` (its `team_topology` step requires it) — that's why the setup toggle is gated on a Team selection.
- **Bounds**: scan is capped at depth 8 and 500 repos; unreadable dirs are skipped + counted. Keep these caps.
- **Conscious deviation from spec UX step 4 (deferred to a follow-up):** the modal imports → shows an imported/skipped toast → emits `imported` → closes, and `ProjectsPage` refreshes the list. It does **not** render live per-project harness-setup progress *inside the modal*; each imported project's setup runs in the background and its status is visible on the project's own page via `GET /api/projects/{id}/harness-setup/status`. In-modal progress polling is a clean follow-up (the `imported[].project_id` list + that endpoint are already available).
- **Out of scope (v1)**: cloning remote repos, a named-template catalog/bundle picker, async/streaming scan.
