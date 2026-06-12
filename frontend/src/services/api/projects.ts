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
  ExecutionDriver,
} from './types';

// v0.7.70 — Forge context bindings + per-prompt attachments. The
// frontend mirrors the server's ``project_forge_bindings`` row shape
// and the ``ContextCompilerService.compile()`` contract one-to-one.
export type ForgeBindingKind =
  | 'rule'
  | 'skill'
  | 'hook'
  | 'command'
  | 'mcp_server'
  | 'plugin';

export interface ForgeBinding {
  id: number;
  project_id: string;
  kind: ForgeBindingKind;
  asset_id: string;
  role: string | null;
  enabled: boolean;
  position: number;
  created_at: string;
}

export interface ForgeSessionOverrides {
  disabled_binding_ids?: number[];
  additions?: Array<{
    kind: ForgeBindingKind;
    asset_id: string;
    role?: string | null;
  }>;
}

export type ForgeAttachment =
  | { kind: 'file'; path: string }
  | { kind: 'snippet'; label?: string; text: string }
  | { kind: 'url'; url: string; summary?: string }
  | { kind: 'entity'; ref: string; payload: unknown };

export interface ForgeBundlePreview {
  system_prompt_text: string;
  prompt_prepend: string;
  overlay_files: string[];
  overlay_symlinks: string[];
  mcp_servers: string[];
  resolved_bindings: Array<Record<string, unknown>>;
  skipped_bindings: Array<Record<string, unknown>>;
}

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
    manager_super_agent_id: string;
    // Phase 19 (REQ-13) — project-level default execution driver,
    // persisted to ``projects.default_driver``.
    default_driver: ExecutionDriver;
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

  // -----------------------------------------------------------------
  // v0.7.70 — Forge context bindings (per-project sticky defaults
  // for which rules/skills/hooks/commands/MCP/plugins get injected
  // into every session of this project).
  // -----------------------------------------------------------------
  listForgeBindings: (projectId: string) =>
    apiFetch<{ bindings: ForgeBinding[] }>(
      `/admin/projects/${projectId}/forge-bindings`,
    ),

  replaceForgeBindings: (
    projectId: string,
    bindings: Array<{
      kind: ForgeBindingKind;
      asset_id: string;
      role?: string | null;
      enabled?: boolean;
    }>,
  ) =>
    apiFetch<{ bindings: ForgeBinding[] }>(
      `/admin/projects/${projectId}/forge-bindings`,
      { method: 'PUT', body: JSON.stringify({ bindings }) },
    ),

  addForgeBinding: (
    projectId: string,
    binding: {
      kind: ForgeBindingKind;
      asset_id: string;
      role?: string | null;
      enabled?: boolean;
    },
  ) =>
    apiFetch<{ binding: ForgeBinding }>(
      `/admin/projects/${projectId}/forge-bindings`,
      { method: 'POST', body: JSON.stringify(binding) },
    ),

  removeForgeBinding: (projectId: string, bindingId: number) =>
    apiFetch<void>(
      `/admin/projects/${projectId}/forge-bindings/${bindingId}`,
      { method: 'DELETE' },
    ),

  previewForgeContext: (
    projectId: string,
    payload: {
      session_overrides?: ForgeSessionOverrides;
      attachments?: ForgeAttachment[];
    } = {},
  ) =>
    apiFetch<{ bundle: ForgeBundlePreview }>(
      `/admin/projects/${projectId}/forge-context/preview`,
      { method: 'POST', body: JSON.stringify(payload) },
    ),

  /**
   * List SuperAgent sessions tied to this project (as opposed to the
   * GRD-spawned interactive ``claude -p`` sessions surfaced by
   * ``grdApi.listSessions``). Sketch routing creates these — they
   * record the SA's work when a /sketch routes to one of the project's
   * super agents. Optional ``status`` filter (e.g. ``"active"``).
   */
  listSuperAgentSessions: (projectId: string, opts?: { status?: string }) => {
    const qs = opts?.status ? `?status=${encodeURIComponent(opts.status)}` : '';
    return apiFetch<{
      sessions: Array<{
        id: string;
        super_agent_id: string;
        status: string;
        started_at?: string;
        ended_at?: string | null;
        worktree_path?: string | null;
        branch_name?: string | null;
        title?: string | null;
        session_type?: string | null;
        token_count?: number;
      }>;
    }>(`/admin/projects/${projectId}/sessions${qs}`);
  },
};
