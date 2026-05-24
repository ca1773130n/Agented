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


def _migrate_122_goal_loop(conn) -> None:
    """v0.7.74 — goal-loop execution type.

    Adds ``project_sessions.goal_loop_config`` (JSON, nullable) and a
    new ``goal_loop_iterations`` audit table. The config column is
    JSON-shaped so adding fields (e.g. ``judge_temperature``) doesn't
    require another migration. The iteration table is the operator's
    "why did it stop on turn 7?" trail — each iteration captures the
    judge's verdict + reason + judging cost so a goal loop's behavior
    is fully reconstructible after the fact.
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(project_sessions)").fetchall()}
    if "goal_loop_config" not in cols:
        conn.execute(
            "ALTER TABLE project_sessions ADD COLUMN goal_loop_config TEXT"
        )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS goal_loop_iterations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT NOT NULL,
            iteration       INTEGER NOT NULL,
            started_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ended_at        TIMESTAMP,
            verdict         TEXT,
            judge_source    TEXT NOT NULL,
            judge_reason    TEXT,
            judge_stdout    TEXT,
            tokens_in       INTEGER,
            tokens_out      INTEGER,
            cost_usd        REAL,
            UNIQUE(session_id, iteration)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_goal_iter_session "
        "ON goal_loop_iterations(session_id, iteration)"
    )


def _migrate_123_skill_conversations(conn) -> None:
    """v0.7.78 — persist skill-creation conversations to DB so
    ``/skills/new`` survives page refresh + backend restart.

    Previously the ``SkillConversationService._conversations`` dict
    was the only store; refreshing the wizard or restarting the
    backend silently lost every in-flight conversation. The new
    table is the durable record; the in-memory dict is now a hot
    cache for the live SSE stream plus a write-through buffer
    that flushes after each message append.

    ``messages_json`` is the full ``ConversationMessage[]`` array
    serialized as JSON — same shape the in-memory dict held —
    so rehydration is a direct ``json.loads``. We don't normalize
    into a per-message rows table because the wizard always
    consumes the whole list and per-row joins would add latency
    to the chat hot path with no read benefit.

    ``user_id`` mirrors the pattern from other owned-entity tables
    (rules, hooks, etc.); ``legacy@local`` fills the column when
    auth isn't surfaced.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS skill_conversations (
            id              TEXT PRIMARY KEY,
            user_id         TEXT REFERENCES users(id),
            status          TEXT NOT NULL DEFAULT 'active',
            messages_json   TEXT NOT NULL,
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_skill_conv_user_status "
        "ON skill_conversations(user_id, status, updated_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_skill_conv_updated_at "
        "ON skill_conversations(updated_at DESC)"
    )


def _migrate_124_design_conversations_user_id(conn) -> None:
    """v0.7.83 — multi-tenant safety: add ``user_id`` to
    ``design_conversations`` so the wizard auto-resume + list
    endpoints can scope to the calling operator instead of
    leaking every active conv across users.

    Mirrors the v0.7.78 skill_conversations.user_id pattern. The
    column is nullable for backwards compat (legacy rows from
    pre-multi-tenant builds get NULL and are visible to
    bootstrap callers only, via the same IS NULL semantics the
    skill_conversations list helper uses).
    """
    cursor = conn.execute("PRAGMA table_info(design_conversations)")
    cols = {row[1] for row in cursor.fetchall()}
    if "user_id" not in cols:
        conn.execute(
            "ALTER TABLE design_conversations ADD COLUMN user_id TEXT REFERENCES users(id)"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_dc_user_status "
        "ON design_conversations(user_id, status, updated_at DESC)"
    )


def _migrate_125_agent_conversations_user_id(conn) -> None:
    """v0.7.83 — same as v124 but for ``agent_conversations``.
    AgentConversationService doesn't trigger an LLM call at
    start so it doesn't have the kickoff race, but it still
    needs per-user scoping for list / ownership checks.
    """
    cursor = conn.execute("PRAGMA table_info(agent_conversations)")
    cols = {row[1] for row in cursor.fetchall()}
    if "user_id" not in cols:
        conn.execute(
            "ALTER TABLE agent_conversations ADD COLUMN user_id TEXT REFERENCES users(id)"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_conv_user_status "
        "ON agent_conversations(user_id, status, updated_at DESC)"
    )


