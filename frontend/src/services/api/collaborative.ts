/**
 * Collaborative execution viewing API module.
 *
 * Provides functions for viewer presence management (join, leave, heartbeat)
 * and inline comment operations anchored to execution log line numbers.
 */
import { apiFetch } from './client';
import type { ViewerInfo, InlineComment } from './types';

export const collaborativeApi = {
  /** Register a viewer for an execution stream. */
  join: (executionId: string, viewerId: string, name: string) =>
    apiFetch<{ viewer_id: string; name: string; joined_at: string }>(
      `/admin/executions/${executionId}/viewers`,
      { method: 'POST', body: JSON.stringify({ viewer_id: viewerId, name }) }
    ),

  /** Remove a viewer from an execution stream. */
  leave: (executionId: string, viewerId: string) =>
    apiFetch<null>(
      `/admin/executions/${executionId}/viewers/${viewerId}`,
      { method: 'DELETE' }
    ),

  /** Send a heartbeat to keep viewer presence active. */
  heartbeat: (executionId: string, viewerId: string) =>
    apiFetch<null>(
      `/admin/executions/${executionId}/viewers/${viewerId}/heartbeat`,
      { method: 'POST' }
    ),

  /** Get all current viewers for an execution. */
  getViewers: (executionId: string) =>
    apiFetch<{ viewers: ViewerInfo[] }>(
      `/admin/executions/${executionId}/viewers`
    ),

  /** Post an inline comment anchored to a log line number. */
  postComment: (executionId: string, data: {
    viewer_id: string;
    viewer_name: string;
    line_number: number;
    content: string;
  }) =>
    apiFetch<InlineComment>(
      `/admin/executions/${executionId}/comments`,
      { method: 'POST', body: JSON.stringify(data) }
    ),

  /** Get all inline comments for an execution. */
  getComments: (executionId: string) =>
    apiFetch<{ comments: InlineComment[] }>(
      `/admin/executions/${executionId}/comments`
    ),

  /** Delete an inline comment. */
  deleteComment: (commentId: string) =>
    apiFetch<null>(
      `/admin/execution-comments/${commentId}`,
      { method: 'DELETE' }
    ),
};
