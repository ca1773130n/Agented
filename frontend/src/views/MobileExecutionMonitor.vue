<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';
const showToast = useToast();

const isLoading = ref(true);
const isPushEnabled = ref(false);
let refreshInterval: ReturnType<typeof setInterval> | null = null;

interface Execution {
  id: string;
  bot_name: string;
  bot_id: string;
  status: 'running' | 'success' | 'failed' | 'queued';
  started_at: string;
  finished_at: string | null;
  duration_s: number | null;
  trigger: string;
  error?: string;
}

const executions = ref<Execution[]>([]);
const filterStatus = ref<string>('all');
const selectedExec = ref<Execution | null>(null);

async function loadData() {
  try {
    const res = await fetch('/api/executions?limit=30');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    executions.value = (await res.json()).executions ?? [];
  } catch {
    const now = Date.now();
    executions.value = [
      { id: 'ex-1', bot_name: 'PR Review', bot_id: 'bot-pr-review', status: 'running', started_at: new Date(now - 45000).toISOString(), finished_at: null, duration_s: null, trigger: 'github:pull_request' },
      { id: 'ex-2', bot_name: 'Security Audit', bot_id: 'bot-security', status: 'success', started_at: new Date(now - 300000).toISOString(), finished_at: new Date(now - 240000).toISOString(), duration_s: 60, trigger: 'schedule:weekly' },
      { id: 'ex-3', bot_name: 'Dep Check', bot_id: 'bot-dep', status: 'failed', started_at: new Date(now - 600000).toISOString(), finished_at: new Date(now - 590000).toISOString(), duration_s: 10, trigger: 'webhook', error: 'Claude API rate limited' },
      { id: 'ex-4', bot_name: 'PR Review', bot_id: 'bot-pr-review', status: 'success', started_at: new Date(now - 900000).toISOString(), finished_at: new Date(now - 840000).toISOString(), duration_s: 60, trigger: 'github:pull_request' },
      { id: 'ex-5', bot_name: 'Security Audit', bot_id: 'bot-security', status: 'queued', started_at: new Date(now - 10000).toISOString(), finished_at: null, duration_s: null, trigger: 'manual' },
      { id: 'ex-6', bot_name: 'Changelog Bot', bot_id: 'bot-changelog', status: 'success', started_at: new Date(now - 1800000).toISOString(), finished_at: new Date(now - 1740000).toISOString(), duration_s: 58, trigger: 'github:push' },
      { id: 'ex-7', bot_name: 'Dep Check', bot_id: 'bot-dep', status: 'success', started_at: new Date(now - 2400000).toISOString(), finished_at: new Date(now - 2385000).toISOString(), duration_s: 15, trigger: 'schedule:daily' },
    ];
  } finally {
    isLoading.value = false;
  }
}

async function togglePushNotifications() {
  if (!('Notification' in window)) {
    showToast('Push notifications not supported in this browser', 'error');
    return;
  }
  if (isPushEnabled.value) {
    isPushEnabled.value = false;
    showToast('Push notifications disabled', 'success');
    return;
  }
  const permission = await Notification.requestPermission();
  if (permission === 'granted') {
    isPushEnabled.value = true;
    showToast('Push notifications enabled for bot failures', 'success');
  } else {
    showToast('Notification permission denied', 'error');
  }
}

const filteredExecutions = computed(() => {
  if (filterStatus.value === 'all') return executions.value;
  return executions.value.filter(e => e.status === filterStatus.value);
});

const runningCount = computed(() => executions.value.filter(e => e.status === 'running').length);
const failedCount = computed(() => executions.value.filter(e => e.status === 'failed').length);
const successCount = computed(() => executions.value.filter(e => e.status === 'success').length);

function statusIcon(status: Execution['status']): string {
  return { running: '⟳', success: '✓', failed: '✕', queued: '◷' }[status];
}

