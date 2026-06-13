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
        "CREATE INDEX IF NOT EXISTS idx_saa_recorded_at ON super_agent_activity(recorded_at)"
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
        "CREATE INDEX IF NOT EXISTS idx_mdc_expires_at ON model_discovery_cache(expires_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mdc_discovered_at ON model_discovery_cache(discovered_at)"
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
        conn.execute("ALTER TABLE project_sessions ADD COLUMN yolo_mode INTEGER NOT NULL DEFAULT 0")


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
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id               TEXT NOT NULL
              REFERENCES projects(id) ON DELETE CASCADE,
            kind                     TEXT NOT NULL,
            asset_id                 TEXT NOT NULL,
            role                     TEXT,
            enabled                  INTEGER NOT NULL DEFAULT 1,
            position                 INTEGER NOT NULL DEFAULT 0,
            created_at               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source_scope             TEXT NOT NULL DEFAULT 'project',
            source_shared_binding_id INTEGER,
            conflict_policy          TEXT NOT NULL DEFAULT 'local_wins',
            fingerprint              TEXT,
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
        conn.execute("ALTER TABLE project_sessions ADD COLUMN goal_loop_config TEXT")
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
        conn.execute("ALTER TABLE agent_conversations ADD COLUMN user_id TEXT REFERENCES users(id)")
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
        "CREATE INDEX IF NOT EXISTS idx_phase_reflections_verdict ON phase_reflections(verdict)"
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
        "CREATE INDEX IF NOT EXISTS idx_grd_evolve_runs_session ON grd_evolve_runs(session_id)"
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


def _migrate_142_harness_kg_signals(conn):
    """Life-Harness Phase E2: storage for Tesserae-KG-derived evolution
    signals. Each signal is a piece of KG-discovered guidance (prose
    answer) with a dedup ``signal_id``, a decayed ``weight``, and an
    ``already_forged`` flag; later tasks use them to seed evolution
    rounds. Idempotent."""
    from app.db.schema._harness_kg_signals import create_harness_kg_signals_tables

    create_harness_kg_signals_tables(conn)


