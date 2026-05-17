"""Migrations for v0.7.0 track — split out of migrations.py in v0.7.3c.

Hosts v116+ migrations specific to the v0.7.x track. Earlier v0.7.x
migrations (114 trigger_events, 115 execution_logs_trigger_started_index)
live in v06_features alongside the v0.6.x batch because they fall in
the same numeric range.
"""


def _migrate_116_super_agent_activity(conn):
    """v0.7.7: super-agent activity timeline + cost rollup."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS super_agent_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            super_agent_id TEXT NOT NULL,
            session_id TEXT,
            event_type TEXT NOT NULL,
            recorded_at TIMESTAMP NOT NULL,
            payload TEXT NOT NULL,
            cost_tokens_in INTEGER,
            cost_tokens_out INTEGER,
            cost_usd REAL,
            status TEXT NOT NULL DEFAULT 'ok',
            error_message TEXT,
            duration_ms INTEGER
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_saa_super_agent_recorded "
        "ON super_agent_activity(super_agent_id, recorded_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_saa_session_recorded "
        "ON super_agent_activity(session_id, recorded_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_saa_recorded_at "
        "ON super_agent_activity(recorded_at)"
    )


def _migrate_118_backfill_sketch_session_project_id(conn):
    """v0.7.40: backfill ``super_agent_sessions.project_id`` from
    ``sketches.routing_json.session_id`` for direct-SA sketch routing.

    Pre-v0.7.40 ``execute_sketch`` reused ``SuperAgentSessionService.
    get_or_create_session(sa_id)`` without forwarding the sketch's
    project_id, so historical /sketch work on a project produced
    ``super_agent_sessions`` rows with ``project_id = NULL``. Those
    rows never surfaced on the project's Sessions tab.

    Idempotent: only updates rows where ``project_id`` is still NULL
    / empty. Re-running over a fully-migrated DB is a no-op.
    """
    import json as _json

    rows = conn.execute(
        "SELECT id, project_id, routing_json FROM sketches "
        "WHERE project_id IS NOT NULL AND routing_json IS NOT NULL"
    ).fetchall()
    for row in rows:
        rj_raw = row["routing_json"]
        if not rj_raw:
            continue
        try:
            rj = _json.loads(rj_raw)
        except (ValueError, TypeError):
            continue
        session_id = rj.get("session_id") if isinstance(rj, dict) else None
        if not session_id:
            continue
        conn.execute(
            "UPDATE super_agent_sessions SET project_id = ? "
            "WHERE id = ? AND (project_id IS NULL OR project_id = '')",
            (row["project_id"], session_id),
        )


def _migrate_117_model_discovery_cache(conn):
    """v0.7.8: per-(backend_kind, auth_method) model cache with TTL."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS model_discovery_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            backend_kind TEXT NOT NULL,
            auth_method TEXT NOT NULL,
            models_json TEXT NOT NULL,
            discovery_method TEXT NOT NULL,
            discovered_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            error_message TEXT,
            UNIQUE(backend_kind, auth_method)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mdc_expires_at "
        "ON model_discovery_cache(expires_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mdc_discovered_at "
        "ON model_discovery_cache(discovered_at)"
    )


