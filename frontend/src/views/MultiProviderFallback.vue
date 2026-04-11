<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { orchestrationApi, triggerApi, backendApi } from '../services/api';
import type { AccountHealth, FallbackChainEntry, Trigger, AIBackend } from '../services/api';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
const showToast = useToast();

// Loading / error state
const isLoading = ref(true);
const loadError = ref<string | null>(null);

// Data from API
const triggers = ref<Trigger[]>([]);
const backends = ref<AIBackend[]>([]);
const accountHealth = ref<AccountHealth[]>([]);

// Chain editing state per trigger
const selectedTriggerId = ref<string | null>(null);
const chainEntries = ref<FallbackChainEntry[]>([]);
const isSaving = ref(false);
const isRefreshingHealth = ref(false);

// Computed helpers
const selectedTrigger = computed(() =>
  triggers.value.find(t => t.id === selectedTriggerId.value) ?? null
);

const chainEntriesWithHealth = computed(() => {
  return chainEntries.value.map((entry, index) => {
    const health = accountHealth.value.find(
      a => a.backend_type === entry.backend_type && (entry.account_id === null || a.account_id === entry.account_id)
    );
    const backend = backends.value.find(b => b.type === entry.backend_type);
    return {
      ...entry,
      chain_order: index,
      backendName: backend?.name ?? entry.backend_type,
      accountName: health?.account_name ?? 'Default',
      status: health
        ? health.is_rate_limited ? 'rate_limited' as const : 'healthy' as const
        : 'unknown' as const,
      cooldownSeconds: health?.cooldown_remaining_seconds ?? null,
      totalExecutions: health?.total_executions ?? 0,
      lastUsedAt: health?.last_used_at ?? null,
      plan: health?.plan ?? null,
    };
  });
});

// Available backend types for adding to chain
const availableBackendTypes = computed(() => {
  return backends.value.map(b => b.type);
});

const accountsForBackend = computed(() => {
  return (backendType: string) =>
    accountHealth.value.filter(a => a.backend_type === backendType);
});

// Load all data on mount — each call is fault-tolerant so one failure doesn't block everything
async function loadData() {
  isLoading.value = true;
  loadError.value = null;
  const errors: string[] = [];
  try {
    const [triggersRes, backendsRes, healthRes] = await Promise.allSettled([
      triggerApi.list(),
      backendApi.list(),
      orchestrationApi.getHealth(),
    ]);

    if (triggersRes.status === 'fulfilled') {
      triggers.value = triggersRes.value.triggers ?? [];
    } else {
      errors.push('triggers');
    }
    if (backendsRes.status === 'fulfilled') {
      backends.value = backendsRes.value.backends ?? [];
    } else {
      errors.push('backends');
    }
    if (healthRes.status === 'fulfilled') {
      accountHealth.value = healthRes.value.accounts ?? [];
    } else {
      errors.push('account health');
    }

    if (errors.length === 3) {
      loadError.value = 'Failed to load data. The backend may be unreachable.';
    } else {
      if (errors.length > 0) {
        loadError.value = `Partial load — could not fetch: ${errors.join(', ')}`;
      }
      // Auto-select first trigger and load its chain
      if (triggers.value.length > 0) {
        await selectTrigger(triggers.value[0].id);
      }
    }
  } catch (err: unknown) {
    loadError.value = err instanceof Error ? err.message : 'Failed to load data';
  } finally {
    isLoading.value = false;
  }
}

async function selectTrigger(triggerId: string) {
  selectedTriggerId.value = triggerId;
  try {
    const res = await orchestrationApi.getFallbackChain(triggerId);
    chainEntries.value = (res.chain ?? []).map(e => ({
      backend_type: e.backend_type,
      account_id: e.account_id ?? null,
    }));
  } catch {
    // No chain configured yet — start empty
    chainEntries.value = [];
  }
}

function moveEntry(idx: number, dir: -1 | 1) {
  const newIdx = idx + dir;
  if (newIdx < 0 || newIdx >= chainEntries.value.length) return;
  const tmp = chainEntries.value[idx];
  chainEntries.value[idx] = chainEntries.value[newIdx];
  chainEntries.value[newIdx] = tmp;
}

function removeEntry(idx: number) {
  chainEntries.value.splice(idx, 1);
}

// Adding a new entry
const addBackendType = ref('');
const addAccountId = ref<string | null>(null);

