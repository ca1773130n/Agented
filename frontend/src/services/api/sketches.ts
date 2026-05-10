/**
 * Sketch API module.
 */
import { apiFetch } from './client';
import type { Sketch, SketchStatus, Delegation } from './types';

export const sketchApi = {
  list: (params?: { status?: SketchStatus; project_id?: string }) => {
    const query = new URLSearchParams();
    if (params?.status) query.set('status', params.status);
    if (params?.project_id) query.set('project_id', params.project_id);
    const qs = query.toString();
    return apiFetch<{ sketches: Sketch[] }>(`/admin/sketches${qs ? `?${qs}` : ''}`);
  },
  get: (id: string) => apiFetch<Sketch>(`/admin/sketches/${id}`),
  create: (data: { title: string; content?: string; project_id?: string }) =>
    apiFetch<{ message: string; sketch_id: string }>('/admin/sketches', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  update: (id: string, data: Partial<Omit<Sketch, 'id' | 'created_at' | 'updated_at'>>) =>
    apiFetch<{ message: string }>(`/admin/sketches/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  delete: (id: string) =>
    apiFetch<{ message: string }>(`/admin/sketches/${id}`, { method: 'DELETE' }),
  classify: (id: string) =>
    apiFetch<{ message: string; classification: Record<string, unknown> }>(`/admin/sketches/${id}/classify`, {
      method: 'POST',
    }),
  /**
   * Route a classified sketch and start execution.
   *
   * `useCliAgent` overrides the global YOLO setting for this run only:
   * `true` forces the autonomous CLI runner (claude/codex/gemini with
   * tool privileges); `false` forces the legacy CLIProxy pure-token
   * path; `undefined` defers to the global `agent_yolo_mode` setting.
   * The AiChatPanel toggle plumbs this through.
   */
  route: (id: string, opts?: { useCliAgent?: boolean }) => {
    const body =
      opts && typeof opts.useCliAgent === 'boolean'
        ? JSON.stringify({ use_cli_agent: opts.useCliAgent })
        : undefined;
    return apiFetch<{ message: string; routing: Record<string, unknown>; session_id?: string; super_agent_id?: string }>(
      `/admin/sketches/${id}/route`,
      {
        method: 'POST',
        ...(body ? { body, headers: { 'Content-Type': 'application/json' } } : {}),
      },
    );
  },
  getDelegations: (id: string) =>
    apiFetch<{ delegations: Delegation[] }>(`/admin/sketches/${id}/delegations`),
};
