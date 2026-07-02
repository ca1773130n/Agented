"""Team YAML authoring service (Phase 26 / REQ-40).

Load, validate, materialize, and export a team topology as a single
human-authorable YAML document.

The import path validates the ENTIRE document before performing any DB
write, so a malformed document can never leave a partially-created team
behind (the partial-state guard). Edge endpoints reference members by a
stable ``ref`` (agent_id, super_agent_id, or member name) rather than by
DB-assigned member ids, which are not portable across instances.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import yaml

from app.database import (
    add_team_edge,
    add_team_member,
    create_team,
    delete_team,
    get_team_by_name,
    get_team_detail,
    get_team_edges,
    get_team_members,
)
from app.models.team import VALID_EDGE_TYPES, VALID_TOPOLOGIES

logger = logging.getLogger(__name__)

CONFIG_VERSION = "1.0"
CONFIG_KIND = "team"

_REQUIRED_KEYS = {"version", "kind", "metadata", "spec"}


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def dump_team_config(config: dict) -> str:
    """Serialize a team config dict to a YAML document."""
    return yaml.dump(config, default_flow_style=False, sort_keys=False, allow_unicode=True)


def load_team_config(yaml_str: str) -> dict:
    """Parse a YAML document into a config dict.

    Raises:
        ValueError: if the document is not valid YAML or not a mapping.
    """
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
# Import (partial-state guarded)
# ---------------------------------------------------------------------------


def import_team(yaml_str: str, upsert: bool = False) -> tuple[str, str]:
    """Materialize a team from a YAML document.

    The whole document is parsed and validated before any DB write. Returns
    ``(team_id, status)`` where status is ``"created"`` or ``"updated"``.

    Raises:
        ValueError: on parse/validation failure, name collision without
            upsert, or a DB write failure.
    """
    config = load_team_config(yaml_str)
    ok, err = validate_team_config(config)
    if not ok:
        raise ValueError(err)

    metadata = config["metadata"]
    spec = config["spec"]
    name = metadata["name"].strip()

    existing = get_team_by_name(name)
    if existing and not upsert:
        raise ValueError(f"A team named {name!r} already exists")

    status = "created"
    if existing and upsert:
        delete_team(existing["id"])
        status = "updated"

    topology_config = spec.get("topology_config")
    topology_config_str = json.dumps(topology_config) if isinstance(topology_config, dict) else None

    team_id = create_team(
        name=name,
        description=metadata.get("description"),
        color=metadata.get("color") or "#00d4ff",
        topology=spec.get("topology"),
        topology_config=topology_config_str,
        trigger_source=spec.get("trigger_source"),
    )
    if not team_id:
        raise ValueError("Failed to create team (name collision or DB error)")

    ref_to_member_id: dict[str, int] = {}
    for member in spec.get("members", []):
        ref = _member_ref(member)
        member_id = add_team_member(
            team_id=team_id,
            name=member.get("name"),
            role=member.get("role") or "member",
            layer=member.get("layer") or "backend",
            agent_id=member.get("agent_id"),
            super_agent_id=member.get("super_agent_id"),
            tier=member.get("tier"),
        )
        if member_id is not None:
            ref_to_member_id[ref] = member_id

    for edge in spec.get("edges", []):
        source_id = ref_to_member_id.get(edge["source"])
        target_id = ref_to_member_id.get(edge["target"])
        if source_id is None or target_id is None:
            continue
        add_team_edge(
            team_id=team_id,
            source_member_id=source_id,
            target_member_id=target_id,
            edge_type=edge.get("edge_type", "delegation"),
            label=edge.get("label"),
            weight=edge.get("weight", 1),
        )

    return team_id, status
