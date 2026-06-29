"""Wave 71 — leaf CRUD batch G (~23 routes).

sketches + agent_conversations (sans SSE) + plugin_exports.

The /api/agents/conversations/{id}/stream SSE endpoint stays on Flask until
the dedicated streaming wave so we can lift the Litestar `Stream` pattern
across all conversation endpoints in one pass.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from litestar import Router, delete, get, post, put
from litestar.exceptions import (
    ClientException,
    HTTPException,
    NotFoundException,
)
from litestar.response import Stream

from app.database import get_plugin_exports_for_plugin
from app.db.plugins import count_plugin_exports_for_plugin
from app.db.sketches import (
    count_sketches,
    delete_sketch,
    get_all_sketches,
    get_sketch,
    update_sketch,
)
from app.db.sketches import create_sketch as db_create_sketch
from app.services.agent_conversation_service import AgentConversationService
from app.services.sketch_execution_service import execute_sketch, find_team_super_agent
from app_litestar.auth import Caller
from app_litestar.list_scope import admin_or_scoped

logger = logging.getLogger(__name__)

# 07.M4 — bound sketch content length.
_CONTENT_MAX_LEN = 100_000

# 07.L3 — replicate the browse_directory path allowlist (leaf_crud_h._ALLOWED_BASES
# is module-private) so plugin import/sync can't read/write arbitrary host paths.
_ALLOWED_BASES = [Path.home(), Path("/tmp"), Path("/opt")]


def _ensure_path_allowed(raw_path: str) -> str:
    """Resolve *raw_path* and confirm it lives under an allowed base, else 400/403."""
    try:
        resolved = Path(raw_path).expanduser().resolve()
    except (OSError, ValueError) as e:
        raise ClientException(detail="Invalid path") from e
    resolved_str = str(resolved)
    if not any(
        resolved_str == str(base) or resolved_str.startswith(str(base) + os.sep)
        for base in _ALLOWED_BASES
    ):
        raise HTTPException(
            status_code=403,
            detail="Path must be under home directory, /tmp, or /opt",
        )
    return resolved_str


def _result_or_raise(payload: tuple[Any, int]) -> Any:
    body, status = payload
    if status >= 400:
        if status == 404:
            raise NotFoundException(
                detail=str(body.get("error") if isinstance(body, dict) else body)
            )
        raise HTTPException(
            status_code=status,
            detail=str(body.get("error") if isinstance(body, dict) else body),
        )
    return body


# ===========================================================================
# /admin/sketches/* (8)
# ===========================================================================


@get("/", sync_to_thread=False)
def list_sketches(
    caller: Caller,
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    project_id: Optional[str] = None,
) -> dict[str, Any]:
    return admin_or_scoped(
        caller,
        "sketches",
        "sketches",
        limit=limit,
        offset=offset,
        all_=lambda: {
            "sketches": get_all_sketches(
                status=status, project_id=project_id, limit=limit, offset=offset
            ),
            "total_count": count_sketches(status=status, project_id=project_id),
        },
    )


@post("/", status_code=201, sync_to_thread=False)
def create_sketch(data: dict) -> dict[str, Any]:
    if not data:
        raise ClientException(detail="JSON body required")
    title = (data.get("title") or "").strip()
    if not title:
        raise ClientException(detail="title is required")
    if len(title) > 255:  # 07.M4 — bound title length
        raise ClientException(detail="title must be at most 255 characters")
    content = data.get("content", "") or ""
    if len(content) > _CONTENT_MAX_LEN:  # 07.M4 — bound content length
        raise ClientException(detail=f"content must be at most {_CONTENT_MAX_LEN} characters")
    sketch_id = db_create_sketch(
        title=title,
        content=content,
        project_id=data.get("project_id"),
    )
    if not sketch_id:
        raise HTTPException(status_code=500, detail="Failed to create sketch")
    return {"message": "Sketch created", "sketch_id": sketch_id}


@get("/{sketch_id:str}", sync_to_thread=False)
def get_sketch_endpoint(sketch_id: str) -> Any:
    sketch = get_sketch(sketch_id)
    if not sketch:
        raise NotFoundException(detail="Sketch not found")
    return sketch


@put("/{sketch_id:str}", sync_to_thread=False)
def update_sketch_endpoint(sketch_id: str, data: dict) -> dict[str, Any]:
    body = {k: v for k, v in (data or {}).items() if v is not None}
    if not update_sketch(sketch_id, **body):
        raise NotFoundException(detail="Sketch not found or no changes made")
    return {"message": "Sketch updated"}


@delete("/{sketch_id:str}", status_code=200, sync_to_thread=False)
def delete_sketch_endpoint(sketch_id: str) -> dict[str, Any]:
    if not delete_sketch(sketch_id):
        raise NotFoundException(detail="Sketch not found")
    return {"message": "Sketch deleted"}


@post("/{sketch_id:str}/classify", sync_to_thread=False)
def classify_sketch(sketch_id: str) -> dict[str, Any]:
    sketch = get_sketch(sketch_id)
    if not sketch:
        raise NotFoundException(detail="Sketch not found")
    from app.services.sketch_routing_service import SketchRoutingService

    classification = SketchRoutingService.classify(sketch)
    update_sketch(sketch_id, classification_json=json.dumps(classification), status="classified")
    return {"message": "Sketch classified", "classification": classification}


@post("/{sketch_id:str}/route", sync_to_thread=False)
def route_sketch(sketch_id: str, data: Optional[dict] = None) -> dict[str, Any]:
    """Route a classified sketch to its target super agent / team and start
    execution.

    The optional request body accepts ``use_cli_agent`` (bool) to override
    the global ``agent_yolo_mode`` setting for this run only — the
    AiChatPanel toggle plumbs this through. ``True`` forces the CLI
    agent runner; ``False`` forces the legacy CLIProxy path; absent
    defers to the global setting.
    """
    sketch = get_sketch(sketch_id)
    if not sketch:
        raise NotFoundException(detail="Sketch not found")
    classification_raw = sketch.get("classification_json")
    if not classification_raw:
        raise ClientException(detail="Sketch must be classified first")
    classification = (
        json.loads(classification_raw)
        if isinstance(classification_raw, str)
        else classification_raw
    )

    from app.services.sketch_routing_service import SketchRoutingService

    routing = SketchRoutingService.route(classification, project_id=sketch.get("project_id"))
    super_agent_id = None
    if routing["target_type"] == "super_agent":
        super_agent_id = routing["target_id"]
    elif routing["target_type"] == "team":
        super_agent_id = find_team_super_agent(routing["target_id"])

    if not super_agent_id:
        update_sketch(sketch_id, status="routed", routing_json=json.dumps(routing))
        return {"routing": routing}

    team_id = routing["target_id"] if routing["target_type"] == "team" else None
    use_cli_agent: Optional[bool] = None
    if isinstance(data, dict) and "use_cli_agent" in data:
        raw = data.get("use_cli_agent")
        if isinstance(raw, bool):
            use_cli_agent = raw
    session_id = execute_sketch(
        sketch_id,
        super_agent_id,
        sketch["content"],
        team_id=team_id,
        use_cli_agent=use_cli_agent,
    )
    routing["session_id"] = session_id
    routing["super_agent_id"] = super_agent_id
    update_sketch(sketch_id, routing_json=json.dumps(routing))
    return {"routing": routing, "session_id": session_id, "super_agent_id": super_agent_id}


@post("/ideate", media_type="text/event-stream")
async def ideate_sketch(data: dict) -> Stream:
    """Stream one grounded ideation turn (the Sketch 'thinking partner').

    Body: ``{"messages": [{role, content}...], "backend"?: str}``. The frontend
    holds the conversation and sends the full history each turn; this replies via
    a GENERAL model grounded with FEDERATED Tesserae knowledge (all projects) and
    does NOT route or execute. Emits SSE frames: ``retrieval`` (provenance) →
    ``content`` chunks → ``done`` (or ``error``).

    The ideation generator is synchronous and does blocking work (the federated
    subprocess + the LLM stream), so each step is offloaded to a thread — never
    blocking the event loop.
    """
    from anyio.to_thread import run_sync

    from app.services.sketch_ideation_service import sse_lines

    body = data or {}
    raw = body.get("messages")
    if not isinstance(raw, list):
        raise ClientException(detail="messages must be a list")
    # Normalize + bound: keep the last 40 user/assistant turns, cap each at 20k
    # chars, drop anything malformed — never forward unbounded/garbage to the
    # subprocess + LLM.
    messages: list[dict] = []
    for m in raw[-40:]:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = m.get("content")
        if role in ("user", "assistant") and isinstance(content, str):
            messages.append({"role": role, "content": content[:20_000]})
    if not messages:
        raise ClientException(detail="messages must contain at least one user/assistant turn")
    backend = body.get("backend")
    if backend not in ("gemini", "claude", "codex", "opencode"):
        backend = None  # service defaults to the general (gemini) backend

    async def event_generator():
        gen = sse_lines(messages, backend=backend)
        while True:
            frame = await run_sync(next, gen, None)
            if frame is None:
                return
            yield frame

    return Stream(event_generator(), media_type="text/event-stream")


@get("/{sketch_id:str}/delegations", sync_to_thread=False)
def sketch_delegations(sketch_id: str) -> dict[str, Any]:
    sketch = get_sketch(sketch_id)
    if not sketch:
        raise NotFoundException(detail="Sketch not found")
    routing = json.loads(sketch.get("routing_json") or "{}")
    return {"delegations": routing.get("delegations", [])}


sketches_router = Router(
    path="/admin/sketches",
    route_handlers=[
        list_sketches,
        create_sketch,
        get_sketch_endpoint,
        update_sketch_endpoint,
        delete_sketch_endpoint,
        classify_sketch,
        route_sketch,
        ideate_sketch,
        sketch_delegations,
    ],
)


# ===========================================================================
# /api/agents/conversations/* (5; SSE deferred)
# ===========================================================================


def _agent_caller_user_id(caller: Caller | None) -> Optional[str]:
    """v0.7.83 — local accessor mirroring the conversation_cluster
    helper. None means bootstrap mode.
    """
    return getattr(caller, "user_id", None) if caller else None


@post("/start", sync_to_thread=False)
def start_conversation(caller: Caller) -> Any:
    return _result_or_raise(
        AgentConversationService.start_conversation(user_id=_agent_caller_user_id(caller))
    )


@get("/{conv_id:str}", sync_to_thread=False)
def get_conversation(conv_id: str, caller: Caller) -> Any:
    return _result_or_raise(
        AgentConversationService.get_conversation(
            conv_id, caller_user_id=_agent_caller_user_id(caller)
        )
    )


@post("/{conv_id:str}/message", sync_to_thread=False)
def send_message(conv_id: str, data: dict, caller: Caller) -> Any:
    body = data or {}
    if not body.get("message"):
        raise ClientException(detail="message is required")
    return _result_or_raise(
        AgentConversationService.send_message(
            conv_id,
            body["message"],
            backend=body.get("backend"),
            account_id=body.get("account_id"),
            model=body.get("model"),
            caller_user_id=_agent_caller_user_id(caller),
        )
    )


@post("/{conv_id:str}/finalize", sync_to_thread=False)
def finalize_agent(conv_id: str, caller: Caller) -> Any:
    return _result_or_raise(
        AgentConversationService.finalize_agent(
            conv_id, caller_user_id=_agent_caller_user_id(caller)
        )
    )


@post("/{conv_id:str}/abandon", sync_to_thread=False)
def abandon_conversation(conv_id: str, caller: Caller) -> Any:
    return _result_or_raise(
        AgentConversationService.abandon_conversation(
            conv_id, caller_user_id=_agent_caller_user_id(caller)
        )
    )


@get("/active", sync_to_thread=False)
def list_active_agent_conversations(caller: Caller) -> Any:
    """v0.7.83 — list the operator's active agent conversations
    so /agents/new can auto-resume on cold-cache loads.
    """
    return _result_or_raise(
        AgentConversationService.list_active(user_id=_agent_caller_user_id(caller))
    )


agent_conversations_router = Router(
    path="/api/agents/conversations",
    route_handlers=[
        start_conversation,
        get_conversation,
        send_message,
        finalize_agent,
        abandon_conversation,
        list_active_agent_conversations,
    ],
)


# ===========================================================================
# /admin/plugin-exports/* (10)
# ===========================================================================


@post("/export", sync_to_thread=False)
def export_plugin(data: dict) -> dict[str, Any]:
    from app.services.plugin_export_service import ExportService

    if not data:
        raise ClientException(detail="JSON body required")
    team_id = data.get("team_id")
    if not team_id:
        raise ClientException(detail="team_id is required")
    export_format = data.get("export_format")
    if export_format not in ("claude", "agented"):
        raise ClientException(detail="export_format must be 'claude' or 'agented'")
    output_dir = data.get("output_dir") or tempfile.mkdtemp(prefix="agented-export-")
    try:
        if export_format == "claude":
            result = ExportService.export_as_claude_plugin(team_id=team_id, output_dir=output_dir)
        else:
            result = ExportService.export_as_agented_package(team_id=team_id, output_dir=output_dir)
    except ValueError as e:
        raise NotFoundException(detail=str(e)) from e
    except Exception as e:  # 07.L1 — log internals, return a generic message
        logger.error("Plugin export failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Export failed") from e
    result["format"] = export_format
    return result


@post("/import", status_code=201, sync_to_thread=False)
def import_plugin(data: dict) -> dict[str, Any]:
    from app.services.plugin_import_service import ImportService

    if not data:
        raise ClientException(detail="JSON body required")
    source_path = data.get("source_path")
    if not source_path:
        raise ClientException(detail="source_path is required")
    source_path = _ensure_path_allowed(source_path)  # 07.L3 — gate host path
    try:
        return ImportService.import_plugin_directory(
            plugin_dir=source_path,
            plugin_name=data.get("plugin_name"),
        )
    except FileNotFoundError as e:
        raise NotFoundException(detail=str(e)) from e
    except NotADirectoryError as e:
        raise ClientException(detail=str(e)) from e
    except Exception as e:  # 07.L1 — log internals, return a generic message
        logger.error("Plugin import failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Import failed") from e


@post("/import-from-marketplace", status_code=201, sync_to_thread=False)
def import_from_marketplace(data: dict) -> dict[str, Any]:
    from app.services.plugin_deploy_service import DeployService

    if not data:
        raise ClientException(detail="JSON body required")
    marketplace_id = data.get("marketplace_id")
    remote_plugin_name = data.get("remote_plugin_name")
    if not marketplace_id:
        raise ClientException(detail="marketplace_id is required")
    if not remote_plugin_name:
        raise ClientException(detail="remote_plugin_name is required")
    try:
        return DeployService.load_from_marketplace(
            marketplace_id=marketplace_id, remote_plugin_name=remote_plugin_name
        )
    except ValueError as e:
        raise NotFoundException(detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:  # 07.L1 — log internals, return a generic message
        logger.error("Marketplace import failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Marketplace import failed") from e


@post("/deploy", sync_to_thread=False)
def deploy_plugin(data: dict) -> dict[str, Any]:
    from app.services.plugin_deploy_service import DeployService

    if not data:
        raise ClientException(detail="JSON body required")
    plugin_id = data.get("plugin_id")
    marketplace_id = data.get("marketplace_id")
    if not plugin_id:
        raise ClientException(detail="plugin_id is required")
    if not marketplace_id:
        raise ClientException(detail="marketplace_id is required")
    version = data.get("version", "1.0.0")
    try:
        return DeployService.deploy_to_marketplace(
            plugin_id=plugin_id, marketplace_id=marketplace_id, version=version
        )
    except ValueError as e:
        raise NotFoundException(detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:  # 07.L1 — log internals, return a generic message
        logger.error("Plugin deploy failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Deploy failed") from e


@post("/test-connection", sync_to_thread=False)
def test_marketplace_connection(data: dict) -> dict[str, Any]:
    from app.services.plugin_deploy_service import DeployService

    if not data:
        raise ClientException(detail="JSON body required")
    marketplace_id = data.get("marketplace_id")
    if not marketplace_id:
        raise ClientException(detail="marketplace_id is required")
    return DeployService.test_connection(marketplace_id=marketplace_id)


@get("/{plugin_id:str}/exports", sync_to_thread=False)
def list_plugin_exports(plugin_id: str, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    exports = get_plugin_exports_for_plugin(plugin_id, limit=limit, offset=offset)
    return {
        "exports": exports,
        "total_count": count_plugin_exports_for_plugin(plugin_id),
    }


@post("/sync", sync_to_thread=False)
def sync_to_disk(data: dict) -> dict[str, Any]:
    from app.services.plugin_sync_service import SyncService

    if not data:
        raise ClientException(detail="JSON body required")
    plugin_id = data.get("plugin_id")
    plugin_dir = data.get("plugin_dir")
    if not plugin_id or not plugin_dir:
        raise ClientException(detail="plugin_id and plugin_dir are required")
    plugin_dir = _ensure_path_allowed(plugin_dir)  # 07.L3 — gate host path
    try:
        summary = SyncService.sync_all_to_disk(plugin_id, plugin_dir)
    except Exception as e:  # 07.L1 — log internals, return a generic message
        logger.error("Plugin sync failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Sync failed") from e
    return {"message": "Sync complete", **summary}


@post("/sync/entity", sync_to_thread=False)
def sync_entity(data: dict) -> dict[str, Any]:
    from app.services.plugin_sync_service import SyncService

    if not data:
        raise ClientException(detail="JSON body required")
    entity_type = data.get("entity_type")
    entity_id = data.get("entity_id")
    plugin_id = data.get("plugin_id")
    plugin_dir = data.get("plugin_dir")
    if not all([entity_type, entity_id, plugin_id, plugin_dir]):
        raise ClientException(
            detail="entity_type, entity_id, plugin_id, and plugin_dir are required"
        )
    plugin_dir = _ensure_path_allowed(plugin_dir)  # 07.L3 — gate host path
    try:
        synced = SyncService.sync_entity_to_disk(entity_type, entity_id, plugin_id, plugin_dir)
    except Exception as e:  # 07.L1 — log internals, return a generic message
        logger.error("Plugin entity sync failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Sync failed") from e
    return {"synced": synced}


@post("/watch", sync_to_thread=False)
def toggle_watcher(data: dict) -> dict[str, Any]:
    from app.services.plugin_sync_service import SyncService

    if not data:
        raise ClientException(detail="JSON body required")
    plugin_id = data.get("plugin_id")
    plugin_dir = data.get("plugin_dir")
    enabled = data.get("enabled", True)
    if not plugin_id:
        raise ClientException(detail="plugin_id is required")
    try:
        if enabled:
            if not plugin_dir:
                raise ClientException(detail="plugin_dir is required when enabling watch")
            plugin_dir = _ensure_path_allowed(plugin_dir)  # 07.L3 — gate host path
            SyncService.start_watching(plugin_id, plugin_dir)
        else:
            SyncService.stop_watching(plugin_id)
    except (ClientException, HTTPException):
        raise
    except Exception as e:  # 07.L1 — log internals, return a generic message
        logger.error("Watch toggle failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Watch toggle failed") from e
    return {"watching": enabled, "plugin_id": plugin_id}


@get("/{plugin_id:str}/sync-status", sync_to_thread=False)
def get_plugin_sync_status(plugin_id: str) -> dict[str, Any]:
    from app.services.plugin_sync_service import SyncService

    try:
        status = SyncService.get_sync_status(plugin_id)
        status["watching"] = SyncService.is_watching(plugin_id)
    except Exception as e:  # 07.L1 — log internals, return a generic message
        logger.error("Failed to get sync status", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get sync status") from e
    return status


plugin_exports_router = Router(
    path="/admin/plugin-exports",
    route_handlers=[
        export_plugin,
        import_plugin,
        import_from_marketplace,
        deploy_plugin,
        test_marketplace_connection,
        list_plugin_exports,
        sync_to_disk,
        sync_entity,
        toggle_watcher,
        get_plugin_sync_status,
    ],
)
