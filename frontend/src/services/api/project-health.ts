/**
 * Project health scorecard API module.
 */
import { apiFetch } from './client';

export interface HealthCategory {
  id: string;
  name: string;
  score: number | null;
  trend: number | null;
  icon: string;
  bars: number[];
}

export interface HealthSignal {
  id: string;
  bot: string;
  metric: string;
  current: string;
  previous: string;
  impact: number;
  status: 'good' | 'warn' | 'bad';
}

export interface HealthRecommendation {
  id: string;
  title: string;
  description: string;
  priority: 'high' | 'medium' | 'low';
  category: string;
}

export interface ProjectHealthScorecard {
  overall_score: number;
  trend_delta: number;
  weekly_history: number[];
  categories: HealthCategory[];
  signals: HealthSignal[];
  recommendations: HealthRecommendation[];
  last_updated: string;
}

export const projectHealthApi = {
  getScorecard: (projectId: string) =>
    apiFetch<ProjectHealthScorecard>(`/admin/projects/${projectId}/health-scorecard`),
};