def _migrate_143_round_kg_signals_col(conn):
    """Life-Harness Phase E2: add ``input_kg_signals_json`` to existing
    ``harness_evolution_rounds`` tables so a round can persist a snapshot
    of the Tesserae-KG-derived signals that seeded it. PRAGMA-guarded,
    idempotent — fresh DBs already get the column from the CREATE TABLE."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(harness_evolution_rounds)")}
    if "input_kg_signals_json" not in cols:
        conn.execute(
            "ALTER TABLE harness_evolution_rounds "
            "ADD COLUMN input_kg_signals_json TEXT NOT NULL DEFAULT '[]'"
        )


def _migrate_141_projects_tesserae(conn):
    """Add ``tesserae_project_root`` to ``projects`` so each Agented
    project can record where its Tesserae ``.tesserae/`` workspace lives.

    Defaults NULL — opt-in per project. A project with this set
    receives every completed session as a Tesserae import (via the
    ``on_session_complete`` handler), so the project's compiled
    Tesserae graph contains code + docs + agent-session history in
    one queryable store.

    The column holds an ABSOLUTE PATH, not an ID — Tesserae's CLI
    keys on the project root directory, not on opaque ids.
    """
    cursor = conn.execute("PRAGMA table_info(projects)")
    cols = {row[1] for row in cursor.fetchall()}
    if "tesserae_project_root" not in cols:
        conn.execute("ALTER TABLE projects ADD COLUMN tesserae_project_root TEXT")


def _migrate_140_team_executions(conn):
    """Life-Harness team-session observation: persist team executions
    so the takeaway extractor + failure annotator can attach to
    ``session_kind='team_session'`` after the in-memory tracker is
    cleaned up (300 s TTL)."""
    from app.db.schema._team_executions import create_team_execution_tables

    create_team_execution_tables(conn)


def _migrate_139_session_takeaways(conn):
    """Life-Harness positive-learning capture: ``session_takeaways`` table
    holds extracted takeaways from each completed session (the inverse of
    the failure annotator's H2/H3/H4 incident capture)."""
    from app.db.schema._harness_takeaways import create_harness_takeaway_tables

    create_harness_takeaway_tables(conn)


def _migrate_138_session_scope_pivot(conn):
    """Life-Harness session-scope pivot: generalize from trigger-execution
    observation to ALL session producers (super-agent, project session,
    workflow node, trigger execution).

    Renames + reshapes three tables:
        execution_layer_incidents  → session_layer_incidents
        execution_annotations      → session_annotations
        execution_harness_snapshots → session_harness_snapshots

    Each gains a polymorphic ``(session_kind, session_id)`` identifier
    and a denormalized ``project_id`` column. Existing rows backfill as
    ``session_kind='trigger_execution'`` with ``session_id`` = the old
    ``execution_id``.

    Idempotent against fresh installs: if the old tables don't exist,
    just create the new ones directly via the bundle.
    """
    from app.db.schema._harness_annotations import (
        create_harness_annotation_tables,
    )
    from app.db.schema._harness_snapshots import (
        create_harness_snapshot_tables,
    )

    # ── execution_layer_incidents → session_layer_incidents ────────────
    old_exists = _column_exists(conn, "execution_layer_incidents", "execution_id")
    new_exists = _column_exists(conn, "session_layer_incidents", "session_id")
    if old_exists and not new_exists:
        create_harness_annotation_tables(conn)
        conn.execute(
            """INSERT INTO session_layer_incidents
                   (id, session_kind, session_id, project_id, layer, priority,
                    kind, evidence_json, event_index, detector_version, created_at)
               SELECT id, 'trigger_execution', execution_id, NULL, layer, priority,
                      kind, evidence_json, event_index, detector_version, created_at
               FROM execution_layer_incidents"""
        )
        conn.execute("DROP TABLE execution_layer_incidents")
    elif not new_exists:
        create_harness_annotation_tables(conn)

    # ── execution_annotations → session_annotations ────────────────────
    old_exists = _column_exists(conn, "execution_annotations", "execution_id")
    new_exists = _column_exists(conn, "session_annotations", "session_id")
    if old_exists and not new_exists:
        create_harness_annotation_tables(conn)  # idempotent
        conn.execute(
            """INSERT INTO session_annotations
                   (session_kind, session_id, project_id, annotator_version,
                    primary_layer, incident_count, h2_count, h3_count, h4_count,
                    general_count, outcome, annotated_at)
               SELECT 'trigger_execution', execution_id, NULL, annotator_version,
                      primary_layer, incident_count, h2_count, h3_count, h4_count,
                      general_count, outcome, annotated_at
               FROM execution_annotations"""
        )
        conn.execute("DROP TABLE execution_annotations")
    elif not new_exists:
        create_harness_annotation_tables(conn)

    # ── execution_harness_snapshots → session_harness_snapshots ────────
    old_exists = _column_exists(conn, "execution_harness_snapshots", "execution_id")
    new_exists = _column_exists(conn, "session_harness_snapshots", "session_id")
    if old_exists and not new_exists:
        create_harness_snapshot_tables(conn)
        conn.execute(
            """INSERT INTO session_harness_snapshots
                   (session_kind, session_id, project_id, harness_kind,
                    bundle_hash, resolved_bindings_json, created_at)
               SELECT 'trigger_execution', execution_id, project_id, harness_kind,
                      bundle_hash, resolved_bindings_json, created_at
               FROM execution_harness_snapshots"""
        )
        conn.execute("DROP TABLE execution_harness_snapshots")
    elif not new_exists:
        create_harness_snapshot_tables(conn)


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
        conn,
        "execution_harness_snapshots",
        "artifact_json",
    )
    if ehs_old_shape:
        conn.execute("ALTER TABLE execution_harness_snapshots RENAME TO _ehs_old")
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
        conn,
        "harness_evolution_rounds",
        "input_layers_json",
    )
    if her_old_shape:
        conn.execute("ALTER TABLE harness_evolution_rounds RENAME TO _her_old")
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
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='harness_evolution_rounds'"
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