def _migrate_119_session_name_and_yolo(conn) -> None:
    """v0.7.57 — session-start dialog needs to persist name + yolo flag.

    * ``name`` (TEXT, nullable) — user-supplied or backend-generated
      title for the session, shown in the History sidebar.
    * ``auto_title`` (BOOLEAN, default 1) — when true, an empty
      ``name`` should be auto-filled (currently a simple fallback
      based on session id; replaced with a claude-generated summary
      in a follow-up).
    * ``yolo_mode`` (BOOLEAN, default 0) — when true, the backend
      appends ``--dangerously-skip-permissions`` and any per-project
      account whitelist is bypassed. Recorded per-session so the
      audit trail shows which sessions ran without permission gates.
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(project_sessions)")}
    if "name" not in cols:
        conn.execute("ALTER TABLE project_sessions ADD COLUMN name TEXT")
    if "auto_title" not in cols:
        conn.execute(
            "ALTER TABLE project_sessions ADD COLUMN auto_title INTEGER NOT NULL DEFAULT 1"
        )
    if "yolo_mode" not in cols:
        conn.execute(
            "ALTER TABLE project_sessions ADD COLUMN yolo_mode INTEGER NOT NULL DEFAULT 0"
        )


def _migrate_120_project_allowed_accounts(conn) -> None:
    """v0.7.58 — per-project whitelist of AI backend accounts.

    A session that starts with ``yolo_mode=false`` must use an
    ``account_id`` (backend ID, e.g. ``bkd-jc3rl4t4dqw4``) that
    appears in this table for its ``project_id``. Yolo bypasses
    the check.

    ``account_id`` is intentionally a free TEXT column (no FK to
    ``backends`` because that table lives in the sidecar's
    ``ai_accounts.db``, a separate SQLite file). Resolution and
    validation happen at request time.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_allowed_accounts (
            project_id TEXT NOT NULL
              REFERENCES projects(id) ON DELETE CASCADE,
            account_id TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (project_id, account_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_allowed_accounts_project "
        "ON project_allowed_accounts(project_id)"
    )


def _migrate_121_project_forge_bindings(conn) -> None:
    """v0.7.70 — per-project sticky Forge bindings.

    Materializes the "Forge assets I want every session of this
    project to inherit" set. The compiler (``ContextCompilerService``)
    reads these, layers session-level overrides + per-prompt
    attachments on top, and produces a backend-specific
    ``ContextBundle`` (system-prompt text + overlay files + MCP
    config + per-prompt prepend).

    ``kind`` is a free TEXT column whose currently-defined values are
    ``rule|skill|hook|command|mcp_server|plugin``. New kinds (e.g.
    ``persona``) can be added without a schema change.

    ``asset_id`` is also free TEXT because the referenced asset
    tables use heterogeneous PK shapes (rules use ``INTEGER`` PKs,
    skills key by ``name``, MCP servers by ``id`` TEXT). The
    compiler resolves the reference; an unresolved binding is
    skipped with a warning rather than failing the whole compile.

    ``role`` is reserved for kind-specific fanout (e.g. a rule may
    play ``system_prompt`` vs ``always_on`` roles). v1 leaves it
    NULL.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_forge_bindings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  TEXT NOT NULL
              REFERENCES projects(id) ON DELETE CASCADE,
            kind        TEXT NOT NULL,
            asset_id    TEXT NOT NULL,
            role        TEXT,
            enabled     INTEGER NOT NULL DEFAULT 1,
            position    INTEGER NOT NULL DEFAULT 0,
            created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(project_id, kind, asset_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pfb_project_enabled "
        "ON project_forge_bindings(project_id, enabled)"
    )


V07_MIGRATIONS: list = [
    # v0.7.7: super-agent activity inspector — timeline + rollup.
    (116, "super_agent_activity", _migrate_116_super_agent_activity),
    # v0.7.8: cached + auth-aware model discovery.
    (117, "model_discovery_cache", _migrate_117_model_discovery_cache),
    # v0.7.40: data backfill — repair sketches routed to direct SAs
    # before project_id was being passed through to the session.
    (
        118,
        "backfill_sketch_session_project_id",
        _migrate_118_backfill_sketch_session_project_id,
    ),
    # v0.7.57: per-session name, auto-title flag, and yolo mode.
    (119, "session_name_and_yolo", _migrate_119_session_name_and_yolo),
    # v0.7.58: per-project AI backend account whitelist.
    (120, "project_allowed_accounts", _migrate_120_project_allowed_accounts),
    # v0.7.70: per-project Forge context bindings.
    (121, "project_forge_bindings", _migrate_121_project_forge_bindings),
]
