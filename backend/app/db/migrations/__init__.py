"""Migration runner + registry (v0.7.3c split).

Historically the migrations registry lived in a single ~4900 line module
``backend/app/db/migrations.py``. In v0.7.3c the migration *bodies* were
carved out into version-bucketed sibling modules
(``v04_initial``, ``v05_features``, ``v06_features``, ``v07_features``)
and the runner moved to ``_runner``. This package's ``__init__`` is the
thin orchestrator that re-exports the runner symbols and concatenates
the bucket lists into the canonical ``VERSIONED_MIGRATIONS`` registry
consumed by ``lifecycle.py`` and the legacy
``from app.db.migrations import init_db`` imports throughout the codebase.

Bucket files do not import each other. They may import shared helpers
from ``._runner`` (e.g. ``_validate_sql_identifier``).
"""

from ._runner import (  # noqa: F401  (re-export)
    PREDEFINED_TRIGGER,
    PREDEFINED_TRIGGER_ID,
    PREDEFINED_TRIGGER_IDS,
    PREDEFINED_TRIGGERS,
    VALID_BACKENDS,
    VALID_TRIGGER_SOURCES,
    _bootstrap_schema_version,
    _create_migration_only_tables,
    _ensure_schema_version_table,
    _get_current_version,
    _mark_stale_executions,
    _migrate_to_string_ids,
    _rebuild_table_fk,
    _record_version,
    _validate_sql_identifier,
    init_db,
)
from .v04_initial import V04_MIGRATIONS
from .v05_features import (  # noqa: F401  (re-export for legacy test imports)
    V05_MIGRATIONS,
    _migrate_76_super_agent_dispatch,
)
from .v06_features import (  # noqa: F401  (re-export for legacy test imports)
    V06_MIGRATIONS,
    _migrate_109_session_audit_columns,
    _migrate_113_rotated_from_token_unique,
    _migrate_114_trigger_events,
    _migrate_115_execution_logs_trigger_started_index,
)
from .v07_features import V07_MIGRATIONS

VERSIONED_MIGRATIONS = V04_MIGRATIONS + V05_MIGRATIONS + V06_MIGRATIONS + V07_MIGRATIONS

# Backwards-compatible alias for callers that historically expected
# ``run_migrations`` (the spec's preferred name). The actual entrypoint
# has always been ``init_db`` — keep both bound.
run_migrations = init_db
