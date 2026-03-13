/**
 * Quality ratings API module.
 * Provides CRUD operations for per-execution quality ratings and
 * aggregated per-bot quality statistics.
 */
import { apiFetch } from './client';

export interface QualityEntry {
  id: number;
  execution_id: string;
  trigger_id: string | null;
  rating: 1 | 2 | 3 | 4 | 5;
  feedback: string;
  rated_at: string;
  timestamp: string | null;
  output_preview: string;
  trigger_name: string | null;
}

export interface BotQualityStats {
  trigger_id: string | null;
  trigger_name: string | null;
  avg_score: number;
  total_rated: number;
  thumbs_up: number;
  thumbs_down: number;
  recent_scores: number[];
  trend: 'up' | 'down' | 'stable';
}

export interface QualityEntriesResponse {
  entries: QualityEntry[];
  total: number;
}

export interface QualityStatsResponse {
  bots: BotQualityStats[];
}

export interface SubmitRatingRequest {
  rating: number;
  feedback?: string;
  trigger_id?: string | null;
}

export const qualityApi = {
  listEntries: (params?: {
    trigger_id?: string;
    limit?: number;
    offset?: number;
  }): Promise<QualityEntriesResponse> => {
    const query = new URLSearchParams();
    if (params?.trigger_id) query.set('trigger_id', params.trigger_id);
    if (params?.limit != null) query.set('limit', String(params.limit));
    if (params?.offset != null) query.set('offset', String(params.offset));
    const qs = query.toString();
    return apiFetch<QualityEntriesResponse>(`/admin/quality/entries${qs ? `?${qs}` : ''}`);
  },

  submitRating: (
    executionId: string,
    body: SubmitRatingRequest
  ): Promise<QualityEntry> =>
    apiFetch<QualityEntry>(`/admin/quality/entries/${executionId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  getStats: (): Promise<QualityStatsResponse> =>
    apiFetch<QualityStatsResponse>('/admin/quality/stats'),
};
