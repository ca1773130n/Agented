"""Project DB-bound Forge primitives into a real .claude/ layout.

DB stays canonical; .claude is a deterministic projection. No git here —
commit_materialization() (a later task) is the separate commit step. See
docs/superpowers/specs/2026-05-29-life-harness-phaseB-forge-design.md.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.db import project_forge_bindings as bindings_repo
from app.db.commands import get_command
from app.db.hooks import get_hook
from app.db.mcp_servers import get_mcp_server
from app.db.rules import get_rule

logger = logging.getLogger(__name__)


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
    if kind == "rule":
        return get_rule(int(asset_id))
    if kind == "hook":
        return get_hook(int(asset_id))
    if kind == "command":
        return get_command(int(asset_id))
    if kind == "mcp_server":
        return get_mcp_server(str(asset_id))
    return None


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


def materialize_primitives(
    project: dict,
    kinds: list[str],
    workspace_path: Path,
) -> MaterializationResult:
    """Write the project's bound primitives of the given kinds into
    workspace_path/.claude. Deterministic; creates no git commit."""
    result = MaterializationResult()
    project_id = project["id"]

    if "command" in kinds:
        for asset in _bound_assets(project_id, "command"):
            safe = _safe(asset.get("name") or str(asset.get("id")))
            rel = f".claude/commands/{safe}.md"
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
            rel = f".claude/agented-forge/rules/{safe}.md"
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

    return result
