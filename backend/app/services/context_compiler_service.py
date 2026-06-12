"""Compile a per-session ``ContextBundle`` from Forge bindings +
session overrides + per-prompt attachments.

The bundle is consumed by a backend-specific renderer
(``app.services.context_renderers``) which translates it into:

* ``--append-system-prompt <text>`` (claude) or a prompt-prepend
  block (codex/gemini/opencode)
* per-session overlay files + symlinks (claude config dir)
* ``mcp.json`` entries
* a universal "prompt prepend" string that all backends can
  splice into the next user message

Three inputs, in priority order (later wins):

1. **Project bindings** — sticky defaults from
   ``project_forge_bindings``. Operator curates these on the
   project page.
2. **Session overrides** — JSON dict on the session-start call.
   Can disable inherited bindings, add session-only bindings.
3. **Attachments** — volatile, per-prompt. File paths, snippets,
   URLs, project-entity references.

Unresolved references (e.g. a rule that was deleted after being
bound) are skipped with a single warning log line, not raised —
the operator's session should not break because of stale config.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.db import (
    get_command,
    get_hook,
    get_plugin,
    get_rule,
    list_project_forge_bindings,
)
from app.db.mcp_servers import get_mcp_server

logger = logging.getLogger(__name__)


# Per-attachment size cap. Files larger than this are truncated
# with a "[truncated]" suffix rather than embedded in full.
# 64 KB is the smallest cap that still admits typical source files;
# larger payloads belong in a tool call, not the prompt.
ATTACHMENT_BYTE_CAP = 64 * 1024


@dataclass
class ContextBundle:
    """The compiled context for one session (and optionally one prompt).

    All fields are populated even when empty — renderers can iterate
    without guarding on ``None``.
    """

    system_prompt_text: str = ""
    overlay_files: dict[str, str] = field(default_factory=dict)
    overlay_symlinks: dict[str, str] = field(default_factory=dict)
    mcp_servers: dict[str, dict] = field(default_factory=dict)
    prompt_prepend: str = ""
    # Bound sub-agents as [{"name": str, "body": str}]. claude discovers these
    # natively via the overlay's agents/ dir (written into overlay_files), so its
    # renderer does NOT inline the body. codex/gemini/opencode have no native
    # sub-agent concept and degrade to a named prompt-prefix block built from
    # this list (see context_renderers.base.subagent_prompt_block).
    subagents: list[dict] = field(default_factory=list)
    # Diagnostic — surfaced via /forge-context/preview so the
    # operator can see what got resolved / skipped.
    resolved_bindings: list[dict] = field(default_factory=list)
    skipped_bindings: list[dict] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any(
            (
                self.system_prompt_text,
                self.overlay_files,
                self.overlay_symlinks,
                self.mcp_servers,
                self.prompt_prepend,
                self.subagents,
            )
        )

    def to_preview_dict(self) -> dict:
        return {
            "system_prompt_text": self.system_prompt_text,
            "prompt_prepend": self.prompt_prepend,
            "overlay_files": sorted(self.overlay_files.keys()),
            "overlay_symlinks": sorted(self.overlay_symlinks.keys()),
            "mcp_servers": sorted(self.mcp_servers.keys()),
            "subagents": sorted(s.get("name", "") for s in self.subagents),
            "resolved_bindings": self.resolved_bindings,
            "skipped_bindings": self.skipped_bindings,
        }

    def to_dict(self) -> dict:
        """Full serialization for cross-call transport (route → PSM).

        Symmetric with ``from_dict``. Kept distinct from
        ``to_preview_dict`` because the preview hides ``overlay_files``
        content (returns just the keys) — applying the bundle in PSM
        needs the bytes.
        """
        return {
            "system_prompt_text": self.system_prompt_text,
            "overlay_files": dict(self.overlay_files),
            "overlay_symlinks": dict(self.overlay_symlinks),
            "mcp_servers": dict(self.mcp_servers),
            "prompt_prepend": self.prompt_prepend,
            "subagents": list(self.subagents),
            "resolved_bindings": list(self.resolved_bindings),
            "skipped_bindings": list(self.skipped_bindings),
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "ContextBundle":
        if not data:
            return cls()
        return cls(
            system_prompt_text=data.get("system_prompt_text", "") or "",
            overlay_files=dict(data.get("overlay_files") or {}),
            overlay_symlinks=dict(data.get("overlay_symlinks") or {}),
            mcp_servers=dict(data.get("mcp_servers") or {}),
            prompt_prepend=data.get("prompt_prepend", "") or "",
            subagents=list(data.get("subagents") or []),
            resolved_bindings=list(data.get("resolved_bindings") or []),
            skipped_bindings=list(data.get("skipped_bindings") or []),
        )


def _merge_bindings(
    project_bindings: list[dict],
    session_overrides: Optional[dict],
) -> list[dict]:
    """Apply session-level opt-outs and additions to project bindings.

    ``session_overrides`` shape::

        {
            "disabled_binding_ids": [12, 13],
            "additions": [
                {"kind": "skill", "asset_id": "code-search"},
                ...
            ]
        }
    """
    overrides = session_overrides or {}
    disabled = set(overrides.get("disabled_binding_ids", []) or [])
    merged = [b for b in project_bindings if b["id"] not in disabled]
    for add in overrides.get("additions", []) or []:
        kind = add.get("kind")
        asset_id = add.get("asset_id")
        if not kind or not asset_id:
            continue
        merged.append(
            {
                "id": None,
                "kind": kind,
                "asset_id": str(asset_id),
                "role": add.get("role"),
                "enabled": True,
                "position": 9999,
                "source": "session_override",
            }
        )
    return merged


def _render_rule(rule: dict) -> str:
    name = rule.get("name") or f"rule-{rule.get('id')}"
    # The rules table stores description/condition/action separately
    # (see backend/app/db/schema/_plugins.py). Compose them into one
    # readable block — empty parts are skipped so a description-only
    # rule renders cleanly.
    parts: list[str] = []
    if rule.get("description"):
        parts.append(str(rule["description"]).strip())
    if rule.get("condition"):
        parts.append(f"**Condition:** {str(rule['condition']).strip()}")
    if rule.get("action"):
        parts.append(f"**Action:** {str(rule['action']).strip()}")
    body = "\n\n".join(p for p in parts if p)
    if not body:
        return ""
    return f"## Rule: {name}\n{body}"


def _render_skill_pointer(skill_id: str) -> str:
    """Skills live in plugin dirs already symlinked via the overlay.

    The system-prompt mention is a hint — claude already discovers
    skills from its config dir.
    """
    return f"## Skill available: {skill_id}"


def _render_hook(hook: dict) -> dict:
    """Produce a settings.json hook fragment.

    The hooks table stores ``content`` (the script body) rather than
    a command path. The claude renderer is responsible for spilling
    ``content`` to a file under the overlay dir and substituting the
    resulting absolute path into the ``command`` field at apply
    time.
    """
    return {
        "event": hook.get("event"),
        "matcher": ".*",
        "name": hook.get("name"),
        "content": hook.get("content") or "",
        "source_path": hook.get("source_path"),
    }


def _render_command(command: dict) -> tuple[str, str]:
    """Return (relative_path, content) for a claude slash command."""
    name = command.get("name") or f"command-{command.get('id')}"
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in name)
    body = command.get("content") or command.get("body") or ""
    return f"commands/{safe}.md", body


def _render_mcp_server(server: dict) -> dict:
    """Compact mcp.json entry — only the fields claude/codex/gemini read."""
    out: dict[str, Any] = {}
    for key in ("command", "args", "env", "url", "type"):
        if server.get(key) is not None:
            out[key] = server[key]
    return out


def _resolve_attachment_file(
    path: str, project_root: Optional[str]
) -> Optional[tuple[str, str]]:
    """Read a repo-relative file, capped at ``ATTACHMENT_BYTE_CAP``.

    Returns ``(label, content)`` or ``None`` if the path is outside
    the project root (treated as untrusted) or unreadable.
    """
    if not project_root:
        return None
    try:
        root = Path(project_root).resolve()
        target = (root / path).resolve()
        target.relative_to(root)  # raises if escape attempt
    except (ValueError, OSError):
        logger.warning("attachment_file: path %r outside project root", path)
        return None
    if not target.is_file():
        return None
    try:
        data = target.read_bytes()
    except OSError:
        return None
    truncated = ""
    if len(data) > ATTACHMENT_BYTE_CAP:
        data = data[:ATTACHMENT_BYTE_CAP]
        truncated = "\n[truncated]"
    try:
        text = data.decode("utf-8", errors="replace")
    except UnicodeDecodeError:
        text = data.decode("latin-1", errors="replace")
    rel = str(target.relative_to(root))
    return (rel, text + truncated)


def _render_attachments(
    attachments: list[dict],
    project_root: Optional[str],
) -> str:
    """Render attachments into the universal prompt-prepend block."""
    if not attachments:
        return ""
    parts: list[str] = []
    for att in attachments:
        kind = att.get("kind")
        if kind == "file":
            resolved = _resolve_attachment_file(att.get("path", ""), project_root)
            if not resolved:
                continue
            rel, text = resolved
            parts.append(f"### file: {rel}\n```\n{text}\n```")
        elif kind == "snippet":
            label = att.get("label") or "note"
            text = (att.get("text") or "").strip()
            if not text:
                continue
            parts.append(f"### {label}\n{text}")
        elif kind == "url":
            url = att.get("url") or ""
            if not url:
                continue
            # Operator-supplied summary wins (saves a fetch and lets
            # them annotate). When absent, fetch + summarize on the
            # backend — failures fall back to "[fetch failed: ...]"
            # so the URL still rides into the prompt.
            inline_summary = (att.get("summary") or att.get("text") or "").strip()
            if inline_summary:
                parts.append(f"### url: {url}\n{inline_summary}")
                continue
            from .url_summarizer import fetch_and_summarize

            summary = fetch_and_summarize(url)
            header = f"### url: {url}"
            if summary.title:
                header += f"  ({summary.title})"
            if summary.error:
                parts.append(f"{header}\n[fetch failed: {summary.error}]")
            elif summary.text:
                parts.append(f"{header}\n{summary.text}")
            else:
                parts.append(f"{header}\n(no content)")
        elif kind == "entity":
            ref = att.get("ref") or ""
            payload = att.get("payload")
            if isinstance(payload, (dict, list)):
                payload = json.dumps(payload, indent=2, ensure_ascii=False)
            parts.append(f"### entity: {ref}\n```json\n{payload}\n```")
    if not parts:
        return ""
    return "=== Operator Context ===\n" + "\n\n".join(parts)


class ContextCompilerService:
    """Stateless compiler — call ``compile()`` for each session start
    and (optionally again) for each prompt with attachments."""

    @classmethod
    def compile(
        cls,
        project_id: str,
        *,
        session_overrides: Optional[dict] = None,
        attachments: Optional[list[dict]] = None,
        project_root: Optional[str] = None,
    ) -> ContextBundle:
        bundle = ContextBundle()

        # 1. Bindings → merged set
        project_bindings = list_project_forge_bindings(project_id, enabled_only=True)
        merged = _merge_bindings(project_bindings, session_overrides)

        system_prompt_chunks: list[str] = []
        hook_entries: list[dict] = []

        for b in merged:
            kind = b["kind"]
            asset_id = b["asset_id"]
            resolved_entry = {"kind": kind, "asset_id": asset_id, "id": b.get("id")}
            try:
                if kind == "rule":
                    rule = get_rule(int(asset_id))
                    if not rule:
                        bundle.skipped_bindings.append(
                            {**resolved_entry, "reason": "not found"}
                        )
                        continue
                    chunk = _render_rule(rule)
                    if chunk:
                        system_prompt_chunks.append(chunk)
                elif kind == "hook":
                    hook = get_hook(int(asset_id))
                    if not hook:
                        bundle.skipped_bindings.append(
                            {**resolved_entry, "reason": "not found"}
                        )
                        continue
                    hook_entries.append(_render_hook(hook))
                elif kind == "command":
                    cmd = get_command(int(asset_id))
                    if not cmd:
                        bundle.skipped_bindings.append(
                            {**resolved_entry, "reason": "not found"}
                        )
                        continue
                    rel, body = _render_command(cmd)
                    bundle.overlay_files[rel] = body
                elif kind == "subagent":
                    from app.db.subagents import get_subagent

                    subagent = get_subagent(str(asset_id))
                    if not subagent:
                        bundle.skipped_bindings.append(
                            {**resolved_entry, "reason": "not found"}
                        )
                        continue
                    name = subagent.get("name") or str(asset_id)
                    body = subagent.get("content") or ""
                    bundle.subagents.append({"name": name, "body": body})
                    # claude discovers this natively from the overlay's agents/
                    # dir; codex/gemini/opencode read bundle.subagents instead.
                    safe = "".join(
                        c if c.isalnum() or c in "-_" else "-" for c in name
                    )
                    bundle.overlay_files[f"agents/{safe}.md"] = body
                elif kind == "skill":
                    system_prompt_chunks.append(_render_skill_pointer(asset_id))
                elif kind == "mcp_server":
                    server = get_mcp_server(asset_id)
                    if not server:
                        bundle.skipped_bindings.append(
                            {**resolved_entry, "reason": "not found"}
                        )
                        continue
                    name = server.get("name") or asset_id
                    bundle.mcp_servers[name] = _render_mcp_server(server)
                elif kind == "plugin":
                    plugin = get_plugin(asset_id)
                    if not plugin:
                        bundle.skipped_bindings.append(
                            {**resolved_entry, "reason": "not found"}
                        )
                        continue
                    # Plugins live on disk under the user's claude
                    # config dir; the renderer chooses whether to
                    # symlink. We record the intent here.
                    resolved_entry["plugin_path"] = plugin.get("path")
                else:
                    bundle.skipped_bindings.append(
                        {**resolved_entry, "reason": f"unknown kind {kind!r}"}
                    )
                    continue
                bundle.resolved_bindings.append(resolved_entry)
            except Exception as exc:
                logger.warning(
                    "ContextCompilerService: failed to resolve %s/%s: %s",
                    kind,
                    asset_id,
                    exc,
                    exc_info=True,
                )
                bundle.skipped_bindings.append(
                    {**resolved_entry, "reason": f"error: {exc}"}
                )

        if system_prompt_chunks:
            bundle.system_prompt_text = "\n\n".join(system_prompt_chunks)

        if hook_entries:
            # Persist hook entries as a JSON sidecar — the claude
            # renderer merges them into the overlay's settings.json.
            bundle.overlay_files["_agented_hooks.json"] = json.dumps(
                hook_entries, indent=2, ensure_ascii=False
            )

        # 2. Attachments → prompt prepend (universal)
        bundle.prompt_prepend = _render_attachments(attachments or [], project_root)
        return bundle
