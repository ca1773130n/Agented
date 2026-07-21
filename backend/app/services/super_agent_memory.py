"""Super-agent layered memory — map Agented super-agents onto Tesserae 0.21.0
per-agent knowledge graphs.

Tesserae 0.21.0 grows a layered KG *per agent* (``harness:account:role``):

- **L0** — the project graph mints one ``Agent`` node per observed agent plus
  ``performed_by`` edges (raw attribution, zero LLM).
- **L1** — ``tesserae distill`` writes one ``.tesserae/agents/<key>/distilled.graph.json``
  per agent: its own distilled runbook, bounded to a single read.
- **L2'** — distilling an agent that has *reports* rolls up the reports' L1s, so a
  manager sees only the distilled layer of its team.

This module maps each Agented **super-agent** to a Tesserae agent identity, wires
the super-agent hierarchy (``parent_super_agent_id``) into Tesserae's manager org,
runs the distill pass, and reads a super-agent's own distilled memory back for
injection into its harness context.

Attribution is by a registry ``{"label": <super_agent_id>}`` rule, because
Agented's session export (``tesserae_integration._normalize_super_agent_session``)
already stamps every super-agent session with ``agent_label = super_agent_id``.
That export also uses ``harness="claude"`` and no config-root, so Tesserae composes
the account slug as ``"unknown"`` — hence the deterministic key below. Verified
end-to-end against tesserae 0.21.0 (``agents list --json`` + ``distill --all``). If
the export ever sets ``harness=backend_type`` or a real config-root, update
``agent_key`` to match, or attribution silently collapses to one ``default`` agent.
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

from app.db.connection import get_connection

from .tesserae_integration import (
    _TESSERAE_CMD,
    get_distill_enabled,
    get_tesserae_root,
    logger,
)

# L1 node types worth surfacing to an agent's own context.
_MEMORY_NODE_TYPES = ("DistilledNote", "ExpertiseProfile")
# A distilled L1 artifact is designed for a single ~48k read; refuse anything
# wildly larger before loading it (defends the harness prompt budget + memory).
_MEMORY_ARTIFACT_MAX_BYTES = 512 * 1024
# Super-agent ids are server-generated ``super-<suffix>``; enforce that shape
# before the id becomes a filesystem path component (defense-in-depth against a
# malformed/poisoned persisted id escaping the agents dir with ``..``/``/``/NUL).
# ``fullmatch`` (not ``$``, which permits a trailing newline) anchors the whole id.
_SAFE_SA_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")


def agent_key(super_agent_id: str) -> str:
    """Tesserae agent identity for an Agented super-agent. See module docstring
    for why the harness/account components are pinned to ``claude:unknown``.

    Rejects an id that isn't a plain ``[A-Za-z0-9_-]`` token — the key becomes a
    path component, so a ``/``/``..``/NUL id must never reach the filesystem."""
    if not _SAFE_SA_ID.fullmatch(super_agent_id or ""):
        raise ValueError(f"unsafe super_agent_id: {super_agent_id!r}")
    return f"claude:unknown:{super_agent_id}"


def _project_super_agents(conn, project_id: str) -> list[dict]:
    """Super-agents that ran at least one session in this project, with name +
    parent. Scoped to the project because the registry is per-project."""
    rows = conn.execute(
        """SELECT DISTINCT sa.id AS id, sa.name AS name,
                  sa.parent_super_agent_id AS parent_super_agent_id
           FROM super_agent_sessions sas
           JOIN super_agents sa ON sa.id = sas.super_agent_id
           WHERE sas.project_id = ?""",
        (project_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def sync_agent_registry(project_id: str) -> Optional[Path]:
    """Write ``.tesserae/agents/registry.json`` mapping each of the project's
    super-agents to a Tesserae agent identity + org parent. Returns the path, or
    ``None`` when tesserae is disabled or no super-agent has run here."""
    root = get_tesserae_root(project_id)
    if root is None:
        return None
    with get_connection() as conn:
        sas = _project_super_agents(conn, project_id)
    if not sas:
        return None
    present = {s["id"] for s in sas}
    parent_of = {s["id"]: s.get("parent_super_agent_id") for s in sas}

    def _acyclic_parent(sa_id: str) -> Optional[str]:
        """The super-agent's parent id, but only if it's present in this project
        and the chain doesn't loop back — ``parent_super_agent_id`` has just an
        existence FK, so A→B→A cycles are possible and would make Tesserae reject
        the whole registry. Nodes in a cycle report to org:root instead."""
        seen: set[str] = set()
        cur = parent_of.get(sa_id)
        while cur is not None and cur in present:
            if cur == sa_id or cur in seen:
                return None  # cycle reachable from this edge → break it
            seen.add(cur)
            cur = parent_of.get(cur)
        direct = parent_of.get(sa_id)
        return direct if direct in present else None

    agents: dict[str, dict] = {}
    for s in sas:
        try:
            key = agent_key(s["id"])
        except ValueError:
            logger.warning("sync_agent_registry: skipping unsafe super_agent_id %r", s["id"])
            continue
        parent_id = _acyclic_parent(s["id"])
        # A registry parent MUST be a declared, acyclic agent (the loader fails
        # loud on unknown parents and cycles), else report to org:root.
        parent = agent_key(parent_id) if parent_id else "org:root"
        agents[key] = {
            "label": s.get("name") or s["id"],
            "parent": parent,
            "match": [{"label": s["id"]}],
        }
    reg_dir = root / ".tesserae" / "agents"
    reg_dir.mkdir(parents=True, exist_ok=True)
    reg_path = reg_dir / "registry.json"
    reg_path.write_text(json.dumps({"version": 1, "agents": agents}, indent=2))
    return reg_path


def distill_super_agents(project_id: str, *, timeout: int = 1800) -> dict[str, Any]:
    """Sync the registry, then run ``tesserae distill --all`` (agent-distill
    enabled via env) to rebuild every super-agent's L1 runbook + L2' manager
    rollups. Gated on the per-project distill toggle. Best-effort — every failure
    path returns a status dict, never raises."""
    root = get_tesserae_root(project_id)
    if root is None:
        return {"ok": False, "reason": "tesserae_disabled"}
    if not get_distill_enabled(project_id):
        return {"ok": False, "reason": "distill_disabled"}
    reg = sync_agent_registry(project_id)
    if reg is None:
        return {"ok": False, "reason": "no_super_agents"}
    # tesserae distill no-ops unless agent-distill is opted in (env or config).
    env = {**os.environ, "TESSERAE_AGENT_DISTILL": "1"}
    try:
        proc = subprocess.run(
            [_TESSERAE_CMD, "distill", "--all", "--project", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except FileNotFoundError:
        return {"ok": False, "reason": "cli_missing"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": f"timeout_after_{timeout}s"}
    ok = proc.returncode == 0
    if not ok:
        logger.warning(
            "tesserae distill --all failed for %s: %s", project_id, (proc.stderr or "")[:300]
        )
    return {"ok": ok, "registry": str(reg), "stdout_tail": (proc.stdout or "")[-500:]}


def read_agent_memory(
    project_id: str, super_agent_id: str, *, max_chars: int = 6000
) -> dict[str, Any]:
    """Load a super-agent's L1 distilled runbook and return a compact, bounded
    memory block for injection into its harness context. Empty (not an error)
    when the agent has no distilled artifact yet."""
    root = get_tesserae_root(project_id)
    if root is None:
        return {"key": None, "notes": [], "text": ""}
    try:
        key = agent_key(super_agent_id)
    except ValueError:
        logger.warning("read_agent_memory: unsafe super_agent_id %r", super_agent_id)
        return {"key": None, "notes": [], "text": ""}
    agents_root = (root / ".tesserae" / "agents").resolve()
    art = (agents_root / key / "distilled.graph.json").resolve()
    # Belt-and-suspenders: the resolved artifact path must stay under the agents
    # dir (the key was already token-validated, but never trust a path built from
    # a persisted id without a containment check).
    if os.path.commonpath([str(agents_root), str(art)]) != str(agents_root):
        logger.warning("read_agent_memory: path escapes agents dir for %r", super_agent_id)
        return {"key": key, "notes": [], "text": ""}
    try:
        if art.stat().st_size > _MEMORY_ARTIFACT_MAX_BYTES:
            logger.warning("read_agent_memory: artifact over size cap for %s", key)
            return {"key": key, "notes": [], "text": ""}
        data = json.loads(art.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"key": key, "notes": [], "text": ""}
    # Cap BOTH the notes list and the rendered text as we collect — a runaway
    # artifact must not blow the harness prompt budget or return every node.
    notes: list[dict[str, str]] = []
    lines: list[str] = []
    total = 0
    for n in data.get("nodes", []):
        if n.get("type") not in _MEMORY_NODE_TYPES:
            continue
        title = (n.get("name") or "").strip()
        body = (n.get("description") or "").strip()
        if not (title or body):
            continue
        chunk = f"**{title}**\n{body}".strip()
        if total + len(chunk) > max_chars:
            break
        notes.append({"title": title, "body": body})
        lines.append(chunk)
        total += len(chunk)
    return {"key": key, "notes": notes, "text": "\n\n".join(lines)}


def agent_org(project_id: str, *, timeout: int = 30) -> Optional[list[dict[str, Any]]]:
    """Return Tesserae's agent org for this project (``tesserae agents list
    --json``): one row per agent — ``{key, label, parent, sessions, registered}``.
    ``None`` when tesserae is disabled or the CLI fails."""
    root = get_tesserae_root(project_id)
    if root is None:
        return None
    try:
        proc = subprocess.run(
            [_TESSERAE_CMD, "agents", "list", "--project", str(root), "--json"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None
