<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import type { SessionStatsSummary } from '../../services/api';
import { useTokenFormatting } from '../../composables/useTokenFormatting';

const { t } = useI18n();
const { formatTokenCount, formatCurrency } = useTokenFormatting();

defineProps<{
  totalInputTokens: number;
  totalOutputTokens: number;
  totalCacheReadTokens: number;
  totalCacheCreationTokens: number;
  totalAllTokens: number;
  cacheHitRate: number;
  periodLabel: string;
  totalSpend: number;
  totalSessions: number;
  totalTurns: number;
  totalExecutions: number;
  sessionStats: SessionStatsSummary | null;
  allTimeSpend: number | null;
}>();
</script>

<template>
  <div class="token-breakdown-card">
    <div class="token-breakdown-header">
      <span class="token-breakdown-title">{{ t('tokenBreakdownCard.title') }} &middot; {{ periodLabel }}</span>
      <span class="token-total-badge">{{ t('tokenBreakdownCard.total', { value: formatTokenCount(totalAllTokens) }) }}</span>
    </div>

    <!-- Spend & Sessions summary row -->
    <div class="summary-blobs">
      <div class="summary-blob">
        <span class="blob-label">{{ t('tokenBreakdownCard.spend') }}</span>
        <span class="blob-value highlight">{{ formatCurrency(totalSpend) }}</span>
      </div>
      <div class="summary-blob">
        <span class="blob-label">{{ t('tokenBreakdownCard.allTimeSpend') }}</span>
        <span class="blob-value highlight">{{ allTimeSpend != null ? formatCurrency(allTimeSpend) : '--' }}</span>
      </div>
      <div class="summary-blob">
        <span class="blob-label">{{ t('tokenBreakdownCard.sessions') }}</span>
        <span class="blob-value">{{ totalSessions }}</span>
        <span class="blob-sub">{{ t('tokenBreakdownCard.turnsRecords', { turns: totalTurns, records: totalExecutions }) }}</span>
      </div>
      <div class="summary-blob">
        <span class="blob-label">{{ t('tokenBreakdownCard.allTimeSessions') }}</span>
        <span class="blob-value">{{ sessionStats ? sessionStats.total_sessions : '--' }}</span>
        <span class="blob-sub">{{ sessionStats ? t('tokenBreakdownCard.messages', { count: sessionStats.total_messages }) : '' }}</span>
      </div>
    </div>

    <div class="token-breakdown-grid">
      <!-- Fresh Tokens -->
      <div class="token-category">
        <div class="token-category-header">
          <span class="token-dot fresh-input"></span>
          <span class="token-category-label">{{ t('tokenBreakdownCard.input') }}</span>
        </div>
        <div class="token-category-value">{{ formatTokenCount(totalInputTokens) }}</div>
        <div class="token-category-sub">{{ t('tokenBreakdownCard.inputSub') }}</div>
      </div>
      <div class="token-category">
        <div class="token-category-header">
          <span class="token-dot fresh-output"></span>
          <span class="token-category-label">{{ t('tokenBreakdownCard.output') }}</span>
        </div>
        <div class="token-category-value">{{ formatTokenCount(totalOutputTokens) }}</div>
        <div class="token-category-sub">{{ t('tokenBreakdownCard.outputSub') }}</div>
      </div>
      <!-- Cached Tokens -->
      <div class="token-category">
        <div class="token-category-header">
          <span class="token-dot cache-read"></span>
          <span class="token-category-label">{{ t('tokenBreakdownCard.cacheRead') }}</span>
        </div>
        <div class="token-category-value">{{ formatTokenCount(totalCacheReadTokens) }}</div>
        <div class="token-category-sub">{{ t('tokenBreakdownCard.cacheReadSub') }}</div>
      </div>
      <div class="token-category">
        <div class="token-category-header">
          <span class="token-dot cache-write"></span>
          <span class="token-category-label">{{ t('tokenBreakdownCard.cacheWrite') }}</span>
        </div>
        <div class="token-category-value">{{ formatTokenCount(totalCacheCreationTokens) }}</div>
        <div class="token-category-sub">{{ t('tokenBreakdownCard.cacheWriteSub') }}</div>
      </div>
    </div>
    <!-- Proportion bar -->
    <div class="token-proportion-bar" v-if="totalAllTokens > 0">
      <div
        class="proportion-segment fresh-input-bg"
        :style="{ width: Math.max((totalInputTokens / totalAllTokens) * 100, 0.5) + '%' }"
        :title="t('tokenBreakdownCard.barInput', { value: formatTokenCount(totalInputTokens) })"
      ></div>
      <div
        class="proportion-segment fresh-output-bg"
        :style="{ width: Math.max((totalOutputTokens / totalAllTokens) * 100, 0.5) + '%' }"
        :title="t('tokenBreakdownCard.barOutput', { value: formatTokenCount(totalOutputTokens) })"
      ></div>
      <div
        class="proportion-segment cache-write-bg"
        :style="{ width: Math.max((totalCacheCreationTokens / totalAllTokens) * 100, 0.5) + '%' }"
        :title="t('tokenBreakdownCard.barCacheWrite', { value: formatTokenCount(totalCacheCreationTokens) })"
      ></div>
      <div
        class="proportion-segment cache-read-bg"
        :style="{ width: Math.max((totalCacheReadTokens / totalAllTokens) * 100, 0.5) + '%' }"
        :title="t('tokenBreakdownCard.barCacheRead', { value: formatTokenCount(totalCacheReadTokens) })"
      ></div>
    </div>
    <div class="token-proportion-legend">
      <span class="legend-item"><span class="token-dot fresh-input"></span> {{ t('tokenBreakdownCard.input') }}</span>
      <span class="legend-item"><span class="token-dot fresh-output"></span> {{ t('tokenBreakdownCard.output') }}</span>
      <span class="legend-item"><span class="token-dot cache-write"></span> {{ t('tokenBreakdownCard.cacheWrite') }}</span>
      <span class="legend-item"><span class="token-dot cache-read"></span> {{ t('tokenBreakdownCard.cacheRead') }}</span>
      <span class="legend-divider"></span>
      <span class="cache-hit-rate">{{ t('tokenBreakdownCard.cacheHitRate', { value: cacheHitRate }) }}</span>
    </div>
  </div>
