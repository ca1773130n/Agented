"""GRD CLI Service — subprocess wrapper for grd-tools.js write operations.

Provides binary auto-detection and graceful degradation when grd-tools.js is
not installed. Used by API routes to update plan status and other write
operations that must preserve GRD's internal consistency logic.
"""

import glob as glob_module
import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


class GrdCliService:
    """Service for shelling out to grd-tools.js for write operations.

    Uses class-level state with @classmethod methods. Binary detection runs
    once at startup via detect_binary() and caches the result.
    """

    _binary_path: Optional[str] = None
    _binary_available: bool = False

    @classmethod
    def detect_binary(cls) -> Optional[str]:
        """Detect grd-tools.js binary path. Called at startup. Caches result.

        Detection order:
        1. Check settings table for grd_binary_path
        2. Check CLAUDE_PLUGIN_ROOT env var + /bin/grd-tools.js
        3. Glob known install locations (most recently modified wins)
        4. If nothing found: return None

        Returns:
            Absolute path to grd-tools.js, or None if not found.
        """
        # 1. Check settings table
        try:
            from app.database import get_setting

            stored = get_setting("grd_binary_path")
            if stored and os.path.isfile(stored):
                cls._binary_path = stored
                cls._binary_available = True
                logger.info(f"GRD binary found via settings: {stored}")
                return stored
        except Exception:
            # Settings table may not be available during import
            pass

        # 2. CLAUDE_PLUGIN_ROOT env var
        plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
        if plugin_root:
            candidate = os.path.join(plugin_root, "bin", "grd-tools.js")
            if os.path.isfile(candidate):
                cls._binary_path = candidate
                cls._binary_available = True
                logger.info(f"GRD binary found via CLAUDE_PLUGIN_ROOT: {candidate}")
                return candidate

        # 3. Glob known install locations
        patterns = [
            os.path.expanduser("~/.claude/plugins/*/GRD/bin/grd-tools.js"),
            os.path.expanduser("~/.claude/plugins/marketplaces/*/plugins/GRD/bin/grd-tools.js"),
            os.path.expanduser("~/.claude-*/plugins/*/GRD/bin/grd-tools.js"),
        ]
        for pattern in patterns:
            matches = glob_module.glob(pattern)
            if matches:
                # Use the most recently modified match (likely latest version)
                matches.sort(key=os.path.getmtime, reverse=True)
                cls._binary_path = matches[0]
                cls._binary_available = True
                logger.info(f"GRD binary found via glob: {matches[0]}")
                return matches[0]

        # 4. Not found
        cls._binary_available = False
        logger.warning("GRD binary not found — GRD CLI write operations will be unavailable")
        return None

    @classmethod
    def run_command(cls, cwd: str, *args) -> dict:
        """Run a grd-tools.js command. Returns {success, output, error}.

        Args:
            cwd: Working directory (project root, where .planning/ lives).
            *args: Command and arguments for grd-tools.js.

        Returns:
            {"success": bool, "output": str|None, "error": str|None}
        """
        if not cls._binary_available or not cls._binary_path:
            return {"success": False, "output": None, "error": "GRD binary not available"}

        cmd = ["node", cls._binary_path] + list(args) + ["--raw"]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=cwd,
            )
            if result.returncode == 0:
                return {"success": True, "output": result.stdout.strip(), "error": None}
            else:
                return {
                    "success": False,
                    "output": result.stdout.strip() or None,
                    "error": result.stderr.strip() or f"Exit code {result.returncode}",
                }
        except subprocess.TimeoutExpired:
            return {"success": False, "output": None, "error": "Command timed out (30s)"}
        except FileNotFoundError:
            cls._binary_available = False
            return {
                "success": False,
                "output": None,
                "error": "node or grd-tools.js not found",
            }
        except Exception as e:
            return {"success": False, "output": None, "error": str(e)}

    @classmethod
    def update_plan_status(cls, project_path: str, plan_file: str, status: str) -> dict:
        """Update a plan's frontmatter status field via grd-tools.js.

        Args:
            project_path: Absolute path to project root (where .planning/ lives).
            plan_file: Absolute path to the PLAN.md file.
            status: New status value (pending, in_progress, completed, failed, in_review).

        Returns:
            {"success": bool, "output": str|None, "error": str|None}
        """
        valid_statuses = {"pending", "in_progress", "completed", "failed", "in_review"}
        if status not in valid_statuses:
            return {
                "success": False,
                "output": None,
                "error": f"Invalid status: {status}. Must be one of: {', '.join(sorted(valid_statuses))}",
            }

        return cls.run_command(
            project_path,
            "frontmatter",
            "set",
            plan_file,
            "--field",
            "status",
            "--value",
            f'"{status}"',
        )
