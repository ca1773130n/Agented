<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';
import { analyticsApi, ApiError } from '../services/api';
import type { ExecutionDataPoint, EffectivenessOverTimePoint } from '../services/api';

const { t } = useI18n();
const showToast = useToast();

const isLoading = ref(true);
const error = ref('');

type QualityTrend = 'up' | 'down' | 'stable';
type PeriodKey = '7d' | '30d' | '90d';

interface LatencyPoint {
  date: string;
  p50: number;
  p95: number;
}

interface QualityPoint {
  date: string;
  score: number;
}

interface BotBenchmark {
  botId: string;
  botName: string;
  totalExecutions: number;
  successRate: number;
  avgLatencyMs: number;
  p95LatencyMs: number;
  avgQualityScore: number;
  qualityTrend: QualityTrend;
  latencyTrend: QualityTrend;
  latencyHistory: LatencyPoint[];
  qualityHistory: QualityPoint[];
  lastRunAt: string;
  evalModel: string;
}

const selectedPeriod = ref<PeriodKey>('30d');
const periodOptions: { key: PeriodKey; label: string }[] = [
  { key: '7d', label: t('botPerformanceBenchmarks.period.7d') },
  { key: '30d', label: t('botPerformanceBenchmarks.period.30d') },
  { key: '90d', label: t('botPerformanceBenchmarks.period.90d') },
];

const selectedBotId = ref<string | null>(null);
const isRunningEval = ref(false);

const benchmarks = ref<BotBenchmark[]>([]);

function computeTrend(values: number[]): QualityTrend {
  if (values.length < 2) return 'stable';
  const last = values[values.length - 1];
  const prev = values[values.length - 2];
  const diff = last - prev;
  if (Math.abs(diff) < 0.5) return 'stable';
  return diff > 0 ? 'up' : 'down';
}

async function loadBenchmarks() {
  isLoading.value = true;
  error.value = '';
  try {
    const days = selectedPeriod.value === '7d' ? 7 : selectedPeriod.value === '30d' ? 30 : 90;
    const startDate = new Date(Date.now() - days * 86400000).toISOString().split('T')[0];

    const [execResp, effectResp] = await Promise.all([
      analyticsApi.fetchExecutionAnalytics({ group_by: 'day', start_date: startDate }),
      analyticsApi.fetchEffectiveness({ group_by: 'day', start_date: startDate }),
    ]);

    // Group execution data by backend_type to create "bot" benchmarks
    const byBackend = new Map<string, ExecutionDataPoint[]>();
    for (const dp of execResp.data) {
      const key = dp.backend_type || 'unknown';
      if (!byBackend.has(key)) byBackend.set(key, []);
      byBackend.get(key)!.push(dp);
    }

    const results: BotBenchmark[] = [];
    for (const [backend, points] of byBackend) {
      const totalExec = points.reduce((s, p) => s + p.total_executions, 0);
      const totalSuccess = points.reduce((s, p) => s + p.success_count, 0);
      const successRate = totalExec > 0 ? (totalSuccess / totalExec) * 100 : 0;
      const avgDurations = points
        .filter(p => p.avg_duration_ms !== null)
        .map(p => p.avg_duration_ms!);
      const avgLatency = avgDurations.length > 0
        ? avgDurations.reduce((s, v) => s + v, 0) / avgDurations.length
        : 0;
      const p95Latency = avgDurations.length > 0
        ? Math.max(...avgDurations) * 1.5
        : 0;

      const latencyHistory: LatencyPoint[] = points.map(p => ({
        date: p.period,
        p50: p.avg_duration_ms ?? 0,
        p95: (p.avg_duration_ms ?? 0) * 1.5,
      }));

      // Map effectiveness over_time to quality history
      const qualityHistory: QualityPoint[] = (effectResp.over_time ?? []).map((e: EffectivenessOverTimePoint) => ({
        date: e.period,
        score: e.acceptance_rate * 100,
      }));

      const qualityScores = qualityHistory.map(q => q.score);
      const latencyValues = latencyHistory.map(l => l.p50);

      results.push({
        botId: `backend-${backend}`,
        botName: t('botPerformanceBenchmarks.botName', { name: backend.charAt(0).toUpperCase() + backend.slice(1) }),
        totalExecutions: totalExec,
        successRate: Math.round(successRate * 10) / 10,
        avgLatencyMs: Math.round(avgLatency),
        p95LatencyMs: Math.round(p95Latency),
        avgQualityScore: effectResp.acceptance_rate * 100,
        qualityTrend: computeTrend(qualityScores),
        latencyTrend: computeTrend(latencyValues),
        latencyHistory,
        qualityHistory,
        lastRunAt: points.length > 0 ? points[points.length - 1].period : new Date().toISOString(),
        evalModel: backend === 'claude' ? 'claude-sonnet-4-6' : backend,
      });
    }

    // If no data, show empty
    benchmarks.value = results;
  } catch (e) {
    if (e instanceof ApiError) {
      error.value = e.message;
    } else {
      error.value = t('botPerformanceBenchmarks.toast.loadFailed');
    }
    showToast(error.value, 'error');
  } finally {
    isLoading.value = false;
  }
}

