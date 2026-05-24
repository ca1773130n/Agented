/**
 * Life-Harness annotation API (T1).
 *
 * Surfaces the per-execution interface-failure classifications produced by
 * ``HarnessFailureAnnotator``. Consumed by ``HarnessLayerCard`` on the
 * Activity lane and (later) by the execution-inspector tools.
 *
 * Reference: arXiv 2605.22166 (Life-Harness).
 */

import { apiFetch } from './client';

export type HarnessLayer = 'h2' | 'h3' | 'h4' | 'general';

export interface HarnessAnnotation {
  session_kind: string;
  session_id: string;
  project_id: string | null;
  annotator_version: string;
  primary_layer: HarnessLayer | null;
  incident_count: number;
  h2_count: number;
  h3_count: number;
  h4_count: number;
  general_count: number;
  outcome: string | null;
  annotated_at: string;
}

export interface HarnessIncident {
  id: string;
  layer: HarnessLayer;
  priority: number;
  kind: string;
  evidence: Record<string, unknown>;
  event_index: number | null;
  detector_version: string;
  created_at: string;
}

export interface HarnessSummaryByLayer {
  h2: number;
  h3: number;
  h4: number;
  general: number;
  none: number;
  total: number;
}

export interface HarnessRecentFailure {
  session_kind: string;
  session_id: string;
  project_id: string | null;
  primary_layer: HarnessLayer;
  incident_count: number;
  h2_count: number;
  h3_count: number;
  h4_count: number;
  general_count: number;
  outcome: string | null;
  annotated_at: string;
}

export interface HarnessSummaryResponse {
  since: string | null;
  by_layer: HarnessSummaryByLayer;
  recent_failures: HarnessRecentFailure[];
}

export interface HarnessAnnotationDetailResponse {
  annotation: HarnessAnnotation | null;
  incidents: HarnessIncident[];
}

export const harnessAnnotationsApi = {
  /** Aggregate harness-layer counts plus a few recent failures. */
  getSummary: (opts: {
    since?: string;
    limit?: number;
    primary_layer?: HarnessLayer;
  } = {}): Promise<HarnessSummaryResponse> => {
    const params = new URLSearchParams();
    if (opts.since) params.set('since', opts.since);
    if (opts.limit !== undefined) params.set('limit', String(opts.limit));
    if (opts.primary_layer) params.set('primary_layer', opts.primary_layer);
    const qs = params.toString();
    return apiFetch<HarnessSummaryResponse>(
      `/admin/executions/annotations/summary${qs ? `?${qs}` : ''}`,
    );
  },

  /** Full annotation + incident list for a single execution. */
  getForExecution: (executionId: string): Promise<HarnessAnnotationDetailResponse> =>
    apiFetch<HarnessAnnotationDetailResponse>(
      `/admin/executions/${encodeURIComponent(executionId)}/annotation`,
    ),
};

/** Human-readable label for each layer — used by the badge component. */
export const HARNESS_LAYER_LABEL: Record<HarnessLayer, string> = {
  h2: 'Action realization',
  h3: 'Environment contract',
  h4: 'Trajectory regulation',
  general: 'General',
};

/** Maps a layer to a CSS variable so colour stays consistent across screens. */
export const HARNESS_LAYER_COLOR_VAR: Record<HarnessLayer, string> = {
  h2: 'var(--accent-red, #ef4444)',
  h3: 'var(--accent-amber, #f59e0b)',
  h4: 'var(--accent-cyan, #06b6d4)',
  general: 'var(--text-tertiary, #6b7280)',
};
