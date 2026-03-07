/**
 * Project, ProjectSkill, and deployment-related types.
 */

export interface Project {
  id: string;
  name: string;
  description?: string;
  status: string;
  product_id?: string;
  product_name?: string;
  github_repo?: string;
  github_host?: string;
  owner_team_id?: string;
  owner_team_name?: string;
  local_path?: string;
  clone_path?: string;
  clone_error?: string;
  clone_status?: 'none' | 'cloning' | 'cloned' | 'error';
  last_synced_at?: string;
  manager_super_agent_id?: string;
  team_count: number;
  team_topology_config?: string;
  created_at?: string;
  updated_at?: string;
  teams?: { id: string; name: string; color: string }[];
}

export interface ProjectTeamEdge {
  id: number;
  project_id: string;
  source_team_id: string;
  target_team_id: string;
  edge_type: string;
  label?: string;
  weight: number;
  created_at?: string;
}

export interface ProjectInstallation {
  id: number;
  project_id: string;
  component_type: 'agent' | 'skill' | 'hook' | 'command' | 'rule';
  component_id: string;
  component_name?: string;
  installed_at?: string;
}

// Project skill type
export interface ProjectSkill {
  id: number;
  project_id: string;
  skill_name: string;
  skill_path?: string;
  source: string;  // 'manual', 'team_sync', 'agent_sync'
  created_at?: string;
}

// Deploy result types
export interface ProjectDeployResult {
  project_id: string;
  project_name: string;
  teams_count: number;
  generated: {
    team_name: string;
    folder_name: string;
    files: Record<string, string>;
  }[];
  error?: string;
}

// Harness result types
export interface HarnessStatusResult {
  exists: boolean;
  subdirs?: Record<string, boolean>;
  project_id: string;
  github_repo?: string;
  error?: string;
}

export interface HarnessLoadResult {
  message?: string;
  project_id: string;
  github_repo?: string;
  imported?: {
    agents: string[];
    skills: string[];
    hooks: string[];
    commands: string[];
    teams: string[];
  };
  counts?: Record<string, number>;
  error?: string;
}

export interface HarnessDeployResult {
  message?: string;
  project_id: string;
  github_repo?: string;
  pr_url?: string;
  branch?: string;
  generated?: {
    files_created: string[];
    counts: Record<string, number>;
  };
  error?: string;
}