def _migrate_126_plugin_conversations(conn) -> None:
    """v0.7.83 — new ``plugin_conversations`` table mirroring the
    v0.7.78 skill_conversations schema. PluginConversationService
    previously had only an in-memory dict; this gives /plugins/new
    survival across page refresh + backend restart, with the same
    user_id-scoped resume + ownership semantics skill enjoys.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS plugin_conversations (
            id              TEXT PRIMARY KEY,
            user_id         TEXT REFERENCES users(id),
            status          TEXT NOT NULL DEFAULT 'active',
            messages_json   TEXT NOT NULL,
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_plugin_conv_user_status "
        "ON plugin_conversations(user_id, status, updated_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_plugin_conv_updated_at "
        "ON plugin_conversations(updated_at DESC)"
    )


def _migrate_127_grd_ouroboros_artifacts(conn) -> None:
    """v0.7.85 — DB-side mirror for the v0.3.24 Ouroboros artifacts.

    GRD v0.3.24 writes three new artifact families that Agented now
    surfaces in the planning UI:
      * Per-phase ``REFLECTION.md`` — hypothesis → predicted →
        actual → verdict (per the Ouroboros hypothesis loop).
      * Per-project ``DEAD-ENDS.md`` — falsified approaches with
        provenance (manual entry vs. promoted from a phase reflection).
      * Per-project ``GENOME.md`` — append-only strategy snapshots.

    Three new tables, parallel to the existing GRD tables in
    layout (TEXT PK with prefix, FK back to project / phase). Plus
    three additive columns on ``project_plans`` to capture the
    ``hypothesis`` / ``predicted_outcome`` / ``verdict`` frontmatter
    scalars the v0.3.24 planner emits — the parser tolerates extra
    keys, but we type the columns so the UI doesn't have to round-
    trip through ``tasks_json``.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS phase_reflections (
            id                  TEXT PRIMARY KEY,
            phase_id            TEXT NOT NULL REFERENCES project_phases(id) ON DELETE CASCADE,
            hypothesis          TEXT,
            predicted_outcome   TEXT,
            actual_outcome      TEXT,
            verdict             TEXT,
            evidence            TEXT,
            source_path         TEXT,
            content_hash        TEXT,
            recorded_at         TIMESTAMP,
            created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_phase_reflections_phase "
        "ON phase_reflections(phase_id, recorded_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_phase_reflections_verdict "
        "ON phase_reflections(verdict)"
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_dead_ends (
            id                  TEXT PRIMARY KEY,
            project_id          TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            approach            TEXT NOT NULL,
            reason              TEXT NOT NULL,
            phase_label         TEXT,
            source              TEXT NOT NULL DEFAULT 'manual',
            recorded_at         TIMESTAMP,
            created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_dead_ends_project "
        "ON project_dead_ends(project_id, recorded_at DESC)"
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS project_genome_snapshots (
            id                  TEXT PRIMARY KEY,
            project_id          TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            sequence_number     INTEGER NOT NULL,
            content             TEXT NOT NULL,
            content_hash        TEXT,
            captured_at         TIMESTAMP,
            created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_genome_snapshots_project "
        "ON project_genome_snapshots(project_id, sequence_number DESC)"
    )

    # Additive columns on project_plans for the v0.3.24 frontmatter
    # scalars. ``PRAGMA table_info`` keeps the migration idempotent.
    cursor = conn.execute("PRAGMA table_info(project_plans)")
    cols = {row[1] for row in cursor.fetchall()}
    for col in ("hypothesis", "predicted_outcome", "verdict"):
        if col not in cols:
            conn.execute(f"ALTER TABLE project_plans ADD COLUMN {col} TEXT")


def _migrate_128_goal_loop_ouroboros(conn) -> None:
    """v0.7.86 — Ouroboros adaptation in ``GoalLoopRunner`` (Layer C
    of the GRD v0.3.24 migration).

    Adds three additive columns to ``goal_loop_iterations`` so the
    runner can persist the per-iteration hypothesis loop alongside
    the existing binary met/not-met verdict:

      * ``hypothesis`` — what the iteration's agent claimed it
        would do
      * ``predicted_outcome`` — the testable prediction
      * ``ouroboros_verdict`` — 4-state verdict
        (``confirmed`` / ``partial`` / ``falsified`` / ``unknown``)
        as judged after the iteration completes; lives alongside
        the legacy ``verdict`` column rather than replacing it so
        pre-v0.7.86 rows don't need backfill.

    Plus a new ``goal_loop_dead_ends`` table — session-scoped
    record of falsified approaches so the runner can inject them
    into subsequent iteration prompts. Modeled on GRD's
    ``DEAD-ENDS.md`` registry but unique per ``session_id`` rather
    than per project (a goal loop owns its own attempt history).
    """
    cursor = conn.execute("PRAGMA table_info(goal_loop_iterations)")
    cols = {row[1] for row in cursor.fetchall()}
    for col in ("hypothesis", "predicted_outcome", "ouroboros_verdict"):
        if col not in cols:
            conn.execute(f"ALTER TABLE goal_loop_iterations ADD COLUMN {col} TEXT")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS goal_loop_dead_ends (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT NOT NULL,
            iteration       INTEGER NOT NULL,
            approach        TEXT NOT NULL,
            reason          TEXT NOT NULL,
            evidence        TEXT,
            approach_hash   TEXT NOT NULL,
            recorded_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, approach_hash)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_gl_dead_ends_session "
        "ON goal_loop_dead_ends(session_id, recorded_at DESC)"
    )


def _migrate_129_grd_evolve_runs(conn) -> None:
    """v0.7.88 — track ``gd evolve`` sessions.

    ``gd evolve`` is GRD's self-improvement loop: discover →
    group → execute → review → repeat. Each run can last hours
    and spawns multiple Claude subprocesses, so we can't treat
    it as a single PSM session and call it a day — operators
    need iteration progress visibility across page reloads, plus
    a row to point a "stop" button at.

    The schema mirrors ``goal_loop_iterations`` in shape but
    keys on the parent ``session_id`` (one row per evolve run)
    and stores the full ``EVOLVE-STATE.json`` payload as
    ``last_state_json`` so the UI can render selected groups
    and per-item status without a CLI hop. A periodic sync
    thread (see ``app/services/grd_evolve_runner.py``) polls
    the file on disk and writes through here every ~30s while
    the session is active.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS grd_evolve_runs (
            id                      TEXT PRIMARY KEY,
            project_id              TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            session_id              TEXT NOT NULL UNIQUE,
            status                  TEXT NOT NULL DEFAULT 'active',
            config_json             TEXT,
            iteration               INTEGER NOT NULL DEFAULT 0,
            total_iterations        INTEGER,
            pick_pct                INTEGER,
            last_state_json         TEXT,
            last_state_synced_at    TIMESTAMP,
            started_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ended_at                TIMESTAMP,
            error_message           TEXT,
            created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_grd_evolve_runs_project "
        "ON grd_evolve_runs(project_id, started_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_grd_evolve_runs_session "
        "ON grd_evolve_runs(session_id)"
    )


def _migrate_130_project_sessions_super_agent_link(conn) -> None:
    """v0.7.92 — link goal_loop sessions spawned from a SuperAgent
    back to the originating SA.

    The v0.7.91 bridge ``POST /admin/super-agents/{sa_id}/ouroboros-runs``
    creates a ``project_sessions`` row but loses the SA pointer
    immediately afterward — the run appears in the project's
    session list but not on the SuperAgent's activity surface.
    Adding ``super_agent_id`` as a nullable column lets the SA
    detail page list its own Ouroboros runs without joining
    against external state, and keeps existing project_sessions
    rows valid (column defaults to NULL for non-SA-spawned runs).
    """
    cursor = conn.execute("PRAGMA table_info(project_sessions)")
    cols = {row[1] for row in cursor.fetchall()}
    if "super_agent_id" not in cols:
        # ``ON DELETE SET NULL`` so deleting a SuperAgent doesn't
        # cascade-delete the project_sessions row (the run still
        # happened — its history shouldn't disappear) and doesn't
        # block the SA delete entirely (the default ``NO ACTION``
        # behaviour would, once FK enforcement is on for this
        # connection).
        conn.execute(
            "ALTER TABLE project_sessions ADD COLUMN super_agent_id TEXT "
            "REFERENCES super_agents(id) ON DELETE SET NULL"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_sessions_super_agent "
        "ON project_sessions(super_agent_id, started_at DESC)"
    )


def _migrate_137_harness_forge_pivot(conn):
    """Life-Harness pivot: drop the parallel ``harness_layers`` /
    ``harness_skill_index`` tables (Forge already owns rules/skills/hooks/
    commands/mcp_servers) and re-key the audit tables on ``project_id``
    instead of ``bot_id``.

    ``harness_evolution_rounds`` and ``execution_harness_snapshots`` are
    rebuilt because SQLite can't ALTER existing column constraints; the
    rebuild widens nullability on ``bot_id`` and adds the project-side
    columns. Existing rows are preserved with NULL ``project_id`` — they
    remain queryable as historical audit but won't participate in the new
    project-scoped evolution loop.
    """
    # 1. Drop the duplicates-of-Forge tables. IF EXISTS so the migration
    #    is idempotent and a fresh install (where these never landed)
    #    is a no-op.
    conn.execute("DROP TABLE IF EXISTS harness_skill_index")
    conn.execute("DROP TABLE IF EXISTS harness_layers")

    # 2. Rebuild ``execution_harness_snapshots`` — but only when the table
    #    still has the pre-pivot shape (the fresh-install bundle creates
    #    the new shape directly, so this migration is a no-op there).
    ehs_old_shape = _column_exists(
        conn, "execution_harness_snapshots", "artifact_json",
    )
    if ehs_old_shape:
        conn.execute(
            "ALTER TABLE execution_harness_snapshots RENAME TO _ehs_old"
        )
        from app.db.schema._harness_snapshots import (
            create_harness_snapshot_tables,
        )
        create_harness_snapshot_tables(conn)
        conn.execute(
            """INSERT INTO execution_harness_snapshots
                   (execution_id, project_id, bot_id, harness_kind,
                    bundle_hash, resolved_bindings_json, created_at)
               SELECT execution_id, NULL, bot_id, harness_kind,
                      NULL, '[]', created_at
               FROM _ehs_old"""
        )
        conn.execute("DROP TABLE _ehs_old")

    # 3. Rebuild ``harness_evolution_rounds`` — same idempotency probe.
    her_old_shape = _column_exists(
        conn, "harness_evolution_rounds", "input_layers_json",
    )
    if her_old_shape:
        conn.execute(
            "ALTER TABLE harness_evolution_rounds RENAME TO _her_old"
        )
        from app.db.schema._harness_evolution import (
            create_harness_evolution_tables,
        )
        create_harness_evolution_tables(conn)
        # Backfill rounds with NULL project_id — they predate the pivot
        # and stay as historical audit. New rounds carry project_id.
        # NOTE: the new table requires project_id NOT NULL. To keep the
        # legacy rows we relax it by storing the old bot_id there as a
        # placeholder so the constraint passes; consumers filter on
        # ``status = 'applied'`` for impact computations and the placeholder
        # never matches a real project id.
        conn.execute(
            """INSERT INTO harness_evolution_rounds
                   (id, project_id, started_at, finished_at, status,
                    input_window_since, input_window_until, input_execution_count,
                    input_forge_json, output_patch_json, applied_asset_ids_json,
                    error_message, notes, scratch_dir)
               SELECT id,
                      COALESCE(NULLIF(bot_id, ''), 'legacy-pre-pivot') AS project_id,
                      started_at, finished_at, status,
                      input_window_since, input_window_until, input_execution_count,
                      COALESCE(input_layers_json, '{}'),
                      output_patch_json,
                      COALESCE(applied_layer_ids_json, '[]'),
                      error_message, notes, scratch_dir
               FROM _her_old"""
        )
        conn.execute("DROP TABLE _her_old")


def _column_exists(conn, table: str, column: str) -> bool:
    """Probe ``PRAGMA table_info`` to see whether a column is present."""
    try:
        cursor = conn.execute(f"PRAGMA table_info({table})")
        return any(row[1] == column for row in cursor.fetchall())
    except Exception:
        return False


def _migrate_136_harness_skill_index(conn):
    """Life-Harness T-final: FTS5 index over H5 procedural skills (historical).

    Removed by migration 137 (Forge pivot — Forge owns skills directly).
    DDL inlined so the migration chain stays runnable post-pivot.
    """
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS harness_skill_index USING fts5(
            layer_id UNINDEXED,
            bot_id UNINDEXED,
            title,
            when_clause,
            recipe,
            tags
        )
        """
    )


