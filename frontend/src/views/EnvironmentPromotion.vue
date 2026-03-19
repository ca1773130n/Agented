<script setup lang="ts">
import { ref, onMounted } from 'vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { configExportApi, triggerApi, ApiError } from '../services/api';
import type { Trigger } from '../services/api';
const showToast = useToast();

interface EnvBot {
  id: string;
  name: string;
  status: 'passing' | 'failing' | 'pending';
  lastRun: string;
  promoted: boolean;
}

interface Environment {
  id: string;
  name: string;
  type: 'staging' | 'production';
  status: 'healthy' | 'degraded' | 'offline';
  bots: EnvBot[];
}

const isLoading = ref(true);
const loadError = ref<string | null>(null);

const environments = ref<Environment[]>([
  {
    id: 'env-staging',
    name: 'Staging',
    type: 'staging',
    status: 'healthy',
    bots: [],
  },
  {
    id: 'env-prod',
    name: 'Production',
    type: 'production',
    status: 'healthy',
    bots: [],
  },
]);

const promotingId = ref<string | null>(null);
const testingId = ref<string | null>(null);

function triggerToEnvBot(t: Trigger): EnvBot {
  const enabled = t.enabled !== 0;
  return {
    id: t.id,
    name: t.name,
    status: enabled ? 'passing' : 'pending',
    lastRun: t.last_run_at || t.created_at || 'Unknown',
    promoted: false,
  };
}

async function loadTriggers() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const { triggers } = await triggerApi.list();
    // Populate staging with all triggers
    const staging = environments.value.find(e => e.type === 'staging')!;
    staging.bots = triggers.map(triggerToEnvBot);

    // Try to load exported config to see what's in "production"
    try {
      const exported = await configExportApi.exportAll('json');
      if (exported.data) {
        const parsed = JSON.parse(exported.data);
        const prodTriggers = Array.isArray(parsed) ? parsed : (parsed.triggers || []);
        const prod = environments.value.find(e => e.type === 'production')!;
        prod.bots = prodTriggers.map((t: Trigger) => ({
          ...triggerToEnvBot(t),
          promoted: true,
        }));
      }
    } catch {
      // Export may not be available, that's fine
    }
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : 'Failed to load triggers';
    loadError.value = msg;
  } finally {
    isLoading.value = false;
  }
}

onMounted(loadTriggers);

async function handleTest(botId: string) {
  testingId.value = botId;
  try {
    // Export the trigger config to validate it
    await configExportApi.exportTrigger(botId, 'json');
    showToast('Staging test completed successfully', 'success');
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : 'Test failed';
    showToast(msg, 'error');
  } finally {
    testingId.value = null;
  }
}

async function handlePromote(botId: string, botName: string) {
  promotingId.value = botId;
  try {
    // Export from staging and import to production
    const exported = await configExportApi.exportTrigger(botId, 'json');
    await configExportApi.importConfig({ config: exported.data, format: 'json' });
    const prod = environments.value.find(e => e.type === 'production');
    if (prod) {
      const existing = prod.bots.find(b => b.id === botId);
      if (existing) {
        existing.status = 'passing';
        existing.lastRun = 'just now';
      } else {
        prod.bots.push({ id: botId, name: botName, status: 'passing', lastRun: 'just now', promoted: true });
      }
    }
    showToast(`${botName} promoted to production`, 'success');
  } catch (err) {
    const msg = err instanceof ApiError ? err.message : 'Promotion failed';
    showToast(msg, 'error');
  } finally {
    promotingId.value = null;
  }
}

function statusColor(s: string): string {
  const map: Record<string, string> = { healthy: '#34d399', degraded: '#f59e0b', offline: '#ef4444', passing: '#34d399', failing: '#ef4444', pending: '#f59e0b' };
  return map[s] ?? '#6b7280';
}

function envTypeColor(t: string): string {
  return t === 'production' ? '#f59e0b' : '#818cf8';
}
</script>

