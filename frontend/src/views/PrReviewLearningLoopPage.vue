<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { prReviewApi } from '../services/api/triggers';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();
const showToast = useToast();

type FindingCategory = 'security' | 'style' | 'performance' | 'correctness' | 'docs';

interface FindingSignal {
  id: string;
  category: FindingCategory;
  pattern: string;
  acceptedCount: number;
  dismissedCount: number;
  commentedCount: number;
  resolvedCount: number;
  acceptRate: number;
  trend: 'up' | 'down' | 'stable';
  lastSeen: string;
  examplePromptFragment: string;
}

interface RefinementSuggestion {
  id: string;
  type: 'suppress' | 'promote' | 'reword';
  category: FindingCategory;
  description: string;
  impact: 'high' | 'medium' | 'low';
  appliedAt?: string;
}

const isLoading = ref(true);
const signals = ref<FindingSignal[]>([]);
const suggestions = ref<RefinementSuggestion[]>([]);

onMounted(async () => {
  try {
    const data = await prReviewApi.getLearningLoop();
    signals.value = data.signals;
    suggestions.value = data.suggestions;
  } catch {
    showToast(t('prReviewLearningLoop.toasts.loadFailed'), 'error');
  } finally {
    isLoading.value = false;
  }
});

const hasData = computed(() => signals.value.length > 0 || suggestions.value.length > 0);

const filterCategory = ref<FindingCategory | 'all'>('all');
const sortBy = ref<'acceptRate' | 'volume' | 'lastSeen'>('acceptRate');
const LOW_ACCEPTANCE_THRESHOLD = 0.25;
const HIGH_ACCEPTANCE_THRESHOLD = 0.75;

const filteredSignals = computed(() => {
  let list = signals.value;
  if (filterCategory.value !== 'all') {
    list = list.filter((s) => s.category === filterCategory.value);
  }
  return [...list].sort((a, b) => {
    if (sortBy.value === 'acceptRate') return b.acceptRate - a.acceptRate;
    if (sortBy.value === 'volume')
      return b.acceptedCount + b.dismissedCount - (a.acceptedCount + a.dismissedCount);
    return new Date(b.lastSeen).getTime() - new Date(a.lastSeen).getTime();
  });
});

const pendingSuggestions = computed(() => suggestions.value.filter((s) => !s.appliedAt));
const appliedSuggestions = computed(() => suggestions.value.filter((s) => !!s.appliedAt));

function acceptRate(s: FindingSignal): string {
  return `${Math.round(s.acceptRate * 100)}%`;
}

function totalVolume(s: FindingSignal): number {
  return s.acceptedCount + s.dismissedCount + s.commentedCount;
}

function categoryColor(cat: FindingCategory): string {
  const colors: Record<FindingCategory, string> = {
    security: 'var(--accent-red)',
    style: 'var(--accent-cyan)',
    performance: 'var(--accent-amber)',
    correctness: 'var(--accent-yellow)',
    docs: 'var(--accent-blue)',
  };
  return colors[cat];
}

function trendIcon(trend: 'up' | 'down' | 'stable'): string {
  return trend === 'up' ? '↑' : trend === 'down' ? '↓' : '→';
}

function trendColor(trend: 'up' | 'down' | 'stable'): string {
  return trend === 'up' ? 'var(--accent-green)' : trend === 'down' ? 'var(--accent-red)' : 'var(--text-secondary)';
}

function impactColor(impact: 'high' | 'medium' | 'low'): string {
  return impact === 'high' ? 'var(--accent-red)' : impact === 'medium' ? 'var(--accent-amber)' : 'var(--accent-cyan)';
}

function suggestionTypeLabel(type: RefinementSuggestion['type']): string {
  return type === 'suppress'
    ? t('prReviewLearningLoop.suggestionTypes.suppress')
    : type === 'promote'
    ? t('prReviewLearningLoop.suggestionTypes.promote')
    : t('prReviewLearningLoop.suggestionTypes.reword');
}

function applySuggestion(sug: RefinementSuggestion) {
  sug.appliedAt = new Date().toISOString();
  showToast(t('prReviewLearningLoop.toasts.refinementApplied', { type: suggestionTypeLabel(sug.type) }), 'success');
}