def _migrate_144_token_usage_immutable_date(conn):
    """Cost-dashboard correctness: a session's per-day cost must be FIXED
    once the day has passed. The daily summary grouped on ``recorded_at``,
    which ``_update_usage_if_changed`` rewrites to the session's newest
    message timestamp on every re-collection — so a growing/active session
    silently migrated its whole cost from one day's bucket to another,
    mutating *past* days. Add an immutable ``usage_date`` (YYYY-MM-DD)
    frozen on first insert; the summary groups on it instead. PRAGMA-guarded
    + backfilled from existing rows so historical charts are unchanged at
    migration time.
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(token_usage)")}
    if "usage_date" not in cols:
        conn.execute("ALTER TABLE token_usage ADD COLUMN usage_date TEXT")
        conn.execute(
            "UPDATE token_usage SET usage_date = date(recorded_at) "
            "WHERE usage_date IS NULL AND recorded_at IS NOT NULL"
        )


def _migrate_145_subscription_cost_zero(conn):
    """RETIRED no-op. This briefly zeroed total_cost_usd for OAuth/subscription
    backends, but the chosen UX is to KEep the per-model cost and label it as a
    notional API-equivalent estimate (it is not charged on a subscription).
    Cost is recomputed/restored by the collector on re-collection. Kept as a
    no-op so the migration number stays stable; the original zeroing logic is
    intentionally removed.
    """
    return


def _migrate_146_project_autonomy_config(conn):
    """Phase D/E tables (autonomy + forge propagation) were added to
    ``create_fresh_schema`` but never got migrations, so any DB created before
    those phases lacks them: ``project_autonomy_config`` (the 5-minute
    ``autonomous_apply_job`` crashes with "no such table" every run),
    ``shared_forge_bindings``, ``forge_promotion_evidence``, and
    ``project_shared_forge_adoptions`` (propagation paths). Create them all
    idempotently for existing DBs (CREATE TABLE/INDEX IF NOT EXISTS)."""
    from app.db.schema._forge_promotion import create_forge_promotion_tables
    from app.db.schema._project_autonomy import create_project_autonomy_tables

    create_project_autonomy_tables(conn)
    create_forge_promotion_tables(conn)


def _migrate_147_chat_retry_queue(conn):
    """Chat rate-limit rotation Phase 2 — persistent retry queue. When every
    eligible account is rate-limited, a chat turn is parked in
    ``chat_retry_queue`` and re-dispatched by the ``chat_retry_queue``
    scheduler job once any account's cooldown expires. Added to
    ``create_fresh_schema`` (_misc); this migration creates it idempotently on
    existing DBs."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_retry_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL UNIQUE,
            super_agent_id TEXT NOT NULL,
            backend TEXT,
            account_id TEXT,
            model TEXT,
            cwd TEXT,
            chat_mode TEXT,
            instance_id TEXT,
            use_cli_agent INTEGER,
            attempts INTEGER DEFAULT 0,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_attempt_at TIMESTAMP
        )
        """
    )


def _migrate_148_harness_state(conn):
    """Harness-1 integration Phase 1 (P1): durable run-state store.

    Adds ``harness_runs`` (per-execution step cursor + running budget +
    lifecycle status) and ``harness_checkpoints`` (append-only serialized
    turn ledger), both FK'd to ``execution_logs(execution_id)``. Added to
    ``create_fresh_schema`` (_harness_state); this migration creates them
    idempotently on existing DBs so a crashed run leaves recoverable state
    instead of a stale 'running' row.

    Reference: docs/research/harness-1-integration.md; arXiv:2606.02373.
    """
    from app.db.schema._harness_state import create_harness_state_tables

    create_harness_state_tables(conn)


def _migrate_149_harness_evidence(conn):
    """Harness-1 Phase 2 (P3): typed tool_use evidence ledger keyed by
    session_id. Added to create_fresh_schema; idempotent on existing DBs."""
    from app.db.schema._harness_evidence import create_harness_evidence_tables

    create_harness_evidence_tables(conn)


def _migrate_150_verification_records(conn):
    """Harness-1 Phase 2 (P5): durable verification records keyed by
    execution_id. Added to create_fresh_schema; idempotent on existing DBs."""
    from app.db.schema._verification_records import create_verification_records_tables

    create_verification_records_tables(conn)


def _migrate_151_per_run_budget_limit(conn):
    """Harness-1 Phase 3 (P6): nullable per-run cost ceiling on budget_limits.
    NULL = feature off (default), so existing installs are unchanged.
    PRAGMA-guarded ALTER — idempotent (pattern: _migrate_144)."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(budget_limits)")}
    if "per_run_limit_usd" not in cols:
        conn.execute("ALTER TABLE budget_limits ADD COLUMN per_run_limit_usd REAL")


