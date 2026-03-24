/**
 * Tracing API module.
 * Provides structured trace and span operations for observability.
 */
import { apiFetch } from './client';

// --- Types ---

export type SpanType =
  | 'AGENT_RUN'
  | 'BOT_RUN'
  | 'TEAM_RUN'
  | 'PROMPT_BUILD'
  | 'EXECUTION'
  | 'TOOL_CALL'
  | 'MEMORY_RECALL'
  | 'MEMORY_SAVE'
  | 'BUDGET_CHECK'
  | 'RETRY'
  | 'GENERIC';

export type TraceStatus = 'running' | 'completed' | 'error';
export type EntityType = 'agent' | 'bot' | 'trigger' | 'team';

export interface Trace {
  id: string;
  name: string;
  entity_type: EntityType;
  entity_id: string;
  execution_id: string | null;
  status: TraceStatus;
  input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  metadata: Record<string, unknown> | null;
  error_message: string | null;
  duration_ms: number | null;
  started_at: string;
  finished_at: string | null;
  created_at: string;
  spans?: TraceSpan[];
  span_count?: number;
}

export interface TraceSpan {
  id: string;
  trace_id: string;
  parent_span_id: string | null;
  name: string;
  span_type: SpanType;
  status: TraceStatus;
  input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  attributes: Record<string, unknown> | null;
  metadata: Record<string, unknown> | null;
  error_message: string | null;
  duration_ms: number | null;
  started_at: string;
  finished_at: string | null;
  children?: TraceSpan[];
}

export interface TraceStats {
  total_traces: number;
  completed: number;
  errors: number;
  running: number;
  avg_duration_ms: number | null;
  max_duration_ms: number | null;
  min_duration_ms: number | null;
}

export interface TraceListResponse {
  traces: Trace[];
  total: number;
}

export interface SpanListResponse {
  spans: TraceSpan[];
  count: number;
}

export interface CreateTraceRequest {
  name: string;
  entity_type: EntityType;
  entity_id: string;
  execution_id?: string;
  input?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

export interface EndTraceRequest {
  status?: TraceStatus;
  output?: Record<string, unknown>;
  error_message?: string;
}

export interface CreateSpanRequest {
  name: string;
  span_type: SpanType;
  parent_span_id?: string;
  input?: Record<string, unknown>;
  attributes?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

export interface EndSpanRequest {
  status?: TraceStatus;
  output?: Record<string, unknown>;
  error_message?: string;
  attributes?: Record<string, unknown>;
}

// --- Helpers ---

function toQueryString(params?: Record<string, unknown>): string {
  if (!params) return '';
  const sp = new URLSearchParams();
  for (const [key, val] of Object.entries(params)) {
    if (val !== undefined && val !== null) sp.set(key, String(val));
  }
  const qs = sp.toString();
  return qs ? `?${qs}` : '';
}

// --- API ---

export const tracingApi = {
  // Trace operations
  listTraces: (params?: { entity_type?: string; entity_id?: string; status?: string; limit?: number; offset?: number }) =>
    apiFetch<TraceListResponse>(`/admin/traces${toQueryString(params)}`),

  createTrace: (body: CreateTraceRequest) =>
    apiFetch<Trace>('/admin/traces', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  getTrace: (traceId: string) =>
    apiFetch<Trace>(`/admin/traces/${traceId}`),

  endTrace: (traceId: string, body: EndTraceRequest = {}) =>
    apiFetch<Trace>(`/admin/traces/${traceId}/end`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  deleteTrace: (traceId: string) =>
    apiFetch<{ message: string }>(`/admin/traces/${traceId}`, {
      method: 'DELETE',
    }),

  getStats: (params?: { entity_type?: string; entity_id?: string }) =>
    apiFetch<TraceStats>(`/admin/traces/stats${toQueryString(params)}`),

  // Span operations
  createSpan: (traceId: string, body: CreateSpanRequest) =>
    apiFetch<TraceSpan>(`/admin/traces/${traceId}/spans`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  listSpans: (traceId: string) =>
    apiFetch<SpanListResponse>(`/admin/traces/${traceId}/spans`),

  getSpan: (traceId: string, spanId: string) =>
    apiFetch<TraceSpan>(`/admin/traces/${traceId}/spans/${spanId}`),

  endSpan: (traceId: string, spanId: string, body: EndSpanRequest = {}) =>
    apiFetch<TraceSpan>(`/admin/traces/${traceId}/spans/${spanId}/end`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  // Agent-specific (uses filter params, no dedicated backend route)
  listAgentTraces: (agentId: string) =>
    apiFetch<TraceListResponse>(`/admin/traces${toQueryString({ entity_type: 'agent', entity_id: agentId })}`),
};
