"""Session-scoped ``CODEX_HOME`` overlay (v0.7.71).

Codex reads MCP server definitions from ``~/.codex/config.toml``
under ``[mcp_servers.<NAME>]`` sections, plus slash commands /
prompts under ``~/.codex/prompts/`` and auth tokens under
``~/.codex/auth.json``. Like the claude overlay, we:

1. Make a tmp dir.
2. Symlink the user's existing items so auth still works.
3. Write a merged ``config.toml`` with the bundle's MCP servers
   appended (existing user MCP entries preserved by name).
4. Spill bundle slash commands into ``prompts/`` (codex reads
   ``~/.codex/prompts/<name>.md`` as ``/<name>`` slash commands).
5. Set ``CODEX_HOME`` for the subprocess.

Hooks are intentionally not materialized — codex has no
PreToolUse hook concept.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .cli_overlay_base import cleanup_cli_overlay, prepare_cli_overlay

logger = logging.getLogger(__name__)


_PASSTHROUGH = (
    "auth.json",
    "config.toml",
    "history.jsonl",
    "log",
    "sessions",
    "rollouts",
    "prompts",
)

_OVERLAY_PREFIX = "agented-codex-overlay"


def prepare_session_overlay(session_id: str, user_config_dir: str) -> Optional[str]:
    return prepare_cli_overlay(
        session_id=session_id,
        user_config_dir=user_config_dir,
        overlay_prefix=_OVERLAY_PREFIX,
        passthrough_items=_PASSTHROUGH,
    )


def cleanup_session_overlay(session_id: str) -> None:
    cleanup_cli_overlay(session_id, _OVERLAY_PREFIX)


def _toml_quote(value: str) -> str:
    """Minimal TOML basic-string quoter — escapes backslash + quote."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_array(values) -> str:
    return "[" + ", ".join(_toml_quote(str(v)) for v in values) + "]"


def _toml_inline_table(d: dict) -> str:
    parts = [f"{k} = {_toml_quote(str(v))}" for k, v in d.items()]
    return "{ " + ", ".join(parts) + " }"


def _render_mcp_section(name: str, cfg: dict) -> str:
    """Serialize one ``[mcp_servers.NAME]`` section.

    Codex's TOML schema covers ``command``, ``args``, ``env``,
    ``url``. We pass through whatever the bundle gave us. Symbols
    not understood by codex are ignored by it, which is fine.
    """
    safe_name = "".join(c if c.isalnum() or c in "-_" else "-" for c in name)
    lines = [f"[mcp_servers.{safe_name}]"]
    if "command" in cfg:
        lines.append(f"command = {_toml_quote(str(cfg['command']))}")
    if "args" in cfg and cfg["args"]:
        lines.append(f"args = {_toml_array(cfg['args'])}")
    if "url" in cfg and cfg["url"]:
        lines.append(f"url = {_toml_quote(str(cfg['url']))}")
    if "env" in cfg and cfg["env"]:
        lines.append(f"env = {_toml_inline_table(cfg['env'])}")
    return "\n".join(lines)


def apply_forge_bundle(overlay_dir: str, bundle: dict) -> None:
    """Materialize the bundle's overlay portions into the codex overlay.

    No-op if ``bundle`` is empty or ``overlay_dir`` is missing. Pure
    additive — existing user MCP entries kept; we append ours.
    """
    if not bundle:
        return
    base = Path(overlay_dir)
    if not base.exists():
        logger.warning("codex_overlay: dir %s missing, skipping apply", overlay_dir)
        return

    _append_mcp_servers(base, bundle.get("mcp_servers") or {})
    _write_prompts(base, bundle.get("overlay_files") or {})


def _append_mcp_servers(base: Path, mcp_servers: dict) -> None:
    if not mcp_servers:
        return
    config_path = base / "config.toml"
    existing = ""
    if config_path.exists():
        try:
            existing = config_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning(
                "codex_overlay: cannot read %s: %s — starting fresh",
                config_path,
                exc,
            )
            existing = ""
    sections = [_render_mcp_section(name, cfg) for name, cfg in mcp_servers.items()]
    appended = existing.rstrip() + (
        "\n\n# --- agented-managed MCP servers ---\n" + "\n\n".join(sections) + "\n"
    )
    try:
        config_path.write_text(appended, encoding="utf-8")
    except OSError as exc:
        logger.warning("codex_overlay: cannot write %s: %s", config_path, exc)


def _write_prompts(base: Path, overlay_files: dict) -> None:
    """Slash commands → ``prompts/<name>.md``. Commands compiled by
    ``ContextCompilerService`` land at ``commands/<name>.md`` in the
    bundle; codex reads them from ``prompts/``, so we re-key.
    """
    prompts_dir = base / "prompts"
    base_resolved = base.resolve()
    wrote_any = False
    for rel, content in overlay_files.items():
        if not rel.startswith("commands/") or not rel.endswith(".md"):
            continue
        name = rel[len("commands/") : -len(".md")]
        target = (prompts_dir / f"{name}.md").resolve()
        try:
            target.relative_to(base_resolved)
        except ValueError:
            logger.warning("codex_overlay: refusing to write outside overlay (%s)", rel)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_text(content, encoding="utf-8")
            wrote_any = True
        except OSError as exc:
            logger.warning("codex_overlay: failed to write %s: %s", rel, exc)
    if wrote_any:
        logger.debug("codex_overlay: wrote prompts into %s", prompts_dir)
