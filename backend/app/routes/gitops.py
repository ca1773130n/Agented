"""GitOps management endpoints for repository sync configuration."""

from http import HTTPStatus

from flask_openapi3 import APIBlueprint, Tag

from app.models.common import error_response

from ..db.gitops import (
    create_gitops_repo,
    delete_gitops_repo,
    get_gitops_repo,
    list_gitops_repos,
    list_sync_logs,
    update_gitops_repo,
)
from ..models.gitops import (
    GitOpsRepoCreate,
    GitOpsRepoPath,
    GitOpsRepoUpdate,
    GitOpsSyncLogQuery,
    GitOpsSyncQuery,
)
from ..services.gitops_sync_service import GitOpsSyncService

tag = Tag(name="gitops", description="GitOps repository sync management")
gitops_bp = APIBlueprint("gitops", __name__, url_prefix="/admin", abp_tags=[tag])


@gitops_bp.post("/gitops/repos")
def create_repo(body: GitOpsRepoCreate):
    """Create a new GitOps watched repository configuration."""
    repo_id = create_gitops_repo(
        name=body.name,
        repo_url=body.repo_url,
        branch=body.branch,
        config_path=body.config_path,
        poll_interval=body.poll_interval_seconds,
    )
    repo = get_gitops_repo(repo_id)
    return repo, HTTPStatus.CREATED


@gitops_bp.get("/gitops/repos")
def list_repos():
    """List all configured GitOps repositories."""
    repos = list_gitops_repos()
    return repos


@gitops_bp.get("/gitops/repos/<repo_id>")
def get_repo(path: GitOpsRepoPath):
    """Get GitOps repository detail with last sync info."""
    repo = get_gitops_repo(path.repo_id)
    if not repo:
        return error_response("NOT_FOUND", "GitOps repo not found", HTTPStatus.NOT_FOUND)
    return repo


@gitops_bp.put("/gitops/repos/<repo_id>")
def update_repo(path: GitOpsRepoPath, body: GitOpsRepoUpdate):
    """Update GitOps repository configuration."""
    updates = body.model_dump(exclude_none=True)
    if "enabled" in updates:
        updates["enabled"] = 1 if updates["enabled"] else 0

    if not updates:
        return error_response("BAD_REQUEST", "No fields to update", HTTPStatus.BAD_REQUEST)

    found = update_gitops_repo(path.repo_id, **updates)
    if not found:
        return error_response("NOT_FOUND", "GitOps repo not found", HTTPStatus.NOT_FOUND)

    repo = get_gitops_repo(path.repo_id)
    return repo


@gitops_bp.delete("/gitops/repos/<repo_id>")
def delete_repo(path: GitOpsRepoPath):
    """Remove a watched GitOps repository."""
    found = delete_gitops_repo(path.repo_id)
    if not found:
        return error_response("NOT_FOUND", "GitOps repo not found", HTTPStatus.NOT_FOUND)
    return {"message": "GitOps repo deleted"}, HTTPStatus.OK


@gitops_bp.post("/gitops/repos/<repo_id>/sync")
def trigger_sync(path: GitOpsRepoPath, query: GitOpsSyncQuery):
    """Trigger manual sync for a GitOps repository.

    Use ?dry_run=true to preview changes without applying.
    """
    repo = get_gitops_repo(path.repo_id)
    if not repo:
        return error_response("NOT_FOUND", "GitOps repo not found", HTTPStatus.NOT_FOUND)

    try:
        result = GitOpsSyncService.sync_repo(path.repo_id, dry_run=bool(query.dry_run))
    except ValueError as e:
        return error_response("BAD_REQUEST", str(e), HTTPStatus.BAD_REQUEST)

    return result


@gitops_bp.get("/gitops/repos/<repo_id>/logs")
def get_sync_logs(path: GitOpsRepoPath, query: GitOpsSyncLogQuery):
    """List sync history for a GitOps repository."""
    repo = get_gitops_repo(path.repo_id)
    if not repo:
        return error_response("NOT_FOUND", "GitOps repo not found", HTTPStatus.NOT_FOUND)

    logs = list_sync_logs(path.repo_id, limit=query.limit or 20)
    return logs