function dismissSuggestion(sug: RefinementSuggestion) {
  suggestions.value = suggestions.value.filter((s) => s.id !== sug.id);
  showToast(t('prReviewLearningLoop.toasts.suggestionDismissed'), 'info');
}

const overallAcceptRate = computed(() => {
  const total = signals.value.reduce((acc, s) => acc + s.acceptedCount + s.dismissedCount, 0);
  const accepted = signals.value.reduce((acc, s) => acc + s.acceptedCount, 0);
  return total > 0 ? Math.round((accepted / total) * 100) : 0;
});
</script>

<template>
  <div class="page-container">
    <PageHeader
      :title="t('prReviewLearningLoop.title')"
      :subtitle="t('prReviewLearningLoop.subtitle')"
    />

    <!-- Loading state -->
    <div v-if="isLoading" class="card" style="padding: 48px; text-align: center;">
      <div style="color: var(--text-secondary); font-size: 0.875rem;">{{ t('prReviewLearningLoop.loading') }}</div>
    </div>

    <!-- Empty state -->
    <div v-else-if="!hasData" class="card" style="padding: 48px; text-align: center;">
      <div style="color: var(--text-secondary); font-size: 0.875rem; margin-bottom: 8px;">{{ t('prReviewLearningLoop.emptyTitle') }}</div>
      <div style="color: var(--text-secondary); font-size: 0.82rem;">{{ t('prReviewLearningLoop.emptyDescription') }}</div>
    </div>

    <template v-else>
    <!-- Summary Cards -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-label">{{ t('prReviewLearningLoop.stats.overallAcceptRate') }}</div>
        <div class="stat-value" :style="{ color: overallAcceptRate >= 60 ? 'var(--accent-green)' : 'var(--accent-amber)' }">
          {{ overallAcceptRate }}%
        </div>
        <div class="stat-sub">{{ t('prReviewLearningLoop.stats.overallAcceptRateSub') }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">{{ t('prReviewLearningLoop.stats.patternsTracked') }}</div>
        <div class="stat-value">{{ signals.length }}</div>
        <div class="stat-sub">{{ t('prReviewLearningLoop.stats.patternsTrackedSub') }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">{{ t('prReviewLearningLoop.stats.refinementsPending') }}</div>
        <div class="stat-value" :style="{ color: pendingSuggestions.length > 0 ? 'var(--accent-amber)' : 'var(--text-secondary)' }">
          {{ pendingSuggestions.length }}
        </div>
        <div class="stat-sub">{{ t('prReviewLearningLoop.stats.refinementsPendingSub') }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">{{ t('prReviewLearningLoop.stats.lowValuePatterns') }}</div>
        <div class="stat-value" :style="{ color: 'var(--accent-red)' }">
          {{ signals.filter((s) => s.acceptRate < LOW_ACCEPTANCE_THRESHOLD).length }}
        </div>
        <div class="stat-sub">{{ t('prReviewLearningLoop.stats.lowValuePatternsSub', { pct: Math.round(LOW_ACCEPTANCE_THRESHOLD * 100) }) }}</div>
      </div>
    </div>

    <!-- Refinement Suggestions -->
    <section v-if="pendingSuggestions.length > 0" class="card suggestions-section">
      <div class="section-header">
        <h2>{{ t('prReviewLearningLoop.refinementSuggestions') }}</h2>
        <span class="badge-count">{{ t('prReviewLearningLoop.pendingCount', { count: pendingSuggestions.length }) }}</span>
      </div>
      <p class="section-desc">{{ t('prReviewLearningLoop.suggestionsDesc') }}</p>
      <div class="suggestions-list">
        <div v-for="sug in pendingSuggestions" :key="sug.id" class="suggestion-card">
          <div class="suggestion-header">
            <span class="suggestion-type" :style="{ color: impactColor(sug.impact) }">
              {{ suggestionTypeLabel(sug.type) }}
            </span>
            <span class="suggestion-category" :style="{ color: categoryColor(sug.category) }">
              {{ sug.category }}
            </span>
            <span class="impact-badge" :style="{ background: impactColor(sug.impact) + '22', color: impactColor(sug.impact) }">
              {{ t('prReviewLearningLoop.impactBadge', { impact: sug.impact }) }}
            </span>
          </div>
          <p class="suggestion-desc">{{ sug.description }}</p>
          <div class="suggestion-actions">
            <button class="btn-primary" @click="applySuggestion(sug)">{{ t('prReviewLearningLoop.apply') }}</button>
            <button class="btn-ghost" @click="dismissSuggestion(sug)">{{ t('common.dismiss') }}</button>
          </div>
        </div>
      </div>
    </section>

    <!-- Signal Table -->
    <section class="card">
      <div class="section-header">
        <h2>{{ t('prReviewLearningLoop.signalBreakdown') }}</h2>
        <div class="filters">
          <select v-model="filterCategory" class="filter-select">
            <option value="all">{{ t('prReviewLearningLoop.categories.all') }}</option>
            <option value="security">{{ t('prReviewLearningLoop.categories.security') }}</option>
            <option value="style">{{ t('prReviewLearningLoop.categories.style') }}</option>
            <option value="performance">{{ t('prReviewLearningLoop.categories.performance') }}</option>
            <option value="correctness">{{ t('prReviewLearningLoop.categories.correctness') }}</option>
            <option value="docs">{{ t('prReviewLearningLoop.categories.docs') }}</option>
          </select>
          <select v-model="sortBy" class="filter-select">
            <option value="acceptRate">{{ t('prReviewLearningLoop.sort.acceptRate') }}</option>
            <option value="volume">{{ t('prReviewLearningLoop.sort.volume') }}</option>
            <option value="lastSeen">{{ t('prReviewLearningLoop.sort.lastSeen') }}</option>
          </select>
        </div>
      </div>
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>{{ t('prReviewLearningLoop.table.pattern') }}</th>
              <th>{{ t('prReviewLearningLoop.table.category') }}</th>
              <th>{{ t('prReviewLearningLoop.table.acceptRate') }}</th>
              <th>{{ t('prReviewLearningLoop.table.volume') }}</th>
              <th>{{ t('prReviewLearningLoop.table.accepted') }}</th>
              <th>{{ t('prReviewLearningLoop.table.dismissed') }}</th>
              <th>{{ t('prReviewLearningLoop.table.trend') }}</th>
              <th>{{ t('prReviewLearningLoop.table.lastSeen') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="sig in filteredSignals"
              :key="sig.id"
              :class="{
                'row-low': sig.acceptRate < LOW_ACCEPTANCE_THRESHOLD,
                'row-high': sig.acceptRate >= HIGH_ACCEPTANCE_THRESHOLD,
              }"
            >
              <td>
                <div class="pattern-cell">
                  <span class="pattern-name">{{ sig.pattern }}</span>
                  <span class="pattern-example">{{ sig.examplePromptFragment }}</span>
                </div>
              </td>
              <td>
                <span class="cat-badge" :style="{ background: categoryColor(sig.category) + '22', color: categoryColor(sig.category) }">
                  {{ sig.category }}
                </span>
              </td>
              <td>
                <div class="rate-cell">
                  <span
                    class="rate-value"
                    :style="{
                      color:
                        sig.acceptRate >= HIGH_ACCEPTANCE_THRESHOLD
                          ? 'var(--accent-green)'
                          : sig.acceptRate < LOW_ACCEPTANCE_THRESHOLD
                          ? 'var(--accent-red)'
                          : 'var(--accent-amber)',
                    }"
                  >
                    {{ acceptRate(sig) }}
                  </span>
                  <div class="rate-bar-bg">
                    <div
                      class="rate-bar-fill"
                      :style="{
                        width: acceptRate(sig),
                        background:
                          sig.acceptRate >= HIGH_ACCEPTANCE_THRESHOLD
                            ? 'var(--accent-green)'
                            : sig.acceptRate < LOW_ACCEPTANCE_THRESHOLD
                            ? 'var(--accent-red)'
                            : 'var(--accent-amber)',
                      }"
                    ></div>
                  </div>
                </div>
              </td>
              <td class="num-cell">{{ totalVolume(sig) }}</td>
              <td class="num-cell accepted">{{ sig.acceptedCount }}</td>
              <td class="num-cell dismissed">{{ sig.dismissedCount }}</td>
              <td class="trend-cell" :style="{ color: trendColor(sig.trend) }">{{ trendIcon(sig.trend) }}</td>
              <td class="date-cell">{{ new Date(sig.lastSeen).toLocaleDateString() }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Applied Refinements -->
    <section v-if="appliedSuggestions.length > 0" class="card applied-section">
      <h2>{{ t('prReviewLearningLoop.appliedRefinements') }}</h2>
      <div class="applied-list">
        <div v-for="sug in appliedSuggestions" :key="sug.id" class="applied-item">
          <span class="applied-icon">✓</span>
          <div>
            <div class="applied-type">{{ suggestionTypeLabel(sug.type) }} — {{ sug.category }}</div>
            <div class="applied-desc">{{ sug.description }}</div>
            <div class="applied-date">{{ t('prReviewLearningLoop.appliedDate', { date: new Date(sug.appliedAt!).toLocaleDateString() }) }}</div>
          </div>
        </div>
      </div>
    </section>
    </template>
  </div>
</template>

<style scoped>
.page-container {
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.stat-card {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 20px;
}

.stat-label {
  font-size: 12px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 32px;
  font-weight: 700;
  line-height: 1;
  margin-bottom: 4px;
}

.stat-sub {
  font-size: 12px;
  color: var(--text-secondary);
}

.card {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 24px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
}

.section-header h2 {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}

.badge-count {
  background: var(--accent-amber);
  color: #000;
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 12px;
}

.section-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 16px;
}

.filters {
  display: flex;
  gap: 8px;
}

.filter-select {
  background: var(--surface-3);
  border: 1px solid var(--border);
  color: var(--text-primary);
  font-size: 13px;
  padding: 6px 10px;
  border-radius: 6px;
  cursor: pointer;
}

.suggestions-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.suggestion-card {
  background: var(--surface-3);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 16px;
}

.suggestion-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.suggestion-type {
  font-size: 13px;
  font-weight: 600;
}

.suggestion-category {
  font-size: 12px;
  font-weight: 500;
}

.impact-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  margin-left: auto;
}

.suggestion-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0 0 12px;
  line-height: 1.5;
}

.suggestion-actions {
  display: flex;
  gap: 8px;
}

.btn-primary {
  background: var(--accent-blue);
  color: #fff;
  border: none;
  padding: 6px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.btn-ghost {
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border);
  padding: 6px 16px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}

.table-wrap {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.data-table th {
  text-align: left;
  padding: 10px 12px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border);
}

.data-table td {
  padding: 12px 12px;
  border-bottom: 1px solid var(--border-light, var(--border));
  vertical-align: top;
}

.data-table tr:last-child td {
  border-bottom: none;
}

.row-low {
  background: rgba(255, 80, 80, 0.04);
}

.row-high {
  background: rgba(80, 200, 120, 0.04);
}

.pattern-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.pattern-name {
  font-weight: 500;
}

.pattern-example {
  font-size: 11px;
  color: var(--text-secondary);
  font-style: italic;
}

.cat-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  white-space: nowrap;
}

.rate-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 80px;
}

.rate-value {
  font-weight: 700;
  font-size: 14px;
}

.rate-bar-bg {
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  overflow: hidden;
}

.rate-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.3s ease;
}

.num-cell {
  text-align: right;
  color: var(--text-secondary);
}

.accepted {
  color: var(--accent-green) !important;
}

.dismissed {
  color: var(--accent-red) !important;
}

.trend-cell {
  font-size: 18px;
  text-align: center;
}

.date-cell {
  color: var(--text-secondary);
  white-space: nowrap;
}

.applied-section {
  border-color: var(--accent-green);
}

.applied-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.applied-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.applied-icon {
  color: var(--accent-green);
  font-size: 16px;
  margin-top: 2px;
}

.applied-type {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 2px;
}

.applied-desc {
  font-size: 12px;
  color: var(--text-secondary);
}

.applied-date {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 2px;
}
</style>
