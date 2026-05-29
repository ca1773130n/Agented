# Phase B — Make the Forge Real — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver on the "git-traceable, per-project" forge claim — when an evolution round applies, materialize the affected primitives (including skills) into the project's real `.claude/` layout and record one git commit per applied round; add `skill` to the writable kinds.

**Architecture:** DB stays canonical; `.claude/` is a deterministic projection; one project-repo commit records each applied round. A new `forge_materialization_service.py` owns the projection (`materialize_primitives`) + commit (`commit_materialization`) + a round-aware wrapper (`materialize_round`) — the exact contract Phase C's eval gate and rollback reuse. The file layout mirrors how the harness already consumes config (`context_compiler_service._render_command`, `claude_config_overlay` settings.json hooks schema, `harness_loader_service` importing from `.claude/hooks` + `.claude/commands`), so we project into real paths, not invented ones. Skill forging reuses the path-based `user_skills` model (`app/db/skills.py`) and the SKILL.md rendering pattern already in the takeaway extractor.

**Tech Stack:** Python 3.10, raw SQLite, `subprocess` for git, pytest with `isolated_db` + `tmp_path`, ruff line-length=100.

**Deviation from design doc (noted):** the design proposed `user_skills.content TEXT`; the real skill model is **path-based** (`user_skills.skill_path` → on-disk `SKILL.md`). We follow the existing model — no `content` column — and store the rendered body on disk. This is a refinement caught by reading source.

---

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `backend/app/services/forge_materialization_service.py` | **Create** | `MaterializationResult`, `materialize_primitives`, `materialize_round`, `commit_materialization`, frontmatter/safe-name helpers |
| `backend/app/services/harness_evolver.py` | **Modify** | Add `skill` to `WRITABLE_KINDS`; skill create/update/delete dispatch; call materialize+commit after `apply_patch` (line 1145); store result+sha |
| `backend/app/db/harness_evolution.py` | **Modify** | `mark_applied` accepts + persists `materialization_result_json`, `git_commit_sha` |
| `backend/app/db/schema/_harness_evolution.py` | **Modify** | Add the two columns to the fresh-DB schema |
| `backend/tests/test_forge_materialization.py` | **Create** | materialize_primitives per-kind + manifest + cleanup |
| `backend/tests/test_forge_git_commit.py` | **Create** | commit_materialization git behavior + no-git fallback |
| `backend/tests/test_forge_skill_dispatch.py` | **Create** | skill create/update/delete dispatch in evolver |
| `backend/tests/test_forge_round_wiring.py` | **Create** | materialize_round + run_evolution_round integration |

---

## Task 1: `MaterializationResult` + `materialize_primitives` (command + rule writers)

**Files:**
- Create: `backend/app/services/forge_materialization_service.py`
- Test: `backend/tests/test_forge_materialization.py` (create)

