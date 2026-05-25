/**
 * Session takeaways API — positive-learning capture (the inverse of
 * the failure annotator).
 *
 * Takeaways are proposals by default. Operator approves → asset is
 * written to its suggested target. All five targets (memory, rule,
 * knowledge_graph, skill, claude_md) have auto-writers; operator
 * approval just gates when the write happens.
 *
 * Set ``AGENTED_TAKEAWAY_AUTOAPPLY=1`` on the backend to auto-apply
 * high-confidence (>= 0.85) takeaways at extraction time.
 */

import { apiFetch } from './client';

export type TakeawayKind =
  | 'user_preference'
  | 'discovered_procedure'
  | 'tool_pattern'
  | 'constraint'
  | 'domain_fact'
  | 'failure_root_cause'
  | 'success_pattern';

export type TakeawayTarget =
  | 'memory'
  | 'rule'
  | 'skill'
  | 'knowledge_graph'
  | 'claude_md';

export interface Takeaway {
  id: string;
  session_kind: string;
  session_id: string;
  project_id: string | null;
  kind: TakeawayKind;
  content: string;
  confidence: number;
  evidence: Record<string, unknown>;
  suggested_target: TakeawayTarget | null;
  suggested_payload: Record<string, unknown>;
  extractor_version: string;
  applied: boolean;
  applied_at: string | null;
  applied_target: TakeawayTarget | null;
  applied_asset_id: string | null;
  dismissed: boolean;
  dismissed_reason: string | null;
  created_at: string;
}

export interface ApplyResult {
  applied: boolean;
  target?: TakeawayTarget;
  asset_id?: string;
  takeaway_id?: string;
  reason?: string;
}

export interface DismissResult {
  dismissed: boolean;
  takeaway_id?: string;
  reason?: string;
}

export const harnessTakeawaysApi = {
  listRecent: (
    opts: {
      limit?: number;
      applied?: boolean;
      dismissed?: boolean;
      project_id?: string;
    } = {},
  ) => {
    const params = new URLSearchParams();
    if (opts.limit !== undefined) params.set('limit', String(opts.limit));
    if (opts.applied !== undefined) params.set('applied', String(opts.applied));
    if (opts.dismissed !== undefined)
      params.set('dismissed', String(opts.dismissed));
    if (opts.project_id) params.set('project_id', opts.project_id);
    const qs = params.toString();
    return apiFetch<{ takeaways: Takeaway[] }>(
      `/admin/takeaways/recent${qs ? `?${qs}` : ''}`,
    );
  },

  listForProject: (
    projectId: string,
    opts: {
      kind?: TakeawayKind;
      applied?: boolean;
      dismissed?: boolean;
      limit?: number;
    } = {},
  ) => {
    const params = new URLSearchParams();
    if (opts.kind) params.set('kind', opts.kind);
    if (opts.applied !== undefined) params.set('applied', String(opts.applied));
    if (opts.dismissed !== undefined)
      params.set('dismissed', String(opts.dismissed));
    if (opts.limit !== undefined) params.set('limit', String(opts.limit));
    const qs = params.toString();
    return apiFetch<{ project_id: string; takeaways: Takeaway[] }>(
      `/admin/projects/${encodeURIComponent(projectId)}/takeaways${qs ? `?${qs}` : ''}`,
    );
  },

  get: (takeawayId: string) =>
    apiFetch<Takeaway>(
      `/admin/takeaways/${encodeURIComponent(takeawayId)}`,
    ),

  apply: (takeawayId: string) =>
    apiFetch<ApplyResult>(
      `/admin/takeaways/${encodeURIComponent(takeawayId)}/apply`,
      { method: 'POST' },
    ),

  dismiss: (takeawayId: string, reason?: string) =>
    apiFetch<DismissResult>(
      `/admin/takeaways/${encodeURIComponent(takeawayId)}/dismiss`,
      {
        method: 'POST',
        body: JSON.stringify({ reason: reason || null }),
      },
    ),
};

export const TAKEAWAY_KIND_LABEL: Record<TakeawayKind, string> = {
  user_preference: 'User preference',
  discovered_procedure: 'Discovered procedure',
  tool_pattern: 'Tool pattern',
  constraint: 'Constraint',
  domain_fact: 'Domain fact',
  failure_root_cause: 'Failure root cause',
  success_pattern: 'Success pattern',
};

export const TAKEAWAY_TARGET_LABEL: Record<TakeawayTarget, string> = {
  memory: 'Memory',
  rule: 'Rule',
  skill: 'Skill',
  knowledge_graph: 'Knowledge graph',
  claude_md: 'CLAUDE.md',
};

export const TAKEAWAY_TARGET_COLOR_VAR: Record<TakeawayTarget, string> = {
  memory: 'var(--accent-cyan, #06b6d4)',
  rule: 'var(--accent-amber, #f59e0b)',
  skill: 'var(--accent-green, #10b981)',
  knowledge_graph: 'var(--accent-red, #ef4444)',
  claude_md: 'var(--text-tertiary, #6b7280)',
};
