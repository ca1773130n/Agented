/**
 * Product API module.
 */
import { apiFetch } from './client';
import type {
  Product,
  ProductDecision,
  ProductMilestone,
  MilestoneProject,
  ProductDashboardData,
  MeetingMessage,
} from './types';

// Product API
export const productApi = {
  list: (params?: { limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.limit != null) qs.set('limit', String(params.limit));
    if (params?.offset != null) qs.set('offset', String(params.offset));
    const query = qs.toString();
    return apiFetch<{ products: Product[]; total_count?: number }>(`/admin/products${query ? `?${query}` : ''}`);
  },

  get: (productId: string) => apiFetch<Product>(`/admin/products/${productId}`),

  create: (data: {
    name: string;
    description?: string;
    status?: string;
    owner_team_id?: string;
  }) => apiFetch<{ message: string; product: Product }>('/admin/products', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  update: (productId: string, data: Partial<{
    name: string;
    description: string;
    status: string;
    owner_team_id: string;
  }>) => apiFetch<Product>(`/admin/products/${productId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  delete: (productId: string) => apiFetch<{ message: string }>(`/admin/products/${productId}`, {
    method: 'DELETE',
  }),

  // Decisions
  listDecisions: (productId: string, status?: string) =>
    apiFetch<{ decisions: ProductDecision[] }>(
      `/admin/products/${productId}/decisions${status ? `?status=${status}` : ''}`
    ),

  createDecision: (productId: string, data: {
    title: string; description?: string; rationale?: string;
    decision_type?: string; tags?: string[];
  }) => apiFetch<{ message: string; decision: ProductDecision }>(
    `/admin/products/${productId}/decisions`,
    { method: 'POST', body: JSON.stringify(data) }
  ),

  getDecision: (productId: string, decisionId: string) =>
    apiFetch<ProductDecision>(`/admin/products/${productId}/decisions/${decisionId}`),

  updateDecision: (productId: string, decisionId: string, data: Partial<{
    title: string; description: string; rationale: string; status: string;
    decided_by: string; tags_json: string; context_json: string;
  }>) => apiFetch<ProductDecision>(
    `/admin/products/${productId}/decisions/${decisionId}`,
    { method: 'PUT', body: JSON.stringify(data) }
  ),

  deleteDecision: (productId: string, decisionId: string) =>
    apiFetch<{ message: string }>(
      `/admin/products/${productId}/decisions/${decisionId}`,
      { method: 'DELETE' }
    ),

  // Milestones
  listMilestones: (productId: string, status?: string) =>
    apiFetch<{ milestones: ProductMilestone[] }>(
      `/admin/products/${productId}/milestones${status ? `?status=${status}` : ''}`
    ),

  createMilestone: (productId: string, data: {
    version: string; title: string; description?: string;
    target_date?: string; sort_order?: number; progress_pct?: number;
  }) => apiFetch<{ message: string; milestone: ProductMilestone }>(
    `/admin/products/${productId}/milestones`,
    { method: 'POST', body: JSON.stringify(data) }
  ),

  getMilestone: (productId: string, milestoneId: string) =>
    apiFetch<{ milestone: ProductMilestone; projects: MilestoneProject[] }>(
      `/admin/products/${productId}/milestones/${milestoneId}`
    ),

  updateMilestone: (productId: string, milestoneId: string, data: Partial<{
    version: string; title: string; description: string; status: string;
    target_date: string; sort_order: number; progress_pct: number; completed_date: string;
  }>) => apiFetch<ProductMilestone>(
    `/admin/products/${productId}/milestones/${milestoneId}`,
    { method: 'PUT', body: JSON.stringify(data) }
  ),

  deleteMilestone: (productId: string, milestoneId: string) =>
    apiFetch<{ message: string }>(
      `/admin/products/${productId}/milestones/${milestoneId}`,
      { method: 'DELETE' }
    ),

  // Milestone-Project junction
  listMilestoneProjects: (productId: string, milestoneId: string) =>
    apiFetch<{ projects: MilestoneProject[] }>(
      `/admin/products/${productId}/milestones/${milestoneId}/projects`
    ),

  linkProjectToMilestone: (productId: string, milestoneId: string, data: {
    project_id: string; contribution?: string;
  }) => apiFetch<{ message: string }>(
    `/admin/products/${productId}/milestones/${milestoneId}/projects`,
    { method: 'POST', body: JSON.stringify(data) }
  ),

  unlinkProjectFromMilestone: (productId: string, milestoneId: string, projectId: string) =>
    apiFetch<{ message: string }>(
      `/admin/products/${productId}/milestones/${milestoneId}/projects/${projectId}`,
      { method: 'DELETE' }
    ),

  // Owner assignment
  assignOwner: (productId: string, ownerAgentId: string) =>
    apiFetch<{ message: string }>(
      `/admin/products/${productId}/owner`,
      { method: 'PUT', body: JSON.stringify({ owner_agent_id: ownerAgentId }) }
    ),

  // Meeting protocol
  triggerStandup: (productId: string) =>
    apiFetch<{ meeting_id: string; message_ids: string[]; participants: number }>(
      `/admin/products/${productId}/meetings/standup`,
      { method: 'POST' }
    ),

  getMeetingHistory: (productId: string) =>
    apiFetch<{ meetings: MeetingMessage[] }>(
      `/admin/products/${productId}/meetings/history`
    ),

  // Dashboard
  getDashboard: (productId: string) =>
    apiFetch<ProductDashboardData>(
      `/admin/products/${productId}/dashboard`
    ),
};
