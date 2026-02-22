"""Database operations for Hive.

This module is a backward-compatibility shim. All database functions
have been moved to the app.db package. This module re-exports everything
from app.db so that existing imports continue to work.

For new code, import directly from app.db or its sub-modules:
    from app.db import add_trigger
    from app.db.triggers import add_trigger
"""

from app.db import *  # noqa: F401, F403

# Private names required by lazy imports in migrations.py and tests.
# `import *` skips underscore-prefixed names, so we import them explicitly.
from app.db import (  # noqa: F401
    _create_symlink,
    _ensure_symlink_dir,
    _generate_short_id,
    _generate_symlink_name,
    _get_unique_agent_id,
    _get_unique_conversation_id,
    _get_unique_plugin_id,
    _get_unique_product_id,
    _get_unique_project_id,
    _get_unique_team_id,
    _get_unique_trigger_id,
    _remove_symlink,
    _sanitize_name,
)
