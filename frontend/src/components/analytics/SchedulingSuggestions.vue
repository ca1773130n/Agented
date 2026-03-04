<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import type { SchedulingSuggestion, SchedulingSuggestionsResponse } from '../../services/api';
import { analyticsApi } from '../../services/api';

const props = defineProps<{
  triggerId: string;
}>();

const isLoading = ref(true);
const data = ref<SchedulingSuggestionsResponse | null>(null);

async function loadSuggestions() {
  isLoading.value = true;
  try {
    data.value = await analyticsApi.fetchSchedulingSuggestions(props.triggerId);
  } catch {
    // Silently fail — suggestions are non-critical
  } finally {
    isLoading.value = false;
  }
}

onMounted(loadSuggestions);

const hourSuggestions = computed(() =>
  (data.value?.suggestions || []).filter((s: SchedulingSuggestion) => s.type === 'hour').slice(0, 3)
);

const daySuggestions = computed(() =>
  (data.value?.suggestions || []).filter((s: SchedulingSuggestion) => s.type === 'day').slice(0, 2)
);

function getSuccessRateClass(rate: number): string {
  if (rate >= 0.8) return 'high';
  if (rate >= 0.6) return 'medium';
  return 'low';
}

function formatDuration(ms: number | null): string {
  if (ms == null) return '-';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}
</script>

<template>
  <div class="scheduling-suggestions">
    <div v-if="isLoading" class="suggestions-loading">
      <svg class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
      </svg>
      Loading scheduling suggestions...
    </div>

    <template v-else-if="data">
      <!-- Insufficient data message -->
      <div v-if="data.message" class="info-box">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="16" x2="12" y2="12"/>
          <line x1="12" y1="8" x2="12.01" y2="8"/>
        </svg>
        <div>
          <p>{{ data.message }}</p>
          <span class="info-detail">{{ data.total_executions_analyzed }} executions analyzed over {{ data.analysis_period_days }} days</span>
        </div>
      </div>

      <!-- Suggestions -->
      <template v-if="hourSuggestions.length > 0 || daySuggestions.length > 0">
        <div class="suggestions-header">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="10"/>
            <polyline points="12 6 12 12 16 14"/>
          </svg>
          <span>Based on {{ data.total_executions_analyzed }} executions over {{ data.analysis_period_days }} days</span>
        </div>

        <!-- Recommended Hours -->
        <div v-if="hourSuggestions.length > 0" class="suggestion-section">
          <h4>Recommended Hours</h4>
          <div class="suggestion-list">
            <div
              v-for="suggestion in hourSuggestions"
              :key="suggestion.value"
              class="suggestion-card"
            >
              <div class="suggestion-value">{{ suggestion.value }}</div>
              <div class="suggestion-metrics">
                <span class="success-rate" :class="getSuccessRateClass(suggestion.success_rate)">
                  {{ Math.round(suggestion.success_rate * 100) }}% success
                </span>
                <span class="duration">{{ formatDuration(suggestion.avg_duration_ms) }}</span>
                <span class="exec-count">{{ suggestion.execution_count }} runs</span>
              </div>
              <div class="suggestion-rationale">{{ suggestion.rationale }}</div>
            </div>
          </div>
        </div>

        <!-- Recommended Days -->
        <div v-if="daySuggestions.length > 0" class="suggestion-section">
          <h4>Recommended Days</h4>
          <div class="suggestion-list">
            <div
              v-for="suggestion in daySuggestions"
              :key="suggestion.value"
              class="suggestion-card"
            >
              <div class="suggestion-value">{{ suggestion.value }}</div>
              <div class="suggestion-metrics">
                <span class="success-rate" :class="getSuccessRateClass(suggestion.success_rate)">
                  {{ Math.round(suggestion.success_rate * 100) }}% success
                </span>
                <span class="duration">{{ formatDuration(suggestion.avg_duration_ms) }}</span>
                <span class="exec-count">{{ suggestion.execution_count }} runs</span>
              </div>
              <div class="suggestion-rationale">{{ suggestion.rationale }}</div>
            </div>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.scheduling-suggestions {
  margin-top: 16px;
  padding: 16px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border-subtle);
  border-left: 3px solid var(--accent-cyan);
  border-radius: 8px;
}

.suggestions-loading {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.8rem;
  color: var(--text-tertiary);
  padding: 8px 0;
}

.spinner {
  width: 14px;
  height: 14px;
  animation: spin 1s linear infinite;
  flex-shrink: 0;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.info-box {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  background: var(--accent-cyan-dim);
  border: 1px solid var(--accent-cyan);
  border-radius: 6px;
}

.info-box svg {
  width: 18px;
  height: 18px;
  color: var(--accent-cyan);
  flex-shrink: 0;
  margin-top: 1px;
}

.info-box p {
  font-size: 0.85rem;
  color: var(--text-primary);
  margin: 0 0 4px;
}

.info-detail {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.suggestions-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.75rem;
  color: var(--text-tertiary);
  margin-bottom: 12px;
}

.suggestions-header svg {
  width: 14px;
  height: 14px;
  color: var(--accent-cyan);
}

.suggestion-section {
  margin-top: 12px;
}

.suggestion-section h4 {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.suggestion-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.suggestion-card {
  padding: 10px 14px;
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
}

.suggestion-value {
  font-weight: 600;
  font-size: 0.85rem;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.suggestion-metrics {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}

.success-rate {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 4px;
}

.success-rate.high {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.success-rate.medium {
  background: rgba(245, 158, 11, 0.15);
  color: var(--accent-amber);
}

.success-rate.low {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.duration,
.exec-count {
  font-size: 0.7rem;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.suggestion-rationale {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  line-height: 1.4;
}
</style>
