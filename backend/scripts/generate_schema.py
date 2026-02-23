#!/usr/bin/env python3
"""Generate SCHEMA.md from SQLite introspection of a fresh Agented database.

Usage:
    cd backend && python scripts/generate_schema.py

Creates a temporary database, runs init_db() to build the fresh-path schema,
then introspects every table using SQLite PRAGMAs to produce backend/SCHEMA.md.
"""

import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone

# Ensure backend/ is on the Python path so `app` is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Create a temporary database for introspection
tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db")
os.close(tmp_fd)

try:
    # Patch config before importing database (handles post-config-extraction state)
    try:
        import app.config as config

        config.DB_PATH = tmp_path
    except (ImportError, AttributeError):
        pass

    # Also patch database module directly (handles pre-config-extraction state)
    import app.database as db

    db.DB_PATH = tmp_path  # fallback: patch directly on database module

    # Suppress init_db print output
    from contextlib import redirect_stdout
    from io import StringIO

    with redirect_stdout(StringIO()):
        db.init_db()

    # Now introspect the temporary database
    conn = sqlite3.connect(tmp_path)

    # Get all tables (excluding sqlite_sequence)
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence' ORDER BY name"
    ).fetchall()
    table_names = [row[0] for row in tables]

    lines = []
    lines.append("# Agented Database Schema")
    lines.append("")
    lines.append(
        f"*Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} "
        f"| Tables: {len(table_names)}*"
    )
    lines.append("")

    total_indexes = 0

    for table_name in table_names:
        lines.append(f"## {table_name}")
        lines.append("")

        # Columns via PRAGMA table_info
        cols = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        lines.append("| Column | Type | Nullable | Default | PK |")
        lines.append("|--------|------|----------|---------|-----|")
        for col in cols:
            cid, name, type_, notnull, default, pk = col
            nullable = "NO" if notnull else "YES"
            default_str = str(default) if default is not None else ""
            pk_str = "YES" if pk else ""
            lines.append(f"| {name} | {type_} | {nullable} | {default_str} | {pk_str} |")
        lines.append("")

        # Foreign keys via PRAGMA foreign_key_list
        fks = conn.execute(f"PRAGMA foreign_key_list({table_name})").fetchall()
        if fks:
            lines.append("**Foreign Keys:**")
            lines.append("")
            for fk in fks:
                # fk columns: id, seq, table, from, to, on_update, on_delete, match
                lines.append(f"- `{fk[3]}` -> `{fk[2]}`.`{fk[4]}`")
            lines.append("")

        # Indexes via PRAGMA index_list + PRAGMA index_info
        indexes = conn.execute(f"PRAGMA index_list({table_name})").fetchall()
        if indexes:
            lines.append("**Indexes:**")
            lines.append("")
            for idx in indexes:
                # idx columns: seq, name, unique, origin, partial
                idx_name = idx[1]
                is_unique = idx[2]
                idx_cols = conn.execute(f"PRAGMA index_info({idx_name})").fetchall()
                col_names = [c[2] for c in idx_cols]
                unique_str = "UNIQUE " if is_unique else ""
                lines.append(f"- `{idx_name}` ({unique_str}{', '.join(col_names)})")
                total_indexes += 1
            lines.append("")

    # Add migration-only table note
    lines.append("---")
    lines.append(
        "*Note: 4 additional tables (settings, ai_backends, backend_accounts, "
        "design_conversations) exist only in migration code and are not created "
        "in the fresh-schema path. They will appear in production databases that "
        "have been migrated.*"
    )
    lines.append("")

    conn.close()

    # Write output
    output_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "SCHEMA.md"
    )
    with open(output_path, "w") as f:
        f.write("\n".join(lines))

    print(f"Generated SCHEMA.md with {len(table_names)} tables, {total_indexes} indexes")

finally:
    # Clean up temporary database
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)