def _migrate_135_harness_evolution_dry_run(conn):
    """Life-Harness T3 dry-run: widen ``status`` CHECK to include
    ``'awaiting_approval'``. SQLite can't ALTER a CHECK constraint, so we
    rebuild the table (rename → fresh CREATE with new schema → INSERT-SELECT
    → drop old → recreate indexes).

    Idempotent against the post-state: if the column already permits
    ``'awaiting_approval'`` we leave the table alone.
    """
    # Probe: try inserting a sentinel under the new state to see if the
    # constraint already permits it. Cheaper than parsing sqlite_master.
    cur = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' "
        "AND name='harness_evolution_rounds'"
    )
    row = cur.fetchone()
    if row is None:
        # Migration 134 hasn't run yet — nothing to widen. (Should not
        # happen in normal ordering but be safe.)
        from app.db.schema._harness_evolution import (
            create_harness_evolution_tables,
        )
        create_harness_evolution_tables(conn)
        return
    if "'awaiting_approval'" in (row[0] or ""):
        return  # already widened

    conn.execute("ALTER TABLE harness_evolution_rounds RENAME TO _her_old")
    from app.db.schema._harness_evolution import (
        create_harness_evolution_tables,
    )
    create_harness_evolution_tables(conn)
    conn.execute(
        """INSERT INTO harness_evolution_rounds (
               id, bot_id, started_at, finished_at, status,
               input_window_since, input_window_until, input_execution_count,
               input_layers_json, output_patch_json, applied_layer_ids_json,
               error_message, notes, scratch_dir
           )
           SELECT id, bot_id, started_at, finished_at, status,
                  input_window_since, input_window_until, input_execution_count,
                  input_layers_json, output_patch_json, applied_layer_ids_json,
                  error_message, notes, scratch_dir
           FROM _her_old"""
    )
    conn.execute("DROP TABLE _her_old")


