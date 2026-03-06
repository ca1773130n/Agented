<script setup lang="ts">
import { ref, computed } from 'vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const showToast = useToast();

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
  { key: '7d', label: 'Last 7 Days' },
  { key: '30d', label: 'Last 30 Days' },
  { key: '90d', label: 'Last 90 Days' },
];

const selectedBotId = ref<string | null>(null);
const isRunningEval = ref(false);

const benchmarks = ref<BotBenchmark[]>([
  {
    botId: 'bot-pr-review',
    botName: 'PR Review Bot',
    totalExecutions: 312,
    successRate: 94.2,
    avgLatencyMs: 18400,
    p95LatencyMs: 42100,
    avgQualityScore: 87.3,
    qualityTrend: 'up',
    latencyTrend: 'stable',
    evalModel: 'claude-sonnet-4-6',
    lastRunAt: '2026-03-06T11:42:00Z',
    latencyHistory: [
      { date: '2026-02-04', p50: 16200, p95: 38000 },
      { date: '2026-02-11', p50: 17100, p95: 39500 },
      { date: '2026-02-18', p50: 18000, p95: 41000 },
      { date: '2026-02-25', p50: 17800, p95: 40500 },
      { date: '2026-03-04', p50: 18400, p95: 42100 },
    ],
    qualityHistory: [
      { date: '2026-02-04', score: 82.1 },
      { date: '2026-02-11', score: 83.5 },
      { date: '2026-02-18', score: 85.0 },
      { date: '2026-02-25', score: 86.2 },
      { date: '2026-03-04', score: 87.3 },
    ],
  },
  {
    botId: 'bot-security',
    botName: 'Security Audit Bot',
    totalExecutions: 89,
    successRate: 97.8,
    avgLatencyMs: 34200,
    p95LatencyMs: 71000,
    avgQualityScore: 91.6,
    qualityTrend: 'stable',
    latencyTrend: 'down',
    evalModel: 'claude-opus-4-6',
    lastRunAt: '2026-03-06T09:00:00Z',
    latencyHistory: [
      { date: '2026-02-04', p50: 38000, p95: 78000 },
      { date: '2026-02-11', p50: 36500, p95: 75000 },
      { date: '2026-02-18', p50: 35200, p95: 73000 },
      { date: '2026-02-25', p50: 34800, p95: 72000 },
      { date: '2026-03-04', p50: 34200, p95: 71000 },
    ],
    qualityHistory: [
      { date: '2026-02-04', score: 91.0 },
      { date: '2026-02-11', score: 91.2 },
      { date: '2026-02-18', score: 91.5 },
      { date: '2026-02-25', score: 91.8 },
      { date: '2026-03-04', score: 91.6 },
    ],
  },
  {
    botId: 'bot-dep-audit',
    botName: 'Dependency Audit Bot',
    totalExecutions: 54,
    successRate: 88.9,
    avgLatencyMs: 12100,
    p95LatencyMs: 28000,
    avgQualityScore: 74.2,
    qualityTrend: 'down',
    latencyTrend: 'up',
    evalModel: 'claude-haiku-4-5',
    lastRunAt: '2026-03-05T16:30:00Z',
    latencyHistory: [
      { date: '2026-02-04', p50: 10200, p95: 22000 },
      { date: '2026-02-11', p50: 10800, p95: 24000 },
      { date: '2026-02-18', p50: 11400, p95: 26000 },
      { date: '2026-02-25', p50: 11900, p95: 27000 },
      { date: '2026-03-04', p50: 12100, p95: 28000 },
    ],
    qualityHistory: [
      { date: '2026-02-04', score: 79.5 },
      { date: '2026-02-11', score: 78.0 },
      { date: '2026-02-18', score: 76.5 },
      { date: '2026-02-25', score: 75.1 },
      { date: '2026-03-04', score: 74.2 },
    ],
  },
]);

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
  const sum = benchmarks.value.reduce((s, b) => s + b.avgQualityScore, 0);
  return sum / benchmarks.value.length;
});

const avgSuccess = computed(() => {
  const sum = benchmarks.value.reduce((s, b) => s + b.successRate, 0);
  return sum / benchmarks.value.length;
});