function addEntry() {
  if (!addBackendType.value) return;
  chainEntries.value.push({
    backend_type: addBackendType.value,
    account_id: addAccountId.value,
  });
  addBackendType.value = '';
  addAccountId.value = null;
}

async function handleSave() {
  if (!selectedTriggerId.value) return;
  isSaving.value = true;
  try {
    if (chainEntries.value.length === 0) {
      await orchestrationApi.deleteFallbackChain(selectedTriggerId.value);
    } else {
      await orchestrationApi.setFallbackChain(selectedTriggerId.value, chainEntries.value);
    }
    showToast('Fallback chain saved', 'success');
  } catch (err: unknown) {
    showToast(err instanceof Error ? err.message : 'Failed to save', 'error');
  } finally {
    isSaving.value = false;
  }
}

async function refreshHealth() {
  isRefreshingHealth.value = true;
  try {
    const res = await orchestrationApi.getHealth();
    accountHealth.value = res.accounts ?? [];
    showToast('Health status refreshed', 'success');
  } catch {
    showToast('Failed to refresh health', 'error');
  } finally {
    isRefreshingHealth.value = false;
  }
}

async function clearRateLimit(accountId: string) {
  try {
    await orchestrationApi.clearRateLimit(accountId);
    showToast('Rate limit cleared', 'success');
    await refreshHealth();
  } catch {
    showToast('Failed to clear rate limit', 'error');
  }
}

function statusColor(status: string) {
  return {
    healthy: '#34d399',
    rate_limited: '#ef4444',
    unknown: '#6b7280',
  }[status] ?? '#6b7280';
}

function statusLabel(status: string) {
  return {
    healthy: 'healthy',
    rate_limited: 'rate limited',
    unknown: 'unknown',
  }[status] ?? status;
}

onMounted(loadData);
</script>

