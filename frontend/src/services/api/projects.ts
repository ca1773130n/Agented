/**
 * Project API module.
 */
import { apiFetch } from './client';
import type {
  Project,
  ProjectInstallation,
  ProjectSkill,
  ProjectDeployResult,
  HarnessStatusResult,
  HarnessLoadResult,
  HarnessDeployResult,
  ProjectTeamEdge,
} from './types';

// Project API
export const projectApi = {
  list: (params?: { limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.limit != null) qs.set('limit', String(params.limit));
    if (params?.offset != null) qs.set('offset', String(params.offset));
    const query = qs.toString();
    return apiFetch<{ projects: Project[]; total_count?: number }>(`/admin/projects${query ? `?${query}` : ''}`);
  },

  get: (projectId: string) => apiFetch<Project>(`/admin/projects/${projectId}`),

  create: (data: {
    name: string;
    description?: string;
    status?: string;
    product_id?: string;
    github_repo?: string;
    local_path?: string;
    owner_team_id?: string;
  }) => apiFetch<{ message: string; project: Project }>('/admin/projects', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  update: (projectId: string, data: Partial<{
    name: string;
    description: string;
    status: string;
    product_id: string;
    github_repo: string;
    owner_team_id: string;
    local_path: string;
  }>) => apiFetch<Project>(`/admin/projects/${projectId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  delete: (projectId: string) => apiFetch<{ message: string }>(`/admin/projects/${projectId}`, {
    method: 'DELETE',
  }),

  // Team assignment
  listTeams: (projectId: string) => apiFetch<{ teams: { id: string; name: string; color: string }[] }>(`/admin/projects/${projectId}/teams`),

  assignTeam: (projectId: string, teamId: string) =>
    apiFetch<{ message: string }>(`/admin/projects/${projectId}/teams/${teamId}`, {
      method: 'POST',
    }),

  unassignTeam: (projectId: string, teamId: string) =>
    apiFetch<{ message: string }>(`/admin/projects/${projectId}/teams/${teamId}`, {
      method: 'DELETE',
    }),

  // Deploy teams
  deployTeams: (projectId: string) =>
    apiFetch<ProjectDeployResult>(`/admin/projects/${projectId}/deploy`, {
      method: 'POST',
    }),

  previewDeploy: (projectId: string) =>
    apiFetch<ProjectDeployResult>(`/admin/projects/${projectId}/deploy/preview`),

  // Harness operations
  getHarnessStatus: (projectId: string) =>
    apiFetch<HarnessStatusResult>(`/admin/projects/${projectId}/harness/status`),

  loadHarness: (projectId: string) =>
    apiFetch<HarnessLoadResult>(`/admin/projects/${projectId}/harness/load`, {
      method: 'POST',
    }),

  deployHarness: (projectId: string) =>
    apiFetch<HarnessDeployResult>(`/admin/projects/${projectId}/harness/deploy`, {
      method: 'POST',
    }),

  // Project skills
  listSkills: (projectId: string) =>
    apiFetch<{ skills: ProjectSkill[] }>(`/admin/projects/${projectId}/skills`),

  addSkill: (projectId: string, data: { skill_name: string; skill_path?: string; source?: string }) =>
    apiFetch<{ message: string; skill_id: number }>(`/admin/projects/${projectId}/skills`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  removeSkill: (projectId: string, skillId: number) =>
    apiFetch<{ message: string }>(`/admin/projects/${projectId}/skills/${skillId}`, {
      method: 'DELETE',
    }),

  // Run team in project context
  runTeamInProject: (projectId: string, teamId: string, data?: { message?: string }) =>
    apiFetch<{ message: string; team_execution_id?: string; working_directory?: string }>(
      `/admin/projects/${projectId}/run-team/${teamId}`,
      { method: 'POST', body: JSON.stringify(data || {}) },
    ),

  // Installation operations
  listInstallations: (projectId: string, componentType?: string): Promise<{ installations: ProjectInstallation[] }> => {
    const params = componentType ? `?component_type=${componentType}` : '';
    return apiFetch(`/admin/projects/${projectId}/installations${params}`);
  },

  installComponent: (projectId: string, data: { component_type: string; component_id: string }): Promise<{ installed: boolean; path?: string; error?: string }> => {
    return apiFetch(`/admin/projects/${projectId}/install`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  },

  uninstallComponent: (projectId: string, data: { component_type: string; component_id: string }): Promise<{ uninstalled: boolean; path?: string; error?: string }> => {
    return apiFetch(`/admin/projects/${projectId}/uninstall`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  },

  // Team topology (org chart)
  listTeamEdges: (projectId: string) =>
    apiFetch<{ edges: ProjectTeamEdge[] }>(`/admin/projects/${projectId}/team-edges`),

  createTeamEdge: (projectId: string, data: {
    source_team_id: string;
    target_team_id: string;
    edge_type?: string;
    label?: string;
    weight?: number;
  }) => apiFetch<{ message: string; edge_id: number }>(`/admin/projects/${projectId}/team-edges`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  deleteTeamEdge: (projectId: string, edgeId: number) =>
    apiFetch<{ message: string }>(`/admin/projects/${projectId}/team-edges/${edgeId}`, {
      method: 'DELETE',
    }),

  updateTeamTopologyConfig: (projectId: string, config: Record<string, unknown>) =>
    apiFetch<{ message: string }>(`/admin/projects/${projectId}/team-topology`, {
      method: 'PUT',
      body: JSON.stringify({ team_topology_config: config }),
    }),

  // Repository sync
  syncRepo: (projectId: string) =>
    apiFetch<{ status: string; output?: string; error?: string }>(`/admin/projects/${projectId}/sync`, {
      method: 'POST',
    }),

  getCloneStatus: (projectId: string) =>
    apiFetch<{ clone_status: string; clone_error?: string; last_synced_at?: string }>(`/admin/projects/${projectId}/clone-status`),

  getOrCreateManager: (projectId: string) =>
    apiFetch<{ super_agent_id: string; created: boolean }>(`/admin/projects/${projectId}/manager`),
};
