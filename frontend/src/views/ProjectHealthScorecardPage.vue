<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';

const router = useRouter();

interface Project {
  id: string;
  name: string;
}

interface Category {
  id: string;
  name: string;
  score: number;
  trend: number;
  icon: string;
  bars: number[];
}

interface SignalRow {
  id: string;
  bot: string;
  metric: string;
  current: string;
  previous: string;
  impact: number;
  status: 'good' | 'warn' | 'bad';
}

interface Recommendation {
  id: string;
  title: string;
  description: string;
  priority: 'high' | 'medium' | 'low';
  category: string;
}

const projects = ref<Project[]>([
  { id: 'proj-aaa', name: 'Agented Platform' },
  { id: 'proj-bbb', name: 'API Gateway' },
  { id: 'proj-ccc', name: 'Frontend Dashboard' },
]);

const selectedProjectId = ref('proj-aaa');

const selectedProject = computed(() =>
  projects.value.find(p => p.id === selectedProjectId.value) ?? projects.value[0]
);

const overallScore = ref(78);
const trendDelta = ref(3);

const weeklyHistory = ref([72, 74, 71, 75, 73, 76, 75, 78]);
const maxHistory = computed(() => Math.max(...weeklyHistory.value));

const categories = ref<Category[]>([
  {
    id: 'security',
    name: 'Security',
    score: 65,
    trend: -2,
    icon: 'shield',
    bars: [68, 70, 67, 65, 66, 64, 65, 65],
  },
  {
    id: 'test-coverage',
    name: 'Test Coverage',
    score: 82,
    trend: 5,
    icon: 'check-circle',
    bars: [74, 76, 77, 78, 79, 80, 81, 82],
  },
  {
    id: 'pr-velocity',
    name: 'PR Velocity',
    score: 88,
    trend: 1,
    icon: 'git-pull-request',
    bars: [84, 85, 86, 85, 87, 86, 88, 88],
  },
  {
    id: 'dependency-health',
    name: 'Dependency Health',
    score: 71,
    trend: -3,
    icon: 'package',
    bars: [76, 75, 74, 73, 73, 72, 72, 71],
  },
]);

const signals = ref<SignalRow[]>([
  { id: 's-1', bot: 'bot-security', metric: 'Critical CVEs', current: '3', previous: '1', impact: -8, status: 'bad' },
  { id: 's-2', bot: 'bot-security', metric: 'High CVEs', current: '7', previous: '9', impact: 3, status: 'warn' },
  { id: 's-3', bot: 'bot-pr-review', metric: 'Avg Review Time', current: '1.8h', previous: '2.1h', impact: 2, status: 'good' },
  { id: 's-4', bot: 'bot-pr-review', metric: 'PR Merge Rate', current: '94%', previous: '91%', impact: 3, status: 'good' },
  { id: 's-5', bot: 'bot-test-coverage', metric: 'Line Coverage', current: '82%', previous: '77%', impact: 5, status: 'good' },
  { id: 's-6', bot: 'bot-deps', metric: 'Outdated Packages', current: '14', previous: '11', impact: -5, status: 'warn' },
  { id: 's-7', bot: 'bot-deps', metric: 'License Issues', current: '2', previous: '0', impact: -3, status: 'bad' },
]);

const recommendations = ref<Recommendation[]>([
  {
    id: 'rec-1',
    title: 'Patch 3 critical CVEs in dependencies',
    description: 'bot-security flagged lodash, axios, and jsonwebtoken with critical severity vulnerabilities. Update to patched versions immediately.',
    priority: 'high',
    category: 'Security',
  },
  {
    id: 'rec-2',
    title: 'Resolve 2 license compliance violations',
    description: 'Two packages use GPL-3.0 licenses incompatible with your project license. Replace or seek exemptions.',
    priority: 'high',
    category: 'Dependency Health',
  },
  {
    id: 'rec-3',
    title: 'Increase unit test coverage for services layer',
    description: 'Coverage in src/services/ sits at 61%. Adding tests for execution and orchestration paths would push the overall score above 85.',
    priority: 'medium',
    category: 'Test Coverage',
  },
  {
    id: 'rec-4',
    title: 'Update 14 outdated packages to latest minor versions',
    description: 'Running npm audit fix --force will resolve most outdated packages. Review any breaking changes before merging.',
    priority: 'low',
    category: 'Dependency Health',
  },
]);

function scoreColor(score: number): string {
  if (score >= 80) return '#34d399';
  if (score >= 60) return '#f59e0b';
  return '#ef4444';
}

function scoreRingColor(score: number): string {
  if (score >= 80) return 'rgba(52, 211, 153, 0.25)';
  if (score >= 60) return 'rgba(245, 158, 11, 0.25)';
  return 'rgba(239, 68, 68, 0.25)';
}