**Context:** `materialize_primitives(project, kinds, workspace_path)` reads the project's enabled bound primitives and writes them into `workspace_path/.claude`. Read bound primitives by **mirroring the existing read in `harness_evolver.gather_inputs` (harness_evolver.py:377-401)** — for each kind, list the project's enabled bindings then fetch each asset via that kind's repo getter. It must NOT create git commits (a separate helper does). Layout (from the design doc, matching real consumer code): `command → .claude/commands/<safe>.md`, `rule → .claude/agented-forge/rules/<safe>.md`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_forge_materialization.py
"""materialize_primitives projects bound primitives into .claude/."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.database import get_connection
from app.db import rules as rules_repo
from app.db import commands as commands_repo
from app.db import project_forge_bindings as bindings_repo
from app.services.forge_materialization_service import (
    MaterializationResult,
    materialize_primitives,
)


@pytest.fixture()
def _project_with_primitives(isolated_db):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, status) VALUES ('proj-1', 'P', 'active')"
        )
        conn.commit()
    rid = rules_repo.create_rule(
        name="no-force-push", rule_type="validation",
        description="Never force-push to main", project_id="proj-1",
    )
    cid = commands_repo.create_command(
        name="deploy", description="Deploy", content="run deploy.sh",
        project_id="proj-1",
    )
    bindings_repo.add_binding("proj-1", "rule", str(rid))
    bindings_repo.add_binding("proj-1", "command", str(cid))
    return {"id": "proj-1"}


def test_materialize_writes_command_and_rule(_project_with_primitives, tmp_path):
    project = _project_with_primitives
    result = materialize_primitives(project, ["rule", "command"], tmp_path)

    assert isinstance(result, MaterializationResult)
    cmd_file = tmp_path / ".claude" / "commands" / "deploy.md"
    rule_file = tmp_path / ".claude" / "agented-forge" / "rules" / "no-force-push.md"
    assert cmd_file.exists()
    assert "run deploy.sh" in cmd_file.read_text()
    assert rule_file.exists()
    # frontmatter carries provenance keys
    rule_text = rule_file.read_text()
    assert "agented-kind: rule" in rule_text
    assert "agented-source: forge" in rule_text
    # result records every written file (repo-relative)
    rels = {w.rel_path for w in result.written}
    assert ".claude/commands/deploy.md" in rels
    assert ".claude/agented-forge/rules/no-force-push.md" in rels


def test_materialize_is_deterministic(_project_with_primitives, tmp_path):
    project = _project_with_primitives
    r1 = materialize_primitives(project, ["command"], tmp_path)
    text1 = (tmp_path / ".claude" / "commands" / "deploy.md").read_text()
    r2 = materialize_primitives(project, ["command"], tmp_path)
    text2 = (tmp_path / ".claude" / "commands" / "deploy.md").read_text()
    assert text1 == text2
    assert {w.rel_path for w in r1.written} == {w.rel_path for w in r2.written}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_forge_materialization.py::test_materialize_writes_command_and_rule -v`
Expected: FAIL — `ModuleNotFoundError: forge_materialization_service`. (If `create_rule`/`create_command` kwargs differ from the real signatures in `app/db/rules.py`/`commands.py`, align the test seeds first — these are the same functions `harness_evolver._create_rule`/`_create_command` call at lines 955-986.)

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/forge_materialization_service.py
"""Project DB-bound Forge primitives into a real .claude/ layout.

DB stays canonical; .claude is a deterministic projection. No git here —
commit_materialization() is the separate step. See
docs/superpowers/specs/2026-05-29-life-harness-phaseB-forge-design.md.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.db import project_forge_bindings as bindings_repo

logger = __import__("logging").getLogger(__name__)


@dataclass
class WrittenFile:
    rel_path: str          # repo-relative, e.g. ".claude/commands/deploy.md"
    kind: str
    asset_id: str


@dataclass
class MaterializationResult:
    written: list[WrittenFile] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)   # rel_paths removed by cleanup

    def rel_paths(self) -> list[str]:
        return [w.rel_path for w in self.written]


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in (name or "unnamed"))


def _frontmatter(d: dict[str, Any]) -> str:
    lines = ["---"]
    for k, v in d.items():
        if v is None:
            continue
        lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines)


def _bound_assets(project_id: str, kind: str) -> list[dict]:
    """Enabled primitives of one kind bound to the project. Mirrors the
    bound-primitive read used by harness_evolver.gather_inputs (377-401)."""
    from app.services import harness_evolver as ev
    bindings = bindings_repo.list_bindings(project_id, enabled_only=True)
    asset_ids = [b["asset_id"] for b in bindings if b["kind"] == kind]
    out: list[dict] = []
    for aid in asset_ids:
        asset = ev._get_dispatch[kind](aid) if hasattr(ev, "_get_dispatch") else None
        if asset:
            out.append(asset)
    return out


def _write(workspace: Path, rel: str, content: str) -> None:
    target = workspace / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def materialize_primitives(
    project: dict, kinds: list[str], workspace_path: Path,
) -> MaterializationResult:
    """Write the project's bound primitives of the given kinds into
    workspace_path/.claude. Deterministic; creates no git commit."""
    result = MaterializationResult()
    project_id = project["id"]

    if "command" in kinds:
        for asset in _bound_assets(project_id, "command"):
            safe = _safe(asset.get("name") or str(asset.get("id")))
            rel = f".claude/commands/{safe}.md"
            fm = _frontmatter({
                "name": asset.get("name"),
                "description": asset.get("description"),
                "arguments": asset.get("arguments"),
                "agented-kind": "command",
                "agented-asset-id": asset.get("id"),
                "agented-source": "forge",
            })
            _write(workspace_path, rel, f"{fm}\n\n{asset.get('content') or ''}\n")
            result.written.append(WrittenFile(rel, "command", str(asset.get("id"))))

    if "rule" in kinds:
        for asset in _bound_assets(project_id, "rule"):
            safe = _safe(asset.get("name") or str(asset.get("id")))
            rel = f".claude/agented-forge/rules/{safe}.md"
            fm = _frontmatter({
                "name": asset.get("name"),
                "description": asset.get("description"),
                "rule_type": asset.get("rule_type"),
                "enabled": asset.get("enabled"),
                "condition": asset.get("condition"),
                "agented-kind": "rule",
                "agented-asset-id": asset.get("id"),
                "agented-source": "forge",
            })
            _write(workspace_path, rel, f"{fm}\n\n{asset.get('action') or ''}\n")
            result.written.append(WrittenFile(rel, "rule", str(asset.get("id"))))

    return result
