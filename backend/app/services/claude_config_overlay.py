"""Session-scoped CLAUDE_CONFIG_DIR overlay for interactive permission
prompts (v0.7.69).

When a chat session opts in to web-panel permission prompts, we don't
want to mutate the user's real ``~/.claude/settings.json`` — that
would affect every other claude invocation. Instead:

1. Create a temp dir per session under ``/tmp``.
2. Symlink the user's existing config items (``plugins/``, ``mcp.json``,
   transcripts, etc.) into the temp dir so claude still sees skills,
   MCP servers, prior transcripts.
3. Generate a fresh ``settings.json`` in the temp dir merging the
   user's existing settings + a PreToolUse hook pointing at our
   ``agented_permission_hook.py`` script.
4. Set ``CLAUDE_CONFIG_DIR`` for the subprocess to the temp dir.

On session teardown, ``cleanup_session_overlay`` removes the temp dir.
The user's ``~/.claude`` is never touched.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import stat
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# Items in the user's claude config dir that we symlink (passthrough)
# rather than override. Anything else we silently skip.
#
# NOTE: `.credentials.json` / `.oauth-token` carry the account's OAuth login.
# Without them a spawned `claude` reads the overlay as its CLAUDE_CONFIG_DIR,
# finds no credentials, and dies with "Not logged in · Please run /login" —
# even though the account is configured. The gemini/opencode overlays already
# pass their `credentials.json` through; this list simply omitted the claude
# equivalents, which broke every spawned claude harness session (research,
# autopilot, harness-round, grd_chat). Symlinked read-only from the account dir.
_PASSTHROUGH_ITEMS = {
    "plugins",
    "mcp.json",
    "projects",
    "backups",
    "cache",
    "context-mode",
    "session-env",
    "last-activity",
    "settings.local.json",
    "harnesssync_health_history.json",
    ".credentials.json",
    ".oauth-token",
}


def _hook_script_path() -> Path:
    """Resolve the absolute path to our hook script.

    The script lives at ``backend/scripts/agented_permission_hook.py``
    in the repo. We resolve via this module's location so the path is
    correct in any deployment layout.
    """
    return Path(__file__).resolve().parents[2] / "scripts" / "agented_permission_hook.py"


def _build_settings_json(user_settings_path: Optional[Path]) -> dict:
    """Read the user's settings.json (if any) and append the Agented
    permission hook entry. The hook's ``matcher`` of ``.*`` makes it
    fire for every tool call; the actual gate inside the script keys
    off ``AGENTED_PERMISSION_HOOK_ACTIVE`` so non-Agented invocations
    are untouched."""
    settings: dict = {}
    if user_settings_path and user_settings_path.exists():
        try:
            settings = json.loads(user_settings_path.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning(
                "claude_config_overlay: failed to parse %s, starting fresh",
                user_settings_path,
            )
            settings = {}

    hooks_block = settings.setdefault("hooks", {})
    pretooluse = hooks_block.setdefault("PreToolUse", [])
    # Drop any previously-installed entry pointing at our script
    # before adding a fresh one. Idempotent.
    script_path = str(_hook_script_path())
    pretooluse[:] = [
        e
        for e in pretooluse
        if not (
            isinstance(e, dict)
            and any(
                isinstance(h, dict) and h.get("command") == script_path
                for h in (e.get("hooks") or [])
            )
        )
    ]
    pretooluse.append(
        {
            "matcher": ".*",
            "hooks": [
                {
                    "type": "command",
                    "command": script_path,
                    "timeout": 310,  # >= backend long-poll + 5s slack
                }
            ],
        }
    )
    return settings


def build_hook_settings_arg(user_config_dir: str) -> Optional[str]:
    """Build a minimal ``--settings`` JSON payload that installs ONLY our
    PreToolUse permission hook, for AUTONOMOUS claude sessions.

    Autonomous GRD/research/autopilot/harness sessions must keep
    ``CLAUDE_CONFIG_DIR`` pointed at the REAL, daemon-backed account dir
    (see the module docstring + the ``.credentials.json`` note above):
    Claude Code refreshes its OAuth token via an auth daemon tied to the
    config dir, and the temp ``/tmp`` overlay has no such daemon, so a
    spawned ``claude`` there reads the stale file token, can't refresh it,
    and dies "Not logged in · Please run /login". We therefore do NOT
    build a temp overlay for autonomous sessions; instead we deliver the
    same permission hook via the claude CLI ``--settings`` flag, which
    performs a per-KEY MERGE over the real config dir's ``settings.json``
    (auth daemon dir + hook simultaneously).

    We reuse ``_build_settings_json`` so the hook contract has one source
    of truth: it reads the REAL dir's ``settings.json`` first (preserving
    and de-duping any PreToolUse hooks already there), then we ``json.dumps``
    ONLY the ``{"hooks": ...}`` subset so ``--settings`` merges just the
    hooks key and every other real-dir setting stays file-based.

    Returns ``None`` if the user config dir is missing or the build fails —
    the caller then spawns WITHOUT the flag (still authed against the real
    dir, just with no hook), never blocking the session. ``-p`` mode
    silently ignores invalid ``--settings`` JSON, so returning ``None`` on
    failure (rather than passing garbage) is the safe degrade.
    """
    try:
        user_dir = Path(os.path.expanduser(user_config_dir))
        if not user_dir.exists():
            logger.warning(
                "claude_config_overlay: user config dir %s missing, "
                "skipping --settings hook injection",
                user_dir,
            )
            return None
        settings = _build_settings_json(user_dir / "settings.json")
        # Only ship the hooks subset — everything else stays file-based on
        # the real dir. json.dumps of a validated dict is always valid JSON.
        return json.dumps({"hooks": settings.get("hooks", {})}, ensure_ascii=False)
    except Exception:
        logger.warning(
            "claude_config_overlay: failed to build --settings hook arg for %s",
            user_config_dir,
            exc_info=True,
        )
        return None


def prepare_session_overlay(session_id: str, user_config_dir: str) -> Optional[str]:
    """Build the session-scoped overlay dir and return its path.

    Returns ``None`` if the user's config dir doesn't exist (we can't
    overlay something that isn't there). Caller falls back to the
    original ``CLAUDE_CONFIG_DIR`` value in that case.
    """
    user_dir = Path(os.path.expanduser(user_config_dir))
    if not user_dir.exists():
        logger.warning(
            "claude_config_overlay: user config dir %s missing, skipping overlay",
            user_dir,
        )
        return None

    overlay = Path(f"/tmp/agented-claude-overlay-{session_id}")
    if overlay.exists():
        # Stale from a previous run with the same id — nuke it.
        shutil.rmtree(overlay, ignore_errors=True)
    overlay.mkdir(parents=True, exist_ok=True)

    # Symlink passthrough items.
    for name in _PASSTHROUGH_ITEMS:
        src = user_dir / name
        if not src.exists():
            continue
        dst = overlay / name
        try:
            os.symlink(src, dst)
        except OSError as exc:
            logger.warning(
                "claude_config_overlay: symlink %s → %s failed: %s",
                src,
                dst,
                exc,
            )

    # Write merged settings.json.
    try:
        settings = _build_settings_json(user_dir / "settings.json")
        (overlay / "settings.json").write_text(json.dumps(settings, indent=2, ensure_ascii=False))
    except Exception:
        logger.warning(
            "claude_config_overlay: failed to write merged settings.json",
            exc_info=True,
        )
        # Without settings.json the hook won't fire — clean up and bail.
        shutil.rmtree(overlay, ignore_errors=True)
        return None

    logger.info(
        "claude_config_overlay: prepared %s for session %s",
        overlay,
        session_id,
    )
    return str(overlay)


def apply_forge_bundle(overlay_dir: str, bundle: dict) -> None:
    """Materialize a serialized ``ContextBundle`` into an overlay dir.

    Called by ProjectSessionManager *after* its own
    ``prepare_session_overlay`` creates the dir so the bundle's
    files layer on top of the user's existing config (skills,
    plugins, MCP servers) and our PreToolUse permission hook.

    Three things get written:

    1. Plain overlay files (``overlay_files`` dict) — slash commands
       under ``commands/`` for example. Path-escape attempts are
       refused and logged.
    2. Symlinks (``overlay_symlinks`` dict) — same path-confinement
       rules.
    3. MCP server entries merged into ``mcp.json``'s ``mcpServers``
       map (existing entries preserved unless the bundle overrides
       by name).
    4. Hook entries (the ``_agented_hooks.json`` sidecar) — each
       hook's content is spilled to ``hooks/<name>.sh`` and
       registered in the overlay's ``settings.json`` under the
       declared event (default ``PreToolUse``). Hooks merge with
       any existing entries rather than overwriting.

    Empty bundle is a no-op. Errors are logged but never raised:
    a bad binding shouldn't take down the operator's session.
    """
    if not bundle:
        return
    base = Path(overlay_dir)
    if not base.exists():
        logger.warning("apply_forge_bundle: overlay dir %s missing, skipping", overlay_dir)
        return

    _write_overlay_files(base, bundle.get("overlay_files") or {})
    _write_overlay_symlinks(base, bundle.get("overlay_symlinks") or {})
    _merge_mcp_json(base, bundle.get("mcp_servers") or {})
    _materialize_hooks(base, bundle.get("overlay_files") or {})


def _write_overlay_files(base: Path, overlay_files: dict) -> None:
    base_resolved = base.resolve()
    for rel, content in overlay_files.items():
        # Hook sidecars are handled separately by ``_materialize_hooks``.
        if rel == "_agented_hooks.json":
            continue
        try:
            target = (base / rel).resolve()
            target.relative_to(base_resolved)
        except (ValueError, OSError):
            logger.warning("apply_forge_bundle: refusing to write outside overlay (%s)", rel)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            logger.warning("apply_forge_bundle: failed to write %s: %s", rel, exc)


def _write_overlay_symlinks(base: Path, overlay_symlinks: dict) -> None:
    base_resolved = base.resolve()
    for rel, src in overlay_symlinks.items():
        try:
            target = (base / rel).resolve()
            target.relative_to(base_resolved)
        except (ValueError, OSError):
            continue
        if target.exists() or target.is_symlink():
            try:
                target.unlink()
            except OSError:
                continue
        try:
            os.symlink(src, target)
        except OSError as exc:
            logger.warning(
                "apply_forge_bundle: failed to symlink %s -> %s: %s",
                rel,
                src,
                exc,
            )


def _merge_mcp_json(base: Path, mcp_servers: dict) -> None:
    if not mcp_servers:
        return
    mcp_path = base / "mcp.json"
    existing: dict = {}
    if mcp_path.exists():
        try:
            existing = json.loads(mcp_path.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("apply_forge_bundle: existing mcp.json invalid, overwriting")
            existing = {}
    servers = existing.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        servers = {}
    servers.update(mcp_servers)
    existing["mcpServers"] = servers
    mcp_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))


def _materialize_hooks(base: Path, overlay_files: dict) -> None:
    """Spill ``_agented_hooks.json`` entries into ``hooks/`` scripts +
    ``settings.json`` registrations.
    """
    raw = overlay_files.get("_agented_hooks.json")
    if not raw:
        return
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("apply_forge_bundle: _agented_hooks.json invalid; skipping")
        return
    if not entries:
        return
    hooks_dir = base / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    settings_path = base / "settings.json"
    settings: dict = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, OSError):
            settings = {}
    hooks_block = settings.setdefault("hooks", {})

    for entry in entries:
        event = entry.get("event") or "PreToolUse"
        name = entry.get("name") or "agented-hook"
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in name)
        script_path = hooks_dir / f"{safe}.sh"
        content = entry.get("content") or ""
        if not content.startswith("#!"):
            content = "#!/bin/sh\n" + content
        try:
            script_path.write_text(content, encoding="utf-8")
            mode = script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP
            script_path.chmod(mode)
        except OSError as exc:
            logger.warning("apply_forge_bundle: failed to write hook %s: %s", name, exc)
            continue
        event_block = hooks_block.setdefault(event, [])
        if not isinstance(event_block, list):
            event_block = []
            hooks_block[event] = event_block
        event_block.append(
            {
                "matcher": entry.get("matcher") or ".*",
                "hooks": [
                    {
                        "type": "command",
                        "command": str(script_path),
                    }
                ],
            }
        )
    try:
        settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=False))
    except OSError as exc:
        logger.warning("apply_forge_bundle: failed to write merged settings.json: %s", exc)


def cleanup_session_overlay(session_id: str) -> None:
    """Remove the session-scoped overlay dir. Best-effort — failures
    are logged but not raised so a teardown error doesn't take down
    the session-exit handler."""
    overlay = Path(f"/tmp/agented-claude-overlay-{session_id}")
    if not overlay.exists():
        return
    try:
        shutil.rmtree(overlay)
        logger.info("claude_config_overlay: removed %s", overlay)
    except OSError as exc:
        logger.warning("claude_config_overlay: failed to remove %s: %s", overlay, exc)


_OVERLAY_GLOB = "agented-claude-overlay-*"
_DEFAULT_MAX_AGE_HOURS = 2


def cleanup_stale_overlays(*, max_age_hours: int = _DEFAULT_MAX_AGE_HOURS) -> dict:
    """Remove ``/tmp/agented-claude-overlay-*`` dirs older than the threshold.

    Called at backend startup to mop up after crashes / SIGKILLs where the
    per-session ``finally:`` block didn't get to run. Two-hour default gives
    in-flight long executions plenty of slack while still cleaning multi-day
    orphans.

    Returns ``{"removed": N, "kept": N, "errors": N}`` for diagnostic logs.
    Never raises — startup must succeed even when /tmp is hostile.
    """
    import time

    removed = 0
    kept = 0
    errors = 0
    cutoff = time.time() - max_age_hours * 3600

    try:
        for path in Path("/tmp").glob(_OVERLAY_GLOB):
            try:
                if not path.is_dir():
                    continue
                if path.stat().st_mtime >= cutoff:
                    kept += 1
                    continue
                shutil.rmtree(path, ignore_errors=True)
                if path.exists():
                    errors += 1
                else:
                    removed += 1
            except OSError:
                errors += 1
    except OSError:
        errors += 1

    if removed or errors:
        logger.info(
            "claude_config_overlay GC: removed=%d kept=%d errors=%d (max_age_hours=%d)",
            removed,
            kept,
            errors,
            max_age_hours,
        )
    return {"removed": removed, "kept": kept, "errors": errors}