async function runEvaluation(botId: string) {
  isRunningEval.value = true;
  selectedBotId.value = botId;
  await new Promise((r) => setTimeout(r, 1200));
  isRunningEval.value = false;
  showToast('LLM-as-judge evaluation queued — results in ~5 minutes', 'success');
}

function exportCsv() {
  showToast('Benchmark CSV exported', 'success');
}
</script>

<template>
  <div class="page-container">
    <AppBreadcrumb :items="[{ label: 'Bots' }, { label: 'Performance Benchmarks' }]" />
    <PageHeader
      title="Bot Performance Benchmarks"
      subtitle="Track execution latency, LLM-as-judge quality scores, and success rates per bot over time"
    />

    <div class="controls-row">
      <div class="period-tabs">
        <button
          v-for="opt in periodOptions"
          :key="opt.key"
          class="period-tab"
          :class="{ active: selectedPeriod === opt.key }"
          @click="selectedPeriod = opt.key"
        >
          {{ opt.label }}
        </button>
      </div>
      <button class="btn-secondary" @click="exportCsv">↓ Export CSV</button>
    </div>

    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-label">Bots Tracked</div>
        <div class="stat-value">{{ benchmarks.length }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Total Executions</div>
        <div class="stat-value">{{ benchmarks.reduce((s, b) => s + b.totalExecutions, 0) }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Avg Quality Score</div>
        <div class="stat-value" :style="{ color: scoreColor(avgQuality) }">
          {{ avgQuality.toFixed(1) }}
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Avg Success Rate</div>
        <div class="stat-value" :style="{ color: successColor(avgSuccess) }">
          {{ avgSuccess.toFixed(1) }}%
        </div>
      </div>
    </div>

    <div class="section-card">
      <div class="section-header">
        <h3 class="section-title">Bot Benchmark Overview</h3>
        <span class="section-hint">Click a row to view trend history</span>
      </div>
      <table class="bench-table">
        <thead>
          <tr>
            <th>Bot</th>
            <th>Executions</th>
            <th>Success Rate</th>
            <th>Avg Latency</th>
            <th>P95 Latency</th>
            <th>Quality Score</th>
            <th>Eval Model</th>
            <th>Actions</th>
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
              <div class="bot-meta">Last run {{ formatDate(b.lastRunAt) }}</div>
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
                {{ isRunningEval && selectedBotId === b.botId ? 'Queuing…' : 'Run Eval' }}
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
            <h3 class="section-title">Latency Trend — {{ selectedBenchmark.botName }}</h3>
          </div>
          <div class="trend-chart">
            <div v-for="point in selectedBenchmark.latencyHistory" :key="point.date" class="trend-col">
              <div class="bar-group">
                <div
                  class="bar p50"
                  :style="{ height: (point.p50 / selectedBenchmark.p95LatencyMs) * 80 + 'px' }"
                  :title="`P50: ${formatMs(point.p50)}`"
                ></div>
                <div
                  class="bar p95"
                  :style="{ height: (point.p95 / selectedBenchmark.p95LatencyMs) * 80 + 'px' }"
                  :title="`P95: ${formatMs(point.p95)}`"
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
            <h3 class="section-title">Quality Score Trend (LLM-as-judge)</h3>
          </div>
          <div class="quality-chart">
            <div v-for="point in selectedBenchmark.qualityHistory" :key="point.date" class="quality-col">
              <div class="quality-bar-wrap">
                <div
                  class="quality-bar"
                  :style="{ height: point.score + '%', background: scoreColor(point.score) }"
                  :title="`Score: ${point.score}`"
                ></div>
              </div>
              <div class="quality-score">{{ point.score.toFixed(0) }}</div>
              <div class="bar-label">{{ formatDate(point.date) }}</div>
            </div>
          </div>
          <div class="eval-note">
            Judge model: <code class="mono">{{ selectedBenchmark.evalModel }}</code>
          </div>
        </div>
      </div>
    </template>

    <div v-else class="empty-detail">
      <div class="empty-icon">📊</div>
      <div class="empty-text">Select a bot above to view latency and quality trends</div>
    </div>
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
.empty-icon { font-size: 32px; margin-bottom: 12px; }
.empty-text { font-size: 14px; }
</style>