def _migrate_153_extracted_facts(conn):
    """Agentic-RAG answers T1: session-scoped claim extraction store."""
    from app.db.schema._extracted_facts import create_extracted_facts_tables

    create_extracted_facts_tables(conn)


def _migrate_154_answer_eval(conn):
    """Agentic-RAG answers T1: baseline-vs-pipeline answer eval tables."""
    from app.db.schema._answer_eval import create_answer_eval_tables

    create_answer_eval_tables(conn)


def _migrate_155_subagents(conn):
    """Phase 17-02: register ``subagent`` as a forge primitive. A brand-new,
    SEPARATE table from the legacy ``agents`` table (used by
    HarnessLoaderService._import_agents) — do NOT conflate the two. ``content``
    holds the full ``.claude/agents/<name>.md`` body including frontmatter.
    Idempotent CREATE IF NOT EXISTS."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS subagents (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            content TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            project_id TEXT,
            source_path TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)


def _migrate_156_forge_bundles(conn):
    """Phase 17-03: cross-kind forge bundles. A ``forge_bundles`` row is a
    named, scope-tagged group; ``forge_bundle_items`` holds primitives of ANY
    kind in one bundle (unlike skills-only legacy ``skill_sets``). Idempotent
    CREATE IF NOT EXISTS. Does NOT touch skill_sets / skill_set_items."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS forge_bundles (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            scope TEXT NOT NULL DEFAULT 'project',
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS forge_bundle_items (
            bundle_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (bundle_id, kind, asset_id),
            FOREIGN KEY (bundle_id) REFERENCES forge_bundles(id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_forge_bundle_items_pos "
        "ON forge_bundle_items(bundle_id, position)"
    )


def _migrate_157_forge_origin(conn):
    """Phase 17-06: provenance for session-auto-imported forge primitives.
    Records, per (asset_id, kind), the sha256 content-hash of the source
    ``.claude/`` file at import time plus the session that produced it — so the
    import handler can detect unchanged files (skip) and changed files
    (re-import), and so an operator can audit where an auto-bound primitive came
    from. Idempotent CREATE IF NOT EXISTS."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS forge_origin (
            asset_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            origin_hash TEXT NOT NULL,
            source_session_id TEXT,
            imported_at TEXT NOT NULL,
            PRIMARY KEY (asset_id, kind)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_forge_origin_session ON forge_origin(source_session_id)"
    )


def _migrate_152_resume_recovery(conn):
    """Harness-1 Phase 4: redispatch/resume provenance + per-trigger
    auto-recovery flag. PRAGMA-guarded ALTERs — idempotent."""
    el = {r["name"] for r in conn.execute("PRAGMA table_info(execution_logs)")}
    if "redispatched_from" not in el:
        conn.execute("ALTER TABLE execution_logs ADD COLUMN redispatched_from TEXT")
    tr = {r["name"] for r in conn.execute("PRAGMA table_info(triggers)")}
    if "auto_redispatch" not in tr:
        conn.execute("ALTER TABLE triggers ADD COLUMN auto_redispatch INTEGER DEFAULT 0")
    ps = {r["name"] for r in conn.execute("PRAGMA table_info(project_sessions)")}
    if "resumed_from" not in ps:
        conn.execute("ALTER TABLE project_sessions ADD COLUMN resumed_from TEXT")


def _migrate_158_driver_columns(conn):
    """Phase 19 (19-01): per-scope execution-driver columns for the
    precedence-driven, default-GRD ``resolve_execution_driver()`` resolver.

    Adds two nullable TEXT columns (NULL = inherit the next precedence
    level, ultimately the global default ``"grd"``):

      - ``projects.default_driver`` — a project's fallback driver when no
        more-specific (turn / SuperAgent / instance) source is set.
      - ``project_sa_instances.driver`` — a per-instance override that wins
        over the project default but loses to the SuperAgent config / turn.

    PRAGMA-guarded ALTERs — idempotent under re-run.
    """
    pcols = {row[1] for row in conn.execute("PRAGMA table_info(projects)")}
    if "default_driver" not in pcols:
        conn.execute("ALTER TABLE projects ADD COLUMN default_driver TEXT")
    icols = {row[1] for row in conn.execute("PRAGMA table_info(project_sa_instances)")}
    if "driver" not in icols:
        conn.execute("ALTER TABLE project_sa_instances ADD COLUMN driver TEXT")


def _migrate_159_harness_setup(conn):
    """Phase 21 (21-01): persistence floor for one-click team harness setup.

    Adds ``projects.harness_setup_status`` (TEXT DEFAULT 'none', the
    none/running/ready/failed state machine), mirroring the PRAGMA-guard
    pattern of ``_migrate_v54_project_grd_init_status`` (v05_features.py:38),
    plus a ``harness_setup_steps`` table giving per-step idempotent upsert +
    retry granularity with PK ``(project_id, step_key)``.

    PRAGMA-guarded ALTER + CREATE TABLE IF NOT EXISTS — double-apply is a
    pure no-op.
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(projects)")}
    if "harness_setup_status" not in cols:
        conn.execute("ALTER TABLE projects ADD COLUMN harness_setup_status TEXT DEFAULT 'none'")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS harness_setup_steps (
            project_id TEXT NOT NULL,
            step_key TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            detail TEXT,
            fingerprint TEXT,
            updated_at TEXT,
            PRIMARY KEY (project_id, step_key)
        )
        """
    )


def _migrate_160_skill_sleep(conn):
    """SkillOpt integration: gated skill-optimization run store.

    One row per Skill-Sleep attempt — the blind judge scored the current
    SKILL.md (arm A) vs a candidate body (arm B) on a held-out question
    partition; the candidate is accepted only on strict improvement.
    """
    from app.db.schema._skill_sleep import create_skill_sleep_tables

    create_skill_sleep_tables(conn)


def _migrate_161_skill_sleep_adopted(conn):
    """SkillOpt integration Phase 4: operator-adopt timestamp.

    Adds ``skill_sleep_runs.adopted_at`` (TEXT, nullable) so an accepted
    candidate that has been written to disk is distinguishable from one merely
    awaiting adoption. PRAGMA-guarded ALTER — double-apply is a no-op, and
    fresh DBs already get the column from create_fresh_schema.
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(skill_sleep_runs)")}
    if "adopted_at" not in cols:
        conn.execute("ALTER TABLE skill_sleep_runs ADD COLUMN adopted_at TEXT")


def _migrate_162_skill_sleep_body_hash(conn):
    """SkillOpt integration Phase 4: stale-adoption guard.

    Adds ``skill_sleep_runs.current_body_hash`` (the hash of the current body
    the candidate beat) so adoption can refuse to overwrite a skill that has
    changed since the run was gated. PRAGMA-guarded ALTER; fresh DBs get it
    from create_fresh_schema.
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(skill_sleep_runs)")}
    if "current_body_hash" not in cols:
        conn.execute("ALTER TABLE skill_sleep_runs ADD COLUMN current_body_hash TEXT")


def _migrate_163_skill_sleep_outcome(conn):
    """SkillOpt integration Phase 6: disjoint-split outcome measurement.

    Adds outcome columns so a run can record whether the candidate also
    improved a measured outcome on a held-out partition DISJOINT from the one
    the gate scored — the honest check that the gate did not game itself.
    PRAGMA-guarded ALTERs; fresh DBs get the columns from create_fresh_schema.
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(skill_sleep_runs)")}
    for col, decl in (
        ("outcome_before_score", "REAL"),
        ("outcome_after_score", "REAL"),
        ("outcome_delta", "REAL"),
        ("outcome_question_count", "INTEGER"),
    ):
        if col not in cols:
            conn.execute(f"ALTER TABLE skill_sleep_runs ADD COLUMN {col} {decl}")


def _migrate_164_skill_sleep_current_body(conn):
    """SkillOpt follow-up: store the current SKILL.md body the candidate was
    gated against (not just its hash), so the operator review drawer can render
    a true current-vs-candidate diff. PRAGMA-guarded ALTER; fresh DBs get it
    from create_fresh_schema.
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(skill_sleep_runs)")}
    if "current_body" not in cols:
        conn.execute("ALTER TABLE skill_sleep_runs ADD COLUMN current_body TEXT")


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
    # Life-Harness session-scope pivot: generalize observation from
    # trigger-executions-only to all session producers.
    (138, "session_scope_pivot", _migrate_138_session_scope_pivot),
    # Life-Harness positive-learning capture: session takeaways.
    (139, "session_takeaways", _migrate_139_session_takeaways),
    # Life-Harness team-session observation: durable mirror of the
    # in-memory TeamExecutionTracker so takeaway/annotator can run
    # after the tracker's 5-minute cleanup.
    (140, "team_executions", _migrate_140_team_executions),
    # Life-Harness Tesserae integration: per-project link to the
    # Tesserae workspace that consolidates code + docs + sessions
    # into a typed KG for retrieval.
    (141, "projects_tesserae", _migrate_141_projects_tesserae),
    # Life-Harness Phase E2: Tesserae-KG-derived evolution signals store.
    (142, "harness_kg_signals", _migrate_142_harness_kg_signals),
    # Life-Harness Phase E2: round column persisting seeded KG signals.
    (143, "round_kg_signals_col", _migrate_143_round_kg_signals_col),
    # Cost-dashboard correctness: immutable per-row usage_date so past
    # days' cost cannot drift when active sessions are re-collected.
    (144, "token_usage_immutable_date", _migrate_144_token_usage_immutable_date),
    # Cost correctness: $0 for OAuth/subscription backends (flat fee), only
    # API-key (metered) backends accrue per-token cost.
    (145, "subscription_cost_zero", _migrate_145_subscription_cost_zero),
    # Backfill Phase D autonomy table on pre-Phase-D DBs (was fresh-schema
    # only) so autonomous_apply_job stops crashing with "no such table".
    (146, "project_autonomy_config", _migrate_146_project_autonomy_config),
    # Chat rate-limit rotation Phase 2: persistent retry queue for turns
    # parked when every eligible account is rate-limited.
    (147, "chat_retry_queue", _migrate_147_chat_retry_queue),
    # Harness-1 integration Phase 1: durable harness run-state store
    # (harness_runs step cursor + harness_checkpoints turn ledger) so a
    # crash mid-run leaves recoverable state instead of a stale 'running' row.
    (148, "harness_state", _migrate_148_harness_state),
    # Harness-1 Phase 2: typed tool_use evidence ledger (chat substrate).
    (149, "harness_evidence", _migrate_149_harness_evidence),
    # Harness-1 Phase 2: durable verification records (execution substrate).
    (150, "verification_records", _migrate_150_verification_records),
    # Harness-1 Phase 3: per-run budget ceiling (soft warn 80% / hard kill 100%).
    (151, "per_run_budget_limit", _migrate_151_per_run_budget_limit),
    # Harness-1 Phase 4: restart recovery + resume provenance.
    (152, "resume_recovery", _migrate_152_resume_recovery),
    # Agentic-RAG T1: session-scoped claim extraction + provenance store.
    (153, "extracted_facts", _migrate_153_extracted_facts),
    # Agentic-RAG T1: baseline-vs-pipeline answer eval runs + results.
    (154, "answer_eval", _migrate_154_answer_eval),
    # v0.8.0 (17-03): cross-kind forge bundles (155 reserved for 17-02 subagents).
    (155, "subagents", _migrate_155_subagents),
    (156, "forge_bundles", _migrate_156_forge_bundles),
    (157, "forge_origin", _migrate_157_forge_origin),
    # v0.8.0 (19-01): per-scope execution-driver columns for the
    # precedence-driven, default-GRD resolve_execution_driver() resolver.
    (158, "driver_columns", _migrate_158_driver_columns),
    # v0.8.0 (21-01): persistence floor for one-click team harness setup —
    # projects.harness_setup_status column + harness_setup_steps table.
    (159, "harness_setup", _migrate_159_harness_setup),
    # SkillOpt integration: gated skill-optimization run store.
    (160, "skill_sleep", _migrate_160_skill_sleep),
    # SkillOpt integration Phase 4: operator-adopt timestamp.
    (161, "skill_sleep_adopted", _migrate_161_skill_sleep_adopted),
    # SkillOpt integration Phase 4: stale-adoption guard (current body hash).
    (162, "skill_sleep_body_hash", _migrate_162_skill_sleep_body_hash),
    # SkillOpt integration Phase 6: disjoint-split outcome measurement.
    (163, "skill_sleep_outcome", _migrate_163_skill_sleep_outcome),
    # SkillOpt follow-up: store current body for the review-drawer diff.
    (164, "skill_sleep_current_body", _migrate_164_skill_sleep_current_body),
]