```

Also add a `_get_dispatch` to `harness_evolver.py` next to `_create_dispatch` so `_bound_assets` can fetch by id (use the real per-kind getters — confirm names in `app/db/rules.py` etc.):

```python
from app.db.rules import get_rule
from app.db.hooks import get_hook
from app.db.commands import get_command
from app.db.mcp_servers import get_mcp_server  # or get-by-id equivalent

_get_dispatch = {
    "rule": get_rule,
    "hook": get_hook,
    "command": get_command,
    "mcp_server": get_mcp_server,
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_forge_materialization.py -v`
Expected: PASS. (If a `get_*` name is wrong, fix the import to the real getter in that repo — `grep -n "^def get" app/db/rules.py`.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/forge_materialization_service.py backend/app/services/harness_evolver.py backend/tests/test_forge_materialization.py
git commit -m "feat(forge): materialize_primitives — command + rule .claude/ projection"
```

---

## Task 2: Hook writer (`.sh` + settings.json registration)

**Files:**
- Modify: `backend/app/services/forge_materialization_service.py`
- Test: `backend/tests/test_forge_materialization.py`

**Context:** Mirror the live hooks schema (`claude_config_overlay.py:326-340`): `settings.json["hooks"][event] = [{"matcher": ".*", "hooks": [{"type": "command", "command": <rel-path>}]}]`. Use the **relative** path `.claude/hooks/<safe>.sh` so the repo is portable.

- [ ] **Step 1: Write the failing test**

```python
# Append to backend/tests/test_forge_materialization.py
import json as _json
from app.db import hooks as hooks_repo


def test_materialize_writes_hook_and_settings(_project_with_primitives, tmp_path):
    hid = hooks_repo.create_hook(
        name="guard", event="PreToolUse",
        description="block force push", content="#!/bin/sh\necho block",
        project_id="proj-1",
    )
    bindings_repo.add_binding("proj-1", "hook", str(hid))

    materialize_primitives({"id": "proj-1"}, ["hook"], tmp_path)

    sh = tmp_path / ".claude" / "hooks" / "guard.sh"
    settings = tmp_path / ".claude" / "settings.json"
    assert sh.exists()
    assert "echo block" in sh.read_text()
    data = _json.loads(settings.read_text())
    entry = data["hooks"]["PreToolUse"][0]
    assert entry["hooks"][0]["command"] == ".claude/hooks/guard.sh"
    assert entry["hooks"][0]["type"] == "command"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_forge_materialization.py::test_materialize_writes_hook_and_settings -v`
Expected: FAIL — no hook handling in `materialize_primitives`.

- [ ] **Step 3: Write minimal implementation**

Add a `"hook" in kinds` block inside `materialize_primitives`, before `return result`:

```python
    if "hook" in kinds:
        settings_path = workspace_path / ".claude" / "settings.json"
        settings: dict[str, Any] = {}
        if settings_path.exists():
            try:
                settings = json.loads(settings_path.read_text())
            except (OSError, json.JSONDecodeError):
                settings = {}
        hooks_block = settings.setdefault("hooks", {})
        for asset in _bound_assets(project_id, "hook"):
            safe = _safe(asset.get("name") or str(asset.get("id")))
            rel = f".claude/hooks/{safe}.sh"
            _write(workspace_path, rel, (asset.get("content") or "") + "\n")
            event = asset.get("event") or "PreToolUse"
            event_block = hooks_block.setdefault(event, [])
            if not isinstance(event_block, list):
                event_block = []
                hooks_block[event] = event_block
            event_block.append({
                "matcher": asset.get("matcher") or ".*",
                "hooks": [{"type": "command", "command": rel}],
            })
            result.written.append(WrittenFile(rel, "hook", str(asset.get("id"))))
        _write(
            workspace_path, ".claude/settings.json",
            json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
        )
        result.written.append(WrittenFile(".claude/settings.json", "hook", "settings"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_forge_materialization.py::test_materialize_writes_hook_and_settings -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/forge_materialization_service.py backend/tests/test_forge_materialization.py
git commit -m "feat(forge): hook materialization (.sh + settings.json registration)"
```

---

## Task 3: mcp_server writer (`.claude/mcp.json`)

**Files:**
- Modify: `backend/app/services/forge_materialization_service.py`
- Test: `backend/tests/test_forge_materialization.py`

**Context:** Compact entry like `context_compiler_service._render_mcp_server` — only `command/args/env/url/type`.

- [ ] **Step 1: Write the failing test**

```python
# Append to backend/tests/test_forge_materialization.py
from app.db import mcp_servers as mcp_repo


def test_materialize_writes_mcp_json(_project_with_primitives, tmp_path):
    mcp_repo.create_mcp_server(
        name="ctx", description="ctx", server_type="stdio",
        command="ctx-server", args=None, env_json=None, url=None,
    )
    # bind by the resolved id
    from app.services.harness_evolver import _find_mcp_server_id_by_name
    mid = _find_mcp_server_id_by_name("ctx")
    bindings_repo.add_binding("proj-1", "mcp_server", str(mid))

    materialize_primitives({"id": "proj-1"}, ["mcp_server"], tmp_path)

    mcp_file = tmp_path / ".claude" / "mcp.json"
    assert mcp_file.exists()
    data = _json.loads(mcp_file.read_text())
    assert "ctx" in data.get("mcpServers", {})
    assert data["mcpServers"]["ctx"]["command"] == "ctx-server"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_forge_materialization.py::test_materialize_writes_mcp_json -v`
Expected: FAIL — no mcp handling.

- [ ] **Step 3: Write minimal implementation**

Add an `"mcp_server" in kinds` block inside `materialize_primitives`, before `return result`:

```python
    if "mcp_server" in kinds:
        servers: dict[str, Any] = {}
        for asset in _bound_assets(project_id, "mcp_server"):
            name = asset.get("name") or str(asset.get("id"))
            entry: dict[str, Any] = {}
            for key in ("command", "args", "env", "url", "type"):
                val = asset.get(key) if key != "type" else asset.get("server_type")
                if val is not None:
                    entry[key] = val
            servers[name] = entry
        if servers:
            _write(
                workspace_path, ".claude/mcp.json",
                json.dumps({"mcpServers": servers}, indent=2, ensure_ascii=False) + "\n",
            )
            result.written.append(WrittenFile(".claude/mcp.json", "mcp_server", "mcp"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_forge_materialization.py::test_materialize_writes_mcp_json -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/forge_materialization_service.py backend/tests/test_forge_materialization.py
git commit -m "feat(forge): mcp_server materialization (.claude/mcp.json)"
```

---

## Task 4: Manifest + cleanup of stale generated files

**Files:**
- Modify: `backend/app/services/forge_materialization_service.py`
- Test: `backend/tests/test_forge_materialization.py`

**Context:** Write `.claude/agented-forge/manifest.json` listing every generated rel_path. On the next run, any path in the *previous* manifest that's NOT in the current written set is deleted (ownership boundary — never touch files outside the manifest).

- [ ] **Step 1: Write the failing test**

```python
# Append to backend/tests/test_forge_materialization.py
def test_cleanup_removes_stale_generated_file(_project_with_primitives, tmp_path):
    # First run binds command "deploy".
    materialize_primitives({"id": "proj-1"}, ["command"], tmp_path)
    assert (tmp_path / ".claude" / "commands" / "deploy.md").exists()

    # Unbind the command, re-run → its file must be cleaned up via the manifest.
    bindings = bindings_repo.list_bindings("proj-1")
    for b in bindings:
        if b["kind"] == "command":
            bindings_repo.remove_binding("proj-1", "command", b["asset_id"])
    result = materialize_primitives({"id": "proj-1"}, ["command"], tmp_path)

    assert not (tmp_path / ".claude" / "commands" / "deploy.md").exists()
    assert ".claude/commands/deploy.md" in result.deleted


def test_manifest_written(_project_with_primitives, tmp_path):
    materialize_primitives({"id": "proj-1"}, ["command"], tmp_path)
    manifest = tmp_path / ".claude" / "agented-forge" / "manifest.json"
    assert manifest.exists()
    data = _json.loads(manifest.read_text())
    assert ".claude/commands/deploy.md" in data["paths"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_forge_materialization.py::test_cleanup_removes_stale_generated_file tests/test_forge_materialization.py::test_manifest_written -v`
Expected: FAIL — no manifest/cleanup. (If `remove_binding`'s signature differs, check `app/db/project_forge_bindings.py` and adjust.)

- [ ] **Step 3: Write minimal implementation**

Add to `forge_materialization_service.py`, and call from the end of `materialize_primitives` (just before `return result`):

```python
_MANIFEST_REL = ".claude/agented-forge/manifest.json"


def _load_manifest(workspace: Path) -> list[str]:
    p = workspace / _MANIFEST_REL
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text()).get("paths", [])
    except (OSError, json.JSONDecodeError):
        return []


def _finalize_manifest(workspace: Path, result: MaterializationResult) -> None:
    current = set(result.rel_paths())
    previous = set(_load_manifest(workspace))
    for stale in previous - current:
        if stale == _MANIFEST_REL:
            continue
        target = workspace / stale
        try:
            if target.exists():
                target.unlink()
                result.deleted.append(stale)
        except OSError:
            logger.warning("forge cleanup: could not remove %s", stale)
    _write(
        workspace, _MANIFEST_REL,
        json.dumps({"paths": sorted(current)}, indent=2) + "\n",
    )
```

At the end of `materialize_primitives`, before `return result`:

```python
    _finalize_manifest(workspace_path, result)
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_forge_materialization.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/forge_materialization_service.py backend/tests/test_forge_materialization.py
git commit -m "feat(forge): manifest.json ownership boundary + stale-file cleanup"
```

---

## Task 5: Add `skill` to writable kinds + skill dispatch in the evolver

**Files:**
- Modify: `backend/app/services/harness_evolver.py` (`WRITABLE_KINDS`, `_create_dispatch`/`_update_dispatch`/`_delete_dispatch`)
- Test: `backend/tests/test_forge_skill_dispatch.py` (create)

**Context:** Skill create writes a `SKILL.md` to `.claude/skills/<safe>/SKILL.md` under the project and inserts a `user_skills` row (`add_user_skill(skill_name, skill_path, ...)`). Reuse the SKILL.md rendering pattern from the takeaway extractor (`_render_skill_md`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_forge_skill_dispatch.py
"""Skill create/update/delete dispatch in the evolver."""
from __future__ import annotations

import pytest

from app.database import get_connection
from app.db import skills as skills_repo
from app.services import harness_evolver as ev


@pytest.fixture()
def _proj(isolated_db, tmp_path):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, status, local_path) "
            "VALUES ('proj-1', 'P', 'active', ?)",
            (str(tmp_path),),
        )
        conn.commit()
    return str(tmp_path)


def test_skill_in_writable_kinds():
    assert "skill" in ev.WRITABLE_KINDS


def test_create_skill_writes_md_and_row(_proj):
    asset_id = ev._create_dispatch["skill"](
        name="commit-style",
        payload={"description": "Use conventional commits", "content": "Body here"},
        project_id="proj-1",
    )
    assert asset_id is not None
    row = skills_repo.get_user_skill_by_name("commit-style")
    assert row is not None
    skill_md = (
        __import__("pathlib").Path(_proj) / ".claude" / "skills"
        / "commit-style" / "SKILL.md"
    )
    assert skill_md.exists()
    assert "Body here" in skill_md.read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_forge_skill_dispatch.py -v`
Expected: FAIL — `skill` not in `WRITABLE_KINDS`; `_create_dispatch["skill"]` KeyError.

- [ ] **Step 3: Write minimal implementation**

In `harness_evolver.py`, change line 64:

```python
WRITABLE_KINDS = ("rule", "hook", "command", "mcp_server", "skill")
```

Add skill dispatch functions and register them in the three dispatch dicts:

```python
def _project_root(project_id: str) -> Optional[Path]:
    from app.db.projects import get_project
    proj = get_project(project_id)
    if not proj:
        return None
    root = proj.get("local_path") or proj.get("clone_path")
    return Path(root) if root else None


def _render_skill_md(name: str, payload: dict) -> str:
    description = (payload.get("description") or "")[:200]
    body = payload.get("content") or payload.get("body") or ""
    return f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n"


def _create_skill(*, name, payload, project_id):
    root = _project_root(project_id)
    if root is None:
        logger.warning("skill create: project %s has no local_path", project_id)
        return None
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in name)
    skill_dir = root / ".claude" / "skills" / safe
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(_render_skill_md(name, payload), encoding="utf-8")
    from app.db.skills import add_user_skill
    return add_user_skill(
        skill_name=name,
        skill_path=str(skill_dir / "SKILL.md"),
        description=payload.get("description"),
        enabled=1,
    )


