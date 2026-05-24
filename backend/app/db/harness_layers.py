"""Repository helpers for the harness_layers IR (T2).

Thin SQL over ``harness_layers``. Business logic — payload parsing, version
bumping, conflict resolution — lives in the service layer.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Optional

from . import harness_skill_index as _skill_index
from .connection import get_connection
from .ids import generate_id

VALID_LAYERS = frozenset({"h2", "h3", "h4", "h5"})
VALID_SOURCE_KINDS = frozenset({"manual", "template", "evolved"})


def _maybe_index_h5(layer_id: str, bot_id: str, layer: str,
                    enabled: bool, payload: dict[str, Any]) -> None:
    """H5 only: keep the FTS5 retrieval index in sync with the layer state."""
    if layer != "h5":
        return
    if enabled:
        try:
            _skill_index.upsert(layer_id, bot_id, payload)
        except Exception:
            # Best-effort; index is read-only at compile time and we fall
            # back to "all skills" when retrieval returns nothing.
            pass
    else:
        try:
            _skill_index.remove(layer_id)
        except Exception:
            pass


def create_layer(
    *,
    bot_id: str,
    layer: str,
    name: str,
    payload: dict[str, Any],
    trigger_id: Optional[str] = None,
    source_kind: str = "manual",
    parent_layer_id: Optional[str] = None,
    version: int = 1,
    enabled: bool = True,
) -> str:
    """Insert a new harness-layer row and return its ID."""
    if layer not in VALID_LAYERS:
        raise ValueError(f"unknown harness layer: {layer!r}")
    if source_kind not in VALID_SOURCE_KINDS:
        raise ValueError(f"unknown source_kind: {source_kind!r}")

    layer_id = generate_id("hl")
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO harness_layers
               (id, bot_id, trigger_id, layer, name, enabled, version,
                parent_layer_id, source_kind, payload_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                layer_id,
                bot_id,
                trigger_id,
                layer,
                name,
                1 if enabled else 0,
                version,
                parent_layer_id,
                source_kind,
                json.dumps(payload, default=str),
            ),
        )
        conn.commit()
    _maybe_index_h5(layer_id, bot_id, layer, enabled, payload)
    return layer_id


def supersede_layer(
    layer_id: str,
    *,
    new_payload: dict[str, Any],
    source_kind: str = "evolved",
) -> str:
    """Disable ``layer_id`` and insert a successor row with version+1 and
    ``parent_layer_id = layer_id``. Returns the new row's ID.

    Atomic: a single transaction so the bot never observes both versions
    active or both disabled simultaneously.
    """
    with get_connection() as conn:
        prior = conn.execute(
            "SELECT bot_id, trigger_id, layer, name, version "
            "FROM harness_layers WHERE id = ?",
            (layer_id,),
        ).fetchone()
        if prior is None:
            raise LookupError(f"harness layer not found: {layer_id}")

        new_id = generate_id("hl")
        conn.execute(
            """INSERT INTO harness_layers
               (id, bot_id, trigger_id, layer, name, enabled, version,
                parent_layer_id, source_kind, payload_json)
               VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)""",
            (
                new_id,
                prior["bot_id"],
                prior["trigger_id"],
                prior["layer"],
                prior["name"],
                prior["version"] + 1,
                layer_id,
                source_kind,
                json.dumps(new_payload, default=str),
            ),
        )
        conn.execute(
            "UPDATE harness_layers SET enabled = 0, updated_at = datetime('now') "
            "WHERE id = ?",
            (layer_id,),
        )
        conn.commit()
    # Keep the H5 retrieval index in sync: the parent gets removed (it's
    # now disabled), the successor gets indexed if it's H5.
    _maybe_index_h5(layer_id, prior["bot_id"], prior["layer"], False, {})
    _maybe_index_h5(
        new_id, prior["bot_id"], prior["layer"], True, new_payload,
    )
    return new_id


def set_enabled(layer_id: str, enabled: bool) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE harness_layers SET enabled = ?, updated_at = datetime('now') "
            "WHERE id = ?",
            (1 if enabled else 0, layer_id),
        )
        conn.commit()
    row = get_layer(layer_id)
    if row is not None:
        _maybe_index_h5(
            layer_id, row["bot_id"], row["layer"], enabled, row["payload"],
        )


def list_enabled_for_bot(
    bot_id: str,
    *,
    trigger_id: Optional[str] = None,
    layers: Optional[Iterable[str]] = None,
) -> list[dict]:
    """Return enabled rows for the bot, optionally narrowed by trigger override.

    Trigger semantics: if ``trigger_id`` is provided, both global rows
    (``trigger_id IS NULL``) and trigger-specific rows are returned. Otherwise
    only global rows are returned.
    """
    sql = [
        "SELECT id, bot_id, trigger_id, layer, name, enabled, version,",
        "       parent_layer_id, source_kind, payload_json,",
        "       created_at, updated_at",
        "FROM harness_layers",
        "WHERE bot_id = ? AND enabled = 1",
    ]
    params: list[Any] = [bot_id]

    if trigger_id is None:
        sql.append("AND trigger_id IS NULL")
    else:
        sql.append("AND (trigger_id IS NULL OR trigger_id = ?)")
        params.append(trigger_id)

    if layers is not None:
        marks = ",".join(["?"] * len(list(layers)))
        # rebuild because the iterable above was consumed
        layer_list = list(layers)
        marks = ",".join(["?"] * len(layer_list))
        sql.append(f"AND layer IN ({marks})")
        params.extend(layer_list)

    sql.append("ORDER BY layer ASC, name ASC, version DESC")

    with get_connection() as conn:
        rows = conn.execute("\n".join(sql), params).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_layer(layer_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, bot_id, trigger_id, layer, name, enabled, version,"
            " parent_layer_id, source_kind, payload_json, created_at, updated_at"
            " FROM harness_layers WHERE id = ?",
            (layer_id,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def _row_to_dict(row) -> dict:
    d = dict(row)
    try:
        d["payload"] = json.loads(d.pop("payload_json"))
    except (TypeError, ValueError):
        d["payload"] = {}
    d["enabled"] = bool(d["enabled"])
    return d
