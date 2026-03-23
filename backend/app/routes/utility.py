"""Utility API endpoints."""

import logging
import os
import shutil

logger = logging.getLogger(__name__)
import subprocess
import threading
from http import HTTPStatus
from pathlib import Path

from flask import request
from flask_openapi3 import APIBlueprint, Tag

from app.config import PROJECT_ROOT
from app.models.common import error_response

from ..database import get_paths_for_trigger, get_trigger
from ..services.execution_service import ExecutionService
from ..services.github_service import GitHubService
from ..services.skill_discovery_service import SkillDiscoveryService

tag = Tag(name="utility", description="Utility endpoints")
utility_bp = APIBlueprint("utility", __name__, url_prefix="/api", abp_tags=[tag])


@utility_bp.get("/version")
def get_version():
    """Get the application version from git tag or commit hash."""
    try:
        # Try to get the latest tag first
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=PROJECT_ROOT,
        )
        if result.returncode == 0 and result.stdout.strip():
            return {"version": result.stdout.strip()}, HTTPStatus.OK

        # Fall back to short commit hash
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=PROJECT_ROOT,
        )
        if result.returncode == 0 and result.stdout.strip():
            return {"version": result.stdout.strip()}, HTTPStatus.OK

        return {"version": "unknown"}, HTTPStatus.OK

    except Exception:
        logger.debug("Failed to determine CLI version", exc_info=True)
        return {"version": "unknown"}, HTTPStatus.OK


@utility_bp.get("/check-backend")
def check_backend():
    """Check if a CLI backend (claude/opencode) is installed and runnable."""
    backend_name = (request.args.get("backend") or request.args.get("name") or "").lower()

    if backend_name not in ("claude", "opencode"):
        return error_response(
            "BAD_REQUEST", "Invalid backend. Use 'claude' or 'opencode'", HTTPStatus.BAD_REQUEST
        )

    try:
        result = subprocess.run(
            [backend_name, "--version"], capture_output=True, text=True, timeout=10
        )
        installed = result.returncode == 0
        version = result.stdout.strip() if installed else None

        return {
            "backend": backend_name,
            "installed": installed,
            "version": version,
            "path": shutil.which(backend_name),
        }, HTTPStatus.OK

    except FileNotFoundError:
        return {
            "backend": backend_name,
            "installed": False,
            "version": None,
            "path": None,
        }, HTTPStatus.OK

    except subprocess.TimeoutExpired:
        return {
            "backend": backend_name,
            "installed": False,
            "error": "Command timed out",
        }, HTTPStatus.OK


@utility_bp.get("/validate-path")
def validate_path():
    """Validate if a path exists and is a directory (restricted to home dir or /tmp)."""
    path = request.args.get("path", "")
    if not path:
        return error_response("BAD_REQUEST", "Path parameter required", HTTPStatus.BAD_REQUEST)

    path_obj = Path(path)
    try:
        resolved = path_obj.resolve()
    except (OSError, ValueError):
        return error_response("BAD_REQUEST", "Invalid path", HTTPStatus.BAD_REQUEST)

    allowed_bases = [Path.home(), Path("/tmp")]
    if not any(str(resolved).startswith(str(base)) for base in allowed_bases):
        return {
            "path": path,
            "exists": False,
            "is_directory": False,
            "is_file": False,
            "is_absolute": path_obj.is_absolute(),
            "error": "Path must be under home directory or /tmp",
        }, HTTPStatus.FORBIDDEN

    return {
        "path": path,
        "exists": resolved.exists(),
        "is_directory": resolved.is_dir() if resolved.exists() else False,
        "is_file": resolved.is_file() if resolved.exists() else False,
        "is_absolute": path_obj.is_absolute(),
    }, HTTPStatus.OK


@utility_bp.get("/validate-github-url")
def validate_github_url():
    """Validate if a GitHub repo URL is accessible."""
    url = request.args.get("url", "")
    if not url:
        return error_response("BAD_REQUEST", "url parameter required", HTTPStatus.BAD_REQUEST)

    valid = GitHubService.validate_repo_url(url)
    owner, repo = None, None
    try:
        owner, repo = GitHubService.parse_repo_url(url)
    except ValueError:
        pass

    return {
        "url": url,
        "valid": valid,
        "owner": owner,
        "repo": repo,
    }, HTTPStatus.OK


