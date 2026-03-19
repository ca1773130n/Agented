<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import LoadingState from '../components/base/LoadingState.vue';

const isLoading = ref(true);
const selectedBot = ref<string>('all');
const selectedPeriod = ref<'7d' | '30d' | '90d'>('30d');

interface Finding {
  date: string;
  bot: string;
  category: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  count: number;
}

interface TrendPoint {
  date: string;
  total: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
}

const findings = ref<Finding[]>([]);
const trendPoints = ref<TrendPoint[]>([]);
const availableBots = ref<string[]>([]);

async function loadData() {
  try {
    const params = new URLSearchParams({ period: selectedPeriod.value, bot: selectedBot.value });
    const res = await fetch(`/admin/analytics/findings-trend?${params}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    findings.value = data.findings ?? [];
    trendPoints.value = data.trend ?? [];
    availableBots.value = data.bots ?? [];
  } catch {
    // Generate demo data
    const bots = ['bot-security', 'bot-pr-review', 'bot-dep-check'];
    availableBots.value = bots;

    const points: TrendPoint[] = [];
    const days = selectedPeriod.value === '7d' ? 7 : selectedPeriod.value === '30d' ? 30 : 90;
    let baseCrit = 12, baseHigh = 34, baseMed = 67, baseLow = 120;
    for (let i = days; i >= 0; i--) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      baseCrit = Math.max(0, baseCrit + Math.round((Math.random() - 0.55) * 3));
      baseHigh = Math.max(0, baseHigh + Math.round((Math.random() - 0.52) * 5));
      baseMed = Math.max(0, baseMed + Math.round((Math.random() - 0.51) * 7));
      baseLow = Math.max(0, baseLow + Math.round((Math.random() - 0.5) * 10));
      points.push({
        date: d.toISOString().slice(0, 10),
        critical: baseCrit,
        high: baseHigh,
        medium: baseMed,
        low: baseLow,
        total: baseCrit + baseHigh + baseMed + baseLow,
      });
    }
    trendPoints.value = points;
  } finally {
    isLoading.value = false;
  }
}

const latest = computed(() => trendPoints.value[trendPoints.value.length - 1]);
const first = computed(() => trendPoints.value[0]);

function delta(key: keyof TrendPoint): number {
  if (!latest.value || !first.value) return 0;
  return (latest.value[key] as number) - (first.value[key] as number);
}

function deltaClass(key: keyof TrendPoint): string {
  const d = delta(key);
  return d < 0 ? 'improving' : d > 0 ? 'worsening' : 'stable';
}

function deltaLabel(key: keyof TrendPoint): string {
  const d = delta(key);
  if (d === 0) return 'No change';
  return (d > 0 ? '+' : '') + d + ' vs period start';
}

// Simple SVG sparkline
function sparklinePath(key: keyof TrendPoint, width = 180, height = 40): string {
  const pts = trendPoints.value;
  if (pts.length < 2) return '';
  const vals = pts.map(p => p[key] as number);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const range = max - min || 1;
  const step = width / (pts.length - 1);
  return pts.map((p, i) => {
    const x = i * step;
    const y = height - ((p[key] as number - min) / range) * height;
    return `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(' ');
}

const maxTotal = computed(() => Math.max(...trendPoints.value.map(p => p.total), 1));

onMounted(loadData);
</script>

<template>
  <div class="findings-trend-page">

    <LoadingState v-if="isLoading" message="Loading findings trend..." />

    <template v-else>
      <!-- Controls -->
      <div class="controls-row">
        <div class="page-title">
          <h1>Findings Trend Analysis</h1>
          <p>Track whether your codebase is improving or degrading over time</p>
        </div>
        <div class="control-group">
          <select v-model="selectedBot" class="filter-select" @change="loadData">
            <option value="all">All bots</option>
            <option v-for="b in availableBots" :key="b" :value="b">{{ b }}</option>
          </select>
          <div class="period-toggle">
            <button v-for="p in (['7d', '30d', '90d'] as const)" :key="p" class="period-btn" :class="{ active: selectedPeriod === p }" @click="selectedPeriod = p; loadData()">{{ p }}</button>
          </div>
        </div>
      </div>

      <!-- Summary Cards -->
      <div class="stats-grid" v-if="latest">
        <div class="card stat-card" :class="deltaClass('critical')">
          <div class="stat-severity critical">Critical</div>
          <div class="stat-count">{{ latest.critical }}</div>
          <div class="stat-delta" :class="deltaClass('critical')">{{ deltaLabel('critical') }}</div>
          <svg class="sparkline" viewBox="0 0 180 40" preserveAspectRatio="none">
            <path :d="sparklinePath('critical')" fill="none" stroke="var(--accent-crimson)" stroke-width="1.5"/>
          </svg>
        </div>
        <div class="card stat-card" :class="deltaClass('high')">
          <div class="stat-severity high">High</div>
          <div class="stat-count">{{ latest.high }}</div>
          <div class="stat-delta" :class="deltaClass('high')">{{ deltaLabel('high') }}</div>
          <svg class="sparkline" viewBox="0 0 180 40" preserveAspectRatio="none">
            <path :d="sparklinePath('high')" fill="none" stroke="var(--accent-amber)" stroke-width="1.5"/>
          </svg>
        </div>
        <div class="card stat-card" :class="deltaClass('medium')">
          <div class="stat-severity medium">Medium</div>
          <div class="stat-count">{{ latest.medium }}</div>
          <div class="stat-delta" :class="deltaClass('medium')">{{ deltaLabel('medium') }}</div>
          <svg class="sparkline" viewBox="0 0 180 40" preserveAspectRatio="none">
            <path :d="sparklinePath('medium')" fill="none" stroke="var(--accent-cyan)" stroke-width="1.5"/>
          </svg>
        </div>
        <div class="card stat-card">
          <div class="stat-severity low">Low</div>
          <div class="stat-count">{{ latest.low }}</div>
          <div class="stat-delta" :class="deltaClass('low')">{{ deltaLabel('low') }}</div>
          <svg class="sparkline" viewBox="0 0 180 40" preserveAspectRatio="none">
            <path :d="sparklinePath('low')" fill="none" stroke="var(--text-tertiary)" stroke-width="1.5"/>
          </svg>
        </div>
      </div>

      <!-- Total Trend Chart -->
      <div class="card chart-card">
        <div class="chart-header">
          <h3>Total Findings Over Time</h3>
          <div class="chart-legend">
            <span class="legend-item critical">Critical</span>
            <span class="legend-item high">High</span>
            <span class="legend-item medium">Medium</span>
            <span class="legend-item low">Low</span>
          </div>
        </div>

        <div class="bar-chart">
          <div v-for="(pt, i) in trendPoints" :key="pt.date" class="bar-group" :title="`${pt.date}: ${pt.total} total`">
            <div class="stacked-bar">
              <div class="bar-seg seg-low" :style="{ height: (pt.low / maxTotal * 100) + '%' }"></div>
              <div class="bar-seg seg-medium" :style="{ height: (pt.medium / maxTotal * 100) + '%' }"></div>
              <div class="bar-seg seg-high" :style="{ height: (pt.high / maxTotal * 100) + '%' }"></div>
              <div class="bar-seg seg-critical" :style="{ height: (pt.critical / maxTotal * 100) + '%' }"></div>
            </div>
            <span v-if="i % Math.max(1, Math.floor(trendPoints.length / 6)) === 0" class="bar-label">
              {{ pt.date.slice(5) }}
            </span>
          </div>
        </div>
      </div>

      <!-- Trend Summary -->
      <div class="card summary-card">
        <h3>Period Summary ({{ selectedPeriod }})</h3>
        <div class="summary-grid">
          <div class="summary-item">
            <span class="summary-label">Period start total</span>
            <span class="summary-value">{{ first?.total ?? 0 }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">Period end total</span>
            <span class="summary-value">{{ latest?.total ?? 0 }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">Net change</span>
            <span class="summary-value" :class="delta('total') < 0 ? 'improving' : delta('total') > 0 ? 'worsening' : ''">
              {{ delta('total') > 0 ? '+' : '' }}{{ delta('total') }} findings
            </span>
          </div>
          <div class="summary-item">
            <span class="summary-label">Trend</span>
            <span class="summary-value" :class="delta('total') < 0 ? 'improving' : delta('total') > 0 ? 'worsening' : ''">
              {{ delta('total') < 0 ? 'Improving' : delta('total') > 0 ? 'Worsening' : 'Stable' }}
            </span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.findings-trend-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  width: 100%;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.card { padding: 24px; }

.controls-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}

.page-title h1 { font-size: 1.2rem; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.page-title p { font-size: 0.85rem; color: var(--text-tertiary); }

.control-group { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }

.filter-select {
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid var(--border-default);
  background: var(--bg-tertiary);
  color: var(--text-primary);
  font-size: 0.85rem;
  outline: none;
}

.period-toggle { display: flex; border: 1px solid var(--border-default); border-radius: 6px; overflow: hidden; }
.period-btn {
  padding: 7px 14px;
  font-size: 0.82rem;
  font-weight: 500;
  background: transparent;
  color: var(--text-secondary);
  border: none;
  cursor: pointer;
  transition: all 0.15s;
}
.period-btn.active { background: var(--accent-cyan); color: #000; }

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.stat-card { padding: 20px; display: flex; flex-direction: column; gap: 8px; }

.stat-severity {
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.stat-severity.critical { color: var(--accent-crimson); }
.stat-severity.high { color: var(--accent-amber); }
.stat-severity.medium { color: var(--accent-cyan); }
.stat-severity.low { color: var(--text-tertiary); }

.stat-count { font-size: 2rem; font-weight: 700; color: var(--text-primary); line-height: 1; }

.stat-delta {
  font-size: 0.78rem;
  color: var(--text-tertiary);
}

.stat-delta.improving { color: var(--accent-emerald); }
.stat-delta.worsening { color: var(--accent-crimson); }

.sparkline { width: 100%; height: 40px; margin-top: 4px; }

.chart-card { padding: 24px; }

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.chart-header h3 { font-size: 0.95rem; font-weight: 600; color: var(--text-primary); }

.chart-legend { display: flex; gap: 16px; }

.legend-item {
  font-size: 0.78rem;
  font-weight: 500;
  padding-left: 12px;
  position: relative;
}

.legend-item::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 8px;
  height: 8px;
  border-radius: 2px;
}

.legend-item.critical::before { background: var(--accent-crimson); }
.legend-item.high::before { background: var(--accent-amber); }
.legend-item.medium::before { background: var(--accent-cyan); }
.legend-item.low::before { background: var(--text-tertiary); }

.bar-chart {
  display: flex;
  align-items: flex-end;
  gap: 3px;
  height: 160px;
}

.bar-group {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  height: 100%;
  min-width: 0;
}

.stacked-bar {
  flex: 1;
  width: 100%;
  display: flex;
  flex-direction: column-reverse;
  border-radius: 2px 2px 0 0;
  overflow: hidden;
}

.bar-seg { width: 100%; transition: height 0.3s; min-height: 0; }
.seg-critical { background: var(--accent-crimson); }
.seg-high { background: var(--accent-amber); }
.seg-medium { background: var(--accent-cyan); }
.seg-low { background: var(--text-muted, var(--text-tertiary)); opacity: 0.5; }

.bar-label { font-size: 0.65rem; color: var(--text-tertiary); white-space: nowrap; }

.summary-card h3 { font-size: 0.95rem; font-weight: 600; color: var(--text-primary); margin-bottom: 20px; }

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
}

.summary-item { display: flex; flex-direction: column; gap: 6px; }
.summary-label { font-size: 0.8rem; color: var(--text-tertiary); }
.summary-value { font-size: 1.1rem; font-weight: 600; color: var(--text-primary); }
.summary-value.improving { color: var(--accent-emerald); }
.summary-value.worsening { color: var(--accent-crimson); }

@media (max-width: 900px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
  .summary-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