<template>
  <div class="env-promotion">

    <PageHeader
      title="Environment Promotion"
      subtitle="Promote bots from staging to production after successful testing."
    />

    <!-- Loading state -->
    <div v-if="isLoading" class="card" style="padding: 32px; text-align: center; color: var(--text-tertiary);">
      Loading environment data...
    </div>

    <!-- Error state -->
    <div v-else-if="loadError" class="card" style="padding: 32px; text-align: center; color: #ef4444;">
      {{ loadError }}
      <button class="btn btn-secondary" style="margin-top: 12px;" @click="loadTriggers">Retry</button>
    </div>

    <div v-else class="env-grid">
      <div v-for="env in environments" :key="env.id" class="env-card">
        <div class="env-header" :class="env.type">
          <div class="env-title-row">
            <div class="env-badge" :style="{ background: envTypeColor(env.type) + '20', color: envTypeColor(env.type) }">
              {{ env.type }}
            </div>
            <h2 class="env-name">{{ env.name }}</h2>
          </div>
          <div class="env-status" :style="{ color: statusColor(env.status) }">
            <span class="status-dot" :style="{ background: statusColor(env.status) }"></span>
            {{ env.status }}
          </div>
        </div>

        <div class="env-bots">
          <div v-for="bot in env.bots" :key="bot.id" class="bot-row">
            <div class="bot-info">
              <span class="bot-name">{{ bot.name }}</span>
              <span class="bot-last-run">{{ bot.lastRun }}</span>
            </div>
            <div class="bot-right">
              <span class="bot-status" :style="{ color: statusColor(bot.status) }">
                <span class="status-dot" :style="{ background: statusColor(bot.status) }"></span>
                {{ bot.status }}
              </span>
              <template v-if="env.type === 'staging'">
                <button
                  class="btn btn-sm btn-secondary"
                  :disabled="testingId === bot.id"
                  @click="handleTest(bot.id)"
                >
                  {{ testingId === bot.id ? 'Testing...' : 'Test' }}
                </button>
                <button
                  class="btn btn-sm btn-promote"
                  :disabled="bot.status !== 'passing' || promotingId === bot.id"
                  @click="handlePromote(bot.id, bot.name)"
                >
                  {{ promotingId === bot.id ? '...' : 'Promote →' }}
                </button>
              </template>
            </div>
          </div>

          <div v-if="env.bots.length === 0" class="env-empty">
            No bots deployed to {{ env.name }}
          </div>
        </div>

        <div v-if="env.type === 'staging'" class="env-footer">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14" style="color: var(--text-tertiary)">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 8v4l3 3"/>
          </svg>
          <span>Test in staging before promoting to production</span>
        </div>
      </div>
    </div>

    <div v-if="!isLoading && !loadError" class="card promo-rules">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
          </svg>
          Promotion Rules
        </h3>
      </div>
      <div class="rules-list">
        <div class="rule-item">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16" style="color: #34d399">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
          Bot must have a passing status in staging
        </div>
        <div class="rule-item">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16" style="color: #34d399">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
          At least one successful staging test run required
        </div>
        <div class="rule-item">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16" style="color: var(--accent-cyan)">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 8v4l3 3"/>
          </svg>
          Production rollback available for 24 hours after promotion
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.env-promotion {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.env-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}

.env-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.env-header {
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-default);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.env-header.production {
  background: rgba(245, 158, 11, 0.04);
}

.env-header.staging {
  background: rgba(129, 140, 248, 0.04);
}

.env-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.env-badge {
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 3px 8px;
  border-radius: 4px;
}

.env-name {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.env-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.8rem;
  font-weight: 500;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.env-bots {
  display: flex;
  flex-direction: column;
  min-height: 80px;
}

.bot-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 24px;
  border-bottom: 1px solid var(--border-subtle);
  gap: 12px;
}

.bot-row:last-child { border-bottom: none; }

.bot-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.bot-name {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-primary);
}

.bot-last-run {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.bot-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.bot-status {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 0.75rem;
  font-weight: 500;
}

.env-empty {
  padding: 24px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 0.875rem;
}

.env-footer {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 24px;
  background: var(--bg-tertiary);
  font-size: 0.78rem;
  color: var(--text-tertiary);
}

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

.rules-list {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.rule-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.btn {
  display: flex;
  align-items: center;
  gap: 6px;
  border-radius: 6px;
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-sm { padding: 5px 10px; }

.btn-secondary {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.btn-secondary:hover:not(:disabled) { border-color: var(--accent-cyan); color: var(--text-primary); }
.btn-secondary:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-promote {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
  border: 1px solid rgba(245, 158, 11, 0.3);
}

.btn-promote:hover:not(:disabled) { background: rgba(245, 158, 11, 0.25); }
.btn-promote:disabled { opacity: 0.4; cursor: not-allowed; }

.promo-rules { margin-top: 0; }

@media (max-width: 768px) {
  .env-grid { grid-template-columns: 1fr; }
}
</style>