function scoreBorderColor(score: number): string {
  if (score >= 80) return '#34d399';
  if (score >= 60) return '#f59e0b';
  return '#ef4444';
}

function trendClass(trend: number): string {
  if (trend > 0) return 'trend-up';
  if (trend < 0) return 'trend-down';
  return 'trend-flat';
}

function trendLabel(trend: number): string {
  if (trend > 0) return `↑ +${trend}`;
  if (trend < 0) return `↓ ${trend}`;
  return '→ 0';
}

function impactClass(impact: number): string {
  if (impact > 0) return 'impact-pos';
  if (impact < 0) return 'impact-neg';
  return 'impact-neutral';
}

function impactLabel(impact: number): string {
  if (impact > 0) return `+${impact} pts`;
  return `${impact} pts`;
}

function statusClass(status: SignalRow['status']): string {
  if (status === 'good') return 'badge-good';
  if (status === 'warn') return 'badge-warn';
  return 'badge-bad';
}

function priorityClass(priority: Recommendation['priority']): string {
  if (priority === 'high') return 'priority-high';
  if (priority === 'medium') return 'priority-medium';
  return 'priority-low';
}

function barHeightPct(val: number): number {
  const min = 55;
  const max = 100;
  return Math.round(((val - min) / (max - min)) * 100);
}

function historyBarHeightPct(val: number): number {
  const min = Math.min(...weeklyHistory.value) - 5;
  return Math.round(((val - min) / (maxHistory.value - min)) * 100);
}
</script>

