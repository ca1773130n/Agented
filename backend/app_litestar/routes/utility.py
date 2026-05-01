"""Utility read-only endpoints (track A, wave 45).

Port of /api/version, /api/check-backend, /api/validate-path from
Flask. Each is a small, side-effect-free probe — natural early
candidates for migration.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

from litestar import Router, get
from litestar.exceptions import ClientException

from app.config import PROJECT_ROOT

logger = logging.getLogger(__name__)


@get("/version", sync_to_thread=False)
def get_version() -> dict[str, str]:
    """Application version from git tag, with commit-hash fallback."""
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=PROJECT_ROOT,
        )
        if result.returncode == 0 and result.stdout.strip():
            return {"version": result.stdout.strip()}
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=PROJECT_ROOT,
        )
        if result.returncode == 0 and result.stdout.strip():
            return {"version": result.stdout.strip()}
    except Exception:  # noqa: BLE001
        logger.debug("Failed to determine version", exc_info=True)
    return {"version": "unknown"}


@get("/check-backend", sync_to_thread=False)
def check_backend(backend: Optional[str] = None, name: Optional[str] = None) -> dict[str, Any]:
    """Check whether a CLI backend (claude/opencode) is installed."""
    backend_name = (backend or name or "").lower()
    if backend_name not in ("claude", "opencode"):
        raise ClientException(detail="Invalid backend. Use 'claude' or 'opencode'")

    try:
        result = subprocess.run(
            [backend_name, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        installed = result.returncode == 0
        return {
            "backend": backend_name,
            "installed": installed,
            "version": result.stdout.strip() if installed else None,
            "path": shutil.which(backend_name),
        }
    except FileNotFoundError:
        return {
            "backend": backend_name,
            "installed": False,
            "version": None,
            "path": None,
        }
    except subprocess.TimeoutExpired:
        return {
            "backend": backend_name,
            "installed": False,
            "error": "Command timed out",
        }


@get("/validate-path", sync_to_thread=False)
def validate_path(path: str = "") -> dict[str, Any]:
    """Validate a directory path (restricted to home dir or /tmp)."""
    if not path:
        raise ClientException(detail="Path parameter required")
    path_obj = Path(path)
    try:
        resolved = path_obj.resolve()
    except (OSError, ValueError):
        raise ClientException(detail="Invalid path") from None

    allowed_bases = [Path.home(), Path("/tmp")]
    if not any(str(resolved).startswith(str(base)) for base in allowed_bases):
        return {
            "path": path,
            "exists": False,
            "is_directory": False,
            "is_file": False,
            "is_absolute": path_obj.is_absolute(),
            "error": "Path must be under home directory or /tmp",
        }
    return {
        "path": path,
        "exists": resolved.exists(),
        "is_directory": resolved.is_dir() if resolved.exists() else False,
        "is_file": resolved.is_file() if resolved.exists() else False,
        "is_absolute": path_obj.is_absolute(),
    }


utility_router = Router(
    path="/api",
    route_handlers=[get_version, check_backend, validate_path],
)


# Silence unused-import lint for the side-effecting os module used by
# any future expansion of validate_path.
_ = os
