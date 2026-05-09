"""Fresh-database schema. Domain DDL in schema/ package (v0.7.3b).

Public API: ``create_fresh_schema(conn)`` — called by ``init_db()`` when
no existing tables are detected. Each domain module owns one logical
cluster of tables and exposes a single ``create_<domain>_tables`` entry
point. Modules MUST NOT import each other.
"""

import logging

from ._agents import create_agent_tables
from ._core import create_core_tables
from ._embeddings import create_embedding_tables
from ._misc import create_misc_tables
from ._monitoring import create_monitoring_tables
from ._orgs import create_org_tables
from ._plugins import create_plugin_tables
from ._security import create_security_tables
from ._setup import create_setup_tables
from ._skills import create_skill_tables
from ._super_agents import create_super_agent_tables
from ._triggers_infra import create_triggers_infra_tables
from ._workflows import create_workflow_tables

logger = logging.getLogger(__name__)


def create_fresh_schema(conn):
    """Create all tables and indexes on a fresh (empty) database.

    Calls each per-domain DDL module in dependency order, then commits.

    Args:
        conn: An open sqlite3 connection.
    """
    create_core_tables(conn)
    create_agent_tables(conn)
    create_skill_tables(conn)
    create_org_tables(conn)
    create_plugin_tables(conn)
    create_workflow_tables(conn)
    create_security_tables(conn)
    create_monitoring_tables(conn)
    create_triggers_infra_tables(conn)
    create_super_agent_tables(conn)
    create_setup_tables(conn)
    create_embedding_tables(conn)
    create_misc_tables(conn)
    conn.commit()
