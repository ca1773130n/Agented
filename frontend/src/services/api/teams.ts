/**
 * Team API module.
 */
import { apiFetch } from './client';
import type {
  Team,
  TeamMember,
  TeamAgentAssignment,
  TeamEdge,
  TeamEdgeType,
  TeamConnection,
  EntityType,
  TopologyType,
  TriggerSource,
  GeneratedTeamConfig,
} from './types';

// Team API
export const teamApi = {
  list: (params?: { limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.limit != null) qs.set('limit', String(params.limit));
    if (params?.offset != null) qs.set('offset', String(params.offset));
    const query = qs.toString();
    return apiFetch<{ teams: Team[]; total_count?: number }>(`/admin/teams${query ? `?${query}` : ''}`);
  },

  get: (teamId: string) => apiFetch<Team>(`/admin/teams/${teamId}`),

  create: (data: {
    name: string;
    description?: string;
    color?: string;
    leader_id?: string;
  }) => apiFetch<{ message: string; team: Team }>('/admin/teams', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  update: (teamId: string, data: Partial<{
    name: string;
    description: string;
    color: string;
    leader_id: string;
  }>) => apiFetch<Team>(`/admin/teams/${teamId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  delete: (teamId: string) => apiFetch<{ message: string }>(`/admin/teams/${teamId}`, {
    method: 'DELETE',
  }),

  // Member operations
  listMembers: (teamId: string) => apiFetch<{ members: TeamMember[] }>(`/admin/teams/${teamId}/members`),

  addMember: (teamId: string, data: {
    name: string;
    email?: string;
    role?: string;
    layer?: string;
    description?: string;
    agent_id?: string;
    super_agent_id?: string;
    tier?: string;
  }) => apiFetch<{ message: string; member: TeamMember }>(`/admin/teams/${teamId}/members`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  updateMember: (teamId: string, memberId: number, data: Partial<{
    name: string;
    email: string;
    role: string;
    layer: string;
    description: string;
    tier: string;
  }>) => apiFetch<{ member: TeamMember }>(`/admin/teams/${teamId}/members/${memberId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  removeMember: (teamId: string, memberId: number) =>
    apiFetch<{ message: string }>(`/admin/teams/${teamId}/members/${memberId}`, {
      method: 'DELETE',
    }),

  // Assignment operations
  getAssignments: (teamId: string, agentId: string) =>
    apiFetch<{ assignments: TeamAgentAssignment[] }>(
      `/admin/teams/${teamId}/agents/${agentId}/assignments`
    ),

  getAllAssignments: (teamId: string) =>
    apiFetch<{ assignments: TeamAgentAssignment[] }>(
      `/admin/teams/${teamId}/assignments`
    ),

  addAssignment: (teamId: string, agentId: string, data: {
    entity_type: EntityType;
    entity_id: string;
    entity_name?: string;
  }) => apiFetch<{ message: string; assignment: TeamAgentAssignment }>(
    `/admin/teams/${teamId}/agents/${agentId}/assignments`,
    { method: 'POST', body: JSON.stringify(data) }
  ),

  deleteAssignment: (teamId: string, assignmentId: number) =>
    apiFetch<{ message: string }>(
      `/admin/teams/${teamId}/assignments/${assignmentId}`,
      { method: 'DELETE' }
    ),

  // Topology
  updateTopology: (teamId: string, data: {
    topology?: TopologyType | null;
    topology_config?: string;
  }) => apiFetch<Team>(`/admin/teams/${teamId}/topology`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  // Trigger
  updateTrigger: (teamId: string, data: {
    trigger_source: TriggerSource | null;
    trigger_config?: string;
    enabled?: number;
  }) => apiFetch<Team>(`/admin/teams/${teamId}/trigger`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  // Execution
  runTeam: (teamId: string, data?: { message?: string }) =>
    apiFetch<{ message: string; team_execution_id?: string }>(
      `/admin/teams/${teamId}/run`,
      { method: 'POST', body: JSON.stringify(data || {}) }
    ),

  // AI Generation
  generateConfig: (data: { description: string }) =>
    apiFetch<{ config: GeneratedTeamConfig; warnings: string[] }>(
      '/admin/teams/generate',
      { method: 'POST', body: JSON.stringify(data) }
    ),

  // Edges
  getEdges: (teamId: string) =>
    apiFetch<{ edges: TeamEdge[] }>(`/admin/teams/${teamId}/edges`),

  addEdge: (teamId: string, data: {
    source_member_id: number;
    target_member_id: number;
    edge_type?: TeamEdgeType;
    label?: string;
    weight?: number;
  }) => apiFetch<{ message: string; edge: TeamEdge }>(`/admin/teams/${teamId}/edges`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  deleteEdge: (teamId: string, edgeId: number) =>
    apiFetch<{ message: string }>(`/admin/teams/${teamId}/edges/${edgeId}`, {
      method: 'DELETE',
    }),

  deleteAllEdges: (teamId: string) =>
    apiFetch<{ message: string; deleted_count: number }>(`/admin/teams/${teamId}/edges`, {
      method: 'DELETE',
    }),

  // Team connections (inter-team)
  listConnections: (teamId: string) =>
    apiFetch<{ connections: TeamConnection[] }>(`/admin/teams/${teamId}/connections`),

  createConnection: (teamId: string, data: {
    target_team_id: string;
    connection_type?: string;
    description?: string;
  }) => apiFetch<{ message: string; id: number }>(`/admin/teams/${teamId}/connections`, {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  deleteConnection: (teamId: string, connectionId: number) =>
    apiFetch<{ message: string }>(`/admin/teams/${teamId}/connections/${connectionId}`, {
      method: 'DELETE',
    }),
};