@utility_bp.post("/resolve-issues")
def resolve_issues():
    """Run Claude with edit permissions to resolve security issues."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    audit_summary = data.get("audit_summary", "")
    project_paths = data.get("project_paths", [])

    if not audit_summary:
        return error_response("BAD_REQUEST", "audit_summary required", HTTPStatus.BAD_REQUEST)
    if not project_paths:
        return error_response("BAD_REQUEST", "project_paths required", HTTPStatus.BAD_REQUEST)

    thread = threading.Thread(
        target=ExecutionService.run_resolve_command,
        args=(audit_summary, project_paths),
        daemon=True,
    )
    thread.start()

    return {
        "message": "Resolution started",
        "status": "running",
        "project_count": len(project_paths),
    }, HTTPStatus.ACCEPTED


@utility_bp.get("/discover-skills")
def discover_skills():
    """Discover available Claude skills and commands from project, global, and plugin dirs.

    Query params: trigger_id (look up paths), paths (comma-separated scan dirs).
    """
    trigger_id = request.args.get("trigger_id", "")
    paths_param = request.args.get("paths", "")

    scan_paths = []
    if trigger_id:
        trigger = get_trigger(trigger_id)
        if not trigger:
            return error_response("NOT_FOUND", "Trigger not found", HTTPStatus.NOT_FOUND)
        scan_paths = get_paths_for_trigger(trigger_id)
    elif paths_param:
        scan_paths = [p.strip() for p in paths_param.split(",") if p.strip()]

    # Always include the project root as a scan path
    if PROJECT_ROOT not in scan_paths:
        scan_paths.append(PROJECT_ROOT)

    skills = SkillDiscoveryService.discover_cli_skills(scan_paths)
    return {"skills": skills}, HTTPStatus.OK


# ---------------------------------------------------------------------------
# Directory browser helpers
# ---------------------------------------------------------------------------

_ALLOWED_BASES = [Path.home(), Path("/tmp"), Path("/opt")]


def _is_path_allowed(resolved: Path) -> bool:
    """Return True if resolved path is under an allowed base directory."""
    resolved_str = str(resolved)
    return any(
        resolved_str == str(base) or resolved_str.startswith(str(base) + os.sep)
        for base in _ALLOWED_BASES
    )


@utility_bp.get("/browse-directory")
def browse_directory():
    """List subdirectories of a given path (directory picker).

    Query params:
      path — directory to list (defaults to the user's home directory).

    Only directories are returned. Restricted to paths under the user's home
    directory, /tmp, or /opt. Symlinks that resolve outside allowed paths are
    skipped.
    """
    raw_path = request.args.get("path", "") or str(Path.home())

    path_obj = Path(raw_path)
    try:
        resolved = path_obj.resolve()
    except (OSError, ValueError):
        return error_response("BAD_REQUEST", "Invalid path", HTTPStatus.BAD_REQUEST)

    if not _is_path_allowed(resolved):
        return error_response(
            "FORBIDDEN",
            "Path must be under home directory, /tmp, or /opt",
            HTTPStatus.FORBIDDEN,
        )

    if not resolved.is_dir():
        return error_response("NOT_FOUND", "Directory does not exist", HTTPStatus.NOT_FOUND)

    # Build parent path (stop at the shallowest allowed base)
    parent = resolved.parent
    parent_path = str(parent) if _is_path_allowed(parent) else None

    entries = []
    try:
        for entry in sorted(resolved.iterdir(), key=lambda e: e.name.lower()):
            try:
                entry_resolved = entry.resolve()
            except (OSError, ValueError):
                continue

            # Only directories
            if not entry_resolved.is_dir():
                continue

            # Skip hidden directories
            if entry.name.startswith("."):
                continue

            # Skip symlinks that escape allowed paths
            if entry.is_symlink() and not _is_path_allowed(entry_resolved):
                continue

            # Skip entries the user cannot read
            if not os.access(entry_resolved, os.R_OK):
                continue

            entries.append(
                {
                    "name": entry.name,
                    "path": str(entry_resolved),
                    "type": "directory",
                }
            )
    except PermissionError:
        return error_response("FORBIDDEN", "Cannot read directory contents", HTTPStatus.FORBIDDEN)

    return {
        "current_path": str(resolved),
        "parent_path": parent_path,
        "entries": entries,
    }, HTTPStatus.OK


@utility_bp.post("/create-directory")
def create_directory():
    """Create a new directory (mkdir -p equivalent).

    JSON body:
      path — absolute path of the directory to create.

    Restricted to paths under the user's home directory, /tmp, or /opt.
    """
    data = request.get_json(silent=True)
    if not data or not data.get("path"):
        return error_response(
            "BAD_REQUEST", "path is required in JSON body", HTTPStatus.BAD_REQUEST
        )

    raw_path = data["path"]
    # Expand ~ to home directory
    path_obj = Path(raw_path).expanduser()

    if not path_obj.is_absolute():
        return error_response("BAD_REQUEST", "Path must be absolute", HTTPStatus.BAD_REQUEST)

    # Resolve the *parent* that already exists to validate against allowed bases.
    # The target directory may not exist yet, so walk up to find an existing ancestor.
    try:
        # Resolve as much as possible — Path.resolve() works even for non-existent paths
        resolved = path_obj.resolve()
    except (OSError, ValueError):
        return error_response("BAD_REQUEST", "Invalid path", HTTPStatus.BAD_REQUEST)

    if not _is_path_allowed(resolved):
        return error_response(
            "FORBIDDEN",
            "Path must be under home directory, /tmp, or /opt",
            HTTPStatus.FORBIDDEN,
        )

    try:
        resolved.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        return error_response(
            "FORBIDDEN", "Permission denied when creating directory", HTTPStatus.FORBIDDEN
        )
    except OSError as exc:
        return error_response(
            "BAD_REQUEST", f"Cannot create directory: {exc}", HTTPStatus.BAD_REQUEST
        )

    return {"created": True, "path": str(resolved)}, HTTPStatus.CREATED
