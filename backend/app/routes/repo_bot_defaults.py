"""Repo-bot-defaults API: pivot triggers to a per-repo binding view."""

import re
from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response

from ..db.triggers import (
    add_github_repo,
    get_all_triggers,
    list_paths_for_trigger,
    remove_github_repo,
    update_trigger,
)

tag = Tag(name="repo-bot-defaults", description="Per-repository default bot bindings")
repo_bot_defaults_bp = APIBlueprint(
    "repo_bot_defaults", __name__, url_prefix="/admin/repo-bot-defaults", abp_tags=[tag]
)


def _slug_to_repo(slug: str) -> str:
    """Convert URL-safe slug (owner__repo) back to owner/repo."""
    return slug.replace("__", "/", 1)


def _repo_to_slug(repo: str) -> str:
    """Convert owner/repo to URL-safe slug (owner__repo)."""
    return repo.replace("/", "__", 1)


def _build_bindings(triggers: list) -> list:
    """Pivot triggers into per-repo binding records."""
    # repo -> {bots: set, paths: list, triggers: list}
    repo_map: dict = {}

    for trigger in triggers:
        paths = list_paths_for_trigger(trigger["id"])
        github_paths = [
            p for p in paths if p.get("path_type") == "github" and p.get("github_repo_url")
        ]
        for path in github_paths:
            repo_url = path["github_repo_url"].rstrip("/")
            # Normalise to owner/repo
            match = re.match(r"https?://[^/]+/(.+)", repo_url)
            repo = match.group(1) if match else repo_url

            if repo not in repo_map:
                repo_map[repo] = {"bots": set(), "project_count": 0, "enabled": trigger["enabled"]}
            repo_map[repo]["bots"].add(trigger["id"])
            # enabled = True only if ALL bound triggers are enabled
            if not trigger["enabled"]:
                repo_map[repo]["enabled"] = False

    bindings = []
    for repo, data in repo_map.items():
        bindings.append(
            {
                "repo": repo,
                "bots": sorted(data["bots"]),
                "projectCount": data["project_count"],
                "enabled": bool(data["enabled"]),
            }
        )
    return bindings


def _available_bots(triggers: list) -> list:
    """Return list of available bots from all triggers."""
    TYPE_MAP = {
        "github": "review",
        "webhook": "security",
        "scheduled": "security",
        "manual": "docs",
    }
    bots = []
    for t in triggers:
        bots.append(
            {
                "id": t["id"],
                "name": t["name"],
                "type": TYPE_MAP.get(t.get("trigger_source", ""), "review"),
            }
        )
    return bots


class RepoSlugPath(BaseModel):
    repo_slug: str = Field(..., description="owner__repo slug")


@repo_bot_defaults_bp.get("/")
def list_repo_bot_defaults():
    """List all repo-bot bindings pivoted from trigger project_paths."""
    triggers = get_all_triggers()
    bindings = _build_bindings(triggers)
    bots = _available_bots(triggers)
    return {"bindings": bindings, "bots": bots}, HTTPStatus.OK


@repo_bot_defaults_bp.post("/")
def create_repo_bot_default():
    """Bind one or more bots to a GitHub repository."""
    data = request.get_json()
    if not data:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    repo = (data.get("repo") or "").strip()
    bot_ids = data.get("bot_ids") or []

    if not repo:
        return error_response("BAD_REQUEST", "repo is required", HTTPStatus.BAD_REQUEST)
    if not bot_ids:
        return error_response(
            "BAD_REQUEST", "bot_ids must be a non-empty list", HTTPStatus.BAD_REQUEST
        )

    # Normalise to full GitHub URL
    if not repo.startswith("http"):
        github_repo_url = f"https://github.com/{repo}"
    else:
        github_repo_url = repo

    triggers = get_all_triggers()
    trigger_map = {t["id"]: t for t in triggers}
    added = []
    errors = []
    for bot_id in bot_ids:
        if bot_id not in trigger_map:
            errors.append(f"Bot {bot_id} not found")
            continue
        ok = add_github_repo(bot_id, github_repo_url)
        if ok:
            added.append(bot_id)
        # Duplicate (IntegrityError) silently ignored — already bound

    return {
        "repo": repo,
        "bound_bots": added,
        "errors": errors,
    }, HTTPStatus.CREATED


@repo_bot_defaults_bp.put("/<repo_slug>")
def toggle_repo_bot_default(path: RepoSlugPath):
    """Enable or disable all trigger bindings for a repository."""
    data = request.get_json()
    if data is None:
        return error_response("BAD_REQUEST", "JSON body required", HTTPStatus.BAD_REQUEST)

    enabled = data.get("enabled")
    if not isinstance(enabled, bool):
        return error_response("BAD_REQUEST", "enabled (bool) is required", HTTPStatus.BAD_REQUEST)

    repo = _slug_to_repo(path.repo_slug)
    if not repo.startswith("http"):
        github_repo_url_prefix = f"https://github.com/{repo}"
    else:
        github_repo_url_prefix = repo

    triggers = get_all_triggers()
    updated = []
    for trigger in triggers:
        paths = list_paths_for_trigger(trigger["id"])
        for p in paths:
            purl = (p.get("github_repo_url") or "").rstrip("/")
            if purl == github_repo_url_prefix.rstrip("/"):
                update_trigger(trigger["id"], enabled=int(enabled))
                updated.append(trigger["id"])
                break

    if not updated:
        return error_response(
            "NOT_FOUND", f"No bindings found for repo {repo}", HTTPStatus.NOT_FOUND
        )

    return {"repo": repo, "enabled": enabled, "updated_triggers": updated}, HTTPStatus.OK


@repo_bot_defaults_bp.delete("/<repo_slug>")
def delete_repo_bot_default(path: RepoSlugPath):
    """Remove all trigger bindings for a GitHub repository."""
    repo = _slug_to_repo(path.repo_slug)
    if not repo.startswith("http"):
        github_repo_url = f"https://github.com/{repo}"
    else:
        github_repo_url = repo

    triggers = get_all_triggers()
    removed = []
    for trigger in triggers:
        ok = remove_github_repo(trigger["id"], github_repo_url)
        if ok:
            removed.append(trigger["id"])

    if not removed:
        return error_response(
            "NOT_FOUND", f"No bindings found for repo {repo}", HTTPStatus.NOT_FOUND
        )

    return {"repo": repo, "removed_triggers": removed}, HTTPStatus.OK
