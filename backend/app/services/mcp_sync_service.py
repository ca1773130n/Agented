"""MCP Sync Service -- transforms Hive's canonical MCP config to Claude Code's .mcp.json format.

Supports dry-run mode, non-Hive entry preservation via _hive_managed markers,
backup creation before writes, and atomic file writes.
"""

import difflib
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class McpSyncService:
    """Service for syncing Hive MCP configuration to Claude Code .mcp.json files."""

    @staticmethod
    def transform_to_claude(server: dict, env_overrides: str | None = None) -> dict:
        """Transform a canonical MCP server dict to Claude Code .mcp.json format.

        Args:
            server: Dict with keys like server_type, command, args, env_json, url, headers_json.
            env_overrides: Optional JSON string of env var overrides (overrides win over base).

        Returns:
            Dict suitable for inclusion in .mcp.json with _hive_managed marker.
        """
        config: dict = {"_hive_managed": True}

        server_type = server.get("server_type", "stdio")

        if server_type == "stdio":
            config["command"] = server["command"]
            config["args"] = json.loads(server.get("args") or "[]")

            # Merge base env with overrides
            base_env = json.loads(server.get("env_json") or "{}")
            if env_overrides:
                override_env = json.loads(env_overrides)
                base_env.update(override_env)
            if base_env:
                config["env"] = base_env

        elif server_type in ("http", "sse"):
            config["type"] = server_type
            config["url"] = server["url"]
            headers = json.loads(server.get("headers_json") or "{}")
            if headers:
                config["headers"] = headers

        return config

    @staticmethod
    def build_merged_config(project_id: str) -> dict:
        """Build the Hive-managed portion of .mcp.json for a project.

        Fetches all enabled MCP servers assigned to the project and transforms them.

        Args:
            project_id: The project ID to fetch MCP servers for.

        Returns:
            Dict mapping server_name -> Claude Code config dict (all with _hive_managed=True).
        """
        from app.db import get_project_mcp_servers

        servers = get_project_mcp_servers(project_id)
        result = {}

        for server in servers:
            # Check assignment_enabled from junction table (project_mcp_servers.enabled aliased as assignment_enabled)
            # Falls back to server-level enabled if assignment_enabled not present
            if not server.get("assignment_enabled", server.get("enabled")):
                continue

            name = server.get("server_name") or server.get("name")
            if not name:
                logger.warning("Skipping MCP server with no name: %s", server)
                continue

            # env_overrides_json comes from project_mcp_servers junction or config_override
            env_overrides = server.get("env_overrides_json") or server.get("config_override")
            result[name] = McpSyncService.transform_to_claude(server, env_overrides)

        return result

    @staticmethod
    def _compute_diff(existing: dict, new_config: dict) -> str:
        """Compute a unified diff between existing and new config dicts.

        Args:
            existing: The current .mcp.json content as a dict.
            new_config: The proposed new .mcp.json content as a dict.

        Returns:
            Unified diff string. Empty string if no changes.
        """
        old_text = json.dumps(existing, indent=2, sort_keys=True)
        new_text = json.dumps(new_config, indent=2, sort_keys=True)

        diff_lines = list(
            difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile="current .mcp.json",
                tofile="after sync",
            )
        )
        return "".join(diff_lines)

    @staticmethod
    def sync_project(project_id: str, project_path: str, dry_run: bool = False) -> dict:
        """Sync MCP config for a project to its .mcp.json file.

        The .mcp.json format is flat: server names are top-level keys (no mcpServers wrapper).

        Non-Hive entries (those without _hive_managed: True) are preserved.
        Hive-managed entries are replaced with the current build_merged_config output.

        Args:
            project_id: The project ID to sync.
            project_path: Filesystem path to the project root.
            dry_run: If True, return diff without writing. If False, write the file.

        Returns:
            Dict with result info:
              - dry_run=True: {"diff", "would_write", "servers_count"}
              - dry_run=False: {"written", "servers", "backup"}
              - On error: {"error": "..."}
        """
        mcp_file = Path(project_path) / ".mcp.json"

        # Read existing file
        existing: dict = {}
        if mcp_file.exists():
            try:
                existing = json.loads(mcp_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {"error": "Invalid JSON in existing .mcp.json"}

        # Preserve non-Hive entries (those without _hive_managed key)
        preserved = {
            k: v
            for k, v in existing.items()
            if not (isinstance(v, dict) and v.get("_hive_managed"))
        }

        # Build Hive-managed entries
        try:
            hive_entries = McpSyncService.build_merged_config(project_id)
        except Exception as e:
            logger.error("Failed to build MCP config for project %s: %s", project_id, e)
            return {"error": f"Failed to build config: {e}"}

        # Merge: preserved non-Hive entries + new Hive entries
        merged = {**preserved, **hive_entries}

        if dry_run:
            diff = McpSyncService._compute_diff(existing, merged)
            return {
                "diff": diff,
                "would_write": str(mcp_file),
                "servers_count": len(hive_entries),
            }

        # Write mode
        try:
            # Create backup if file exists
            backup_path = None
            if mcp_file.exists():
                backup_path = str(mcp_file) + ".bak"
                shutil.copy2(str(mcp_file), backup_path)
                logger.info("Created backup: %s", backup_path)

            # Atomic write: write to temp file then os.replace
            dir_path = mcp_file.parent
            fd, tmp_path = tempfile.mkstemp(dir=str(dir_path), suffix=".mcp.json.tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(merged, f, indent=2)
                    f.write("\n")
                os.replace(tmp_path, str(mcp_file))
            except Exception:
                # Clean up temp file on failure
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise

            logger.info("Wrote MCP config to %s (%d servers)", mcp_file, len(merged))
            return {
                "written": str(mcp_file),
                "servers": len(merged),
                "backup": backup_path,
            }

        except PermissionError:
            return {"error": f"Permission denied: {mcp_file}"}

    @staticmethod
    def validate_project_path(project_path: str) -> tuple[bool, str]:
        """Validate that a project path exists and is writable.

        Args:
            project_path: Filesystem path to validate.

        Returns:
            Tuple of (is_valid, reason). reason is empty string if valid.
        """
        path = Path(project_path)
        if not path.exists():
            return (False, f"Path does not exist: {project_path}")
        if not path.is_dir():
            return (False, f"Path is not a directory: {project_path}")
        if not os.access(str(path), os.W_OK):
            return (False, f"No write permission on: {project_path}")
        return (True, "")
