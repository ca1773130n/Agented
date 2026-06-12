"""Session-completion auto-import of session-scaffolded forge primitives.

Fourth handler on the ``execution_events`` session-completion bus (alongside the
failure annotator, takeaway extractor, and tesserae exporter). When an
Agented-driven session finishes, it may have scaffolded `.claude/` primitives
(via the forge-creator skills). This handler diffs the project's `.claude/` tree
against the forge manifest, imports each NEW/CHANGED session-scaffolded primitive
via the 17-05 atomic ``create_and_bind_and_materialize`` API, and records origin
provenance (sha256 content-hash + source session id) in ``forge_origin``.

SECURITY HOUSE RULE (Phase 17 mitigation): auto-imported `.claude/` content is a
system-prompt-injection vector across four harnesses. The ``session_kind`` gate
IS the mitigation and FAILS CLOSED:

    AGENTED_DRIVEN_SESSION_KINDS = {project_session, super_agent,
                                    team_session, goal_loop}

Only sessions whose ``session_kind`` is in that set auto-bind their scaffolded
primitives. ANY other / unknown kind (notably external clone-imports, which is
how foreign-repo `.claude/` content arrives) imports NOTHING. The gate is the
FIRST thing the handler checks, before touching the filesystem.

Provenance/idempotence: the source file bytes are sha256'd. If ``forge_origin``
already holds that exact hash, the file is skipped (no duplicate import). A
changed file (new hash) is re-imported and its origin row refreshed.

Scope (Phase 17): only ``.claude/agents/<name>.md`` (subagents) are imported —
that is the kind the atomic create API supports end-to-end (create + bind +
materialize) and the kind the forge-creator subagent-creator skill scaffolds for
agent delegates. Rule/command/hook session-import is deferred to a later phase;
the diff helper is kind-agnostic so it extends cleanly.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Optional

from app.db.forge_origin import get_origin, record_origin
from app.services.forge_create_service import create_and_bind_and_materialize
from app.services.forge_materialization_service import _load_manifest
from app.services.project_workspace_service import ProjectWorkspaceService

logger = logging.getLogger(__name__)

# RESEARCH.md Open Q1 — the exact Agented-driven session_kind set. Every other
# value (including external clone-import and any unknown kind) is treated as
# FOREIGN and imports nothing (fail-closed).
AGENTED_DRIVEN_SESSION_KINDS = frozenset(
    {"project_session", "super_agent", "team_session", "goal_loop"}
)

# Per-kind import config: where the kind's files live under .claude/ and the
# manifest bucket key. Phase 17 ships only subagents end-to-end.
_AGENTS_SUBDIR = ".claude/agents"

_FRONTMATTER_NAME_RE = re.compile(r"^name:\s*(.+?)\s*$", re.MULTILINE)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_subagent_name(path: Path, text: str) -> str:
    """Prefer a frontmatter ``name:`` if present; else the file stem."""
    head = text[:2000]
    m = _FRONTMATTER_NAME_RE.search(head)
    if m:
        name = m.group(1).strip().strip("'\"")
        if name:
            return name
    return path.stem


def _manifest_managed_rels(workspace: Path) -> set[str]:
    """Repo-relative paths that the forge manifest already tracks (i.e.
    materialized BY Agented, not scaffolded fresh this session). These are NOT
    import candidates."""
    manifest = _load_manifest(workspace)
    managed: set[str] = set()
    for rels in manifest.values():
        if isinstance(rels, list):
            managed.update(rels)
    return managed


def on_session_complete_import(
    session_kind: str,
    session_id: str,
    project_id: Optional[str],
    status: str,
    output: Optional[str] = None,
) -> None:
    """Auto-import session-scaffolded forge primitives. Registered on the
    execution_events session bus. Wrapped by the bus in its own swallow-and-log,
    and additionally guarded here so a handler error never breaks session
    completion."""
    try:
        # --- GATE FIRST (fail-closed): only Agented-driven sessions ---------
        if session_kind not in AGENTED_DRIVEN_SESSION_KINDS:
            logger.debug(
                "forge import: session_kind %r not Agented-driven; skipping",
                session_kind,
            )
            return

        if not project_id:
            return

        # Resolve the project's working directory (raises if unresolvable).
        try:
            workdir = ProjectWorkspaceService.resolve_working_directory(project_id)
        except ValueError:
            logger.debug("forge import: workspace unresolvable for %s; skipping", project_id)
            return

        workspace = Path(workdir)
        agents_dir = workspace / _AGENTS_SUBDIR
        if not agents_dir.is_dir():
            return

        manifest_managed = _manifest_managed_rels(workspace)

        imported = 0
        for md in sorted(agents_dir.glob("*.md")):
            rel = str(md.relative_to(workspace))
            # Skip Agented-materialized files (already tracked in the manifest);
            # those are forge-owned, not session-scaffolded imports.
            if rel in manifest_managed:
                continue
            try:
                raw = md.read_bytes()
            except OSError:
                continue
            content_hash = _sha256(raw)
            text = raw.decode("utf-8", errors="replace")
            name = _parse_subagent_name(md, text)

            # Idempotence: if this (asset, kind) already recorded with the same
            # hash, the file is unchanged — skip.
            prior = get_origin(name, "subagent")
            if prior and prior.get("origin_hash") == content_hash:
                continue

            try:
                create_and_bind_and_materialize(
                    project_id=project_id,
                    kind="subagent",
                    payload={
                        "name": name,
                        "content": text,
                        "description": f"Imported from session {session_id}",
                        "project_id": project_id,
                        "source_path": rel,
                    },
                    bind=True,
                    materialize=True,
                )
            except Exception:
                logger.warning(
                    "forge import: create+bind failed for %s; skipping", rel, exc_info=True
                )
                continue

            # Provenance is keyed on the subagent NAME — stable across
            # re-imports (the db id changes each create, the name does not), so
            # the get_origin idempotence check above and this record agree.
            record_origin(
                asset_id=name,
                kind="subagent",
                origin_hash=content_hash,
                source_session_id=session_id,
            )
            imported += 1

        if imported:
            logger.info(
                "forge import: imported %d subagent(s) from session %s (%s)",
                imported,
                session_id,
                session_kind,
            )
    except Exception:
        # Never let an import error break session completion.
        logger.warning("forge_session_import handler raised", exc_info=True)