def _update_skill(*, asset_id, payload):
    from app.db.skills import get_user_skill, update_user_skill
    row = get_user_skill(int(asset_id))
    if not row:
        return
    if payload.get("content") or payload.get("description"):
        path = row.get("skill_path")
        if path:
            Path(path).write_text(
                _render_skill_md(row["skill_name"], payload), encoding="utf-8",
            )
    update_user_skill(int(asset_id), description=payload.get("description"))


def _delete_skill(*, asset_id):
    from app.db.skills import get_user_skill, delete_user_skill
    row = get_user_skill(int(asset_id))
    if row and row.get("skill_path"):
        skill_dir = Path(row["skill_path"]).parent
        try:
            (Path(row["skill_path"])).unlink(missing_ok=True)
            if skill_dir.name != "skills":
                skill_dir.rmdir()
        except OSError:
            pass
    delete_user_skill(int(asset_id))
```

Register them (find the `_create_dispatch`/`_update_dispatch`/`_delete_dispatch` dict literals and add the `"skill"` entries):

```python
_create_dispatch["skill"] = _create_skill
_update_dispatch["skill"] = _update_skill
_delete_dispatch["skill"] = _delete_skill
```

Also update `validate_patch` so it no longer rejects `skill` as unsupported (remove/relax the skill-unsupported branch).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_forge_skill_dispatch.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/harness_evolver.py backend/tests/test_forge_skill_dispatch.py
git commit -m "feat(forge): skill forging — add skill to WRITABLE_KINDS + create/update/delete dispatch"
```

