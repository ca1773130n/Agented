<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import type { WeeklyReport } from '../services/api';
import { analyticsApi, ApiError } from '../services/api';
import LoadingState from '../components/base/LoadingState.vue';
import StatCard from '../components/base/StatCard.vue';
import { useToast } from '../composables/useToast';
const showToast = useToast();

const isLoading = ref(true);
const report = ref<WeeklyReport | null>(null);

async function loadData() {
  isLoading.value = true;
  try {
    report.value = await analyticsApi.fetchWeeklyReport();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load weekly report';
    showToast(message, 'error');
  } finally {
    isLoading.value = false;
  }
}

const periodDisplay = computed(() => {
  if (!report.value) return '';
  const start = new Date(report.value.period_start);
  const end = new Date(report.value.period_end);
  const opts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' };
  const yearOpts: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric', year: 'numeric' };
  return `${start.toLocaleDateString('en-US', opts)} - ${end.toLocaleDateString('en-US', yearOpts)}`;
});

const timeSavedDisplay = computed(() => {
  if (!report.value) return '-';
  const mins = report.value.estimated_time_saved_minutes;
  if (mins >= 60) {
    const hours = Math.floor(mins / 60);
    const remainder = mins % 60;
    return remainder > 0 ? `${hours}h ${remainder}m` : `${hours}h`;
  }
  return `${mins}m`;
});

function formatFailureRate(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}

onMounted(loadData);
</script>

