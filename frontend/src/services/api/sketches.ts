/**
 * Sketch API module.
 */
import { apiFetch, API_BASE, buildAuthHeaders } from './client';
import type { Sketch, SketchStatus, Delegation } from './types';

/** A single cited source from the federated retrieval. */
export interface RetrievalSource {
  name: string | null;
  path: string | null;
  wiki_kind: string | null;
  project: string | null;
}

/** Tesserae retrieval stats — surfaces the semantic backend actually used (so a
 *  hash-bucket fallback is visible vs real embeddings) and the graph size. */
export interface RetrievalStats {
  nodes: number | null;
  edges: number | null;
  semantic_backend: string | null;
  semantic_skipped: string | null;
  semantic_added: number | null;
}

/** Full provenance of one ideation turn's grounding. */
/** Tesserae 0.12.0 `federation status` — how the cross-project graph is composed. */
export interface RetrievalFederation {
  per_project_nodes: Record<string, number>;
  identity_merges: number | null;
}

export interface RetrievalDetails {
  scope: string | null; // "federated" | null (no grounding)
  projects: string[];
  citations: number;
  stats: RetrievalStats;
  sources: RetrievalSource[];
  federation: RetrievalFederation;
}

export interface IdeateHandlers {
  onRetrieval?: (p: RetrievalDetails) => void;
  onContent?: (chunk: string) => void;
  onDone?: () => void;
  onError?: (message: string) => void;
  signal?: AbortSignal;
}

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

  /**
   * Stream one grounded ideation turn (the Sketch 'thinking partner'). POSTs the
   * full conversation `messages` and consumes the SSE response (federated Tesserae
   * grounding → content chunks). Does NOT route/execute. POST-SSE, so we use a
   * fetch stream reader (native EventSource is GET-only) with the X-API-Key.
   */
  ideateStream: async (
    messages: { role: string; content: string }[],
    handlers: IdeateHandlers,
    backend?: string,
  ): Promise<void> => {
    let resp: Response;
    try {
      resp = await fetch(`${API_BASE}/admin/sketches/ideate`, {
        method: 'POST',
        // Same auth as apiFetch: X-API-Key + bearer + X-CSRF-Token + cookies.
        headers: { 'Content-Type': 'application/json', ...buildAuthHeaders('POST') },
        credentials: 'include',
        body: JSON.stringify({ messages, backend }),
        signal: handlers.signal,
      });
    } catch (e) {
      handlers.onError?.(e instanceof Error ? e.message : 'ideate request failed');
      return;
    }
    if (!resp.ok || !resp.body) {
      handlers.onError?.(`ideate failed (${resp.status})`);
      return;
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    let doneEmitted = false;
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const frames = buf.split('\n\n');
      buf = frames.pop() ?? ''; // keep the trailing partial frame
      for (const frame of frames) {
        let event = 'message';
        let dataStr = '';
        for (const line of frame.split('\n')) {
          if (line.startsWith('event:')) event = line.slice(6).trim();
          else if (line.startsWith('data:')) dataStr += line.slice(5).trim();
        }
        if (!dataStr) continue;
        let data: Record<string, unknown> = {};
        try {
          data = JSON.parse(dataStr);
        } catch {
          continue;
        }
        if (event === 'retrieval') {
          handlers.onRetrieval?.({
            scope: (data.scope as string) ?? null,
            projects: (data.projects as string[]) ?? [],
            citations: (data.citations as number) ?? 0,
            stats: (data.stats as RetrievalStats) ?? ({} as RetrievalStats),
            sources: (data.sources as RetrievalSource[]) ?? [],
            federation: (data.federation as RetrievalFederation) ?? {
              per_project_nodes: {},
              identity_merges: null,
            },
          });
        } else if (event === 'content') {
          handlers.onContent?.((data.content as string) ?? '');
        } else if (event === 'error') {
          // Terminal: fire exactly one of onError/onDone (suppress the EOF onDone).
          doneEmitted = true;
          handlers.onError?.((data.message as string) ?? 'stream error');
        } else if (event === 'done') {
          doneEmitted = true;
          handlers.onDone?.();
        }
      }
    }
    if (!doneEmitted) handlers.onDone?.();
  },
};