---

## Task 6: `commit_materialization` git helper + `materialize_round` wrapper

**Files:**
- Modify: `backend/app/services/forge_materialization_service.py`
- Test: `backend/tests/test_forge_git_commit.py` (create)

**Context:** `commit_materialization(project, result, round_id)` stages **only** the `result.written`/`result.deleted` rel_paths (never `git add .`), commits with a round-referencing message, returns the SHA — or `None` if the project has no git repo. `materialize_round(round_id, workspace_dir)` resolves project + applied kinds from the round and calls `materialize_primitives`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_forge_git_commit.py
"""commit_materialization git behavior + no-git fallback."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.services.forge_materialization_service import (
    MaterializationResult,
    WrittenFile,
    commit_materialization,
)


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
    ).stdout.strip()


def test_commit_stages_only_claude_paths(tmp_path):
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "t@t.io")
    _git(tmp_path, "config", "user.name", "t")
    # An operator-owned file that must NOT be swept into the forge commit.
    (tmp_path / "operator.txt").write_text("hand-edited")
    (tmp_path / ".claude" / "commands").mkdir(parents=True)
    (tmp_path / ".claude" / "commands" / "deploy.md").write_text("x")

    result = MaterializationResult(
        written=[WrittenFile(".claude/commands/deploy.md", "command", "c1")]
    )
    sha = commit_materialization({"id": "p", "local_path": str(tmp_path)},
                                 result, "her-round-1")

    assert sha
    # operator.txt remains unstaged/uncommitted
    status = _git(tmp_path, "status", "--porcelain")
    assert "operator.txt" in status
    # commit message references the round id
    msg = _git(tmp_path, "log", "-1", "--pretty=%B")
    assert "her-round-1" in msg


def test_commit_returns_none_without_git(tmp_path):
    (tmp_path / ".claude").mkdir()
    result = MaterializationResult(
        written=[WrittenFile(".claude/x.md", "command", "c1")]
    )
    sha = commit_materialization({"id": "p", "local_path": str(tmp_path)},
                                 result, "her-round-2")
    assert sha is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_forge_git_commit.py -v`
Expected: FAIL — `commit_materialization` not defined.

- [ ] **Step 3: Write minimal implementation**

Add to `forge_materialization_service.py`:

```python
import subprocess


def _is_git_repo(root: Path) -> bool:
    return (root / ".git").exists()


def commit_materialization(
    project: dict, result: MaterializationResult, round_id: str,
) -> Optional[str]:
    """Stage only the materialized paths and commit. Returns the commit SHA,
    or None if the project has no git repo or nothing changed."""
    root_str = project.get("local_path") or project.get("clone_path")
    if not root_str:
        return None
    root = Path(root_str)
    if not _is_git_repo(root):
        return None

    paths = sorted(set(result.rel_paths()) | set(result.deleted) | {_MANIFEST_REL})
    try:
        subprocess.run(["git", "add", "--", *paths], cwd=root, check=True,
                       capture_output=True, text=True)
        status = subprocess.run(["git", "status", "--porcelain", "--", *paths],
                                cwd=root, capture_output=True, text=True)
        if not status.stdout.strip():
            return None
        asset_ids = ", ".join(w.asset_id for w in result.written) or "none"
        msg = (
            f"chore(forge): apply evolution round {round_id}\n\n"
            f"Materialized {len(result.written)} primitive(s); "
            f"removed {len(result.deleted)}.\nassets: {asset_ids}\n"
            f"round: {round_id}"
        )
        subprocess.run(["git", "commit", "-m", msg], cwd=root, check=True,
                       capture_output=True, text=True)
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                              capture_output=True, text=True).stdout.strip()
    except subprocess.CalledProcessError as exc:
        logger.warning("forge commit failed for round %s: %s", round_id, exc)
        return None


def materialize_round(round_id: str, workspace_dir: Path) -> MaterializationResult:
    """Round-aware wrapper consumed by Phase C eval + rollback. Resolves the
    project + applied kinds from the round, then materializes."""
    from app.db.harness_evolution import get_round
    from app.db.projects import get_project
    rnd = get_round(round_id)
    if rnd is None:
        return MaterializationResult()
    project = get_project(rnd["project_id"])
    if project is None:
        return MaterializationResult()
    applied = rnd.get("applied_asset_ids") or []
    kinds = sorted({a["kind"] for a in applied}) or list(WRITABLE_KINDS_FOR_MATERIALIZE)
    return materialize_primitives(project, kinds, workspace_dir)


WRITABLE_KINDS_FOR_MATERIALIZE = ("rule", "hook", "command", "mcp_server", "skill")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_forge_git_commit.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/forge_materialization_service.py backend/tests/test_forge_git_commit.py
git commit -m "feat(forge): commit_materialization git helper + materialize_round wrapper"
```

---

## Task 7: Schema columns + wire materialize+commit into `run_evolution_round`

**Files:**
- Modify: `backend/app/db/schema/_harness_evolution.py` (add columns to fresh schema)
- Modify: `backend/app/db/harness_evolution.py` (`mark_applied` accepts + persists the two fields; add a migration `ALTER`)
- Modify: `backend/app/services/harness_evolver.py` (call materialize+commit after `apply_patch`, line 1145)
- Test: `backend/tests/test_forge_round_wiring.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_forge_round_wiring.py
"""run_evolution_round materializes + commits on apply and records metadata."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.database import get_connection
from app.db import harness_evolution as evo_repo


