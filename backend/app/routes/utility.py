"""Utility API endpoints."""

import shutil
import subprocess
import threading
from http import HTTPStatus
from pathlib import Path

from flask import request
from flask_openapi3 import APIBlueprint, Tag

from app.config import PROJECT_ROOT

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
        return {"version": "unknown"}, HTTPStatus.OK


@utility_bp.get("/check-backend")
def check_backend():
    """Check if a CLI backend (claude/opencode) is installed and runnable."""
    backend_name = request.args.get("name", "").lower()

    if backend_name not in ("claude", "opencode"):
        return {"error": "Invalid backend. Use 'claude' or 'opencode'"}, HTTPStatus.BAD_REQUEST

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
        return {"error": "Path parameter required"}, HTTPStatus.BAD_REQUEST

    path_obj = Path(path)
    try:
        resolved = path_obj.resolve()
    except (OSError, ValueError):
        return {"error": "Invalid path"}, HTTPStatus.BAD_REQUEST

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
        return {"error": "url parameter required"}, HTTPStatus.BAD_REQUEST

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
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    audit_summary = data.get("audit_summary", "")
    project_paths = data.get("project_paths", [])

    if not audit_summary:
        return {"error": "audit_summary required"}, HTTPStatus.BAD_REQUEST
    if not project_paths:
        return {"error": "project_paths required"}, HTTPStatus.BAD_REQUEST

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
            return {"error": "Trigger not found"}, HTTPStatus.NOT_FOUND
        scan_paths = get_paths_for_trigger(trigger_id)
    elif paths_param:
        scan_paths = [p.strip() for p in paths_param.split(",") if p.strip()]

    # Always include the project root as a scan path
    if PROJECT_ROOT not in scan_paths:
        scan_paths.append(PROJECT_ROOT)

    skills = SkillDiscoveryService.discover_cli_skills(scan_paths)
    return {"skills": skills}, HTTPStatus.OK