<template>
  <div class="scorecard-page">
    <AppBreadcrumb :items="[
      { label: 'Projects', action: () => router.push({ name: 'projects' }) },
      { label: 'Health Scorecard' },
    ]" />

    <PageHeader
      title="Project Health Scorecard"
      subtitle="Aggregate bot signals into a single health score with trend tracking and drill-down."
    />

    <!-- Project Selector -->
    <div class="selector-bar">
      <label class="selector-label">Project</label>
      <select v-model="selectedProjectId" class="project-select">
        <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
      </select>
      <span class="selector-meta">Last updated: just now</span>
    </div>

    <!-- Hero Score -->
    <div class="card hero-card">
      <div class="hero-inner">
        <div
          class="score-ring"
          :style="{
            borderColor: scoreBorderColor(overallScore),
            background: scoreRingColor(overallScore),
          }"
        >
          <span class="score-number" :style="{ color: scoreColor(overallScore) }">
            {{ overallScore }}
          </span>
          <span class="score-denom">/100</span>
        </div>
        <div class="hero-meta">
          <div class="hero-project">{{ selectedProject.name }}</div>
          <div class="hero-label">Overall Health Score</div>
          <div :class="['hero-trend', trendDelta > 0 ? 'trend-up' : 'trend-down']">
            {{ trendDelta > 0 ? '↑' : '↓' }} {{ trendDelta > 0 ? '+' : '' }}{{ trendDelta }} from last week
          </div>
          <div class="hero-status-label" :style="{ color: scoreColor(overallScore) }">
            {{ overallScore >= 80 ? 'Healthy' : overallScore >= 60 ? 'Needs Attention' : 'Critical' }}
          </div>
        </div>
      </div>
    </div>

    <!-- Category Cards 2x2 -->
    <div class="categories-grid">
      <div
        v-for="cat in categories"
        :key="cat.id"
        class="card category-card"
      >
        <div class="cat-header">
          <span class="cat-name">{{ cat.name }}</span>
          <span :class="['cat-trend', trendClass(cat.trend)]">{{ trendLabel(cat.trend) }}</span>
        </div>
        <div class="cat-score" :style="{ color: scoreColor(cat.score) }">{{ cat.score }}</div>
        <div class="cat-score-label">/ 100</div>
        <div class="cat-bar-track">
          <div
            class="cat-bar-fill"
            :style="{
              width: cat.score + '%',
              background: scoreColor(cat.score),
            }"
          ></div>
        </div>
        <!-- Mini sparkline -->
        <div class="sparkline">
          <div
            v-for="(val, i) in cat.bars"
            :key="i"
            class="spark-bar"
            :style="{
              height: barHeightPct(val) + '%',
              background: i === cat.bars.length - 1 ? scoreColor(cat.score) : 'var(--border-default)',
            }"
          ></div>
        </div>
      </div>
    </div>

    <!-- Signal Breakdown Table -->
    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
          </svg>
          Signal Breakdown
        </h3>
        <span class="header-meta">{{ signals.length }} signals from {{ [...new Set(signals.map(s => s.bot))].length }} bots</span>
      </div>
      <div class="table-wrapper">
        <table class="signal-table">
          <thead>
            <tr>
              <th>Bot</th>
              <th>Metric</th>
              <th>Current</th>
              <th>Previous</th>
              <th>Score Impact</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="sig in signals" :key="sig.id">
              <td><code class="bot-code">{{ sig.bot }}</code></td>
              <td class="metric-col">{{ sig.metric }}</td>
              <td class="value-col">{{ sig.current }}</td>
              <td class="prev-col">{{ sig.previous }}</td>
              <td>
                <span :class="['impact-badge', impactClass(sig.impact)]">
                  {{ impactLabel(sig.impact) }}
                </span>
              </td>
              <td>
                <span :class="['status-badge', statusClass(sig.status)]">
                  {{ sig.status }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Weekly Score History -->
    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <rect x="3" y="3" width="18" height="18" rx="2"/>
            <path d="M3 9h18M9 21V9"/>
          </svg>
          Weekly Score History
        </h3>
        <span class="header-meta">Last 8 weeks</span>
      </div>
      <div class="history-section">
        <div class="history-bars">
          <div v-for="(val, i) in weeklyHistory" :key="i" class="history-bar-col">
            <div class="history-bar-wrap">
              <div
                class="history-bar-fill"
                :style="{
                  height: historyBarHeightPct(val) + '%',
                  background: i === weeklyHistory.length - 1 ? scoreColor(val) : 'var(--border-default)',
                  opacity: i === weeklyHistory.length - 1 ? 1 : 0.6 + (i / weeklyHistory.length) * 0.4,
                }"
              ></div>
            </div>
            <div class="history-label">
              <span class="history-val" :style="{ color: i === weeklyHistory.length - 1 ? scoreColor(val) : 'var(--text-tertiary)' }">
                {{ val }}
              </span>
              <span class="history-week">W{{ i + 1 }}</span>
            </div>
          </div>
        </div>
        <div class="history-axis">
          <span>55</span>
          <span>70</span>
          <span>85</span>
          <span>100</span>
        </div>
      </div>
    </div>

    <!-- Recommendations -->
    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          Recommendations
        </h3>
        <span class="header-meta">{{ recommendations.length }} actionable items</span>
      </div>
      <div class="recs-list">
        <div v-for="rec in recommendations" :key="rec.id" class="rec-row">
          <div class="rec-left">
            <span :class="['priority-dot', priorityClass(rec.priority)]"></span>
          </div>
          <div class="rec-body">
            <div class="rec-title-row">
              <span class="rec-title">{{ rec.title }}</span>
              <span :class="['priority-badge', priorityClass(rec.priority)]">{{ rec.priority }}</span>
              <span class="rec-category">{{ rec.category }}</span>
            </div>
            <p class="rec-desc">{{ rec.description }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.scorecard-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Selector Bar */
.selector-bar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.selector-label {
  font-size: 0.82rem;
  font-weight: 500;
  color: var(--text-tertiary);
}

.project-select {
  padding: 7px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 7px;
  color: var(--text-primary);
  font-size: 0.875rem;
  cursor: pointer;
  outline: none;
  min-width: 200px;
}

.project-select:focus {
  border-color: var(--accent-cyan);
}

.selector-meta {
  font-size: 0.78rem;
  color: var(--text-muted);
  margin-left: auto;
}

/* Card base */
.card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-default);
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-header h3 svg {
  color: var(--accent-cyan);
}

.header-meta {
  font-size: 0.78rem;
  color: var(--text-tertiary);
}

/* Hero Card */
.hero-card {
  padding: 40px 32px;
}

.hero-inner {
  display: flex;
  align-items: center;
  gap: 40px;
}

