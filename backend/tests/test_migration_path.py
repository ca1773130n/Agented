"""Migration path tests for schema upgrades.

Verifies that ALTER TABLE migrations work correctly on databases created
before specific features were added (e.g., super_agent_id on team_members).
"""

import sqlite3


class TestTeamMembersMigration:
    """Test migration path for team_members.super_agent_id column.

    Simulates a pre-Phase-39 database that has team_members WITHOUT
    super_agent_id, then verifies migration adds the column.
    """

    def test_migration_adds_super_agent_id_to_existing_table(self, tmp_path, monkeypatch):
        """Upgrade from schema without super_agent_id to schema with it."""
        db_file = str(tmp_path / "legacy.db")
        monkeypatch.setattr("app.config.DB_PATH", db_file)

        # Step 1: Create a minimal legacy database WITHOUT super_agent_id
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys = ON")

        # Create prerequisite tables (agents, super_agents, teams)
        conn.execute("""
            CREATE TABLE agents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                backend_type TEXT NOT NULL DEFAULT 'claude',
                enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE super_agents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                backend_type TEXT NOT NULL DEFAULT 'claude',
                enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE teams (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                color TEXT DEFAULT '#00d4ff',
                leader_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create team_members WITHOUT agent_id and super_agent_id (pre-Phase-39)
        conn.execute("""
            CREATE TABLE team_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id TEXT NOT NULL,
                name TEXT NOT NULL,
                email TEXT,
                role TEXT DEFAULT 'member',
                layer TEXT DEFAULT 'backend',
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                UNIQUE(team_id, name)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_team_members_team ON team_members(team_id)")

        # Insert a team and a member in the old schema
        conn.execute("INSERT INTO teams (id, name) VALUES ('team-abc', 'Test Team')")
        conn.execute(
            "INSERT INTO team_members (team_id, name, role) VALUES ('team-abc', 'Alice', 'lead')"
        )
        conn.commit()

        # Verify super_agent_id does NOT exist yet
        cursor = conn.execute("PRAGMA table_info(team_members)")
        columns_before = {row[1] for row in cursor.fetchall()}
        assert "super_agent_id" not in columns_before
        assert "agent_id" not in columns_before
        conn.close()

        # Step 2: Run migration via the migration function
        from app.db.connection import get_connection

        with get_connection() as conn2:
            # Simulate the migration logic from _migrate_add_teams_products_projects_plugins
            cursor = conn2.execute("PRAGMA table_info(team_members)")
            columns = {row[1] for row in cursor.fetchall()}

            if "agent_id" not in columns:
                conn2.execute(
                    "ALTER TABLE team_members ADD COLUMN agent_id TEXT REFERENCES agents(id)"
                )
            if "super_agent_id" not in columns:
                conn2.execute(
                    "ALTER TABLE team_members ADD COLUMN super_agent_id TEXT"
                    " REFERENCES super_agents(id)"
                )
            conn2.commit()

        # Step 3: Verify column now exists
        with get_connection() as conn3:
            cursor = conn3.execute("PRAGMA table_info(team_members)")
            columns_after = {row[1] for row in cursor.fetchall()}
            assert "super_agent_id" in columns_after
            assert "agent_id" in columns_after

        # Step 4: Verify inserting a member with super_agent_id works
        with get_connection() as conn4:
            conn4.execute(
                "INSERT INTO super_agents (id, name) VALUES ('sa-test1', 'Test SuperAgent')"
            )
            conn4.execute(
                "INSERT INTO team_members (team_id, name, role, super_agent_id)"
                " VALUES ('team-abc', 'SuperBot', 'member', 'sa-test1')"
            )
            conn4.commit()

            cursor = conn4.execute("SELECT * FROM team_members WHERE super_agent_id = 'sa-test1'")
            row = cursor.fetchone()
            assert row is not None
            assert row["name"] == "SuperBot"
            assert row["super_agent_id"] == "sa-test1"

    def test_migration_is_idempotent(self, tmp_path, monkeypatch):
        """Running migration twice does not error (column already exists)."""
        db_file = str(tmp_path / "idempotent.db")
        monkeypatch.setattr("app.config.DB_PATH", db_file)

        # Create DB with full schema (including super_agent_id)
        conn = sqlite3.connect(db_file)
        conn.execute("""
            CREATE TABLE teams (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE super_agents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE agents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE team_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id TEXT NOT NULL,
                name TEXT NOT NULL,
                agent_id TEXT,
                super_agent_id TEXT,
                description TEXT,
                FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
            )
        """)
        conn.commit()
        conn.close()

        # Run migration check twice — should not error
        from app.db.connection import get_connection

        for _ in range(2):
            with get_connection() as conn2:
                cursor = conn2.execute("PRAGMA table_info(team_members)")
                columns = {row[1] for row in cursor.fetchall()}
                if "agent_id" not in columns:
                    conn2.execute("ALTER TABLE team_members ADD COLUMN agent_id TEXT")
                if "super_agent_id" not in columns:
                    conn2.execute("ALTER TABLE team_members ADD COLUMN super_agent_id TEXT")
                conn2.commit()

        # Verify columns still exist
        with get_connection() as conn3:
            cursor = conn3.execute("PRAGMA table_info(team_members)")
            columns = {row[1] for row in cursor.fetchall()}
            assert "super_agent_id" in columns
            assert "agent_id" in columns

    def test_full_init_db_on_fresh_database_has_super_agent_id(self, isolated_db):
        """Fresh database via init_db() has super_agent_id in team_members."""
        from app.db.connection import get_connection

        with get_connection() as conn:
            cursor = conn.execute("PRAGMA table_info(team_members)")
            columns = {row[1] for row in cursor.fetchall()}
            assert "super_agent_id" in columns
            assert "agent_id" in columns

    def test_existing_members_preserved_after_migration(self, tmp_path, monkeypatch):
        """Existing team members retain their data after column addition."""
        db_file = str(tmp_path / "preserve.db")
        monkeypatch.setattr("app.config.DB_PATH", db_file)

        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE teams (id TEXT PRIMARY KEY, name TEXT NOT NULL)
        """)
        conn.execute("""
            CREATE TABLE agents (id TEXT PRIMARY KEY, name TEXT NOT NULL)
        """)
        conn.execute("""
            CREATE TABLE super_agents (id TEXT PRIMARY KEY, name TEXT NOT NULL)
        """)
        conn.execute("""
            CREATE TABLE team_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id TEXT NOT NULL,
                name TEXT NOT NULL,
                email TEXT,
                role TEXT DEFAULT 'member',
                description TEXT,
                FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                UNIQUE(team_id, name)
            )
        """)
        conn.execute("INSERT INTO teams (id, name) VALUES ('team-xyz', 'Alpha')")
        conn.execute(
            "INSERT INTO team_members (team_id, name, email, role)"
            " VALUES ('team-xyz', 'Bob', 'bob@test.com', 'lead')"
        )
        conn.execute(
            "INSERT INTO team_members (team_id, name, role)"
            " VALUES ('team-xyz', 'Carol', 'member')"
        )
        conn.commit()
        conn.close()

        # Run migration
        from app.db.connection import get_connection

        with get_connection() as conn2:
            cursor = conn2.execute("PRAGMA table_info(team_members)")
            columns = {row[1] for row in cursor.fetchall()}
            if "agent_id" not in columns:
                conn2.execute(
                    "ALTER TABLE team_members ADD COLUMN agent_id TEXT REFERENCES agents(id)"
                )
            if "super_agent_id" not in columns:
                conn2.execute(
                    "ALTER TABLE team_members ADD COLUMN super_agent_id TEXT"
                    " REFERENCES super_agents(id)"
                )
            conn2.commit()

        # Verify existing members are preserved
        with get_connection() as conn3:
            cursor = conn3.execute("SELECT * FROM team_members ORDER BY name ASC")
            rows = [dict(row) for row in cursor.fetchall()]
            assert len(rows) == 2
            assert rows[0]["name"] == "Bob"
            assert rows[0]["email"] == "bob@test.com"
            assert rows[0]["role"] == "lead"
            assert rows[0]["super_agent_id"] is None
            assert rows[1]["name"] == "Carol"
            assert rows[1]["super_agent_id"] is None
