<!--
  ServiceHealthCard — extracted from ServiceHealthDashboard.vue for the Health lane.
  Owns its own data fetching for AI backend account health groupings.
-->
<template>
  <section id="service-health" class="lane-card service-health-card">
    <header class="lane-card__head">
      <div>
        <h2 class="lane-card__title">{{ t('serviceHealthCard.title') }}</h2>
        <p class="lane-card__subtitle">{{ t('serviceHealthCard.subtitle') }}</p>
      </div>
      <div class="head-actions">
        <label class="auto-refresh-toggle">
          <input type="checkbox" v-model="autoRefresh" />
          <span>{{ t('serviceHealthCard.autoRefresh') }}</span>
        </label>
        <button class="refresh-btn" @click="refresh" :disabled="isLoading">
          <svg :class="{ spinning: isLoading }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M23 4v6h-6M1 20v-6h6"/>
            <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
          </svg>
          {{ t('serviceHealthCard.refresh') }}
        </button>
      </div>
    </header>

    <ErrorState
      v-if="error"
      :title="t('serviceHealthCard.connectionError')"
      :message="error"
      @retry="refresh"
    />

    <div class="stats-grid">
      <StatCard :title="t('serviceHealthCard.stat.totalAccounts')" :value="accounts.length" />
      <StatCard :title="t('serviceHealthCard.stat.healthy')" :value="healthyCount" color="var(--accent-emerald)" />
      <StatCard :title="t('serviceHealthCard.stat.rateLimited')" :value="rateLimitedCount" color="var(--accent-crimson)" />
    </div>

    <EmptyState
      v-if="!isLoading && accounts.length === 0"
      :title="t('serviceHealthCard.emptyTitle')"
      :description="t('serviceHealthCard.emptyDescription')"
    />

    <div v-for="(group, backendType) in groupedAccounts" :key="backendType" class="backend-group">
      <h3 class="group-header">
        <span class="group-dot" :class="backendType"></span>
        {{ formatGroupTitle(backendType as string) }}
        <span class="group-count">{{ group.length }}</span>
      </h3>
      <ServiceHealthGrid
        :accounts="group"
        :loading="isLoading"
        @clear-rate-limit="handleClearRateLimit"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { orchestrationApi, type AccountHealth } from '../../../services/api';
import ServiceHealthGrid from '../../../components/monitoring/ServiceHealthGrid.vue';
import ErrorState from '../../../components/base/ErrorState.vue';
import EmptyState from '../../../components/base/EmptyState.vue';
import StatCard from '../../../components/base/StatCard.vue';
import { useToast } from '../../../composables/useToast';
import { useWebMcpTool } from '../../../composables/useWebMcpTool';

const emit = defineEmits<{ loaded: [slug: string] }>();
const { t } = useI18n();
const showToast = useToast();

const accounts = ref<AccountHealth[]>([]);
const isLoading = ref(true);
const error = ref<string | null>(null);
const autoRefresh = ref(true);
let refreshInterval: ReturnType<typeof setInterval> | null = null;

const healthyCount = computed(() => accounts.value.filter(a => !a.is_rate_limited).length);
const rateLimitedCount = computed(() => accounts.value.filter(a => a.is_rate_limited).length);

const groupedAccounts = computed(() => {
  const groups: Record<string, AccountHealth[]> = {};
  for (const account of accounts.value) {
    const type = account.backend_type || 'unknown';
    if (!groups[type]) groups[type] = [];
    groups[type].push(account);
  }
  return groups;
});

useWebMcpTool({
  name: 'agented_service_health_get_state',
  description: 'Returns the current state of the ServiceHealthCard',
  page: 'ServiceHealthCard',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'ServiceHealthCard',
        isLoading: isLoading.value,
        error: error.value,
        accountCount: accounts.value.length,
        healthyCount: healthyCount.value,
        rateLimitedCount: rateLimitedCount.value,
        autoRefresh: autoRefresh.value,
        backendGroupCount: Object.keys(groupedAccounts.value).length,
      }),
    }],
  }),
  deps: [isLoading, error, accounts, healthyCount, rateLimitedCount, autoRefresh, groupedAccounts],
});

function formatGroupTitle(backendType: string): string {
  const names: Record<string, string> = {
    claude: 'Claude',
    opencode: 'OpenCode',
    gemini: 'Gemini',
    codex: 'Codex',
  };
  const name = names[backendType] || (backendType.charAt(0).toUpperCase() + backendType.slice(1));
  return t('serviceHealthCard.groupTitle', { name });
}

async function refresh() {
  isLoading.value = true;
  error.value = null;
  try {
    const data = await orchestrationApi.getHealth();
    accounts.value = data.accounts || [];
  } catch {
    error.value = t('serviceHealthCard.error.load');
  } finally {
    isLoading.value = false;
    emit('loaded', 'service-health');
  }
}

async function handleClearRateLimit(accountId: string) {
  try {
    await orchestrationApi.clearRateLimit(accountId);
    showToast?.(t('serviceHealthCard.toast.rateLimitCleared'), 'success');
    await refresh();
  } catch {
    showToast?.(t('serviceHealthCard.error.clearRateLimit'), 'error');
  }
}

function startAutoRefresh() {
  stopAutoRefresh();
  if (autoRefresh.value) {
    refreshInterval = setInterval(refresh, 10000);
  }
}

function stopAutoRefresh() {
  if (refreshInterval) {
    clearInterval(refreshInterval);
    refreshInterval = null;
  }
}

watch(autoRefresh, (val) => {
  if (val) startAutoRefresh();
  else stopAutoRefresh();
});

onMounted(() => {
  refresh();
  startAutoRefresh();
});

onUnmounted(() => {
  stopAutoRefresh();
});
</script>

<style scoped>
.lane-card {
  padding: 20px;
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: 10px;
  background: var(--bg-secondary, rgba(255, 255, 255, 0.02));
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.lane-card__head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}
.lane-card__title { font-size: 16px; font-weight: 600; margin: 0 0 4px; color: var(--text-primary); }
.lane-card__subtitle { font-size: 12px; color: var(--text-secondary); margin: 0; }
.head-actions { display: flex; gap: 12px; align-items: center; }

.auto-refresh-toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
}

.auto-refresh-toggle input[type="checkbox"] {
  width: 14px;
  height: 14px;
  accent-color: var(--accent-cyan);
}

.refresh-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.8125rem;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.refresh-btn:hover:not(:disabled) {
  background: var(--bg-tertiary);
  border-color: var(--border-strong);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.refresh-btn svg {
  width: 14px;
  height: 14px;
}

.refresh-btn svg.spinning {
  animation: spin 1s linear infinite;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}

.backend-group {
  margin-bottom: 1rem;
}

.group-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0 0 1rem;
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--text-primary);
}

.group-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.group-dot.claude { background: var(--accent-violet); }
.group-dot.opencode { background: var(--accent-emerald); }
.group-dot.gemini { background: var(--accent-cyan); }
.group-dot.codex { background: var(--accent-amber); }

.group-count {
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
  padding: 0.1rem 0.5rem;
  border-radius: 10px;
  margin-left: 0.25rem;
}

@media (max-width: 900px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
