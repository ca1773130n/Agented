/**
 * Trigger, audit, resolve, execution, and PR review API modules.
 */
import { API_BASE, apiFetch, createBackoffEventSource } from './client';
import type { BackoffEventSourceOptions } from './client';
import type {
  Trigger,
  ExecutionStatus,
  ProjectPath,
  PathType,
  TriggerSource,
  AuditEvent,
  AuditRecord,
  AuditStats,
  ProjectInfo,
  Execution,
  PRStatus,
  ReviewStatusType,
  PrReview,
  PrReviewStats,
  PrHistoryPoint,
} from './types';

// Trigger API (renamed from Bot API)
export const triggerApi = {
  list: () => apiFetch<{ triggers: Trigger[] }>('/admin/triggers'),

  get: (triggerId: string) => apiFetch<Trigger>(`/admin/triggers/${triggerId}`),

  getStatus: (triggerId: string) => apiFetch<ExecutionStatus>(`/admin/triggers/${triggerId}/status`),

  create: (data: {
    name: string;
    prompt_template: string;
    backend_type?: 'claude' | 'opencode';
    trigger_source?: TriggerSource;
    match_field_path?: string;
    match_field_value?: string;
    text_field_path?: string;
    detection_keyword?: string;
    group_id?: number;  // Deprecated
    skill_command?: string;
    model?: string;
    execution_mode?: 'direct' | 'team';
    team_id?: string | null;
    schedule_type?: string;
    schedule_time?: string;
    schedule_day?: number;
    schedule_timezone?: string;
    timeout_seconds?: number | null;
    webhook_secret?: string | null;
  }) => apiFetch<{ message: string; trigger_id: string; name: string }>('/admin/triggers', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  update: (triggerId: string, data: Partial<{
    name: string;
    prompt_template: string;
    backend_type: 'claude' | 'opencode';
    trigger_source: TriggerSource;
    match_field_path: string;
    match_field_value: string;
    text_field_path: string;
    detection_keyword: string;
    group_id: number;  // Deprecated
    enabled: number;
    skill_command: string;
    model: string;
    execution_mode: 'direct' | 'team';
    team_id: string | null;
    timeout_seconds: number | null;
    webhook_secret: string | null;
  }>) => apiFetch<{ message: string }>(`/admin/triggers/${triggerId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  delete: (triggerId: string) => apiFetch<{ message: string }>(`/admin/triggers/${triggerId}`, {
    method: 'DELETE',
  }),

  run: (triggerId: string, message?: string) =>
    apiFetch<{ message: string; trigger_id: string; status: string; execution_id?: string }>(`/admin/triggers/${triggerId}/run`, {
      method: 'POST',
      body: JSON.stringify({ message: message || '' }),
    }),

  // Path operations
  listPaths: (triggerId: string) => apiFetch<{ paths: ProjectPath[] }>(`/admin/triggers/${triggerId}/paths`),

  addPath: (triggerId: string, localProjectPath: string) =>
    apiFetch<{ message: string; local_project_path: string; path_type: PathType }>(`/admin/triggers/${triggerId}/paths`, {
      method: 'POST',
      body: JSON.stringify({ local_project_path: localProjectPath }),
    }),

  addGitHubRepo: (triggerId: string, githubRepoUrl: string) =>
    apiFetch<{ message: string; github_repo_url: string; path_type: PathType }>(`/admin/triggers/${triggerId}/paths`, {
      method: 'POST',
      body: JSON.stringify({ github_repo_url: githubRepoUrl }),
    }),

  removePath: (triggerId: string, localProjectPath: string) =>
    apiFetch<{ message: string }>(`/admin/triggers/${triggerId}/paths`, {
      method: 'DELETE',
      body: JSON.stringify({ local_project_path: localProjectPath }),
    }),

  removeGitHubRepo: (triggerId: string, githubRepoUrl: string) =>
    apiFetch<{ message: string }>(`/admin/triggers/${triggerId}/paths`, {
      method: 'DELETE',
      body: JSON.stringify({ github_repo_url: githubRepoUrl }),
    }),

  addProject: (triggerId: string, projectId: string) =>
    apiFetch<{ message: string; project_id: string; project_name: string; github_repo: string }>(`/admin/triggers/${triggerId}/projects`, {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId }),
    }),

  removeProject: (triggerId: string, projectId: string) =>
    apiFetch<{ message: string }>(`/admin/triggers/${triggerId}/projects/${projectId}`, {
      method: 'DELETE',
    }),

  setAutoResolve: (triggerId: string, autoResolve: boolean) =>
    apiFetch<{ message: string }>(`/admin/triggers/${triggerId}/auto-resolve`, {
      method: 'PUT',
      body: JSON.stringify({ auto_resolve: autoResolve }),
    }),

  previewPrompt: (triggerId: string, sampleData?: {
    paths?: string;
    message?: string;
    pr_url?: string;
    pr_number?: string | number;
    pr_title?: string;
    pr_author?: string;
    repo_url?: string;
    repo_full_name?: string;
  }) => apiFetch<{
    rendered_prompt: string;
    trigger_id: string;
    trigger_name: string;
    unresolved_placeholders: string[];
  }>(`/admin/triggers/${triggerId}/preview-prompt`, {
    method: 'POST',
    body: JSON.stringify(sampleData || {}),
  }),
};

// Audit API
export const auditApi = {
  getHistory: (options?: { limit?: number; project_path?: string; trigger_id?: string }) => {
    const params = new URLSearchParams();
    if (options?.limit) params.set('limit', String(options.limit));
    if (options?.project_path) params.set('project_path', options.project_path);
    if (options?.trigger_id) params.set('trigger_id', options.trigger_id);
    const query = params.toString();
    return apiFetch<{ audits: AuditRecord[] }>(`/api/audit/history${query ? `?${query}` : ''}`);
  },

  getStats: (options?: { project_path?: string; trigger_id?: string } | string) => {
    const params = new URLSearchParams();
    if (typeof options === 'string') {
      if (options) params.set('project_path', options);
    } else if (options) {
      if (options.project_path) params.set('project_path', options.project_path);
      if (options.trigger_id) params.set('trigger_id', options.trigger_id);
    }
    const query = params.toString();
    return apiFetch<AuditStats>(`/api/audit/stats${query ? `?${query}` : ''}`);
  },

  getProjects: () => apiFetch<{ projects: ProjectInfo[] }>('/api/audit/projects'),

  getDetail: (auditId: string) => apiFetch<AuditRecord>(`/api/audit/${auditId}`),

  getWeeklyReport: (auditWeek: string) => apiFetch<AuditRecord>(`/api/audit/reports/${auditWeek}`),

  getEvents: (limit?: number) => {
    const query = limit ? `?limit=${limit}` : '';
    return apiFetch<{ events: AuditEvent[]; total: number }>(`/api/audit/events${query}`);
  },
};

// Resolve API
export const resolveApi = {
  resolveIssues: (auditSummary: string, projectPaths: string[]) =>
    apiFetch<{ message: string }>('/api/resolve-issues', {
      method: 'POST',
      body: JSON.stringify({ audit_summary: auditSummary, project_paths: projectPaths }),
    }),
};

// Execution API
export const executionApi = {
  // List executions for a trigger
  listForBot: (triggerId: string, options?: { limit?: number; offset?: number; status?: string }) => {
    const params = new URLSearchParams();
    if (options?.limit) params.set('limit', String(options.limit));
    if (options?.offset) params.set('offset', String(options.offset));
    if (options?.status) params.set('status', options.status);
    const query = params.toString();
    return apiFetch<{ executions: Execution[]; running_execution: Execution | null; total: number }>(
      `/admin/triggers/${triggerId}/executions${query ? `?${query}` : ''}`
    );
  },

  // List all executions
  listAll: (options?: { limit?: number; offset?: number }) => {
    const params = new URLSearchParams();
    if (options?.limit) params.set('limit', String(options.limit));
    if (options?.offset) params.set('offset', String(options.offset));
    const query = params.toString();
    return apiFetch<{ executions: Execution[]; total: number }>(
      `/admin/executions${query ? `?${query}` : ''}`
    );
  },

  // Get a single execution with full logs
  get: (executionId: string) => apiFetch<Execution>(`/admin/executions/${executionId}`),

  // Get currently running execution for a trigger
  getRunning: (triggerId: string) =>
    apiFetch<{ running: boolean; execution?: Execution }>(`/admin/triggers/${triggerId}/executions/running`),

  // Cancel a running execution
  cancel: (executionId: string) =>
    apiFetch<{ message: string }>(`/admin/executions/${executionId}`, {
      method: 'DELETE',
    }),

  // Create SSE connection for real-time log streaming with exponential backoff reconnection
  streamLogs: (executionId: string, options?: BackoffEventSourceOptions): EventSource => {
    return createBackoffEventSource(`${API_BASE}/admin/executions/${executionId}/stream`, options);
  },
};

// PR Review API
export const prReviewApi = {
  list: (options?: { limit?: number; offset?: number; pr_status?: string; review_status?: string }) => {
    const params = new URLSearchParams();
    if (options?.limit) params.set('limit', String(options.limit));
    if (options?.offset) params.set('offset', String(options.offset));
    if (options?.pr_status) params.set('pr_status', options.pr_status);
    if (options?.review_status) params.set('review_status', options.review_status);
    const query = params.toString();
    return apiFetch<{ reviews: PrReview[]; total: number }>(`/api/pr-reviews/${query ? `?${query}` : ''}`);
  },

  getStats: () => apiFetch<PrReviewStats>('/api/pr-reviews/stats'),

  getHistory: (days?: number) => {
    const query = days ? `?days=${days}` : '';
    return apiFetch<{ history: PrHistoryPoint[] }>(`/api/pr-reviews/history${query}`);
  },

  get: (id: number) => apiFetch<PrReview>(`/api/pr-reviews/${id}`),

  create: (data: {
    project_name: string;
    github_repo_url?: string;
    pr_number: number;
    pr_url: string;
    pr_title: string;
    pr_author?: string;
  }) => apiFetch<{ message: string; id: number }>('/api/pr-reviews/', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  update: (id: number, data: {
    pr_status?: PRStatus;
    review_status?: ReviewStatusType;
    review_comment?: string;
    fixes_applied?: number;
    fix_comment?: string;
  }) => apiFetch<{ message: string }>(`/api/pr-reviews/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  delete: (id: number) => apiFetch<{ message: string }>(`/api/pr-reviews/${id}`, {
    method: 'DELETE',
  }),
};
