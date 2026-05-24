"""Bot template marketplace routes (track A, wave 50)."""

from __future__ import annotations

import json
from typing import Any

from litestar import Router, get, post
from litestar.exceptions import HTTPException, NotFoundException

from app.db.bot_templates import deploy_template, get_all_templates, get_template

from ..auth import Caller, require_role


@get(
    "/",
    dependencies={"authorized": require_role("viewer", "operator", "editor", "admin")},
    sync_to_thread=False,
)
def list_templates(authorized: Caller) -> dict[str, Any]:
    del authorized
    return {"templates": get_all_templates()}


@get(
    "/{template_id:str}",
    dependencies={"authorized": require_role("viewer", "operator", "editor", "admin")},
    sync_to_thread=False,
)
def get_template_detail(template_id: str, authorized: Caller) -> dict[str, Any]:
    del authorized
    template = get_template(template_id)
    if not template:
        raise NotFoundException(detail="Template not found")
    return template


@post(
    "/{template_id:str}/deploy",
    dependencies={"authorized": require_role("editor", "admin")},
    sync_to_thread=False,
)
def deploy_template_endpoint(template_id: str, authorized: Caller) -> dict[str, Any]:
    del authorized
    template = get_template(template_id)
    if not template:
        raise NotFoundException(detail="Template not found")

    trigger_id = deploy_template(template_id)
    if not trigger_id:
        raise NotFoundException(detail="Failed to deploy template")

    try:
        config = json.loads(template["config_json"])
        trigger_name = config.get("name", template["name"])
    except (json.JSONDecodeError, TypeError):
        trigger_name = template["name"]

    from app.db.triggers import get_trigger

    trigger = get_trigger(trigger_id)
    if trigger:
        trigger_name = trigger["name"]

    return {
        "trigger_id": trigger_id,
        "template_id": template_id,
        "trigger_name": trigger_name,
        "message": f"Template '{template['name']}' deployed as trigger '{trigger_name}'",
    }


bot_templates_router = Router(
    path="/admin/bot-templates",
    route_handlers=[list_templates, get_template_detail, deploy_template_endpoint],
)


# ===========================================================================
# PR-J3b: specialized-bot config stubs (CodeExplanation, CrossRepoImpact,
# TestCoverage). The respective views ship a "Not yet enabled" banner in PR-J3;
# these handlers return 501 instead of 404 so the frontend sees a consistent
# error contract.
# ===========================================================================


@get("/code-explanations", sync_to_thread=False)
def list_code_explanations() -> dict[str, Any]:
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


@post("/code-explanations", sync_to_thread=False)
def create_code_explanation(data: dict) -> dict[str, Any]:
    del data
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


@get("/cross-repo-impact", sync_to_thread=False)
def list_cross_repo_impact() -> dict[str, Any]:
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


@post("/cross-repo-impact", sync_to_thread=False)
def create_cross_repo_impact(data: dict) -> dict[str, Any]:
    del data
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


@get("/test-coverage/config", sync_to_thread=False)
def get_test_coverage_config() -> dict[str, Any]:
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


@post("/test-coverage/config", sync_to_thread=False)
def set_test_coverage_config(data: dict) -> dict[str, Any]:
    del data
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


bot_stubs_router = Router(
    path="/admin/bots",
    route_handlers=[
        list_code_explanations,
        create_code_explanation,
        list_cross_repo_impact,
        create_cross_repo_impact,
        get_test_coverage_config,
        set_test_coverage_config,
    ],
)
