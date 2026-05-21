// Shared types + helpers for cards extracted from AnalyticsDashboard.
// Each card owns its own filter state — these are just the types and
// the dateRange helper to avoid copy-pasting four times.

export type AnalyticsDateRange = '7d' | '30d' | '90d';
export type AnalyticsGroupBy = 'day' | 'week' | 'month';

export const rangeOptions: { key: AnalyticsDateRange; label: string }[] = [
  { key: '7d', label: '7 Days' },
  { key: '30d', label: '30 Days' },
  { key: '90d', label: '90 Days' },
];

export const groupByOptions: { key: AnalyticsGroupBy; label: string }[] = [
  { key: 'day', label: 'Day' },
  { key: 'week', label: 'Week' },
  { key: 'month', label: 'Month' },
];

function toLocalDateString(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function buildDateRange(range: AnalyticsDateRange): { start_date: string; end_date: string } {
  const now = new Date();
  const days = range === '7d' ? 7 : range === '30d' ? 30 : 90;
  const start = new Date(now);
  start.setDate(start.getDate() - days);
  return {
    start_date: toLocalDateString(start),
    end_date: toLocalDateString(now),
  };
}