</template>

<style scoped>
.token-breakdown-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 28px;
}

.token-breakdown-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.token-breakdown-title {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-primary);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.token-total-badge {
  padding: 4px 12px;
  border-radius: 12px;
  font-family: var(--font-mono);
  font-size: 0.8rem;
  font-weight: 700;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

/* Spend & Sessions summary blobs */
.summary-blobs {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 20px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.summary-blob {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  background: var(--bg-tertiary);
  border-radius: 10px;
}

.blob-label {
  font-size: 0.65rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.blob-value {
  font-family: var(--font-mono);
  font-size: 1.2rem;
  font-weight: 700;
  color: var(--text-primary);
}

.blob-value.highlight {
  color: var(--accent-violet);
}

.blob-sub {
  font-size: 0.65rem;
  color: var(--text-muted);
}

.token-breakdown-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.token-category {
  padding: 16px;
  background: var(--bg-tertiary);
  border-radius: 10px;
}

.token-category-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.token-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.token-dot.fresh-input { background: #5B9BD5; }
.token-dot.fresh-output { background: #E55C5C; }
.token-dot.cache-read { background: #66C060; }
.token-dot.cache-write { background: #F5A623; }

.token-category-label {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.token-category-value {
  font-family: var(--font-mono);
  font-size: 1.4rem;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.token-category-sub {
  font-size: 0.65rem;
  color: var(--text-muted);
  line-height: 1.3;
}

/* Proportion bar */
.token-proportion-bar {
  display: flex;
  height: 8px;
  border-radius: 4px;
  overflow: hidden;
  background: var(--bg-primary);
  margin-bottom: 12px;
}

.proportion-segment {
  transition: width 0.5s ease;
  min-width: 2px;
}

.fresh-input-bg { background: #5B9BD5; }
.fresh-output-bg { background: #E55C5C; }
.cache-read-bg { background: #66C060; }
.cache-write-bg { background: #F5A623; }

.token-proportion-legend {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.7rem;
  color: var(--text-muted);
}

.legend-divider {
  width: 1px;
  height: 14px;
  background: var(--border-subtle);
}

.cache-hit-rate {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  font-weight: 600;
  color: #66C060;
}

@media (max-width: 900px) {
  .summary-blobs,
  .token-breakdown-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
