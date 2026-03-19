/**
 * Project instance types for project-scoped superagent and team instances.
 */

export type ChatMode = 'management' | 'work';

export interface ProjectSAInstance {
  id: string;
  project_id: string;
  template_sa_id: string;
  worktree_path?: string;
  default_chat_mode: ChatMode;
  config_overrides?: string;
  created_at?: string;
  updated_at?: string;
  // Joined from template SA
  sa_name?: string;
  sa_description?: string;
  sa_backend_type?: string;
}

export interface ProjectTeamInstance {
  id: string;
  project_id: string;
  template_team_id: string;
  config_overrides?: string;
  created_at?: string;
  updated_at?: string;
}

export interface SAInstanceInfo {
  id: string;
  template_sa_id: string;
  worktree_path?: string;
  session_id?: string;
}

export interface CreateInstanceRequest {
  team_id?: string;
  super_agent_id?: string;
}

export interface CreateInstanceResponse {
  team_instance_id?: string;
  sa_instances: SAInstanceInfo[];
}
