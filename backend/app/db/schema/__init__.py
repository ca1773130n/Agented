"""Fresh-database schema. Domain DDL in schema/ package (v0.7.3b).

Public API: ``create_fresh_schema(conn)`` — called by ``init_db()`` when
no existing tables are detected. Each domain module owns one logical
cluster of tables and exposes a single ``create_<domain>_tables`` entry
point. Modules MUST NOT import each other.
"""

import logging

from ._agents import create_agent_tables
from ._answer_eval import create_answer_eval_tables
from ._core import create_core_tables
from ._embeddings import create_embedding_tables
from ._extracted_facts import create_extracted_facts_tables
from ._forge_promotion import create_forge_promotion_tables
from ._harness_annotations import create_harness_annotation_tables
from ._harness_evidence import create_harness_evidence_tables
from ._harness_evolution import create_harness_evolution_tables
from ._harness_kg_signals import create_harness_kg_signals_tables
from ._harness_snapshots import create_harness_snapshot_tables
from ._harness_state import create_harness_state_tables
from ._harness_takeaways import create_harness_takeaway_tables
from ._misc import create_misc_tables
from ._monitoring import create_monitoring_tables
from ._orgs import create_org_tables
from ._plugins import create_plugin_tables
from ._project_autonomy import create_project_autonomy_tables
from ._security import create_security_tables
from ._setup import create_setup_tables
from ._skills import create_skill_tables
from ._super_agents import create_super_agent_tables
from ._team_executions import create_team_execution_tables
from ._triggers_infra import create_triggers_infra_tables
from ._verification_records import create_verification_records_tables
from ._workflows import create_workflow_tables

logger = logging.getLogger(__name__)


def create_fresh_schema(conn):
    """Create all tables and indexes on a fresh (empty) database.

    Calls each per-domain DDL module in FK dependency order — referenced
    tables come before their referencing tables. SQLite does not validate
    FK targets at CREATE TABLE time, but matching dependency order keeps
    intent explicit and survives a future migration to a stricter dialect.

    Note: ``_super_agents.super_agents`` references ``teams`` and
    ``_orgs.team_members`` references ``super_agents`` — a true cycle.
    SQLite tolerates one direction of unresolved FK at CREATE time, so we
    create ``_super_agents`` first; the reverse edge resolves at INSERT.

    Args:
        conn: An open sqlite3 connection.
    """
    create_agent_tables(conn)
    create_super_agent_tables(conn)
    create_harness_evidence_tables(conn)
    create_org_tables(conn)
    create_skill_tables(conn)
    create_core_tables(conn)
    create_verification_records_tables(conn)
    create_workflow_tables(conn)
    create_security_tables(conn)
    create_plugin_tables(conn)
    create_triggers_infra_tables(conn)
    create_setup_tables(conn)
    create_embedding_tables(conn)
    create_misc_tables(conn)
    create_monitoring_tables(conn)
    create_harness_annotation_tables(conn)
    create_harness_snapshot_tables(conn)
    create_harness_evolution_tables(conn)
    create_harness_takeaway_tables(conn)
    create_harness_state_tables(conn)
    create_team_execution_tables(conn)
    create_project_autonomy_tables(conn)
    create_forge_promotion_tables(conn)
    create_harness_kg_signals_tables(conn)
    create_extracted_facts_tables(conn)
    create_answer_eval_tables(conn)
    conn.commit()