def test_mark_applied_persists_materialization_metadata(isolated_db):
    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name, status) VALUES ('p', 'P', 'active')")
        conn.commit()
    rid = evo_repo.start_round(
        project_id="p", input_window_since=None, input_window_until=None,
        input_execution_count=0, input_forge={}, scratch_dir="/tmp/x",
    )
    evo_repo.mark_applied(
        rid, output_patch={"entries": []}, applied_asset_ids=[], notes="",
        materialization_result_json='{"written": []}', git_commit_sha="abc123",
    )
    row = evo_repo.get_round(rid)
    assert row["git_commit_sha"] == "abc123"
    assert row["materialization_result_json"] == '{"written": []}'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_forge_round_wiring.py -v`
Expected: FAIL — `mark_applied` has no `materialization_result_json`/`git_commit_sha` params, and the columns don't exist.

- [ ] **Step 3: Write minimal implementation**

(a) In `backend/app/db/schema/_harness_evolution.py`, add to the `harness_evolution_rounds` CREATE TABLE column list:

```python
    materialization_result_json TEXT,
    git_commit_sha TEXT,
```

(b) In `backend/app/db/harness_evolution.py`, add an idempotent migration near the other `ALTER`s (or in the module's ensure/migrate path):

```python
def _ensure_materialization_columns(conn) -> None:
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(harness_evolution_rounds)")}
    if "materialization_result_json" not in cols:
        conn.execute("ALTER TABLE harness_evolution_rounds ADD COLUMN materialization_result_json TEXT")
    if "git_commit_sha" not in cols:
        conn.execute("ALTER TABLE harness_evolution_rounds ADD COLUMN git_commit_sha TEXT")
