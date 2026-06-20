"""Wave 61 — rules + plugins + hooks + commands. 36 routes total.

Mechanical CRUD migration. SSE /generate/stream routes use Litestar Stream.
plugin_exports deferred (subprocess + external API + sync watchers).
"""

from __future__ import annotations

from typing import Any, Optional

from litestar import MediaType, Router, delete, get, post, put
from litestar.exceptions import (
    ClientException,
    HTTPException,
    NotFoundException,
)
from litestar.response import Stream

from app.database import (
    add_plugin_component,
    count_commands,
    count_hooks,
    count_plugins,
    count_rules,
    delete_command,
    delete_hook,
    delete_plugin,
    delete_plugin_component,
    delete_rule,
    get_all_commands,
    get_all_hooks,
    get_all_plugins,
    get_all_rules,
    get_command,
    get_commands_by_project,
    get_hook,
    get_hooks_by_event,
    get_hooks_by_project,
    get_plugin,
    get_plugin_components,
    get_rule,
    get_rules_by_project,
    get_rules_by_type,
    update_command,
    update_hook,
    update_plugin,
    update_plugin_component,
    update_rule,
)
from app.database import create_command as db_create_command
from app.database import create_hook as db_create_hook
from app.database import create_plugin as db_create_plugin
from app.database import create_rule as db_create_rule
from app.db.owned_entities import get_for_user

from ..auth import Caller

VALID_RULE_TYPES = ["pre_check", "post_check", "validation"]
HOOK_EVENTS = ["PreToolUse", "PostToolUse", "Notification", "Stop", "SubagentStop"]


