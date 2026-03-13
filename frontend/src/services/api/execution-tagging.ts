/**
 * Execution tagging API module.
 *
 * Provides functions for managing execution tags and assigning them to
 * execution log entries for categorization and full-text search.
 */
import { apiFetch } from './client';

export interface ExecutionTag {
  id: string;
  name: string;
  color: string;
  execution_count: number;
  created_at: string;
}

export interface TaggedExecution {
  id: string;
  trigger_name: string | null;
  bot_id: string | null;
  started_at: string;
  duration_ms: number | null;
  status: string;
  log_snippet: string;
  tags: string[];
}

export const executionTaggingApi = {
  /** List all execution tags with their assignment counts. */
  listTags: () =>
    apiFetch<{ tags: ExecutionTag[]; total: number }>('/admin/execution-tags'),

  /** Create a new execution tag. */
  createTag: (name: string, color: string) =>
    apiFetch<{ tag: ExecutionTag }>('/admin/execution-tags', {
      method: 'POST',
      body: JSON.stringify({ name, color }),
    }),

  /** Delete an execution tag and all its assignments. */
  deleteTag: (tagId: string) =>
    apiFetch<{ message: string }>(`/admin/execution-tags/${tagId}`, {
      method: 'DELETE',
    }),

  /** List executions with their tag arrays, optionally filtered by tag IDs. */
  listExecutions: (params?: {
    limit?: number;
    offset?: number;
    tagIds?: string[];
  }) => {
    const url = new URL('/admin/execution-tagging', window.location.origin);
    if (params?.limit !== undefined) url.searchParams.set('limit', String(params.limit));
    if (params?.offset !== undefined) url.searchParams.set('offset', String(params.offset));
    if (params?.tagIds && params.tagIds.length > 0) {
      url.searchParams.set('tag_ids', params.tagIds.join(','));
    }
    return apiFetch<{ executions: TaggedExecution[]; total: number }>(
      url.pathname + url.search
    );
  },

  /** Add a tag to an execution. */
  addTag: (executionId: string, tagId: string) =>
    apiFetch<{ message: string }>(`/admin/execution-tagging/${executionId}/tags`, {
      method: 'POST',
      body: JSON.stringify({ tag_id: tagId }),
    }),

  /** Remove a tag from an execution. */
  removeTag: (executionId: string, tagId: string) =>
    apiFetch<{ message: string }>(
      `/admin/execution-tagging/${executionId}/tags/${tagId}`,
      { method: 'DELETE' }
    ),
};
