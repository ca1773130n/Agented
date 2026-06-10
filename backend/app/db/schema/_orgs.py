"""Org / hierarchy DDL: teams, products, projects, project sub-instances, milestones, phases."""


def create_org_tables(conn):
    # Teams table - for team management
    conn.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            color TEXT DEFAULT '#00d4ff',
            leader_id TEXT,
            source TEXT DEFAULT 'ui_created',
            topology TEXT DEFAULT NULL,
            topology_config TEXT DEFAULT NULL,
            trigger_source TEXT DEFAULT NULL,
            trigger_config TEXT DEFAULT NULL,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (leader_id) REFERENCES agents(id) ON DELETE SET NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_teams_name ON teams(name)")

    # Team members table - members of teams (can reference agents or super_agents)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS team_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT,
            role TEXT DEFAULT 'member',
            layer TEXT DEFAULT 'backend',
            description TEXT,
            agent_id TEXT,
            super_agent_id TEXT,
            tier TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
            FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE SET NULL,
            FOREIGN KEY (super_agent_id) REFERENCES super_agents(id) ON DELETE SET NULL,
            UNIQUE(team_id, name)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_team_members_team ON team_members(team_id)")

    # Team agent assignments table - skills/commands/hooks/rules per agent per team
    conn.execute("""
        CREATE TABLE IF NOT EXISTS team_agent_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            entity_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
            FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE,
            UNIQUE(team_id, agent_id, entity_type, entity_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_taa_team ON team_agent_assignments(team_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_taa_agent ON team_agent_assignments(team_id, agent_id)"
    )

    # Products table - for product management
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'active',
            owner_team_id TEXT,
            owner_agent_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_team_id) REFERENCES teams(id) ON DELETE SET NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_products_name ON products(name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_products_status ON products(status)")

    # Projects table - for project management
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'active',
            product_id TEXT,
            github_repo TEXT,
            github_host TEXT DEFAULT 'github.com',
            owner_team_id TEXT,
            local_path TEXT,
            team_topology_config TEXT,
            grd_config TEXT,
            grd_sync_hash TEXT,
            grd_sync_at TIMESTAMP,
            current_milestone_id TEXT,
            worktree_base_path TEXT,
            clone_status TEXT DEFAULT 'none',
            clone_error TEXT,
            grd_init_status TEXT DEFAULT 'none',
            last_synced_at TIMESTAMP,
            manager_super_agent_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL,
            FOREIGN KEY (owner_team_id) REFERENCES teams(id) ON DELETE SET NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_product ON projects(product_id)")

    # Project teams junction table - teams assigned to projects
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            team_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
            UNIQUE(project_id, team_id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_teams_project ON project_teams(project_id)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_teams_team ON project_teams(team_id)")

    # --- v0.3.0: Team edges table (directed graph relationships) ---

    conn.execute("""
        CREATE TABLE IF NOT EXISTS team_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id TEXT NOT NULL,
            source_member_id INTEGER NOT NULL,
            target_member_id INTEGER NOT NULL,
            edge_type TEXT NOT NULL DEFAULT 'delegation',
            label TEXT,
            weight INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
            FOREIGN KEY (source_member_id) REFERENCES team_members(id) ON DELETE CASCADE,
            FOREIGN KEY (target_member_id) REFERENCES team_members(id) ON DELETE CASCADE,
            CHECK (source_member_id != target_member_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_team_edges_team ON team_edges(team_id)")
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_team_edges_unique
        ON team_edges(team_id, source_member_id, target_member_id, edge_type)
    """)

    # --- v0.3.0: Project team edges table (org chart relationships) ---

    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_team_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            source_team_id TEXT NOT NULL,
            target_team_id TEXT NOT NULL,
            edge_type TEXT NOT NULL DEFAULT 'dependency',
            label TEXT,
            weight INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (source_team_id) REFERENCES teams(id) ON DELETE CASCADE,
            FOREIGN KEY (target_team_id) REFERENCES teams(id) ON DELETE CASCADE,
            CHECK (source_team_id != target_team_id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_team_edges_project ON project_team_edges(project_id)"
    )
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_project_team_edges_unique
        ON project_team_edges(project_id, source_team_id, target_team_id, edge_type)
    """)

    # --- v0.4.0: Project Execution & Autonomous Scheduling ---

    # milestones -- project-level milestones for GRD workflow
    conn.execute("""
        CREATE TABLE IF NOT EXISTS milestones (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            version TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'planning'
                CHECK(status IN ('planning', 'active', 'completed', 'archived')),
            requirements_json TEXT,
            roadmap_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_milestones_project ON milestones(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_milestones_status ON milestones(status)")

    # project_phases -- phases within a milestone
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_phases (
            id TEXT PRIMARY KEY,
            milestone_id TEXT NOT NULL,
            phase_number INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            goal TEXT,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'active', 'completed', 'skipped')),
            dependencies TEXT,
            verification_level TEXT DEFAULT 'sanity',
            success_criteria TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (milestone_id) REFERENCES milestones(id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_phases_milestone ON project_phases(milestone_id)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_phases_status ON project_phases(status)")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_project_phases_number ON project_phases(milestone_id, phase_number)"
    )

    # project_plans -- plans within a phase
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_plans (
            id TEXT PRIMARY KEY,
            phase_id TEXT NOT NULL,
            plan_number INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'in_progress', 'completed', 'failed', 'in_review')),
            tasks_json TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (phase_id) REFERENCES project_phases(id) ON DELETE CASCADE
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_plans_phase ON project_plans(phase_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_project_plans_status ON project_plans(status)")

    # project_sessions -- GRD execution sessions
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_sessions (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            phase_id TEXT,
            plan_id TEXT,
            agent_id TEXT,
            status TEXT NOT NULL DEFAULT 'active'
                CHECK(status IN ('active', 'paused', 'completed', 'failed')),
            summary TEXT,
            log_json TEXT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP,
            pid INTEGER,
            pgid INTEGER,
            worktree_path TEXT,
            execution_type TEXT DEFAULT 'direct',
            execution_mode TEXT DEFAULT 'autonomous',
            idle_timeout_seconds INTEGER DEFAULT 3600,
            max_lifetime_seconds INTEGER DEFAULT 14400,
            last_activity_at TIMESTAMP,
            resumed_from TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (phase_id) REFERENCES project_phases(id) ON DELETE SET NULL,
            FOREIGN KEY (plan_id) REFERENCES project_plans(id) ON DELETE SET NULL,
            FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE SET NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_sessions_project ON project_sessions(project_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_sessions_status ON project_sessions(status)"
    )

    # project_sync_state -- tracks file-to-entity mapping for GRD sync
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_sync_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            content_hash TEXT,
            entity_type TEXT NOT NULL,
            entity_id TEXT,
            last_synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            UNIQUE(project_id, file_path)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_sync_project ON project_sync_state(project_id)"
    )

    # team_connections -- directed relationships between teams
    conn.execute("""
        CREATE TABLE IF NOT EXISTS team_connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_team_id TEXT NOT NULL,
            target_team_id TEXT NOT NULL,
            connection_type TEXT NOT NULL DEFAULT 'dependency',
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (source_team_id) REFERENCES teams(id) ON DELETE CASCADE,
            FOREIGN KEY (target_team_id) REFERENCES teams(id) ON DELETE CASCADE,
            UNIQUE(source_team_id, target_team_id, connection_type),
            CHECK (source_team_id != target_team_id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_team_connections_source ON team_connections(source_team_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_team_connections_target ON team_connections(target_team_id)"
    )

    # product_decisions -- decision records for products
    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_decisions (
            id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            rationale TEXT,
            tags_json TEXT DEFAULT '[]',
            decision_type TEXT DEFAULT 'technical',
            status TEXT NOT NULL DEFAULT 'proposed'
                CHECK(status IN ('proposed', 'approved', 'rejected', 'superseded')),
            decided_by TEXT,
            decided_at TIMESTAMP,
            context_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_product_decisions_product ON product_decisions(product_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_product_decisions_status ON product_decisions(status)"
    )

    # product_milestones -- milestones at the product level
    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_milestones (
            id TEXT PRIMARY KEY,
            product_id TEXT NOT NULL,
            version TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'planning',
            target_date TEXT,
            sort_order INTEGER DEFAULT 0,
            progress_pct INTEGER DEFAULT 0 CHECK(progress_pct BETWEEN 0 AND 100),
            completed_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_product_milestones_product ON product_milestones(product_id)"
    )

    # milestone_projects -- junction: which projects contribute to a product milestone
    conn.execute("""
        CREATE TABLE IF NOT EXISTS milestone_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            milestone_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            contribution TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (milestone_id) REFERENCES product_milestones(id) ON DELETE CASCADE,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            UNIQUE(milestone_id, project_id)
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_milestone_projects_milestone ON milestone_projects(milestone_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_milestone_projects_project ON milestone_projects(project_id)"
    )

    # --- Project-scoped SA instances ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_sa_instances (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            template_sa_id TEXT NOT NULL REFERENCES super_agents(id),
            worktree_path TEXT,
            default_chat_mode TEXT NOT NULL DEFAULT 'management'
                CHECK(default_chat_mode IN ('management', 'work')),
            config_overrides TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(project_id, template_sa_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_psa_project ON project_sa_instances(project_id)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_psa_template ON project_sa_instances(template_sa_id)"
    )

    # --- Project-scoped team instances ---
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_team_instances (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            template_team_id TEXT NOT NULL REFERENCES teams(id),
            config_overrides TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(project_id, template_team_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pti_project ON project_team_instances(project_id)")