def _stream(generator) -> Stream:
    return Stream(
        generator,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ===========================================================================
# /admin/rules/* (10)
# ===========================================================================


@get("/", sync_to_thread=False)
def list_rules(
    caller: Caller,
    project_id: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> dict[str, Any]:
    if caller.user_id:
        rows = get_for_user("rules", caller.user_id, limit=limit, offset=offset or 0)
        return {"rules": rows, "total_count": len(rows)}
    return {
        "rules": get_all_rules(project_id, limit=limit, offset=offset or 0),
        "total_count": count_rules(project_id),
    }


@post("/", sync_to_thread=False)
def create_rule(data: dict, caller: Caller) -> dict[str, Any]:
    del caller
    if not data:
        raise ClientException(detail="JSON body required")
    rule_id = db_create_rule(
        name=data.get("name", ""),
        rule_type=data.get("rule_type", ""),
        description=data.get("description"),
        condition=data.get("condition"),
        action=data.get("action"),
        enabled=data.get("enabled", 1),
        project_id=data.get("project_id"),
        source_path=data.get("source_path"),
    )
    if not rule_id:
        raise HTTPException(status_code=500, detail="Failed to create rule")
    return {"message": "Rule created", "rule": get_rule(rule_id)}


@get("/types", sync_to_thread=False)
def list_rule_types(caller: Caller) -> dict[str, Any]:
    del caller
    return {"types": VALID_RULE_TYPES}


@get("/{rule_id:int}", sync_to_thread=False)
def get_rule_endpoint(rule_id: int, caller: Caller) -> dict[str, Any]:
    del caller
    rule = get_rule(rule_id)
    if not rule:
        raise NotFoundException(detail="Rule not found")
    return rule


@put("/{rule_id:int}", sync_to_thread=False)
def update_rule_endpoint(rule_id: int, data: dict, caller: Caller) -> dict[str, Any]:
    del caller
    if not update_rule(
        rule_id,
        name=data.get("name"),
        rule_type=data.get("rule_type"),
        description=data.get("description"),
        condition=data.get("condition"),
        action=data.get("action"),
        enabled=data.get("enabled"),
    ):
        raise NotFoundException(detail="Rule not found or no changes made")
    return get_rule(rule_id)


@delete("/{rule_id:int}", status_code=200, sync_to_thread=False)
def delete_rule_endpoint(rule_id: int, caller: Caller) -> dict[str, Any]:
    del caller
    if not delete_rule(rule_id):
        raise NotFoundException(detail="Rule not found")
    return {"message": "Rule deleted"}


@get("/project/{project_id:str}", sync_to_thread=False)
def list_project_rules(project_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    return {"rules": get_rules_by_project(project_id), "project_id": project_id}


@get("/type/{rule_type:str}", sync_to_thread=False)
def list_rules_by_type_endpoint(rule_type: str, caller: Caller) -> dict[str, Any]:
    del caller
    if rule_type not in VALID_RULE_TYPES:
        raise ClientException(
            detail=f"Invalid rule type. Must be one of: {', '.join(VALID_RULE_TYPES)}"
        )
    return {"rules": get_rules_by_type(rule_type), "rule_type": rule_type}


@get("/{rule_id:int}/export", sync_to_thread=False)
def export_rule(rule_id: int, caller: Caller) -> dict[str, Any]:
    del caller
    rule = get_rule(rule_id)
    if not rule:
        raise NotFoundException(detail="Rule not found")
    export_data = {
        "name": rule["name"],
        "rule_type": rule["rule_type"],
        "description": rule.get("description"),
        "condition": rule.get("condition"),
        "action": rule.get("action"),
        "enabled": bool(rule.get("enabled", 1)),
    }
    return {"rule": export_data, "format": "json"}


@post(
    "/generate/stream",
    media_type=MediaType.TEXT,
    sync_to_thread=False,
)
def generate_rule_stream(data: dict, caller: Caller) -> Stream:
    del caller
    from app.services.rule_generation_service import RuleGenerationService

    return _stream(RuleGenerationService.generate_streaming((data or {}).get("description", "")))


rules_router = Router(
    path="/admin/rules",
    route_handlers=[
        list_rules,
        create_rule,
        list_rule_types,
        get_rule_endpoint,
        update_rule_endpoint,
        delete_rule_endpoint,
        list_project_rules,
        list_rules_by_type_endpoint,
        export_rule,
        generate_rule_stream,
    ],
)


# ===========================================================================
# /admin/plugins/* (10)
# ===========================================================================


@get("/", sync_to_thread=False)
def list_plugins(
    caller: Caller,
    project_id: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> dict[str, Any]:
    if caller.user_id:
        rows = get_for_user("plugins", caller.user_id, limit=limit, offset=offset or 0)
        return {"plugins": rows, "total_count": len(rows)}
    del project_id  # original Flask version didn't filter by it either
    return {
        "plugins": get_all_plugins(limit=limit, offset=offset or 0),
        "total_count": count_plugins(),
    }


@post("/", sync_to_thread=False)
def create_plugin(data: dict, caller: Caller) -> dict[str, Any]:
    del caller
    if not data:
        raise ClientException(detail="JSON body required")
    plugin_id = db_create_plugin(
        name=data.get("name", ""),
        version=data.get("version", "1.0.0"),
        description=data.get("description"),
        author=data.get("author"),
        repository_url=data.get("repository_url"),
        config=data.get("config"),
        project_id=data.get("project_id"),
    )
    if not plugin_id:
        raise HTTPException(status_code=500, detail="Failed to create plugin")
    return {"message": "Plugin created", "plugin": get_plugin(plugin_id)}


@get("/{plugin_id:str}", sync_to_thread=False)
def get_plugin_endpoint(plugin_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    plugin = get_plugin(plugin_id)
    if not plugin:
        raise NotFoundException(detail="Plugin not found")
    return plugin


@put("/{plugin_id:str}", sync_to_thread=False)
def update_plugin_endpoint(plugin_id: str, data: dict, caller: Caller) -> dict[str, Any]:
    del caller
    if not update_plugin(
        plugin_id,
        name=data.get("name"),
        version=data.get("version"),
        description=data.get("description"),
        author=data.get("author"),
        repository_url=data.get("repository_url"),
        config=data.get("config"),
    ):
        raise NotFoundException(detail="Plugin not found or no changes")
    return get_plugin(plugin_id)


@delete("/{plugin_id:str}", status_code=200, sync_to_thread=False)
def delete_plugin_endpoint(plugin_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    if not delete_plugin(plugin_id):
        raise NotFoundException(detail="Plugin not found")
    return {"message": "Plugin deleted"}


@get("/{plugin_id:str}/components", sync_to_thread=False)
def list_components(plugin_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    components = get_plugin_components(plugin_id)
    return {"components": components, "total_count": len(components)}


@post("/{plugin_id:str}/components", sync_to_thread=False)
def create_component(plugin_id: str, data: dict, caller: Caller) -> dict[str, Any]:
    del caller
    if not data:
        raise ClientException(detail="JSON body required")
    cid = add_plugin_component(
        plugin_id=plugin_id,
        component_type=data.get("component_type", ""),
        name=data.get("name", ""),
        config=data.get("config"),
        enabled=data.get("enabled", 1),
    )
    if not cid:
        raise HTTPException(status_code=500, detail="Failed to create component")
    return {"message": "Component added", "id": cid}


@put("/{plugin_id:str}/components/{component_id:int}", sync_to_thread=False)
def update_component(
    plugin_id: str, component_id: int, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller, plugin_id
    if not update_plugin_component(
        component_id,
        component_type=data.get("component_type"),
        name=data.get("name"),
        config=data.get("config"),
        enabled=data.get("enabled"),
    ):
        raise NotFoundException(detail="Component not found")
    return {"message": "Component updated"}


@delete(
    "/{plugin_id:str}/components/{component_id:int}",
    status_code=200,
    sync_to_thread=False,
)
def delete_component(plugin_id: str, component_id: int, caller: Caller) -> dict[str, Any]:
    del caller, plugin_id
    if not delete_plugin_component(component_id):
        raise NotFoundException(detail="Component not found")
    return {"message": "Component deleted"}


@post(
    "/generate/stream",
    media_type=MediaType.TEXT,
    sync_to_thread=False,
)
def generate_plugin_stream(data: dict, caller: Caller) -> Stream:
    del caller
    from app.services.plugin_generation_service import PluginGenerationService

    return _stream(PluginGenerationService.generate_streaming((data or {}).get("description", "")))


# PR-J3b: PluginSandboxPage.vue calls /admin/plugins/sandbox/{run,runs} and
# neither has a real handler. The view ships a "Not yet enabled" banner in
# PR-J3; these handlers return 501 instead of 404 so the contract is explicit.
@get("/sandbox/runs", sync_to_thread=False)
def list_plugin_sandbox_runs() -> dict[str, Any]:
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


@post("/sandbox/run", sync_to_thread=False)
def run_plugin_sandbox(data: dict) -> dict[str, Any]:
    del data
    raise HTTPException(status_code=501, detail="Feature not yet enabled")


plugins_router = Router(
    path="/admin/plugins",
    route_handlers=[
        list_plugins,
        create_plugin,
        get_plugin_endpoint,
        update_plugin_endpoint,
        delete_plugin_endpoint,
        list_components,
        create_component,
        update_component,
        delete_component,
        generate_plugin_stream,
        list_plugin_sandbox_runs,
        run_plugin_sandbox,
    ],
)


# ===========================================================================
# /admin/hooks/* (9)
# ===========================================================================


@get("/", sync_to_thread=False)
def list_hooks(
    caller: Caller,
    project_id: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> dict[str, Any]:
    if caller.user_id:
        rows = get_for_user("hooks", caller.user_id, limit=limit, offset=offset or 0)
        return {"hooks": rows, "total_count": len(rows)}
    return {
        "hooks": get_all_hooks(project_id, limit=limit, offset=offset or 0),
        "total_count": count_hooks(project_id),
    }


@post("/", sync_to_thread=False)
def create_hook(data: dict, caller: Caller) -> dict[str, Any]:
    del caller
    if not data:
        raise ClientException(detail="JSON body required")
    hook_id = db_create_hook(
        name=data.get("name", ""),
        event=data.get("event", ""),
        description=data.get("description"),
        content=data.get("content"),
        enabled=data.get("enabled", 1),
        project_id=data.get("project_id"),
        source_path=data.get("source_path"),
    )
    if not hook_id:
        raise HTTPException(status_code=500, detail="Failed to create hook")
    return {"message": "Hook created", "hook": get_hook(hook_id)}


@get("/events", sync_to_thread=False)
def list_hook_events(caller: Caller) -> dict[str, Any]:
    del caller
    return {"events": HOOK_EVENTS}


@get("/{hook_id:int}", sync_to_thread=False)
def get_hook_endpoint(hook_id: int, caller: Caller) -> dict[str, Any]:
    del caller
    hook = get_hook(hook_id)
    if not hook:
        raise NotFoundException(detail="Hook not found")
    return hook


@put("/{hook_id:int}", sync_to_thread=False)
def update_hook_endpoint(hook_id: int, data: dict, caller: Caller) -> dict[str, Any]:
    del caller
    if not update_hook(
        hook_id,
        name=data.get("name"),
        event=data.get("event"),
        description=data.get("description"),
        content=data.get("content"),
        enabled=data.get("enabled"),
    ):
        raise NotFoundException(detail="Hook not found or no changes")
    return get_hook(hook_id)


@delete("/{hook_id:int}", status_code=200, sync_to_thread=False)
def delete_hook_endpoint(hook_id: int, caller: Caller) -> dict[str, Any]:
    del caller
    if not delete_hook(hook_id):
        raise NotFoundException(detail="Hook not found")
    return {"message": "Hook deleted"}


@get("/project/{project_id:str}", sync_to_thread=False)
def list_project_hooks(project_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    return {"hooks": get_hooks_by_project(project_id), "project_id": project_id}


@get("/event/{event:str}", sync_to_thread=False)
def list_hooks_by_event(event: str, caller: Caller) -> dict[str, Any]:
    del caller
    return {"hooks": get_hooks_by_event(event), "event": event}


@post(
    "/generate/stream",
    media_type=MediaType.TEXT,
    sync_to_thread=False,
)
def generate_hook_stream(data: dict, caller: Caller) -> Stream:
    del caller
    from app.services.hook_generation_service import HookGenerationService

    return _stream(HookGenerationService.generate_streaming((data or {}).get("description", "")))


hooks_router = Router(
    path="/admin/hooks",
    route_handlers=[
        list_hooks,
        create_hook,
        list_hook_events,
        get_hook_endpoint,
        update_hook_endpoint,
        delete_hook_endpoint,
        list_project_hooks,
        list_hooks_by_event,
        generate_hook_stream,
    ],
)


# ===========================================================================
# /admin/commands/* (7)
# ===========================================================================


@get("/", sync_to_thread=False)
def list_commands(
    caller: Caller,
    project_id: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> dict[str, Any]:
    if caller.user_id:
        rows = get_for_user("commands", caller.user_id, limit=limit, offset=offset or 0)
        return {"commands": rows, "total_count": len(rows)}
    return {
        "commands": get_all_commands(project_id, limit=limit, offset=offset or 0),
        "total_count": count_commands(project_id),
    }


@post("/", sync_to_thread=False)
def create_command(data: dict, caller: Caller) -> dict[str, Any]:
    del caller
    if not data:
        raise ClientException(detail="JSON body required")
    command_id = db_create_command(
        name=data.get("name", ""),
        description=data.get("description"),
        content=data.get("content"),
        arguments=data.get("arguments"),
        enabled=data.get("enabled", 1),
        project_id=data.get("project_id"),
        source_path=data.get("source_path"),
    )
    if not command_id:
        raise HTTPException(status_code=500, detail="Failed to create command")
    return {"message": "Command created", "command": get_command(command_id)}


@get("/{command_id:int}", sync_to_thread=False)
def get_command_endpoint(command_id: int, caller: Caller) -> dict[str, Any]:
    del caller
    command = get_command(command_id)
    if not command:
        raise NotFoundException(detail="Command not found")
    return command


@put("/{command_id:int}", sync_to_thread=False)
def update_command_endpoint(command_id: int, data: dict, caller: Caller) -> dict[str, Any]:
    del caller
    if not update_command(
        command_id,
        name=data.get("name"),
        description=data.get("description"),
        content=data.get("content"),
        arguments=data.get("arguments"),
        enabled=data.get("enabled"),
    ):
        raise NotFoundException(detail="Command not found or no changes")
    return get_command(command_id)


@delete("/{command_id:int}", status_code=200, sync_to_thread=False)
def delete_command_endpoint(command_id: int, caller: Caller) -> dict[str, Any]:
    del caller
    if not delete_command(command_id):
        raise NotFoundException(detail="Command not found")
    return {"message": "Command deleted"}


@get("/project/{project_id:str}", sync_to_thread=False)
def list_project_commands(project_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    return {
        "commands": get_commands_by_project(project_id),
        "project_id": project_id,
    }


@post(
    "/generate/stream",
    media_type=MediaType.TEXT,
    sync_to_thread=False,
)
def generate_command_stream(data: dict, caller: Caller) -> Stream:
    del caller
    from app.services.command_generation_service import CommandGenerationService

    return _stream(CommandGenerationService.generate_streaming((data or {}).get("description", "")))


commands_router = Router(
    path="/admin/commands",
    route_handlers=[
        list_commands,
        create_command,
        get_command_endpoint,
        update_command_endpoint,
        delete_command_endpoint,
        list_project_commands,
        generate_command_stream,
    ],
)