<template>
  <div class="team-report">

    <LoadingState v-if="isLoading" message="Loading weekly report..." />

    <template v-else-if="report">
      <!-- Header -->
      <div class="card status-card">
        <div class="status-card-inner">
          <div class="status-header">
            <div class="status-title-area">
              <div class="status-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M3 3v18h18"/>
                  <path d="M18 17l-5-5-4 4-4-4"/>
                </svg>
              </div>
              <div>
                <h3>Weekly Impact Report</h3>
                <p class="status-subtitle">{{ periodDisplay }}</p>
              </div>
            </div>
          </div>

          <div class="stats-grid">
            <StatCard title="PRs Reviewed" :value="report.prs_reviewed" color="var(--accent-cyan)" />
            <StatCard title="Issues Found" :value="report.issues_found" color="var(--accent-amber)" />
            <StatCard title="Time Saved" :value="timeSavedDisplay" color="var(--accent-emerald)" />
          </div>
        </div>
      </div>

      <!-- Two column layout -->
      <div class="report-columns">
        <!-- Top Performing Bots -->
        <div class="card">
          <div class="card-header">
            <h3>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
              </svg>
              Top Performing Bots
            </h3>
          </div>
          <div v-if="report.top_bots.length === 0" class="empty-list">
            No execution data for this period.
          </div>
          <div v-else class="ranked-list">
            <div
              v-for="(bot, index) in report.top_bots.slice(0, 5)"
              :key="bot.trigger_id"
              class="ranked-item"
            >
              <span class="rank-number" :class="{ gold: index === 0, silver: index === 1, bronze: index === 2 }">
                {{ index + 1 }}
              </span>
              <div class="ranked-info">
                <span class="ranked-name">{{ bot.name }}</span>
                <span class="ranked-id">{{ bot.trigger_id }}</span>
              </div>
              <span class="ranked-metric">
                {{ bot.execution_count }} <span class="metric-label">runs</span>
              </span>
            </div>
          </div>
        </div>

        <!-- Bots Needing Attention -->
        <div class="card">
          <div class="card-header">
            <h3>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
                <line x1="12" y1="9" x2="12" y2="13"/>
                <line x1="12" y1="17" x2="12.01" y2="17"/>
              </svg>
              Bots Needing Attention
            </h3>
          </div>
          <div v-if="report.bots_needing_attention.length === 0" class="empty-list">
            All bots are performing well.
          </div>
          <div v-else class="attention-list">
            <div
              v-for="bot in report.bots_needing_attention"
              :key="bot.trigger_id"
              class="attention-item"
            >
              <div class="attention-info">
                <span class="attention-name">{{ bot.name }}</span>
                <span class="attention-id">{{ bot.trigger_id }}</span>
              </div>
              <div class="attention-metrics">
                <span
                  class="failure-rate-badge"
                  :class="{ high: bot.failure_rate > 0.5, moderate: bot.failure_rate > 0.2 && bot.failure_rate <= 0.5 }"
                >
                  {{ formatFailureRate(bot.failure_rate) }} fail
                </span>
                <span class="alert-count-badge">
                  {{ bot.alert_count }} alert{{ bot.alert_count !== 1 ? 's' : '' }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <template v-else>
      <div class="card">
        <div class="empty-state">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M3 3v18h18"/>
            <path d="M18 17l-5-5-4 4-4-4"/>
          </svg>
          <p>No execution data for this period.</p>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.team-report {
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

.card {
  padding: 24px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.card-header h3 svg {
  width: 18px;
  height: 18px;
  color: var(--accent-cyan);
}

.status-card {
  background: linear-gradient(135deg, var(--bg-secondary) 0%, var(--bg-tertiary) 100%);
  border-color: var(--border-default);
  padding: 0;
  overflow: hidden;
}

.status-card-inner {
  padding: 28px;
}

.status-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 28px;
  flex-wrap: wrap;
  gap: 16px;
}

.status-title-area {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.status-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent-cyan-dim);
  border: 1px solid var(--accent-cyan);
}

.status-icon svg {
  width: 24px;
  height: 24px;
  color: var(--accent-cyan);
}

.status-title-area h3 {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.status-subtitle {
  font-size: 0.85rem;
  color: var(--text-tertiary);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

/* Two column layout */
.report-columns {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}

/* Ranked list */
.ranked-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ranked-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 16px;
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  transition: all var(--transition-fast);
}

.ranked-item:hover {
  border-color: var(--border-default);
}

.rank-number {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 0.8rem;
  background: var(--bg-elevated);
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.rank-number.gold {
  background: rgba(245, 158, 11, 0.15);
  color: var(--accent-amber);
}

.rank-number.silver {
  background: rgba(156, 163, 175, 0.15);
  color: var(--text-secondary);
}

.rank-number.bronze {
  background: rgba(180, 83, 9, 0.15);
  color: #b45309;
}

.ranked-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ranked-name {
  font-weight: 600;
  font-size: 0.85rem;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ranked-id {
  font-size: 0.7rem;
  font-family: var(--font-mono);
  color: var(--text-muted);
}

.ranked-metric {
  font-family: var(--font-mono);
  font-size: 0.9rem;
  font-weight: 700;
  color: var(--accent-cyan);
  flex-shrink: 0;
}

.metric-label {
  font-size: 0.7rem;
  font-weight: 400;
  color: var(--text-tertiary);
}

/* Attention list */
.attention-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.attention-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 12px 16px;
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-left: 3px solid var(--accent-amber);
  border-radius: 8px;
}

.attention-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.attention-name {
  font-weight: 600;
  font-size: 0.85rem;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.attention-id {
  font-size: 0.7rem;
  font-family: var(--font-mono);
  color: var(--text-muted);
}

.attention-metrics {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.failure-rate-badge {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--bg-elevated);
  color: var(--text-secondary);
}

.failure-rate-badge.high {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.failure-rate-badge.moderate {
  background: rgba(245, 158, 11, 0.15);
  color: var(--accent-amber);
}

.alert-count-badge {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--bg-elevated);
  color: var(--text-tertiary);
}

/* Empty states */
.empty-list {
  padding: 32px 16px;
  text-align: center;
  font-size: 0.85rem;
  color: var(--text-tertiary);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 48px 24px;
  color: var(--text-tertiary);
  text-align: center;
}

.empty-state svg {
  width: 40px;
  height: 40px;
  opacity: 0.6;
}

@media (max-width: 900px) {
  .report-columns {
    grid-template-columns: 1fr;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }
}
</style>