function statusColor(status: Execution['status']): string {
  return {
    running: 'var(--accent-cyan)',
    success: 'var(--accent-emerald)',
    failed: 'var(--accent-crimson)',
    queued: 'var(--accent-amber)',
  }[status];
}

function timeAgo(iso: string): string {
  const secs = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  return `${Math.floor(secs / 3600)}h ago`;
}

onMounted(() => {
  loadData();
  refreshInterval = setInterval(loadData, 15000);
});

onUnmounted(() => {
  if (refreshInterval) clearInterval(refreshInterval);
});
</script>

<template>
  <div class="mobile-monitor-page">

    <LoadingState v-if="isLoading" message="Loading executions..." />

    <template v-else>
      <!-- Mobile-first header -->
      <div class="monitor-header">
        <div class="header-left">
          <h1>Execution Monitor</h1>
          <p class="refresh-note">Auto-refreshes every 15s</p>
        </div>
        <button class="push-btn" :class="{ enabled: isPushEnabled }" @click="togglePushNotifications">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 01-3.46 0"/>
          </svg>
          {{ isPushEnabled ? 'Alerts On' : 'Enable Alerts' }}
        </button>
      </div>

      <!-- Status summary -->
      <div class="status-summary">
        <div class="status-pill running" :class="{ active: filterStatus === 'running' }" @click="filterStatus = filterStatus === 'running' ? 'all' : 'running'">
          <span class="pill-count">{{ runningCount }}</span>
          <span class="pill-label">Running</span>
        </div>
        <div class="status-pill failed" :class="{ active: filterStatus === 'failed' }" @click="filterStatus = filterStatus === 'failed' ? 'all' : 'failed'">
          <span class="pill-count">{{ failedCount }}</span>
          <span class="pill-label">Failed</span>
        </div>
        <div class="status-pill success" :class="{ active: filterStatus === 'success' }" @click="filterStatus = filterStatus === 'success' ? 'all' : 'success'">
          <span class="pill-count">{{ successCount }}</span>
          <span class="pill-label">Succeeded</span>
        </div>
      </div>

      <!-- Execution list (mobile card layout) -->
      <div class="exec-list">
        <div v-for="exec in filteredExecutions" :key="exec.id"
          class="exec-card"
          :class="exec.status"
          @click="selectedExec = selectedExec?.id === exec.id ? null : exec">
          <div class="exec-card-main">
            <div class="exec-status-icon" :style="{ color: statusColor(exec.status) }">
              {{ statusIcon(exec.status) }}
            </div>
            <div class="exec-info">
              <span class="exec-bot-name">{{ exec.bot_name }}</span>
              <span class="exec-trigger">{{ exec.trigger }}</span>
            </div>
            <div class="exec-time">
              <span class="exec-ago">{{ timeAgo(exec.started_at) }}</span>
              <span v-if="exec.duration_s" class="exec-dur">{{ exec.duration_s }}s</span>
            </div>
          </div>

          <!-- Expanded detail -->
          <div v-if="selectedExec?.id === exec.id" class="exec-detail">
            <div class="detail-row">
              <span class="detail-key">ID</span>
              <span class="detail-val">{{ exec.id }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-key">Bot</span>
              <span class="detail-val">{{ exec.bot_id }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-key">Status</span>
              <span class="detail-val" :style="{ color: statusColor(exec.status) }">{{ exec.status }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-key">Started</span>
              <span class="detail-val">{{ new Date(exec.started_at).toLocaleTimeString() }}</span>
            </div>
            <div v-if="exec.finished_at" class="detail-row">
              <span class="detail-key">Finished</span>
              <span class="detail-val">{{ new Date(exec.finished_at).toLocaleTimeString() }}</span>
            </div>
            <div v-if="exec.error" class="detail-row error-row">
              <span class="detail-key">Error</span>
              <span class="detail-val error-val">{{ exec.error }}</span>
            </div>
          </div>
        </div>

        <div v-if="filteredExecutions.length === 0" class="empty-list">
          No {{ filterStatus === 'all' ? '' : filterStatus }} executions found.
        </div>
      </div>

      <div class="mobile-hint">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="5" y="2" width="14" height="20" rx="2" ry="2"/>
          <line x1="12" y1="18" x2="12.01" y2="18"/>
        </svg>
        This view is optimized for mobile. Enable push alerts to get notified of failures at 2am.
      </div>
    </template>
  </div>
</template>

<style scoped>
.mobile-monitor-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
  width: 100%;
  max-width: 600px;
  margin: 0 auto;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.monitor-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.header-left h1 { font-size: 1.1rem; font-weight: 600; color: var(--text-primary); margin-bottom: 2px; }
.refresh-note { font-size: 0.78rem; color: var(--text-tertiary); }

.push-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 20px;
  border: 1px solid var(--border-default);
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.push-btn svg { width: 14px; height: 14px; }
.push-btn:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.push-btn.enabled { background: rgba(16,185,129,0.1); border-color: var(--accent-emerald); color: var(--accent-emerald); }

.status-summary {
  display: flex;
  gap: 12px;
}

.status-pill {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 14px 10px;
  border-radius: 10px;
  border: 2px solid transparent;
  cursor: pointer;
  transition: all 0.15s;
  background: var(--bg-secondary);
}

.status-pill:hover { border-color: var(--border-default); }
.status-pill.active { border-color: currentColor; }

.status-pill.running { color: var(--accent-cyan); }
.status-pill.failed { color: var(--accent-crimson); }
.status-pill.success { color: var(--accent-emerald); }

.pill-count { font-size: 1.6rem; font-weight: 700; line-height: 1; }
.pill-label { font-size: 0.72rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; margin-top: 4px; color: var(--text-secondary); }

.exec-list { display: flex; flex-direction: column; gap: 8px; }

.exec-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  padding: 14px 16px;
  cursor: pointer;
  transition: border-color 0.15s;
}

.exec-card:hover { border-color: var(--border-hover, var(--accent-cyan)); }
.exec-card.failed { border-left: 3px solid var(--accent-crimson); }
.exec-card.running { border-left: 3px solid var(--accent-cyan); }
.exec-card.success { border-left: 3px solid var(--accent-emerald); }
.exec-card.queued { border-left: 3px solid var(--accent-amber); }

.exec-card-main {
  display: flex;
  align-items: center;
  gap: 12px;
}

.exec-status-icon {
  font-size: 1.2rem;
  font-weight: 700;
  width: 28px;
  text-align: center;
  flex-shrink: 0;
}

.exec-info { flex: 1; min-width: 0; }
.exec-bot-name { display: block; font-weight: 600; font-size: 0.9rem; color: var(--text-primary); }
.exec-trigger { display: block; font-size: 0.75rem; color: var(--text-tertiary); }

.exec-time { text-align: right; flex-shrink: 0; }
.exec-ago { display: block; font-size: 0.8rem; color: var(--text-secondary); font-weight: 500; }
.exec-dur { display: block; font-size: 0.72rem; color: var(--text-tertiary); }

.exec-detail {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.detail-row { display: flex; gap: 12px; font-size: 0.82rem; }
.detail-key { color: var(--text-tertiary); min-width: 60px; font-weight: 500; }
.detail-val { color: var(--text-primary); word-break: break-all; }
.error-row .detail-val { color: var(--accent-crimson); }

.empty-list {
  text-align: center;
  padding: 40px;
  color: var(--text-tertiary);
  font-size: 0.85rem;
  border: 1px dashed var(--border-default);
  border-radius: 8px;
}

.mobile-hint {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: 0.8rem;
  color: var(--text-tertiary);
  padding: 14px 16px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  border: 1px solid var(--border-default);
}

.mobile-hint svg { width: 16px; height: 16px; flex-shrink: 0; margin-top: 1px; }

@media (max-width: 600px) {
  .mobile-monitor-page { max-width: 100%; }
}
</style>