def _migrate_134_harness_evolution(conn):
    """Life-Harness T3: per-round audit table for the Codex-driven
    evolution loop. Idempotent.

    Reference: arXiv 2605.22166 §5.2 Evolution Dynamics.
    """
    from app.db.schema._harness_evolution import create_harness_evolution_tables

    create_harness_evolution_tables(conn)


def _migrate_133_harness_snapshots(conn):
    """Life-Harness T2 integration: per-execution snapshot of the active
    harness IR. Capture-only — does not yet inject into the spawn argv/env.
    Feeds T3's evolution loop (which has to attribute trajectories to
    harness versions). Idempotent.
    """
    from app.db.schema._harness_snapshots import create_harness_snapshot_tables

    create_harness_snapshot_tables(conn)


def _migrate_132_harness_layers(conn):
    """Life-Harness T2: harness_layers table (historical).

    NOTE: this table is removed by migration 137 (Forge pivot). The DDL
    is inlined here rather than imported from a schema bundle because the
    bundle file no longer exists post-pivot. We keep the migration runnable
    on its own so the version chain stays intact.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS harness_layers (
            id               TEXT    PRIMARY KEY,
            bot_id           TEXT    NOT NULL,
            trigger_id       TEXT,
            layer            TEXT    NOT NULL,
            name             TEXT    NOT NULL,
            enabled          INTEGER NOT NULL DEFAULT 1,
            version          INTEGER NOT NULL DEFAULT 1,
            parent_layer_id  TEXT,
            source_kind      TEXT    NOT NULL DEFAULT 'manual',
            payload_json     TEXT    NOT NULL DEFAULT '{}',
            created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at       TEXT    NOT NULL DEFAULT (datetime('now'))
        )
        """
    )