<template>
  <div class="mpf-page">

    <PageHeader
      title="Multi-Provider Fallback Chains"
      subtitle="Configure ordered fallback sequences so bot executions automatically retry with the next provider on failure."
    />

    <!-- Loading state -->
    <div v-if="isLoading" class="card loading-card">
      <div class="loading-content">Loading fallback chain data...</div>
    </div>

    <!-- Fatal error state (all calls failed) -->
    <div v-else-if="loadError && triggers.length === 0" class="card error-card">
      <div class="error-content">
        <span>{{ loadError }}</span>
        <button class="btn btn-ghost" @click="loadData">Retry</button>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else-if="triggers.length === 0" class="card empty-card">
      <div class="empty-content">No triggers found. Create a trigger first to configure fallback chains.</div>
    </div>

    <div v-else class="layout">
      <!-- Partial-load warning banner -->
      <div v-if="loadError" class="partial-warning" style="grid-column: 1 / -1;">
        <span>{{ loadError }}</span>
        <button class="btn btn-ghost" @click="loadData" style="padding: 4px 10px; font-size: 0.75rem;">Retry</button>
      </div>
      <!-- Trigger list sidebar -->
      <aside class="sidebar card">
        <div class="sidebar-header">
          <span>Triggers</span>
          <button class="btn-refresh" :disabled="isRefreshingHealth" @click="refreshHealth" title="Refresh health">
            <svg :class="{ spinning: isRefreshingHealth }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
              <path d="M1 4v6h6M23 20v-6h-6"/>
              <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/>
            </svg>
          </button>
        </div>
        <div
          v-for="t in triggers"
          :key="t.id"
          class="chain-item"
          :class="{ active: selectedTriggerId === t.id }"
          @click="selectTrigger(t.id)"
        >
          <div class="chain-name">{{ t.name }}</div>
          <div class="chain-meta">{{ t.backend_type }} · {{ t.trigger_source }}</div>
        </div>
      </aside>

      <!-- Chain editor -->
      <div class="chain-editor">
        <div class="card provider-order-card">
          <div class="card-header">
            Provider Fallback Order
            <span v-if="selectedTrigger" class="header-tag">{{ selectedTrigger.name }}</span>
          </div>

          <div v-if="chainEntriesWithHealth.length === 0" class="empty-chain">
            No fallback chain configured for this trigger. Add providers below.
          </div>

          <div v-else class="provider-list">
            <div
              v-for="(p, i) in chainEntriesWithHealth"
              :key="i"
              class="provider-row"
            >
              <div class="provider-order-num">{{ i + 1 }}</div>
              <div class="provider-info">
                <div class="provider-name">{{ p.backendName }}</div>
                <div class="provider-model">{{ p.accountName }}{{ p.plan ? ` (${p.plan})` : '' }}</div>
              </div>
              <div class="provider-status">
                <span class="status-dot" :style="{ background: statusColor(p.status) }"></span>
                <span class="status-text">{{ statusLabel(p.status) }}</span>
                <span v-if="p.cooldownSeconds" class="latency">{{ p.cooldownSeconds }}s cooldown</span>
                <span class="latency">{{ p.totalExecutions }} runs</span>
                <button
                  v-if="p.status === 'rate_limited' && p.account_id"
                  class="btn-clear"
                  @click="clearRateLimit(p.account_id!)"
                  title="Clear rate limit"
                >Clear</button>
              </div>
              <div class="provider-actions">
                <button class="order-btn" :disabled="i === 0" @click="moveEntry(i, -1)">↑</button>
                <button class="order-btn" :disabled="i === chainEntriesWithHealth.length - 1" @click="moveEntry(i, 1)">↓</button>
                <button class="order-btn remove-btn" @click="removeEntry(i)">×</button>
              </div>
            </div>
          </div>
        </div>

        <!-- Add provider -->
        <div class="card add-card">
          <div class="card-header">Add Provider to Chain</div>
          <div class="add-body">
            <div class="add-row">
              <select v-model="addBackendType" class="select-input">
                <option value="">-- Select backend --</option>
                <option v-for="bt in availableBackendTypes" :key="bt" :value="bt">{{ bt }}</option>
              </select>
              <select v-model="addAccountId" class="select-input" :disabled="!addBackendType">
                <option :value="null">Default account</option>
                <option
                  v-for="acc in accountsForBackend(addBackendType)"
                  :key="acc.account_id"
                  :value="acc.account_id"
                >{{ acc.account_name }}{{ acc.plan ? ` (${acc.plan})` : '' }}</option>
              </select>
              <button class="btn btn-primary" :disabled="!addBackendType" @click="addEntry">Add</button>
            </div>
          </div>
        </div>

        <!-- Health overview -->
        <div class="card health-card">
          <div class="card-header">Account Health</div>
          <div v-if="accountHealth.length === 0" class="health-empty">No account health data available.</div>
          <div v-else class="health-list">
            <div v-for="a in accountHealth" :key="a.account_id" class="health-row">
              <span class="status-dot" :style="{ background: a.is_rate_limited ? '#ef4444' : '#34d399' }"></span>
              <span class="health-name">{{ a.account_name }}</span>
              <span class="health-type">{{ a.backend_type }}</span>
              <span class="health-plan">{{ a.plan ?? 'no plan' }}</span>
              <span class="health-runs">{{ a.total_executions }} runs</span>
              <span v-if="a.is_rate_limited" class="health-limited">
                rate limited{{ a.cooldown_remaining_seconds ? ` (${a.cooldown_remaining_seconds}s)` : '' }}
              </span>
            </div>
          </div>
        </div>

        <div class="actions">
          <button class="btn btn-primary" :disabled="isSaving" @click="handleSave">
            {{ isSaving ? 'Saving...' : 'Save Chain' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mpf-page { display: flex; flex-direction: column; gap: 24px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.layout { display: grid; grid-template-columns: 220px 1fr; gap: 20px; align-items: start; }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }

.loading-card, .error-card, .empty-card { padding: 32px 24px; }
.loading-content { text-align: center; color: var(--text-tertiary); font-size: 0.875rem; }
.error-content { display: flex; align-items: center; justify-content: center; gap: 12px; color: #ef4444; font-size: 0.875rem; }
.partial-warning { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 16px; background: rgba(251,191,36,0.08); border: 1px solid rgba(251,191,36,0.3); border-radius: 8px; color: #fbbf24; font-size: 0.8rem; }
.empty-content { text-align: center; color: var(--text-tertiary); font-size: 0.875rem; }

.sidebar-header {
  display: flex; align-items: center; justify-content: space-between; padding: 14px 16px;
  border-bottom: 1px solid var(--border-default); font-size: 0.8rem; font-weight: 600; color: var(--text-secondary);
}
.btn-refresh { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); width: 26px; height: 26px; border-radius: 4px; cursor: pointer; display: flex; align-items: center; justify-content: center; }
.btn-refresh:hover:not(:disabled) { color: var(--accent-cyan); border-color: var(--accent-cyan); }
.btn-refresh:disabled { opacity: 0.4; cursor: not-allowed; }
.spinning { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

.chain-item { padding: 12px 16px; cursor: pointer; border-bottom: 1px solid var(--border-subtle); transition: background 0.1s; }
.chain-item:hover { background: var(--bg-tertiary); }
.chain-item.active { background: rgba(6,182,212,0.08); border-left: 2px solid var(--accent-cyan); }
.chain-item:last-child { border-bottom: none; }
.chain-name { font-size: 0.82rem; font-weight: 600; color: var(--text-primary); }
.chain-meta { font-size: 0.72rem; color: var(--text-muted); margin-top: 2px; }

.chain-editor { display: flex; flex-direction: column; gap: 16px; }

.card-header {
  padding: 14px 20px; border-bottom: 1px solid var(--border-default); font-size: 0.82rem;
  font-weight: 600; color: var(--text-secondary); display: flex; align-items: center; gap: 10px;
}

.header-tag { font-size: 0.72rem; color: var(--accent-cyan); background: rgba(6,182,212,0.1); padding: 2px 8px; border-radius: 4px; font-weight: 500; }

.empty-chain { padding: 24px 20px; text-align: center; color: var(--text-tertiary); font-size: 0.82rem; }

.provider-list { display: flex; flex-direction: column; }

.provider-row {
  display: flex; align-items: center; gap: 12px; padding: 14px 20px;
  border-bottom: 1px solid var(--border-subtle); transition: background 0.1s;
}
.provider-row:last-child { border-bottom: none; }

.provider-order-num { width: 24px; height: 24px; border-radius: 50%; background: var(--bg-tertiary); display: flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: 700; color: var(--text-secondary); flex-shrink: 0; }

.provider-info { flex: 1; }
.provider-name { font-size: 0.88rem; font-weight: 600; color: var(--text-primary); }
.provider-model { font-size: 0.72rem; color: var(--text-muted); font-family: monospace; }

.provider-status { display: flex; align-items: center; gap: 8px; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.status-text { font-size: 0.75rem; color: var(--text-tertiary); }
.latency { font-size: 0.72rem; color: var(--text-muted); }
.btn-clear { font-size: 0.68rem; padding: 2px 6px; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); color: #ef4444; border-radius: 3px; cursor: pointer; }
.btn-clear:hover { background: rgba(239,68,68,0.2); }

.provider-actions { display: flex; align-items: center; gap: 6px; }
.order-btn { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); padding: 3px 7px; border-radius: 4px; cursor: pointer; font-size: 0.8rem; }
.order-btn:disabled { opacity: 0.3; cursor: not-allowed; }
.order-btn:hover:not(:disabled) { background: var(--bg-primary); color: var(--accent-cyan); }
.remove-btn:hover:not(:disabled) { color: #ef4444; border-color: rgba(239,68,68,0.3); }

.add-body { padding: 16px 20px; }
.add-row { display: flex; align-items: center; gap: 10px; }
.select-input { padding: 7px 10px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 6px; color: var(--text-primary); font-size: 0.82rem; flex: 1; }
.select-input:focus { outline: none; border-color: var(--accent-cyan); }
.select-input:disabled { opacity: 0.4; }

.health-empty { padding: 20px; text-align: center; color: var(--text-tertiary); font-size: 0.82rem; }
.health-list { display: flex; flex-direction: column; }
.health-row { display: flex; align-items: center; gap: 10px; padding: 10px 20px; border-bottom: 1px solid var(--border-subtle); font-size: 0.82rem; }
.health-row:last-child { border-bottom: none; }
.health-name { color: var(--text-primary); font-weight: 500; min-width: 120px; }
.health-type { color: var(--text-tertiary); font-family: monospace; font-size: 0.75rem; min-width: 60px; }
.health-plan { color: var(--text-muted); font-size: 0.72rem; min-width: 60px; }
.health-runs { color: var(--text-muted); font-size: 0.72rem; }
.health-limited { color: #ef4444; font-size: 0.72rem; font-weight: 500; }

.actions { display: flex; justify-content: flex-end; gap: 12px; }
.btn { display: flex; align-items: center; gap: 6px; padding: 8px 16px; border-radius: 7px; font-size: 0.82rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-ghost { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-ghost:hover:not(:disabled) { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.btn-ghost:disabled { opacity: 0.4; cursor: not-allowed; }

@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } }
</style>
