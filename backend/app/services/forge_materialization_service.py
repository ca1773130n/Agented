"""Project DB-bound Forge primitives into a real .claude/ layout.

DB stays canonical; .claude is a deterministic projection. No git here —
commit_materialization() (a later task) is the separate commit step. See
docs/superpowers/specs/2026-05-29-life-harness-phaseB-forge-design.md.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.db import project_forge_bindings as bindings_repo
from app.db.commands import get_command
from app.db.hooks import get_hook
from app.db.mcp_servers import get_mcp_server
from app.db.rules import get_rule

logger = logging.getLogger(__name__)

_MANIFEST_REL = ".claude/agented-forge/manifest.json"
# Operator-shared, marker-managed files — NEVER manifest-deleted.
_NEVER_DELETE = {_MANIFEST_REL, ".claude/settings.json", ".claude/mcp.json"}


@dataclass
class WrittenFile:
    rel_path: str  # repo-relative, e.g. ".claude/commands/deploy.md"
    kind: str
    asset_id: str


@dataclass
class MaterializationResult:
    written: list[WrittenFile] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)

    def rel_paths(self) -> list[str]:
        return [w.rel_path for w in self.written]


# rule/hook/command getters take INT ids; mcp_server takes STR.
# Bindings store asset_id as str, so coerce per kind.
def _get_asset(kind: str, asset_id: str) -> Optional[dict]:
    try:
        if kind == "rule":
            return get_rule(int(asset_id))
        if kind == "hook":
            return get_hook(int(asset_id))
        if kind == "command":
            return get_command(int(asset_id))
        if kind == "mcp_server":
            return get_mcp_server(str(asset_id))
        if kind == "skill":
            from app.db.skills import get_user_skill

            return get_user_skill(int(asset_id))
    except (ValueError, TypeError):
        logger.warning("forge materialize: bad asset_id %r for kind %s; skipping", asset_id, kind)
        return None
    return None


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in (name or "unnamed"))


def _frontmatter(d: dict[str, Any]) -> str:
    lines = ["---"]
    for k, v in d.items():
        if v is None:
            continue
        lines.append(f"{k}: {json.dumps(str(v))}")
    lines.append("---")
    return "\n".join(lines)


def _unique_rel(used: set[str], base_rel: str, asset_id: Any) -> str:
    """Return base_rel, or a deterministic asset-id-suffixed variant if base_rel
    is already used this run."""
    if base_rel not in used:
        used.add(base_rel)
        return base_rel
    stem, _, ext = base_rel.rpartition(".")
    alt = f"{stem}-{asset_id}.{ext}" if stem else f"{base_rel}-{asset_id}"
    used.add(alt)
    return alt


def _bound_assets(project_id: str, kind: str) -> list[dict]:
    bindings = bindings_repo.list_bindings(project_id, enabled_only=True)
    out: list[dict] = []
    for b in bindings:
        if b.get("kind") != kind:
            continue
        asset = _get_asset(kind, b["asset_id"])
        if asset:
            out.append(asset)
    return out


def _write(workspace: Path, rel: str, content: str) -> None:
    target = workspace / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _load_manifest(workspace: Path) -> dict[str, list[str]]:
    p = workspace / _MANIFEST_REL
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    by_kind = data.get("paths_by_kind")
    return by_kind if isinstance(by_kind, dict) else {}


def _finalize_manifest(
    workspace: Path,
    result: MaterializationResult,
    kinds: list[str],
) -> None:
    """Reconcile ONLY the manifest buckets for the kinds materialized this run.
    Stale per-asset files (in a reconciled bucket but no longer written) are
    deleted, except operator-shared/marker-managed files. Buckets for kinds not
    in this run are preserved untouched (partial-kinds safety)."""
    manifest = _load_manifest(workspace)
    for kind in kinds:
        current = {w.rel_path for w in result.written if w.kind == kind}
        previous = set(manifest.get(kind, []))
        for stale in previous - current:
            if stale in _NEVER_DELETE:
                continue
            result.deleted.append(stale)  # record for git staging even if already gone
            target = workspace / stale
            try:
                if target.exists():
                    target.unlink()
                    # best-effort: drop the now-empty parent dir
                    parent = target.parent
                    try:
                        if parent != workspace and not any(parent.iterdir()):
                            parent.rmdir()
                    except OSError:
                        pass
            except OSError:
                logger.warning("forge cleanup: could not remove %s", stale)
        manifest[kind] = sorted(current)
    _write(
        workspace,
        _MANIFEST_REL,
        json.dumps({"paths_by_kind": manifest}, indent=2) + "\n",
    )


def materialize_primitives(
    project: dict,
    kinds: list[str],
    workspace_path: Path,
) -> MaterializationResult:
    """Write the project's bound primitives of the given kinds into
    workspace_path/.claude. Deterministic; creates no git commit."""
    result = MaterializationResult()
    project_id = project["id"]
    used_rels: set[str] = set()

    if "command" in kinds:
        for asset in _bound_assets(project_id, "command"):
            safe = _safe(asset.get("name") or str(asset.get("id")))
            base_rel = f".claude/commands/{safe}.md"
            rel = _unique_rel(used_rels, base_rel, asset.get("id"))
            fm = _frontmatter(
                {
                    "name": asset.get("name"),
                    "description": asset.get("description"),
                    "arguments": asset.get("arguments"),
                    "agented-kind": "command",
                    "agented-asset-id": asset.get("id"),
                    "agented-source": "forge",
                }
            )
            _write(workspace_path, rel, f"{fm}\n\n{asset.get('content') or ''}\n")
            result.written.append(WrittenFile(rel, "command", str(asset.get("id"))))

    if "rule" in kinds:
        for asset in _bound_assets(project_id, "rule"):
            safe = _safe(asset.get("name") or str(asset.get("id")))
            base_rel = f".claude/agented-forge/rules/{safe}.md"
            rel = _unique_rel(used_rels, base_rel, asset.get("id"))
            fm = _frontmatter(
                {
                    "name": asset.get("name"),
                    "description": asset.get("description"),
                    "rule_type": asset.get("rule_type"),
                    "enabled": asset.get("enabled"),
                    "condition": asset.get("condition"),
                    "agented-kind": "rule",
                    "agented-asset-id": asset.get("id"),
                    "agented-source": "forge",
                }
            )
            _write(workspace_path, rel, f"{fm}\n\n{asset.get('action') or ''}\n")
            result.written.append(WrittenFile(rel, "rule", str(asset.get("id"))))

    if "hook" in kinds:
        settings_path = workspace_path / ".claude" / "settings.json"
        settings: dict[str, Any] = {}
        if settings_path.exists():
            try:
                settings = json.loads(settings_path.read_text())
            except (OSError, json.JSONDecodeError):
                settings = {}
        hooks_block = settings.setdefault("hooks", {})

        # Idempotence: drop all previously Agented-managed entries (marked with
        # "_agented_asset_id") from every event list before re-adding the
        # current bound set. Operator-authored entries (no marker) are kept.
        had_prior_agented = False
        for event, entries in list(hooks_block.items()):
            if isinstance(entries, list):
                kept = [
                    e for e in entries if not (isinstance(e, dict) and e.get("_agented_asset_id"))
                ]
                if len(kept) != len(entries):
                    had_prior_agented = True
                if kept:
                    hooks_block[event] = kept
                else:
                    del hooks_block[event]

        hook_count = 0
        for asset in _bound_assets(project_id, "hook"):
            safe = _safe(asset.get("name") or str(asset.get("id")))
            rel = _unique_rel(used_rels, f".claude/hooks/{safe}.sh", asset.get("id"))
            _write(workspace_path, rel, (asset.get("content") or "") + "\n")
            # committed hook scripts must be executable
            (workspace_path / rel).chmod(0o755)
            event = asset.get("event") or "PreToolUse"
            event_block = hooks_block.setdefault(event, [])
            if not isinstance(event_block, list):
                event_block = []
                hooks_block[event] = event_block
            event_block.append(
                {
                    "matcher": asset.get("matcher") or ".*",
                    "hooks": [{"type": "command", "command": rel}],
                    "_agented_asset_id": str(asset.get("id")),
                }
            )
            result.written.append(WrittenFile(rel, "hook", str(asset.get("id"))))
            hook_count += 1

        # Only (re)write settings.json if we added entries or removed stale ones.
        if hook_count > 0 or had_prior_agented:
            _write(
                workspace_path,
                ".claude/settings.json",
                json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
            )
            result.written.append(WrittenFile(".claude/settings.json", "hook", "settings"))

    if "mcp_server" in kinds:
        mcp_path = workspace_path / ".claude" / "mcp.json"
        doc: dict[str, Any] = {}
        if mcp_path.exists():
            try:
                doc = json.loads(mcp_path.read_text())
            except (OSError, json.JSONDecodeError):
                doc = {}
        servers: dict[str, Any] = doc.get("mcpServers") or {}
        prior_agented = doc.get("_agented_mcp_servers") or []
        # Drop previously-Agented servers (so unbound ones disappear); keep operator ones.
        for name in prior_agented:
            servers.pop(name, None)

        current_agented: list[str] = []
        for asset in _bound_assets(project_id, "mcp_server"):
            name = asset.get("name") or str(asset.get("id"))
            entry: dict[str, Any] = {}
            args = asset.get("args")
            env = asset.get("env_json")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (ValueError, TypeError):
                    args = None
            if isinstance(env, str):
                try:
                    env = json.loads(env)
                except (ValueError, TypeError):
                    env = None
            if args is not None and not isinstance(args, list):
                args = None
            for key, val in (
                ("command", asset.get("command")),
                ("args", args),
                ("env", env),
                ("url", asset.get("url")),
                ("type", asset.get("server_type")),
            ):
                if val is not None:
                    entry[key] = val
            servers[name] = entry
            current_agented.append(name)

        if current_agented or prior_agented:
            doc["mcpServers"] = servers
            doc["_agented_mcp_servers"] = current_agented
            _write(
                workspace_path,
                ".claude/mcp.json",
                json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
            )
            result.written.append(WrittenFile(".claude/mcp.json", "mcp_server", "mcp"))

    if "skill" in kinds:
        for asset in _bound_assets(project_id, "skill"):
            safe = _safe(asset.get("skill_name") or str(asset.get("id")))
            rel = f".claude/skills/{safe}/SKILL.md"
            # Body lives on disk (written by the evolver's _create_skill); record
            # it for staging + manifest tracking. Don't rewrite from the DB.
            result.written.append(WrittenFile(rel, "skill", str(asset.get("id"))))

    _finalize_manifest(workspace_path, result, kinds)
    return result


# ---------------------------------------------------------------------------
# Git helper
# ---------------------------------------------------------------------------


def _is_git_repo(root: Path) -> bool:
    return (root / ".git").exists()


def commit_materialization(
    project: dict,
    result: MaterializationResult,
    round_id: str,
) -> Optional[str]:
    """Stage only the materialized paths and commit. Returns the commit SHA,
    or None if the project has no git repo, no local_path, or nothing changed."""
    root_str = project.get("local_path") or project.get("clone_path")
    if not root_str:
        return None
    root = Path(root_str)
    if not _is_git_repo(root):
        return None

    # Written + manifest are staged with git add (file must exist on disk).
    add_paths = sorted(
        p for p in (set(result.rel_paths()) | {_MANIFEST_REL}) if (root / p).exists()
    )
    # Deleted paths are staged with git rm --cached (file no longer on disk).
    rm_paths = sorted(set(result.deleted))
    all_paths = sorted(set(add_paths) | set(rm_paths))
    if not all_paths:
        return None
    try:
        if add_paths:
            subprocess.run(
                ["git", "add", "--", *add_paths],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
        if rm_paths:
            subprocess.run(
                ["git", "rm", "--cached", "--ignore-unmatch", "--", *rm_paths],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
        status = subprocess.run(
            ["git", "status", "--porcelain", "--", *all_paths],
            cwd=root,
            capture_output=True,
            text=True,
        )
        if not status.stdout.strip():
            return None
        asset_ids = ", ".join(w.asset_id for w in result.written) or "none"
        if len(asset_ids) > 200:
            asset_ids = asset_ids[:200] + "…"
        msg = (
            f"chore(forge): apply evolution round {round_id}\n\n"
            f"Materialized {len(result.written)} primitive(s); "
            f"removed {len(result.deleted)}.\nassets: {asset_ids}\nround: {round_id}"
        )
        subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        logger.warning("forge commit failed for round %s: %s", round_id, exc)
        return None


# ---------------------------------------------------------------------------
# Round-aware wrapper (consumed by Phase C eval + rollback)
# ---------------------------------------------------------------------------


def materialize_round(round_id: str, workspace_dir: Path) -> MaterializationResult:
    """Resolve the project + applied kinds from the round, then materialize."""
    from app.db.harness_evolution import get_round
    from app.db.projects import get_project

    rnd = get_round(round_id)
    if rnd is None:
        return MaterializationResult()
    project_id = rnd.get("project_id")
    if not project_id:
        return MaterializationResult()
    project = get_project(project_id)
    if project is None:
        return MaterializationResult()
    applied = rnd.get("applied_asset_ids") or []
    # applied_asset_ids is already parsed by _row_to_dict; guard for raw json strings defensively.
    if isinstance(applied, str):
        try:
            applied = json.loads(applied)
        except (ValueError, TypeError):
            applied = []
    kinds = sorted({a["kind"] for a in applied if isinstance(a, dict) and "kind" in a})
    if not kinds:
        kinds = ["rule", "hook", "command", "mcp_server", "skill"]
    return materialize_primitives(project, kinds, workspace_dir)
