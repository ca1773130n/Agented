"""Teams namespace — full /admin/teams/* port (track A, wave 53).

Includes the parent CRUD plus all nested children: members, assignments,
connections, edges. The topology / trigger / manual-run routes preserve
their original behaviour by delegating to TeamService and the existing
auto-edge helper inlined here from app/routes/teams.py.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Optional

from litestar import Router, delete, get, post, put
from litestar.exceptions import ClientException, HTTPException, NotFoundException
from msgspec import Struct

from app.database import (
    VALID_TRIGGER_SOURCES,
    add_team_edge,
    add_team_member,
    count_teams,
    delete_team,
    delete_team_edge,
    delete_team_edges_by_team,
    get_all_teams,
    get_team,
    get_team_by_name,
    get_team_detail,
    get_team_edges,
    get_team_members,
    update_team,
)
from app.models.team import VALID_EDGE_TYPES, VALID_TOPOLOGIES
from app.services.team_service import TeamService

from ..auth import Caller, require_role
from ..list_scope import admin_or_scoped

logger = logging.getLogger(__name__)
_MAX_TOPOLOGY_MEMBERS = 50


def _auto_generate_topology_edges(team_id: str, topology: str, topology_config=None) -> None:
    """Mirror of app/routes/teams.py:_auto_generate_topology_edges (wave 53)."""
    members = get_team_members(team_id)
    if not members or len(members) < 2:
        return
    if len(members) > _MAX_TOPOLOGY_MEMBERS:
        logger.warning(
            "Team %s has %d members, exceeding the topology edge generation limit of %d.",
            team_id,
            len(members),
            _MAX_TOPOLOGY_MEMBERS,
        )
        return

    # Clear existing edges so we don't accumulate duplicates.
    delete_team_edges_by_team(team_id)

    if topology in ("coordinator", "hierarchical"):
        leader = members[0]
        for m in members[1:]:
            add_team_edge(
                team_id=team_id,
                source_member_id=leader["id"],
                target_member_id=m["id"],
                edge_type="delegation",
            )


# ---------------------------------------------------------------------------
# Parent CRUD
# ---------------------------------------------------------------------------


@get(
    "/",
    dependencies={"authorized": require_role("viewer", "operator", "editor", "admin")},
    sync_to_thread=False,
)
def list_teams(
    authorized: Caller, limit: Optional[int] = None, offset: Optional[int] = None
) -> dict[str, Any]:
    return admin_or_scoped(
        authorized,
        "teams",
        "teams",
        limit=limit,
        offset=offset or 0,
        all_=lambda: {
            "teams": get_all_teams(limit=limit, offset=offset or 0),
            "total_count": count_teams(),
        },
    )


class CreateTeamBody(Struct, kw_only=True):
    name: str = ""
    description: Optional[str] = None
    color: Optional[str] = None
    leader_id: Optional[str] = None
    topology: Optional[str] = None
    topology_config: Optional[Any] = None
    trigger_source: Optional[str] = None
    trigger_config: Optional[Any] = None


@post(
    "/",
    dependencies={"authorized": require_role("admin")},
    sync_to_thread=False,
)
def create_team(data: CreateTeamBody, authorized: Caller) -> dict[str, Any]:
    del authorized
    name = (data.name or "").strip()
    if not name:
        raise ClientException(detail="name is required")
    if len(name) > 255:
        raise ClientException(detail="name must not exceed 255 characters")
    if get_team_by_name(name):
        raise HTTPException(status_code=409, detail="A team with this name already exists")

    from app.database import create_team as db_create_team

    try:
        team_id = db_create_team(
            name=name,
            description=data.description,
            color=data.color or "#00d4ff",
            leader_id=data.leader_id,
            topology=data.topology,
            topology_config=data.topology_config,
            trigger_source=data.trigger_source,
            trigger_config=data.trigger_config,
        )
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="A team with this name or configuration already exists",
        ) from None
    except sqlite3.OperationalError:
        raise HTTPException(status_code=503, detail="Database unavailable, please retry") from None

    if not team_id:
        raise HTTPException(status_code=500, detail="Failed to create team")

    if data.leader_id:
        add_team_member(team_id=team_id, agent_id=data.leader_id, role="leader")

    return {"message": "Team created", "team": get_team_detail(team_id)}


@get(
    "/{team_id:str}",
    dependencies={"authorized": require_role("viewer", "operator", "editor", "admin")},
    sync_to_thread=False,
)
def team_detail(team_id: str, authorized: Caller) -> dict[str, Any]:
    del authorized
    team = get_team_detail(team_id)
    if not team:
        raise NotFoundException(detail="Team not found")
    return team


class UpdateTeamBody(Struct, kw_only=True):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    leader_id: Optional[str] = None


@put(
    "/{team_id:str}",
    dependencies={"authorized": require_role("editor", "admin")},
    sync_to_thread=False,
)
def update_team_endpoint(team_id: str, data: UpdateTeamBody, authorized: Caller) -> dict[str, Any]:
    del authorized
    new_name = data.name
    if new_name is not None:
        new_name = new_name.strip()
        if not new_name:
            raise ClientException(detail="name must not be empty")
        if len(new_name) > 255:
            raise ClientException(detail="name must not exceed 255 characters")
        existing = get_team_by_name(new_name)
        if existing and existing["id"] != team_id:
            raise HTTPException(status_code=409, detail="A team with this name already exists")

    if not update_team(
        team_id,
        name=new_name,
        description=data.description,
        color=data.color,
        leader_id=data.leader_id,
    ):
        raise NotFoundException(detail="Team not found or no changes made")
    return get_team_detail(team_id)


@delete(
    "/{team_id:str}",
    dependencies={"authorized": require_role("admin")},
    status_code=200,
    sync_to_thread=False,
)
def delete_team_endpoint(team_id: str, authorized: Caller) -> dict[str, Any]:
    del authorized
    if not delete_team(team_id):
        raise NotFoundException(detail="Team not found")
    return {"message": "Team deleted"}


# ---------------------------------------------------------------------------
# Topology
# ---------------------------------------------------------------------------


class TopologyBody(Struct, kw_only=True):
    topology: Optional[str] = None
    topology_config: Optional[Any] = None


@put(
    "/{team_id:str}/topology",
    dependencies={"authorized": require_role("editor", "admin")},
    sync_to_thread=False,
)
def update_topology(team_id: str, data: TopologyBody, authorized: Caller) -> dict[str, Any]:
    del authorized
    if not get_team(team_id):
        raise NotFoundException(detail="Team not found")

    topology = data.topology
    topology_config = data.topology_config

    if topology is not None and topology not in VALID_TOPOLOGIES:
        raise ClientException(
            detail=f"Invalid topology. Must be one of: {', '.join(VALID_TOPOLOGIES)}"
        )

    if topology_config is not None and topology is not None:
        config_err = TeamService.validate_topology_config(team_id, topology, topology_config)
        if config_err:
            raise ClientException(detail=config_err)

    config_str: Optional[str] = None
    if topology_config is not None:
        config_str = (
            json.dumps(topology_config) if isinstance(topology_config, dict) else topology_config
        )

    update_kwargs: dict[str, Any] = {}
    if topology is not None:
        update_kwargs["topology"] = topology
    if config_str is not None:
        update_kwargs["topology_config"] = config_str

    if update_kwargs:
        update_team(team_id, **update_kwargs)

    if topology in ("coordinator", "hierarchical"):
        _auto_generate_topology_edges(team_id, topology, config_str)

    return get_team_detail(team_id)


# ---------------------------------------------------------------------------
# Trigger
# ---------------------------------------------------------------------------


class TeamTriggerBody(Struct, kw_only=True):
    trigger_source: Optional[str] = None
    trigger_config: Optional[Any] = None
    enabled: Optional[int] = None


@put(
    "/{team_id:str}/trigger",
    dependencies={"authorized": require_role("editor", "admin")},
    sync_to_thread=False,
)
def update_team_trigger(team_id: str, data: TeamTriggerBody, authorized: Caller) -> dict[str, Any]:
    del authorized
    if not get_team(team_id):
        raise NotFoundException(detail="Team not found")
    if data.trigger_source is not None and data.trigger_source not in VALID_TRIGGER_SOURCES:
        raise ClientException(
            detail=f"Invalid trigger_source. Must be one of: {', '.join(VALID_TRIGGER_SOURCES)}"
        )
    config_str: Optional[str] = None
    if data.trigger_config is not None:
        config_str = (
            json.dumps(data.trigger_config)
            if isinstance(data.trigger_config, dict)
            else data.trigger_config
        )
    update_team(
        team_id,
        trigger_source=data.trigger_source,
        trigger_config=config_str,
        enabled=data.enabled,
    )
    return get_team_detail(team_id)


# ---------------------------------------------------------------------------
# Manual run
# ---------------------------------------------------------------------------


class TeamRunBody(Struct):
    message: str = ""


@post(
    "/{team_id:str}/run",
    dependencies={"authorized": require_role("operator", "editor", "admin")},
    sync_to_thread=False,
)
def manual_run(team_id: str, data: TeamRunBody, authorized: Caller) -> dict[str, Any]:
    del authorized
    team = get_team(team_id)
    if not team:
        raise NotFoundException(detail="Team not found")
    if not team.get("enabled", 1):
        raise ClientException(detail="Team is disabled")

    from app.services.team_execution_service import TeamExecutionService

    try:
        team_exec_id = TeamExecutionService.execute_team(
            team_id=team_id,
            message=data.message or "",
            event={},
            trigger_type="manual",
        )
    except ValueError as exc:
        raise ClientException(detail=str(exc)) from None
    return {"message": "Team execution started", "team_execution_id": team_exec_id}


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


class MemberBody(Struct, kw_only=True):
    agent_id: str = ""
    role: Optional[str] = None


class MemberUpdateBody(Struct, kw_only=True):
    role: Optional[str] = None


@get(
    "/{team_id:str}/members",
    dependencies={"authorized": require_role("viewer", "operator", "editor", "admin")},
    sync_to_thread=False,
)
def list_team_members_endpoint(team_id: str, authorized: Caller) -> dict[str, Any]:
    del authorized
    return {"members": get_team_members(team_id)}


@post(
    "/{team_id:str}/members",
    dependencies={"authorized": require_role("editor", "admin")},
    sync_to_thread=False,
)
def add_member_endpoint(team_id: str, data: MemberBody, authorized: Caller) -> dict[str, Any]:
    del authorized
    if not data.agent_id:
        raise ClientException(detail="agent_id is required")
    member_id = add_team_member(team_id=team_id, agent_id=data.agent_id, role=data.role or "member")
    if not member_id:
        raise ClientException(detail="Could not add member")
    return {"message": "Member added", "id": member_id}


@put(
    "/{team_id:str}/members/{member_id:int}",
    dependencies={"authorized": require_role("editor", "admin")},
    sync_to_thread=False,
)
def update_member_endpoint(
    team_id: str, member_id: int, data: MemberUpdateBody, authorized: Caller
) -> dict[str, Any]:
    del authorized
    from app.database import update_team_member

    if not update_team_member(team_id=team_id, member_id=member_id, role=data.role):
        raise NotFoundException(detail="Member not found")
    return {"message": "Member updated"}


@delete(
    "/{team_id:str}/members/{member_id:int}",
    dependencies={"authorized": require_role("editor", "admin")},
    status_code=200,
    sync_to_thread=False,
)
def remove_member_endpoint(team_id: str, member_id: int, authorized: Caller) -> dict[str, Any]:
    del authorized
    from app.database import remove_team_member

    if not remove_team_member(team_id=team_id, member_id=member_id):
        raise NotFoundException(detail="Member not found")
    return {"message": "Member removed"}


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------


class AssignmentBody(Struct, kw_only=True):
    task_description: str = ""
    priority: Optional[str] = None
    metadata: Optional[Any] = None


@post(
    "/{team_id:str}/agents/{agent_id:str}/assignments",
    dependencies={"authorized": require_role("editor", "admin")},
    sync_to_thread=False,
)
def create_assignment(
    team_id: str, agent_id: str, data: AssignmentBody, authorized: Caller
) -> dict[str, Any]:
    del authorized
    from app.database import add_team_assignment

    aid = add_team_assignment(
        team_id=team_id,
        agent_id=agent_id,
        task_description=data.task_description or "",
        priority=data.priority,
        metadata=json.dumps(data.metadata) if isinstance(data.metadata, (dict, list)) else None,
    )
    if not aid:
        raise ClientException(detail="Could not create assignment")
    return {"message": "Assignment created", "id": aid}


@get(
    "/{team_id:str}/agents/{agent_id:str}/assignments",
    dependencies={"authorized": require_role("viewer", "operator", "editor", "admin")},
    sync_to_thread=False,
)
def list_agent_assignments(team_id: str, agent_id: str, authorized: Caller) -> dict[str, Any]:
    del authorized
    from app.database import get_team_assignments_for_agent

    return {"assignments": get_team_assignments_for_agent(team_id, agent_id)}


@get(
    "/{team_id:str}/assignments",
    dependencies={"authorized": require_role("viewer", "operator", "editor", "admin")},
    sync_to_thread=False,
)
def list_team_assignments(team_id: str, authorized: Caller) -> dict[str, Any]:
    del authorized
    from app.database import get_team_assignments

    return {"assignments": get_team_assignments(team_id)}


@delete(
    "/{team_id:str}/assignments/{assignment_id:int}",
    dependencies={"authorized": require_role("editor", "admin")},
    status_code=200,
    sync_to_thread=False,
)
def delete_assignment(team_id: str, assignment_id: int, authorized: Caller) -> dict[str, Any]:
    del authorized, team_id
    from app.database import delete_team_assignment

    if not delete_team_assignment(assignment_id):
        raise NotFoundException(detail="Assignment not found")
    return {"message": "Assignment deleted"}


@delete(
    "/{team_id:str}/agents/{agent_id:str}/assignments",
    dependencies={"authorized": require_role("editor", "admin")},
    status_code=200,
    sync_to_thread=False,
)
def clear_agent_assignments(team_id: str, agent_id: str, authorized: Caller) -> dict[str, Any]:
    del authorized
    from app.database import clear_team_assignments_for_agent

    n = clear_team_assignments_for_agent(team_id, agent_id)
    return {"message": "Assignments cleared", "deleted_count": n}


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------


class ConnectionBody(Struct, kw_only=True):
    target_team_id: str = ""
    connection_type: str = "dependency"
    description: Optional[str] = None


@get(
    "/{team_id:str}/connections",
    dependencies={"authorized": require_role("viewer", "operator", "editor", "admin")},
    sync_to_thread=False,
)
def list_team_connections(team_id: str, authorized: Caller) -> dict[str, Any]:
    del authorized
    from app.db.rotations import get_team_connections

    return {"connections": get_team_connections(team_id)}


@post(
    "/{team_id:str}/connections",
    dependencies={"authorized": require_role("admin")},
    sync_to_thread=False,
)
def create_team_connection(
    team_id: str, data: ConnectionBody, authorized: Caller
) -> dict[str, Any]:
    del authorized
    from app.db.rotations import add_team_connection

    if not data.target_team_id:
        raise ClientException(detail="target_team_id is required")
    cid = add_team_connection(
        source_team_id=team_id,
        target_team_id=data.target_team_id,
        connection_type=data.connection_type,
        description=data.description,
    )
    if not cid:
        raise ClientException(detail="Failed to create connection")
    return {"message": "Connection created", "id": cid}


@delete(
    "/{team_id:str}/connections/{connection_id:int}",
    dependencies={"authorized": require_role("admin")},
    status_code=200,
    sync_to_thread=False,
)
def remove_team_connection(team_id: str, connection_id: int, authorized: Caller) -> dict[str, Any]:
    del authorized, team_id
    from app.db.rotations import delete_team_connection

    if not delete_team_connection(connection_id):
        raise NotFoundException(detail="Connection not found")
    return {"message": "Connection deleted"}


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------


class EdgeBody(Struct, kw_only=True):
    source_member_id: Optional[int] = None
    target_member_id: Optional[int] = None
    edge_type: str = "delegation"
    label: Optional[str] = None
    weight: int = 1


@get(
    "/{team_id:str}/edges",
    dependencies={"authorized": require_role("viewer", "operator", "editor", "admin")},
    sync_to_thread=False,
)
def list_edges(team_id: str, authorized: Caller) -> dict[str, Any]:
    del authorized
    return {"edges": get_team_edges(team_id)}


@post(
    "/{team_id:str}/edges",
    dependencies={"authorized": require_role("editor", "admin")},
    sync_to_thread=False,
)
def create_edge(team_id: str, data: EdgeBody, authorized: Caller) -> dict[str, Any]:
    del authorized
    if data.source_member_id is None or data.target_member_id is None:
        raise ClientException(detail="source_member_id and target_member_id are required")
    if data.edge_type not in VALID_EDGE_TYPES:
        raise ClientException(
            detail=f"Invalid edge_type. Must be one of: {', '.join(VALID_EDGE_TYPES)}"
        )
    edge_id = add_team_edge(
        team_id=team_id,
        source_member_id=data.source_member_id,
        target_member_id=data.target_member_id,
        edge_type=data.edge_type,
        label=data.label,
        weight=data.weight,
    )
    if edge_id is None:
        raise ClientException(detail="Failed to create edge (self-loop or duplicate)")
    edges = get_team_edges(team_id)
    edge = next((e for e in edges if e["id"] == edge_id), None)
    return {"message": "Edge created", "edge": edge}


@delete(
    "/{team_id:str}/edges/{edge_id:int}",
    dependencies={"authorized": require_role("editor", "admin")},
    status_code=200,
    sync_to_thread=False,
)
def delete_edge(team_id: str, edge_id: int, authorized: Caller) -> dict[str, Any]:
    del authorized, team_id
    if not delete_team_edge(edge_id):
        raise NotFoundException(detail="Edge not found")
    return {"message": "Edge deleted"}


@delete(
    "/{team_id:str}/edges",
    dependencies={"authorized": require_role("editor", "admin")},
    status_code=200,
    sync_to_thread=False,
)
def bulk_delete_edges(team_id: str, authorized: Caller) -> dict[str, Any]:
    del authorized
    n = delete_team_edges_by_team(team_id)
    return {"message": f"Deleted {n} edge(s)", "deleted_count": n}


teams_router = Router(
    path="/admin/teams",
    route_handlers=[
        list_teams,
        create_team,
        team_detail,
        update_team_endpoint,
        delete_team_endpoint,
        update_topology,
        update_team_trigger,
        manual_run,
        list_team_members_endpoint,
        add_member_endpoint,
        update_member_endpoint,
        remove_member_endpoint,
        create_assignment,
        list_agent_assignments,
        list_team_assignments,
        delete_assignment,
        clear_agent_assignments,
        list_team_connections,
        create_team_connection,
        remove_team_connection,
        list_edges,
        create_edge,
        delete_edge,
        bulk_delete_edges,
    ],
)
