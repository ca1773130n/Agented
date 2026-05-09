"""Skill-related DDL: user_skills, project_skills, skill_sets."""


def create_skill_tables(conn):
    # User skills table - for skill management and harness integration
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_name TEXT NOT NULL UNIQUE,
            skill_path TEXT NOT NULL,
            description TEXT,
            enabled INTEGER DEFAULT 1,
            selected_for_harness INTEGER DEFAULT 0,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user_skills_enabled ON user_skills(enabled)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_skills_harness ON user_skills(selected_for_harness)"
    )

    # Project skills table - per-project skill associations
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            skill_name TEXT NOT NULL,
            skill_path TEXT,
            source TEXT DEFAULT 'manual',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            UNIQUE(project_id, skill_name)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_skills_project ON project_skills(project_id)"
    )

    # --- Skill sets (VisualSkillComposerPage) ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS skill_sets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            skill_ids TEXT NOT NULL DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