```

Call `_ensure_materialization_columns(conn)` wherever the module ensures its schema (mirror the existing pattern in this file). Extend `mark_applied` signature + UPDATE:

```python
def mark_applied(
    round_id: str,
    *,
    output_patch: dict,
    applied_asset_ids: list,
    notes: str = "",
    materialization_result_json: Optional[str] = None,
    git_commit_sha: Optional[str] = None,
) -> None:
    with get_connection() as conn:
        _ensure_materialization_columns(conn)
        conn.execute(
            """UPDATE harness_evolution_rounds
               SET status='applied', finished_at=CURRENT_TIMESTAMP,
                   output_patch_json=?, applied_asset_ids_json=?, notes=?,
                   materialization_result_json=?, git_commit_sha=?
               WHERE id=?""",
            (json.dumps(output_patch), json.dumps(applied_asset_ids), notes,
             materialization_result_json, git_commit_sha, round_id),
        )
        conn.commit()
```

(Adjust column names — `output_patch_json`/`applied_asset_ids_json` — to match the existing `mark_applied` body before editing; keep its current writes intact, only adding the two new SET columns.)

(c) In `harness_evolver.py` `run_evolution_round`, replace the apply block (lines 1145-1151) with:

```python
        applied = apply_patch(patch, project_id)

        # Materialize the applied primitives into the project's .claude/
        # layout and commit them (git-traceable per round). Best-effort:
        # a materialization/commit failure must not unwind the DB apply.
        import dataclasses
        from app.db.projects import get_project
        from app.services.forge_materialization_service import (
            materialize_primitives, commit_materialization,
        )
        mat_json: Optional[str] = None
        commit_sha: Optional[str] = None
        project = get_project(project_id)
        if project and (project.get("local_path") or project.get("clone_path")):
            try:
                root = Path(project.get("local_path") or project["clone_path"])
                kinds = sorted({a["kind"] for a in applied})
                result = materialize_primitives(project, kinds, root)
                commit_sha = commit_materialization(project, result, round_id)
                mat_json = json.dumps({
                    "written": [dataclasses.asdict(w) for w in result.written],
                    "deleted": result.deleted,
                })
            except Exception:
                logger.warning("forge materialize/commit failed for %s", round_id,
                               exc_info=True)

        evolution_repo.mark_applied(
            round_id,
            output_patch=_patch_to_dict(patch),
            applied_asset_ids=applied,
            notes=notes,
            materialization_result_json=mat_json,
            git_commit_sha=commit_sha,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_forge_round_wiring.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/schema/_harness_evolution.py backend/app/db/harness_evolution.py backend/app/services/harness_evolver.py backend/tests/test_forge_round_wiring.py
git commit -m "feat(forge): persist materialization result + git SHA; wire into run_evolution_round"
```

---

## Task 8: Full verification gate

**Files:** none — runs the three project gates.

- [ ] **Step 1: Backend suite**

Run: `cd backend && uv run pytest`
Expected: all pass. Pay attention to existing evolver tests — adding `skill` to `WRITABLE_KINDS` and relaxing `validate_patch`'s skill rejection may change a prior test's expectation; update those expectations as part of this step if they assert "skill unsupported".

- [ ] **Step 2: Ruff format**

Run: `cd backend && uv run ruff format --check .`
Expected: clean (else `uv run ruff format .` + commit).

- [ ] **Step 3: Frontend suite**

Run: `cd frontend && npm run test:run`
Expected: all pass.

- [ ] **Step 4: Build**

Run: `just build`
Expected: succeeds.

- [ ] **Step 5: Tag**

```bash
git tag life-harness-phaseB-complete
```