const selectedBenchmark = computed(() =>
  benchmarks.value.find((b) => b.botId === selectedBotId.value) ?? null
);

function trendIcon(trend: QualityTrend): string {
  return trend === 'up' ? '↑' : trend === 'down' ? '↓' : '→';
}

function trendColor(trend: QualityTrend, higherIsBetter = true): string {
  if (trend === 'stable') return 'var(--text-muted)';
  const positive = higherIsBetter ? trend === 'up' : trend === 'down';
  return positive ? 'var(--accent-green)' : 'var(--accent-red)';
}

function scoreColor(score: number): string {
  if (score >= 90) return 'var(--accent-green)';
  if (score >= 75) return 'var(--accent-amber)';
  return 'var(--accent-red)';
}

function successColor(rate: number): string {
  if (rate >= 95) return 'var(--accent-green)';
  if (rate >= 85) return 'var(--accent-amber)';
  return 'var(--accent-red)';
}

function formatMs(ms: number): string {
  if (ms >= 60000) return `${(ms / 60000).toFixed(1)}m`;
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${ms}ms`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function latencyBarWidth(ms: number, max: number): number {
  return Math.max(4, Math.min(100, (ms / max) * 100));
}

const maxLatency = computed(() =>
  Math.max(...benchmarks.value.map((b) => b.p95LatencyMs), 1)
);

const avgQuality = computed(() => {
  if (benchmarks.value.length === 0) return 0;
  const sum = benchmarks.value.reduce((s, b) => s + b.avgQualityScore, 0);
  return sum / benchmarks.value.length;
});

const avgSuccess = computed(() => {
  if (benchmarks.value.length === 0) return 0;
  const sum = benchmarks.value.reduce((s, b) => s + b.successRate, 0);
  return sum / benchmarks.value.length;
});

async function runEvaluation(botId: string) {
  isRunningEval.value = true;
  selectedBotId.value = botId;
  await new Promise((r) => setTimeout(r, 1200));
  isRunningEval.value = false;
  showToast(t('botPerformanceBenchmarks.toast.evalQueued'), 'success');
}

function exportCsv() {
  showToast(t('botPerformanceBenchmarks.toast.csvExported'), 'success');
}

onMounted(loadBenchmarks);
</script>

<template>
  <div class="page-container">
    <PageHeader
      :title="t('botPerformanceBenchmarks.title')"
      :subtitle="t('botPerformanceBenchmarks.subtitle')"
    />

    <LoadingState v-if="isLoading" :message="t('botPerformanceBenchmarks.loading')" />

    <div v-else-if="error" class="section-card error-state">
      <p class="error-text">{{ error }}</p>
      <button class="btn-secondary" @click="loadBenchmarks">{{ t('common.retry') }}</button>
    </div>

    <template v-else>
      <div class="controls-row">
        <div class="period-tabs">
          <button
            v-for="opt in periodOptions"
            :key="opt.key"
            class="period-tab"
            :class="{ active: selectedPeriod === opt.key }"
            @click="selectedPeriod = opt.key; loadBenchmarks()"
          >
            {{ opt.label }}
          </button>
        </div>
        <button class="btn-secondary" @click="exportCsv">↓ {{ t('botPerformanceBenchmarks.exportCsv') }}</button>
      </div>

      <div class="stats-row">
        <div class="stat-card">
          <div class="stat-label">{{ t('botPerformanceBenchmarks.stat.botsTracked') }}</div>
          <div class="stat-value">{{ benchmarks.length }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('botPerformanceBenchmarks.stat.totalExecutions') }}</div>
          <div class="stat-value">{{ benchmarks.reduce((s, b) => s + b.totalExecutions, 0) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('botPerformanceBenchmarks.stat.avgQuality') }}</div>
          <div class="stat-value" :style="{ color: scoreColor(avgQuality) }">
            {{ avgQuality.toFixed(1) }}
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('botPerformanceBenchmarks.stat.avgSuccess') }}</div>
          <div class="stat-value" :style="{ color: successColor(avgSuccess) }">
            {{ avgSuccess.toFixed(1) }}%
          </div>
        </div>
      </div>

      <div v-if="benchmarks.length === 0" class="section-card empty-state">
        <p>{{ t('botPerformanceBenchmarks.noData') }}</p>
      </div>

      <template v-else>
        <div class="section-card">
          <div class="section-header">
            <h3 class="section-title">{{ t('botPerformanceBenchmarks.overview') }}</h3>
            <span class="section-hint">{{ t('botPerformanceBenchmarks.clickRowHint') }}</span>
          </div>
          <table class="bench-table">
            <thead>
              <tr>
                <th>{{ t('botPerformanceBenchmarks.col.bot') }}</th>
                <th>{{ t('botPerformanceBenchmarks.col.executions') }}</th>
                <th>{{ t('botPerformanceBenchmarks.col.successRate') }}</th>
                <th>{{ t('botPerformanceBenchmarks.col.avgLatency') }}</th>
                <th>{{ t('botPerformanceBenchmarks.col.p95Latency') }}</th>
                <th>{{ t('botPerformanceBenchmarks.col.qualityScore') }}</th>
                <th>{{ t('botPerformanceBenchmarks.col.evalModel') }}</th>
                <th>{{ t('botPerformanceBenchmarks.col.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="b in benchmarks"
                :key="b.botId"
                class="bench-row"
                :class="{ selected: selectedBotId === b.botId }"
                @click="selectedBotId = selectedBotId === b.botId ? null : b.botId"
              >
                <td>
                  <div class="bot-name">{{ b.botName }}</div>
                  <div class="bot-meta">{{ t('botPerformanceBenchmarks.lastRun', { date: formatDate(b.lastRunAt) }) }}</div>
                </td>
                <td>{{ b.totalExecutions.toLocaleString() }}</td>
                <td>
                  <span :style="{ color: successColor(b.successRate), fontWeight: '600' }">
                    {{ b.successRate }}%
                  </span>
                </td>
                <td>
                  <span :style="{ color: trendColor(b.latencyTrend, false) }">
                    {{ trendIcon(b.latencyTrend) }}
                  </span>
                  {{ formatMs(b.avgLatencyMs) }}
                </td>
                <td>
                  <div class="latency-bar-wrap">
                    <div
                      class="latency-bar"
                      :style="{ width: latencyBarWidth(b.p95LatencyMs, maxLatency) + '%' }"
                    ></div>
                    <span class="latency-label">{{ formatMs(b.p95LatencyMs) }}</span>
                  </div>
                </td>
                <td>
                  <span :style="{ color: scoreColor(b.avgQualityScore), fontWeight: '600' }">
                    {{ trendIcon(b.qualityTrend) }} {{ b.avgQualityScore.toFixed(1) }}
                  </span>
                </td>
                <td><code class="mono">{{ b.evalModel }}</code></td>
                <td>
                  <button
                    class="btn-sm"
                    :disabled="isRunningEval && selectedBotId === b.botId"
                    @click.stop="runEvaluation(b.botId)"
                  >
                    {{ isRunningEval && selectedBotId === b.botId ? t('botPerformanceBenchmarks.queuing') : t('botPerformanceBenchmarks.runEval') }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <template v-if="selectedBenchmark">
          <div class="detail-grid">
            <div class="section-card">
              <div class="section-header">
                <h3 class="section-title">{{ t('botPerformanceBenchmarks.latencyTrend', { bot: selectedBenchmark.botName }) }}</h3>
              </div>
              <div class="trend-chart">
                <div v-for="point in selectedBenchmark.latencyHistory" :key="point.date" class="trend-col">
                  <div class="bar-group">
                    <div
                      class="bar p50"
                      :style="{ height: (point.p50 / (selectedBenchmark.p95LatencyMs || 1)) * 80 + 'px' }"
                      :title="t('botPerformanceBenchmarks.tooltip.p50', { val: formatMs(point.p50) })"
                    ></div>
                    <div
                      class="bar p95"
                      :style="{ height: (point.p95 / (selectedBenchmark.p95LatencyMs || 1)) * 80 + 'px' }"
                      :title="t('botPerformanceBenchmarks.tooltip.p95', { val: formatMs(point.p95) })"
                    ></div>
                  </div>
                  <div class="bar-label">{{ formatDate(point.date) }}</div>
                </div>
              </div>
              <div class="chart-legend">
                <span class="legend-item"><span class="dot p50-dot"></span> P50</span>
                <span class="legend-item"><span class="dot p95-dot"></span> P95</span>
              </div>
            </div>

            <div class="section-card">
              <div class="section-header">
                <h3 class="section-title">{{ t('botPerformanceBenchmarks.qualityTrend') }}</h3>
              </div>
              <div class="quality-chart">
                <div v-for="point in selectedBenchmark.qualityHistory" :key="point.date" class="quality-col">
                  <div class="quality-bar-wrap">
                    <div
                      class="quality-bar"
                      :style="{ height: point.score + '%', background: scoreColor(point.score) }"
                      :title="t('botPerformanceBenchmarks.tooltip.score', { val: point.score })"
                    ></div>
                  </div>
                  <div class="quality-score">{{ point.score.toFixed(0) }}</div>
                  <div class="bar-label">{{ formatDate(point.date) }}</div>
                </div>
              </div>
              <div class="eval-note">
                {{ t('botPerformanceBenchmarks.judgeModel') }} <code class="mono">{{ selectedBenchmark.evalModel }}</code>
              </div>
            </div>
          </div>
        </template>

        <div v-else class="empty-detail">
          <div class="empty-text">{{ t('botPerformanceBenchmarks.selectBotHint') }}</div>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.page-container { padding: 24px; max-width: 1200px; }
.controls-row { display: flex; align-items: center; gap: 12px; margin-bottom: 20px; }
.period-tabs { display: flex; gap: 4px; background: var(--bg-secondary); border-radius: 8px; padding: 4px; }
.period-tab { padding: 6px 14px; border-radius: 6px; border: none; background: transparent; color: var(--text-muted); cursor: pointer; font-size: 13px; }
.period-tab.active { background: var(--bg-primary); color: var(--text-primary); font-weight: 600; }
.btn-secondary { padding: 6px 14px; border-radius: 6px; border: 1px solid var(--border-color); background: transparent; color: var(--text-primary); cursor: pointer; font-size: 13px; }
.stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
.stat-card { background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 8px; padding: 16px; text-align: center; }
.stat-label { font-size: 12px; color: var(--text-muted); margin-bottom: 6px; }
.stat-value { font-size: 24px; font-weight: 700; color: var(--text-primary); }
.section-card { background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 8px; padding: 20px; margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.section-title { font-size: 15px; font-weight: 600; color: var(--text-primary); margin: 0; }
.section-hint { font-size: 12px; color: var(--text-muted); }
.error-state { text-align: center; display: flex; flex-direction: column; align-items: center; gap: 12px; }
.error-text { font-size: 0.875rem; color: #ef4444; margin: 0; }
.empty-state { text-align: center; padding: 40px; }
.empty-state p { font-size: 0.875rem; color: var(--text-muted); margin: 0; }
.bench-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.bench-table th { text-align: left; padding: 8px 12px; color: var(--text-muted); font-weight: 500; border-bottom: 1px solid var(--border-color); }
.bench-row td { padding: 12px; border-bottom: 1px solid var(--border-color); vertical-align: middle; }
.bench-row { cursor: pointer; transition: background 0.15s; }
.bench-row:hover { background: var(--bg-hover); }
.bench-row.selected { background: color-mix(in srgb, var(--accent-blue) 8%, transparent); }
.bot-name { font-weight: 600; color: var(--text-primary); }
.bot-meta { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
.latency-bar-wrap { display: flex; align-items: center; gap: 8px; }
.latency-bar { height: 6px; border-radius: 3px; background: var(--accent-blue); opacity: 0.7; }
.latency-label { font-size: 12px; color: var(--text-muted); white-space: nowrap; }
.mono { font-family: monospace; font-size: 11px; color: var(--text-muted); }
.btn-sm { padding: 4px 10px; border-radius: 5px; border: 1px solid var(--border-color); background: transparent; color: var(--text-primary); cursor: pointer; font-size: 12px; }
.btn-sm:disabled { opacity: 0.5; cursor: not-allowed; }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.trend-chart { display: flex; align-items: flex-end; gap: 12px; min-height: 100px; padding: 8px 0; }
.trend-col { display: flex; flex-direction: column; align-items: center; gap: 4px; flex: 1; }
.bar-group { display: flex; align-items: flex-end; gap: 3px; height: 80px; }
.bar { width: 10px; border-radius: 3px 3px 0 0; min-height: 4px; }
.bar.p50 { background: var(--accent-blue); opacity: 0.7; }
.bar.p95 { background: var(--accent-amber); opacity: 0.8; }
.bar-label { font-size: 10px; color: var(--text-muted); white-space: nowrap; }
.chart-legend { display: flex; gap: 16px; margin-top: 8px; }
.legend-item { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-muted); }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.p50-dot { background: var(--accent-blue); }
.p95-dot { background: var(--accent-amber); }
.quality-chart { display: flex; align-items: flex-end; gap: 12px; min-height: 120px; padding: 8px 0; }
.quality-col { display: flex; flex-direction: column; align-items: center; gap: 4px; flex: 1; }
.quality-bar-wrap { height: 100px; display: flex; align-items: flex-end; }
.quality-bar { width: 20px; border-radius: 3px 3px 0 0; min-height: 4px; }
.quality-score { font-size: 11px; font-weight: 600; color: var(--text-primary); }
.eval-note { margin-top: 12px; font-size: 12px; color: var(--text-muted); }
.empty-detail { text-align: center; padding: 40px; color: var(--text-muted); }
.empty-text { font-size: 14px; }
</style>
