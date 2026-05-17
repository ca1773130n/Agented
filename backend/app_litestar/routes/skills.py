"""Skills cluster: skills + skill_sets + skill_conversations (track A, wave 57).

3 routers under /api/skills, /api/skill-sets, /api/skills/conversations.
SSE streams (/test/{id}/stream and /conversations/{id}/stream) use
Litestar's Stream response with the same headers as the Flask version.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from litestar import MediaType, Request, Router, delete, get, post, put
from litestar.exceptions import (
    ClientException,
    HTTPException,
    NotFoundException,
)
from litestar.response import Stream
from msgspec import Struct

from app.db.skill_sets import (
    create_skill_set,
    delete_skill_set,
    get_all_skill_sets,
    get_skill_set,
    update_skill_set,
)
from app.services.skill_conversation_service import SkillConversationService
from app.services.skills_service import SkillsService, get_playground_working_dir

from ..auth import Caller


def _result_or_raise(payload: tuple[dict, int]) -> dict:
    body, status = payload
    if status >= 400:
        raise HTTPException(status_code=status, detail=body)
    return body


# ===========================================================================
# /api/skills/* — main skills router
# ===========================================================================


@get("/", sync_to_thread=False)
def list_skills(
    caller: Caller, trigger_id: Optional[str] = None
) -> dict[str, Any]:
    del caller
    return _result_or_raise(SkillsService.list_skills(trigger_id=trigger_id))


@get("/discover/{skill_name:str}", sync_to_thread=False)
def get_skill_detail(skill_name: str, caller: Caller) -> dict[str, Any]:
    del caller
    return _result_or_raise(SkillsService.get_skill_detail(skill_name))


# User skills


@get("/user", sync_to_thread=False)
def list_user_skills(caller: Caller) -> dict[str, Any]:
    del caller
    return _result_or_raise(SkillsService.list_user_skills())


@get("/user/{skill_id:int}", sync_to_thread=False)
def get_single_user_skill(skill_id: int, caller: Caller) -> dict[str, Any]:
    del caller
    return _result_or_raise(SkillsService.get_single_skill(skill_id))


@post("/user", sync_to_thread=False)
def add_user_skill(data: dict, caller: Caller) -> dict[str, Any]:
    del caller
    if not data:
        raise ClientException(detail="JSON body required")
    return _result_or_raise(SkillsService.add_skill(data))


@put("/user/{skill_id:int}", sync_to_thread=False)
def update_user_skill(
    skill_id: int, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller
    if not data:
        raise ClientException(detail="JSON body required")
    return _result_or_raise(
        SkillsService.update_skill(
            skill_id, {k: v for k, v in data.items() if v is not None}
        )
    )


@delete("/user/{skill_id:int}", status_code=200, sync_to_thread=False)
def delete_user_skill(skill_id: int, caller: Caller) -> dict[str, Any]:
    del caller
    return _result_or_raise(SkillsService.remove_skill(skill_id))


# Harness


@get("/harness", sync_to_thread=False)
def get_harness_skills(caller: Caller) -> dict[str, Any]:
    del caller
    return _result_or_raise(SkillsService.get_harness_selected_skills())


class ToggleHarnessBody(Struct):
    selected: bool = False


@put("/harness/{skill_id:int}", sync_to_thread=False)
def toggle_harness_skill(
    skill_id: int, data: ToggleHarnessBody, caller: Caller
) -> dict[str, Any]:
    del caller
    return _result_or_raise(
        SkillsService.toggle_harness_selection(skill_id, data.selected)
    )


@get("/harness/config", sync_to_thread=False)
def get_harness_config(caller: Caller) -> dict[str, Any]:
    del caller
    return _result_or_raise(SkillsService.generate_harness_config())


@post("/harness/load-from-marketplace", sync_to_thread=False)
def load_from_marketplace(caller: Caller) -> dict[str, Any]:
    del caller
    return _result_or_raise(SkillsService.load_from_marketplace())


@post("/harness/deploy-to-marketplace", sync_to_thread=False)
def deploy_to_marketplace(caller: Caller) -> dict[str, Any]:
    del caller
    return _result_or_raise(SkillsService.deploy_to_marketplace())


# Playground


@get("/playground/files", sync_to_thread=False)
def list_playground_files(caller: Caller) -> dict[str, Any]:
    del caller
    working_dir = get_playground_working_dir()

    def build_tree(path: str, depth: int = 0, max_depth: int = 5) -> list:
        if depth > max_depth:
            return []
        items: list = []
        try:
            entries = sorted(os.listdir(path))
        except OSError:
            return []
        for entry in entries:
            if entry.startswith(".") or entry in (
                "node_modules", "__pycache__", "dist", "build", ".git",
            ):
                continue
            full_path = os.path.join(path, entry)
            rel_path = os.path.relpath(full_path, working_dir)
            if os.path.isdir(full_path):
                items.append({
                    "name": entry, "path": rel_path, "type": "directory",
                    "children": build_tree(full_path, depth + 1, max_depth),
                })
            else:
                items.append({"name": entry, "path": rel_path, "type": "file"})
        return items

    return {"working_dir": working_dir, "files": build_tree(working_dir)}


@post("/test", sync_to_thread=False)
def test_skill(data: dict, caller: Caller) -> dict[str, Any]:
    del caller
    if not data or "skill_name" not in data:
        raise ClientException(detail="skill_name is required")
    return _result_or_raise(
        SkillsService.test_skill(data["skill_name"], data.get("input", ""))
    )


@get(
    "/test/{test_id:str}/stream",
    media_type=MediaType.TEXT,
    sync_to_thread=False,
)
def stream_test(test_id: str, caller: Caller) -> Stream:
    del caller

    def generate():
        for event in SkillsService.subscribe_test(test_id):
            yield event

    return Stream(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@post("/test/{test_id:str}/stop", sync_to_thread=False)
def stop_test(test_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    return _result_or_raise(SkillsService.stop_test(test_id))


# skills.sh integration


@get("/skills-sh/search", sync_to_thread=False)
def search_skills_sh(caller: Caller, q: str = "") -> dict[str, Any]:
    del caller
    from app.services.skills_sh_service import SkillsShService

    return _result_or_raise(SkillsShService.search(q.strip()))


@post("/skills-sh/install", sync_to_thread=False)
def install_skills_sh(
    data: dict, caller: Caller, request: Request
) -> dict[str, Any]:
    del caller
    if not data or "source" not in data:
        raise ClientException(detail="source is required")
    from app.services.skills_sh_service import SkillsShService

    client_ip = (
        request.client.host
        if request.client and request.client.host
        else "unknown"
    )
    return _result_or_raise(
        SkillsShService.install_skill(data["source"], client_ip=client_ip)
    )


skills_router = Router(
    path="/api/skills",
    route_handlers=[
        list_skills,
        get_skill_detail,
        list_user_skills,
        get_single_user_skill,
        add_user_skill,
        update_user_skill,
        delete_user_skill,
        get_harness_skills,
        toggle_harness_skill,
        get_harness_config,
        load_from_marketplace,
        deploy_to_marketplace,
        list_playground_files,
        test_skill,
        stream_test,
        stop_test,
        search_skills_sh,
        install_skills_sh,
    ],
)


# ===========================================================================
# /api/skill-sets/* — skill-set compositions
# ===========================================================================


@get("/", sync_to_thread=False)
def list_skill_sets(caller: Caller) -> dict[str, Any]:
    del caller
    return {"skill_sets": get_all_skill_sets()}


@post("/", sync_to_thread=False)
def create_skill_set_endpoint(data: dict, caller: Caller) -> dict[str, Any]:
    del caller
    if not data:
        raise ClientException(detail="JSON body required")
    name = (data.get("name") or "").strip()
    if not name:
        raise ClientException(detail="name is required")
    skill_ids = data.get("skill_ids", [])
    if not isinstance(skill_ids, list):
        raise ClientException(detail="skill_ids must be an array")
    sset_id = create_skill_set(name=name, skill_ids_json=json.dumps(skill_ids))
    if not sset_id:
        raise HTTPException(status_code=500, detail="Failed to create skill set")
    return {"message": "Skill set created", "skill_set": get_skill_set(sset_id)}


@put("/{set_id:str}", sync_to_thread=False)
def update_skill_set_endpoint(
    set_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller
    if not data:
        raise ClientException(detail="JSON body required")
    if not get_skill_set(set_id):
        raise NotFoundException(detail="Skill set not found")

    name = data.get("name")
    if name is not None:
        name = name.strip()
        if not name:
            raise ClientException(detail="name cannot be empty")

    skill_ids = data.get("skill_ids")
    skill_ids_json = None
    if skill_ids is not None:
        if not isinstance(skill_ids, list):
            raise ClientException(detail="skill_ids must be an array")
        skill_ids_json = json.dumps(skill_ids)

    if not update_skill_set(set_id, name=name, skill_ids_json=skill_ids_json):
        raise ClientException(detail="No changes made")
    return {"message": "Skill set updated", "skill_set": get_skill_set(set_id)}


@delete("/{set_id:str}", status_code=200, sync_to_thread=False)
def delete_skill_set_endpoint(set_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    if not get_skill_set(set_id):
        raise NotFoundException(detail="Skill set not found")
    if not delete_skill_set(set_id):
        raise HTTPException(status_code=500, detail="Failed to delete skill set")
    return {"message": "Skill set deleted"}


skill_sets_router = Router(
    path="/api/skill-sets",
    route_handlers=[
        list_skill_sets,
        create_skill_set_endpoint,
        update_skill_set_endpoint,
        delete_skill_set_endpoint,
    ],
)


# ===========================================================================
# /api/skills/conversations/* — interactive skill creation
# ===========================================================================


@post("/start", sync_to_thread=False)
def start_conversation(caller: Caller) -> dict[str, Any]:
    del caller
    return _result_or_raise(SkillConversationService.start_conversation())


@get("/{conv_id:str}", sync_to_thread=False)
def get_conversation(conv_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    return _result_or_raise(SkillConversationService.get_conversation(conv_id))


@post("/{conv_id:str}/message", sync_to_thread=False)
def send_message(
    conv_id: str, data: dict, caller: Caller
) -> dict[str, Any]:
    del caller
    if not data or not data.get("message"):
        raise ClientException(detail="message is required")
    return _result_or_raise(
        SkillConversationService.send_message(
            conv_id,
            data["message"],
            backend=data.get("backend"),
            account_id=data.get("account_id"),
            model=data.get("model"),
        )
    )


@get(
    "/{conv_id:str}/stream",
    media_type=MediaType.TEXT,
    sync_to_thread=False,
)
def stream_conversation(conv_id: str, caller: Caller) -> Stream:
    del caller

    def generate():
        for event in SkillConversationService.subscribe(conv_id):
            yield event

    return Stream(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@post("/{conv_id:str}/preview-finalize", sync_to_thread=False)
def preview_finalize_skill(conv_id: str, caller: Caller) -> dict[str, Any]:
    """v0.7.77 — return the rendered skill package tree without
    writing to disk. Used by ``SkillCreatePreviewDrawer`` so the
    operator can inspect SKILL.md + helpers/references before
    finalize lands them. Same validation as ``finalize_skill``: a
    preview that returns 200 is guaranteed to commit.
    """
    del caller
    return _result_or_raise(SkillConversationService.preview_finalize(conv_id))


@post("/{conv_id:str}/finalize", sync_to_thread=False)
def finalize_skill(conv_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    return _result_or_raise(SkillConversationService.finalize_skill(conv_id))


@post("/{conv_id:str}/abandon", sync_to_thread=False)
def abandon_conversation(conv_id: str, caller: Caller) -> dict[str, Any]:
    del caller
    return _result_or_raise(SkillConversationService.abandon_conversation(conv_id))


skill_conversations_router = Router(
    path="/api/skills/conversations",
    route_handlers=[
        start_conversation,
        get_conversation,
        send_message,
        stream_conversation,
        preview_finalize_skill,
        finalize_skill,
        abandon_conversation,
    ],
)
