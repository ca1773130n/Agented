/**
 * Memory System API — bundled session-memory integrations wired into
 * Agented (per-project knowledge graphs, semantic stores, etc.).
 *
 * Designed to absorb additional memory systems (MemPalace, Cognee,
 * etc.) in the same envelope shape; today, only Tesserae is exposed.
 */

import { apiFetch } from './client';

export interface MemorySystemCliStatus {
  installed: boolean;
  version: string | null;
  path: string | null;
}

export interface MemorySystemSummary {
  id: string;
  name: string;
  summary: string;
  cli: MemorySystemCliStatus;
  enabled_project_count: number;
}

export interface TesseraeProjectState {
  project_id: string;
  project_name: string;
  local_path: string | null;
  tesserae_project_root: string | null;
  enabled: boolean;
  workspace_initialized: boolean;
  session_count: number;
  last_imported_at: string | null;
}

export interface TesseraeRefreshResult {
  project_id: string;
  imported: number;
  skipped_reason?: string;
  stdout?: string;
}

export const memorySystemApi = {
  list: () =>
    apiFetch<{ memory_systems: MemorySystemSummary[] }>(
      '/admin/system/memory',
    ),

  listTesseraeProjects: () =>
    apiFetch<{ projects: TesseraeProjectState[] }>(
      '/admin/system/memory/tesserae/projects',
    ),

  setTesseraeRoot: (projectId: string, root: string | null) =>
    apiFetch<{ project: TesseraeProjectState }>(
      `/admin/system/memory/tesserae/projects/${encodeURIComponent(projectId)}`,
      {
        method: 'POST',
        body: JSON.stringify({ root }),
      },
    ),

  refreshTesserae: (projectId: string) =>
    apiFetch<TesseraeRefreshResult>(
      `/admin/system/memory/tesserae/projects/${encodeURIComponent(projectId)}/refresh`,
      { method: 'POST' },
    ),
};
