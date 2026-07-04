"""Team YAML authoring service (Phase 26 / REQ-40).

Load, validate, materialize, and export a team topology as a single
human-authorable YAML document.

The import path validates the ENTIRE document — including every referenced
agent/super_agent — before performing any DB write, and then applies the
delete-on-upsert, team create, member inserts, and edge inserts inside a
SINGLE transaction with one commit at the end. A malformed document, a bad
foreign key, or a duplicate edge can therefore never leave a partially-created
team behind, and an upsert never destroys the prior team unless its
replacement fully materialises (the partial-state / atomicity guard). Edge
endpoints reference members by a stable ``ref`` (agent_id, super_agent_id, or
member name) rather than by DB-assigned member ids, which are not portable
across instances.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import yaml

from app.database import (
    get_team_by_name,
    get_team_detail,
    get_team_edges,
    get_team_members,
)
from app.db import errors
from app.db.agents import get_agent
from app.db.connection import get_connection
from app.db.ids import _get_unique_team_id
from app.db.super_agents import get_super_agent
from app.db.teams import _get_team_members_columns
from app.models.team import VALID_EDGE_TYPES, VALID_TOPOLOGIES

logger = logging.getLogger(__name__)

CONFIG_VERSION = "1.0"
CONFIG_KIND = "team"

_REQUIRED_KEYS = {"version", "kind", "metadata", "spec"}

# Reject an oversized YAML body BEFORE handing it to ``yaml.safe_load`` — an
# unbounded document is a cheap DoS vector (deep nesting / huge scalars) even
# with the safe loader. 256 KiB comfortably fits any hand-authored team
# topology while capping the parser's input. Matches the ``_MAX_BYTES`` cap
# convention in ``url_summarizer`` (256 * 1024).
_YAML_MAX_LEN = 256 * 1024


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def dump_team_config(config: dict) -> str:
    """Serialize a team config dict to a YAML document."""
    return yaml.dump(config, default_flow_style=False, sort_keys=False, allow_unicode=True)


def load_team_config(yaml_str: str) -> dict:
    """Parse a YAML document into a config dict.

    Raises:
        ValueError: if the body exceeds ``_YAML_MAX_LEN`` (checked BEFORE any
            parse), the document is not valid YAML, or it is not a mapping.
    """
    # Size-gate BEFORE parsing: never feed an oversized body to yaml.safe_load.
    if len(yaml_str.encode("utf-8")) > _YAML_MAX_LEN:
        raise ValueError(f"YAML body must be at most {_YAML_MAX_LEN} bytes")
    try:
        parsed = yaml.safe_load(yaml_str)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML: {exc}") from None
    if not isinstance(parsed, dict):
        raise ValueError("Team document must be a YAML mapping")
    return parsed


# ---------------------------------------------------------------------------
# Validation (runs fully BEFORE any DB write)
# ---------------------------------------------------------------------------


def _member_ref(member: dict) -> Optional[str]:
    """Stable identity for a member used by edge endpoints."""
    return (
        member.get("ref")
        or member.get("agent_id")
        or member.get("super_agent_id")
        or member.get("name")
    )


def validate_team_config(config: dict) -> tuple[bool, Optional[str]]:
    """Validate the structure of a parsed team config.

    Returns ``(True, None)`` when valid, else ``(False, error_message)``.
    Performs no DB writes.
    """
    if not isinstance(config, dict):
        return False, "Config must be a mapping"

    missing = _REQUIRED_KEYS - set(config.keys())
    if missing:
        return False, f"Missing required keys: {sorted(missing)}"

    if config.get("kind") != CONFIG_KIND:
        return False, f"Unsupported kind: {config.get('kind')!r}. Expected {CONFIG_KIND!r}"

    metadata = config.get("metadata")
    if not isinstance(metadata, dict):
        return False, "metadata must be a mapping"
    name = metadata.get("name")
    if not isinstance(name, str) or not name.strip():
        return False, "metadata.name is required"

    spec = config.get("spec")
    if not isinstance(spec, dict):
        return False, "spec must be a mapping"

    topology = spec.get("topology")
    if topology is not None and topology not in VALID_TOPOLOGIES:
        return False, f"Invalid topology: {topology!r}"

    members = spec.get("members", [])
    if not isinstance(members, list):
        return False, "spec.members must be a list"

    refs: set[str] = set()
    for i, member in enumerate(members):
        if not isinstance(member, dict):
            return False, f"member {i} must be a mapping"
        if member.get("agent_id") and member.get("super_agent_id"):
            return False, f"member {i} cannot set both agent_id and super_agent_id"
        ref = _member_ref(member)
        if not ref:
            return False, f"member {i} requires one of ref/agent_id/super_agent_id/name"
        if ref in refs:
            return False, f"duplicate member ref: {ref!r}"
        refs.add(ref)

    edges = spec.get("edges", [])
    if not isinstance(edges, list):
        return False, "spec.edges must be a list"

    for i, edge in enumerate(edges):
        if not isinstance(edge, dict):
            return False, f"edge {i} must be a mapping"
        source = edge.get("source")
        target = edge.get("target")
        if not source or not target:
            return False, f"edge {i} requires 'source' and 'target'"
        if source not in refs:
            return False, f"edge {i} source {source!r} is not a declared member"
        if target not in refs:
            return False, f"edge {i} target {target!r} is not a declared member"
        edge_type = edge.get("edge_type", "delegation")
        if edge_type not in VALID_EDGE_TYPES:
            return False, f"edge {i} has invalid edge_type: {edge_type!r}"

    return True, None


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def build_team_config(team_id: str) -> Optional[dict]:
    """Build a portable config dict from a materialized team, or None."""
    team = get_team_detail(team_id)
    if not team:
        return None

    topology_config = team.get("topology_config")
    if isinstance(topology_config, str) and topology_config:
        try:
            topology_config = json.loads(topology_config)
        except json.JSONDecodeError:
            topology_config = None

    members = get_team_members(team_id)
    member_ref_by_id: dict[int, str] = {}
    spec_members: list[dict[str, Any]] = []
    for m in members:
        ref = m.get("agent_id") or m.get("super_agent_id") or m.get("name")
        member_ref_by_id[m["id"]] = ref
        spec_members.append(
            {
                "ref": ref,
                "agent_id": m.get("agent_id"),
                "super_agent_id": m.get("super_agent_id"),
                "name": m.get("name"),
                "role": m.get("role", "member"),
                "layer": m.get("layer", "backend"),
                "tier": m.get("tier"),
            }
        )

    spec_edges: list[dict[str, Any]] = []
    for e in get_team_edges(team_id):
        source = member_ref_by_id.get(e["source_member_id"])
        target = member_ref_by_id.get(e["target_member_id"])
        if source is None or target is None:
            continue
        spec_edges.append(
            {
                "source": source,
                "target": target,
                "edge_type": e.get("edge_type", "delegation"),
                "label": e.get("label"),
                "weight": e.get("weight", 1),
            }
        )

    return {
        "version": CONFIG_VERSION,
        "kind": CONFIG_KIND,
        "metadata": {
            "name": team["name"],
            "description": team.get("description"),
            "color": team.get("color"),
            "exported_at": datetime.now(timezone.utc).isoformat(),
        },
        "spec": {
            "topology": team.get("topology"),
            "topology_config": topology_config,
            "trigger_source": team.get("trigger_source"),
            "members": spec_members,
            "edges": spec_edges,
        },
    }


def export_team(team_id: str) -> Optional[str]:
    """Export a materialized team as a YAML document, or None if missing."""
    config = build_team_config(team_id)
    if config is None:
        return None
    return dump_team_config(config)


# ---------------------------------------------------------------------------
# Import (atomic + partial-state guarded)
# ---------------------------------------------------------------------------


def _validate_db_references(members: list[dict]) -> dict[str, Optional[str]]:
    """Resolve/validate every member's DB reference BEFORE any write.

    For each member with an ``agent_id``/``super_agent_id``, confirm the
    referenced record exists and resolve a display name (matching
    ``add_team_member``'s behaviour). Runs entirely on read connections, so a
    dangling reference is caught before the import transaction is opened.

    Returns a ``ref -> resolved_name`` map for the writer to reuse.

    Raises:
        ValueError: if any member references a non-existent agent/super_agent.
    """
    resolved: dict[str, Optional[str]] = {}
    for i, member in enumerate(members):
        ref = _member_ref(member)
        name = member.get("name")
        agent_id = member.get("agent_id")
        super_agent_id = member.get("super_agent_id")
        if agent_id:
            agent = get_agent(agent_id)
            if not agent:
                raise ValueError(f"member {i} references unknown agent_id: {agent_id!r}")
            if not name:
                name = agent.get("name") or "Unknown Agent"
        elif super_agent_id:
            super_agent = get_super_agent(super_agent_id)
            if not super_agent:
                raise ValueError(
                    f"member {i} references unknown super_agent_id: {super_agent_id!r}"
                )
            if not name:
                name = super_agent.get("name") or "Unknown SuperAgent"
        resolved[ref] = name
    return resolved


def import_team(yaml_str: str, upsert: bool = False) -> tuple[str, str]:
    """Materialize a team from a YAML document, atomically.

    The whole document is parsed and validated — including every referenced
    agent/super_agent — before any DB write. The delete-on-upsert, team
    create, member inserts, and edge inserts then run inside a SINGLE
    connection/transaction with one commit at the end. Any failing member or
    edge insert (bad FK, duplicate edge, self-loop, duplicate member name)
    raises and rolls the whole transaction back, so on failure the DB is left
    unchanged: a prior team survives an upsert, and a create leaves nothing
    behind.

    Returns ``(team_id, status)`` where status is ``"created"`` or
    ``"updated"``.

    Raises:
        ValueError: on parse/validation failure, an unresolved agent/
            super_agent reference, a name collision without upsert, or any DB
            write failure (the transaction is rolled back first).
    """
    config = load_team_config(yaml_str)
    ok, err = validate_team_config(config)
    if not ok:
        raise ValueError(err)

    metadata = config["metadata"]
    spec = config["spec"]
    name = metadata["name"].strip()
    members = spec.get("members", [])
    edges = spec.get("edges", [])

    # Validate ALL DB references before opening the write transaction.
    resolved_names = _validate_db_references(members)

    existing = get_team_by_name(name)
    if existing and not upsert:
        raise ValueError(f"A team named {name!r} already exists")
    status = "updated" if existing else "created"

    topology_config = spec.get("topology_config")
    topology_config_str = json.dumps(topology_config) if isinstance(topology_config, dict) else None

    # Single transaction: delete (if upsert) + create + members + edges. Any
    # exception propagates out of the `with` block, where get_connection()
    # rolls back before closing, so nothing is committed on failure.
    with get_connection() as conn:
        if existing and upsert:
            conn.execute("DELETE FROM teams WHERE id = ?", (existing["id"],))

        team_id = _get_unique_team_id(conn)
        try:
            conn.execute(
                """
                INSERT INTO teams (id, name, description, color, leader_id, source,
                                   topology, topology_config, trigger_source, trigger_config)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    team_id,
                    name,
                    metadata.get("description"),
                    metadata.get("color") or "#00d4ff",
                    None,
                    "ui_created",
                    spec.get("topology"),
                    topology_config_str,
                    spec.get("trigger_source"),
                    None,
                ),
            )
        except errors.IntegrityError as exc:
            raise ValueError(f"Failed to create team {name!r}: {exc}") from exc

        member_cols = _get_team_members_columns(conn)
        ref_to_member_id: dict[str, int] = {}
        for member in members:
            ref = _member_ref(member)
            columns = ["team_id", "name", "email", "role", "layer", "description", "agent_id"]
            values: list[Any] = [
                team_id,
                resolved_names.get(ref),
                None,
                member.get("role") or "member",
                member.get("layer") or "backend",
                None,
                member.get("agent_id"),
            ]
            if "super_agent_id" in member_cols:
                columns.append("super_agent_id")
                values.append(member.get("super_agent_id"))
            if "tier" in member_cols and member.get("tier") is not None:
                columns.append("tier")
                values.append(member.get("tier"))
            placeholders = ", ".join("?" for _ in columns)
            col_str = ", ".join(columns)
            try:
                cursor = conn.execute(
                    f"INSERT INTO team_members ({col_str}) VALUES ({placeholders})",
                    tuple(values),
                )
            except errors.IntegrityError as exc:
                raise ValueError(f"Failed to add team member {ref!r}: {exc}") from exc
            ref_to_member_id[ref] = cursor.lastrowid

        for i, edge in enumerate(edges):
            source_id = ref_to_member_id.get(edge["source"])
            target_id = ref_to_member_id.get(edge["target"])
            # validate_team_config guarantees both refs are declared members;
            # a missing id here would be a logic error, not silently ignorable.
            if source_id is None or target_id is None:
                raise ValueError(f"edge {i} references a member that was not created")
            try:
                conn.execute(
                    """
                    INSERT INTO team_edges
                        (team_id, source_member_id, target_member_id, edge_type, label, weight)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        team_id,
                        source_id,
                        target_id,
                        edge.get("edge_type", "delegation"),
                        edge.get("label"),
                        edge.get("weight", 1),
                    ),
                )
            except errors.IntegrityError as exc:
                raise ValueError(
                    f"Failed to add edge {edge['source']!r} -> {edge['target']!r}: {exc}"
                ) from exc

        conn.commit()

    return team_id, status