.score-ring {
  width: 130px;
  height: 130px;
  border-radius: 50%;
  border: 4px solid;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.score-number {
  font-size: 2.8rem;
  font-weight: 800;
  line-height: 1;
  letter-spacing: -0.03em;
}

.score-denom {
  font-size: 0.85rem;
  color: var(--text-tertiary);
  margin-top: 2px;
}

.hero-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.hero-project {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.hero-label {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
}

.hero-trend {
  font-size: 0.9rem;
  font-weight: 500;
}

.hero-status-label {
  font-size: 0.85rem;
  font-weight: 600;
  margin-top: 4px;
}

.trend-up { color: #34d399; }
.trend-down { color: #ef4444; }
.trend-flat { color: var(--text-tertiary); }

/* Category Cards Grid */
.categories-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.category-card {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.cat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.cat-name {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-secondary);
}

.cat-trend {
  font-size: 0.78rem;
  font-weight: 600;
}

.cat-score {
  font-size: 2rem;
  font-weight: 800;
  line-height: 1.1;
  letter-spacing: -0.02em;
}

.cat-score-label {
  font-size: 0.78rem;
  color: var(--text-tertiary);
  margin-top: -4px;
}

.cat-bar-track {
  height: 4px;
  background: var(--bg-tertiary);
  border-radius: 2px;
  margin-top: 8px;
  overflow: hidden;
}

.cat-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.6s ease;
}

/* Mini Sparkline */
.sparkline {
  display: flex;
  align-items: flex-end;
  gap: 3px;
  height: 32px;
  margin-top: 10px;
}

.spark-bar {
  flex: 1;
  border-radius: 2px 2px 0 0;
  min-height: 4px;
  transition: background 0.2s;
}

/* Signal Table */
.table-wrapper {
  overflow-x: auto;
}

.signal-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.signal-table thead tr {
  border-bottom: 1px solid var(--border-default);
}

.signal-table th {
  padding: 10px 24px;
  text-align: left;
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.signal-table tbody tr {
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.1s;
}

.signal-table tbody tr:hover {
  background: var(--bg-tertiary);
}

.signal-table tbody tr:last-child {
  border-bottom: none;
}

.signal-table td {
  padding: 12px 24px;
  color: var(--text-primary);
}

.bot-code {
  font-size: 0.78rem;
  font-family: 'Geist Mono', monospace;
  color: var(--accent-cyan);
  background: var(--bg-tertiary);
  padding: 2px 7px;
  border-radius: 4px;
}

.metric-col {
  font-weight: 500;
}

.value-col {
  font-weight: 600;
}

.prev-col {
  color: var(--text-tertiary);
}

.impact-badge {
  font-size: 0.78rem;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 4px;
}

.impact-pos {
  background: rgba(52, 211, 153, 0.12);
  color: #34d399;
}

.impact-neg {
  background: rgba(239, 68, 68, 0.12);
  color: #ef4444;
}

.impact-neutral {
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

.status-badge {
  font-size: 0.7rem;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.badge-good {
  background: rgba(52, 211, 153, 0.12);
  color: #34d399;
}

.badge-warn {
  background: rgba(245, 158, 11, 0.12);
  color: #f59e0b;
}

.badge-bad {
  background: rgba(239, 68, 68, 0.12);
  color: #ef4444;
}

/* Weekly History */
.history-section {
  padding: 24px 24px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.history-bars {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  height: 120px;
}

.history-bar-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  height: 100%;
}

.history-bar-wrap {
  flex: 1;
  width: 100%;
  display: flex;
  align-items: flex-end;
  background: var(--bg-tertiary);
  border-radius: 4px 4px 0 0;
  overflow: hidden;
}

.history-bar-fill {
  width: 100%;
  border-radius: 4px 4px 0 0;
  transition: height 0.6s ease, background 0.2s;
}

.history-label {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
}

.history-val {
  font-size: 0.72rem;
  font-weight: 700;
}

.history-week {
  font-size: 0.65rem;
  color: var(--text-muted);
}

.history-axis {
  display: flex;
  justify-content: space-between;
  padding: 0 4px;
  font-size: 0.65rem;
  color: var(--text-muted);
}

/* Recommendations */
.recs-list {
  display: flex;
  flex-direction: column;
}

.rec-row {
  display: flex;
  gap: 16px;
  padding: 18px 24px;
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.1s;
}

.rec-row:hover {
  background: var(--bg-tertiary);
}

.rec-row:last-child {
  border-bottom: none;
}

.rec-left {
  display: flex;
  align-items: flex-start;
  padding-top: 6px;
  flex-shrink: 0;
}

.priority-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.priority-high .priority-dot,
.priority-dot.priority-high {
  background: #ef4444;
}

.priority-medium .priority-dot,
.priority-dot.priority-medium {
  background: #f59e0b;
}

.priority-low .priority-dot,
.priority-dot.priority-low {
  background: #34d399;
}

.rec-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
}

.rec-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.rec-title {
  font-size: 0.92rem;
  font-weight: 600;
  color: var(--text-primary);
}

.priority-badge {
  font-size: 0.68rem;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 3px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.priority-badge.priority-high {
  background: rgba(239, 68, 68, 0.12);
  color: #ef4444;
}

.priority-badge.priority-medium {
  background: rgba(245, 158, 11, 0.12);
  color: #f59e0b;
}

.priority-badge.priority-low {
  background: rgba(52, 211, 153, 0.12);
  color: #34d399;
}

.rec-category {
  font-size: 0.72rem;
  color: var(--text-tertiary);
  padding: 2px 7px;
  background: var(--bg-tertiary);
  border-radius: 3px;
}

.rec-desc {
  font-size: 0.85rem;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.55;
}

/* Buttons */
.btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: 7px;
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-primary {
  background: var(--accent-cyan);
  color: #000;
}

.btn-primary:hover {
  opacity: 0.85;
}
</style>