def _migrate_131_harness_annotations(conn):
    """Life-Harness T1: per-execution interface-failure annotation tables.

    Adds ``execution_layer_incidents`` (one row per detected H2/H3/H4
    incident) and ``execution_annotations`` (denormalized per-execution
    roll-up consumed by the Activity-lane execution-inspector tile).

    Idempotent ``CREATE TABLE IF NOT EXISTS`` blocks — safe on existing
    installs and on a fresh DB that already ran ``create_fresh_schema``.

    Reference: arXiv 2605.22166 (Life-Harness, Appendix A.1).
    """
    from app.db.schema._harness_annotations import create_harness_annotation_tables

    create_harness_annotation_tables(conn)


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
    # v0.7.74: goal-loop execution type — per-session config blob +
    # iteration audit table.
    (122, "goal_loop", _migrate_122_goal_loop),
    # v0.7.78: persist skill-creation conversations so /skills/new
    # survives page refresh + backend restart.
    (123, "skill_conversations", _migrate_123_skill_conversations),
    # v0.7.83: multi-tenant safety + persistence sweep for the
    # remaining wizards. Adds user_id scoping to design_conversations
    # (commands/hooks/rules) and agent_conversations, and introduces
    # plugin_conversations with the v0.7.78 skill schema so /plugins/new
    # survives refresh + restart.
    (124, "design_conversations_user_id", _migrate_124_design_conversations_user_id),
    (125, "agent_conversations_user_id", _migrate_125_agent_conversations_user_id),
    (126, "plugin_conversations", _migrate_126_plugin_conversations),
    # v0.7.85: GRD v0.3.24 Ouroboros artifact mirror — phase
    # reflections (hypothesis/verdict), project-scoped dead-ends,
    # genome snapshots, plus hypothesis/predicted_outcome/verdict
    # columns on project_plans.
    (127, "grd_ouroboros_artifacts", _migrate_127_grd_ouroboros_artifacts),
    # v0.7.86: Ouroboros adaptation in GoalLoopRunner — adds
    # hypothesis / predicted_outcome / ouroboros_verdict columns
    # to goal_loop_iterations, plus per-session dead-ends table.
    (128, "goal_loop_ouroboros", _migrate_128_goal_loop_ouroboros),
    # v0.7.88: ``gd evolve`` integration — long-running session
    # tracking with periodic EVOLVE-STATE.json sync.
    (129, "grd_evolve_runs", _migrate_129_grd_evolve_runs),
    # v0.7.92: link goal_loop sessions spawned from a SuperAgent
    # back to the originating SA so the SA's activity surface
    # can list its own Ouroboros runs.
    (130, "project_sessions_super_agent_link", _migrate_130_project_sessions_super_agent_link),
    # Life-Harness T1: per-execution interface-failure annotation tables.
    (131, "harness_annotations", _migrate_131_harness_annotations),
    # Life-Harness T2: harness_layers IR (H2/H3/H4/H5 first-class rows).
    (132, "harness_layers", _migrate_132_harness_layers),
    # Life-Harness T2 integration: per-execution snapshot table (capture-only).
    (133, "harness_snapshots", _migrate_133_harness_snapshots),
    # Life-Harness T3: per-round audit table for the Codex evolution loop.
    (134, "harness_evolution", _migrate_134_harness_evolution),
    # Life-Harness T3 dry-run: widen status CHECK to allow awaiting_approval.
    (135, "harness_evolution_dry_run", _migrate_135_harness_evolution_dry_run),
    # Life-Harness T-final: FTS5 BM25 index for H5 procedural skills.
    (136, "harness_skill_index", _migrate_136_harness_skill_index),
    # Life-Harness Forge pivot: drop parallel IR; project-scope evolution.
    (137, "harness_forge_pivot", _migrate_137_harness_forge_pivot),
]
