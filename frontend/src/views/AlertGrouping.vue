<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

interface AlertGroup {
  id: string;
  title: string;
  rootCause: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  count: number;
  bots: string[];
  firstSeen: string;
  lastSeen: string;
  status: 'active' | 'suppressed' | 'acknowledged';
}

const groups = ref<AlertGroup[]>([
  { id: 'ag-1', title: 'Bot execution timeouts', rootCause: 'Subprocess timeout limit exceeded — likely due to large PR diffs causing excessive prompt tokens.', severity: 'critical', count: 14, bots: ['bot-pr-review'], firstSeen: '2 hours ago', lastSeen: '5 minutes ago', status: 'active' },
  { id: 'ag-2', title: 'GitHub API rate limit exceeded', rootCause: 'Too many concurrent PR review bots hitting GitHub API. Implement exponential backoff or token rotation.', severity: 'high', count: 8, bots: ['bot-pr-review', 'bot-security'], firstSeen: '6 hours ago', lastSeen: '1 hour ago', status: 'active' },
  { id: 'ag-3', title: 'Empty stdout on security scan', rootCause: 'Prompt template missing {paths} placeholder. Affected executions received empty file list.', severity: 'high', count: 3, bots: ['bot-security'], firstSeen: '1 day ago', lastSeen: '4 hours ago', status: 'acknowledged' },
  { id: 'ag-4', title: 'JSON parse errors in output', rootCause: 'Haiku model occasionally returns markdown-wrapped JSON. Add JSON extraction step.', severity: 'medium', count: 21, bots: ['bot-security'], firstSeen: '3 days ago', lastSeen: '2 days ago', status: 'suppressed' },
]);

const activeFilter = ref<string>('all');

const filtered = computed(() => {
  if (activeFilter.value === 'all') return groups.value;
  return groups.value.filter(g => g.status === activeFilter.value);
});

const processingId = ref<string | null>(null);

async function handleAck(g: AlertGroup) {
  processingId.value = g.id;
  try {
    await new Promise(resolve => setTimeout(resolve, 500));
    g.status = 'acknowledged';
    showToast(`Alert group acknowledged`, 'success');
  } finally {
    processingId.value = null;
  }
}

async function handleSuppress(g: AlertGroup) {
  processingId.value = g.id;
  try {
    await new Promise(resolve => setTimeout(resolve, 500));
    g.status = 'suppressed';
    showToast(`Alert group suppressed`, 'info');
  } finally {
    processingId.value = null;
  }
}

async function handleReactivate(g: AlertGroup) {
  g.status = 'active';
  showToast(`Alert group reactivated`, 'info');
}

function severityColor(s: string): string {
  const map: Record<string, string> = { critical: '#ef4444', high: '#f97316', medium: '#f59e0b', low: '#6b7280' };
  return map[s] ?? '#6b7280';
}

function statusColor(s: string): string {
  const map: Record<string, string> = { active: '#ef4444', suppressed: '#6b7280', acknowledged: '#f59e0b' };
  return map[s] ?? '#6b7280';
}

const counts = computed(() => ({
  all: groups.value.length,
  active: groups.value.filter(g => g.status === 'active').length,
  acknowledged: groups.value.filter(g => g.status === 'acknowledged').length,
  suppressed: groups.value.filter(g => g.status === 'suppressed').length,
}));
</script>

<template>
  <div class="alert-grouping">
    <AppBreadcrumb :items="[
      { label: 'Monitoring', action: () => router.push({ name: 'monitoring' }) },
      { label: 'Alert Groups' },
    ]" />

    <PageHeader
      title="Alert Grouping"
      subtitle="Smart-grouped failure alerts with root cause analysis."
    />

    <div class="filter-tabs">
      <button
        v-for="[key, label] in [['all', 'All'], ['active', 'Active'], ['acknowledged', 'Acknowledged'], ['suppressed', 'Suppressed']]"
        :key="key"
        class="filter-tab"
        :class="{ active: activeFilter === key }"
        @click="activeFilter = key"
      >
        {{ label }}
        <span class="tab-count">{{ counts[key as keyof typeof counts] }}</span>
      </button>
    </div>

    <div class="groups-list">
      <div
        v-for="g in filtered"
        :key="g.id"
        class="card group-card"
        :class="{ 'is-suppressed': g.status === 'suppressed', 'is-acked': g.status === 'acknowledged' }"
      >
        <div class="group-header">
          <div class="severity-bar" :style="{ background: severityColor(g.severity) }"></div>
          <div class="group-main">
            <div class="group-title-row">
              <div class="sev-badge" :style="{ color: severityColor(g.severity), background: severityColor(g.severity) + '20' }">
                {{ g.severity }}
              </div>
              <h3 class="group-title">{{ g.title }}</h3>
              <span class="group-count">{{ g.count }} occurrences</span>
            </div>
            <div class="root-cause">
              <div class="rc-label">Root Cause</div>
              <p class="rc-text">{{ g.rootCause }}</p>
            </div>
            <div class="group-meta">
              <div class="meta-bots">
                <span v-for="b in g.bots" :key="b" class="bot-tag">{{ b }}</span>
              </div>
              <span class="meta-item">First: {{ g.firstSeen }}</span>
              <span class="meta-sep">·</span>
              <span class="meta-item">Last: {{ g.lastSeen }}</span>
              <span class="status-pill" :style="{ color: statusColor(g.status), background: statusColor(g.status) + '15' }">
                {{ g.status }}
              </span>
            </div>
          </div>
          <div class="group-actions">
            <template v-if="g.status === 'active'">
              <button class="btn btn-sm btn-ack" :disabled="processingId === g.id" @click="handleAck(g)">Acknowledge</button>
              <button class="btn btn-sm btn-suppress" :disabled="processingId === g.id" @click="handleSuppress(g)">Suppress</button>
            </template>
            <template v-else>
              <button class="btn btn-sm btn-reactivate" @click="handleReactivate(g)">Reactivate</button>
            </template>
          </div>
        </div>
      </div>

      <div v-if="filtered.length === 0" class="card empty-card">
        <div class="empty-inner">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="40" height="40" style="opacity: 0.3; color: var(--text-tertiary)">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
          <p>No alert groups in this category</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.alert-grouping {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.filter-tabs {
  display: flex;
  gap: 4px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  padding: 4px;
  width: fit-content;
}

.filter-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 7px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.15s;
}

.filter-tab.active {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.tab-count {
  font-size: 0.72rem;
  font-weight: 700;
  background: var(--bg-elevated);
  color: var(--text-tertiary);
  padding: 1px 6px;
  border-radius: 10px;
}

.filter-tab.active .tab-count {
  background: var(--accent-cyan);
  color: #000;
}

.groups-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.group-card.is-suppressed {
  opacity: 0.55;
}

.group-card.is-acked {
  border-color: rgba(245, 158, 11, 0.3);
}

.group-header {
  display: flex;
  gap: 0;
}

.severity-bar {
  width: 4px;
  flex-shrink: 0;
}

.group-main {
  flex: 1;
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.group-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.sev-badge {
  font-size: 0.7rem;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.group-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  flex: 1;
}

.group-count {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  font-weight: 500;
}

.root-cause {
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.rc-label {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 4px;
}

.rc-text {
  font-size: 0.85rem;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
}

.group-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.meta-bots {
  display: flex;
  gap: 6px;
}

.bot-tag {
  font-size: 0.7rem;
  padding: 2px 8px;
  background: rgba(6, 182, 212, 0.1);
  border: 1px solid rgba(6, 182, 212, 0.2);
  border-radius: 4px;
  color: var(--accent-cyan);
  font-family: monospace;
}

.meta-item {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.meta-sep { color: var(--text-muted); }

.status-pill {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: capitalize;
  margin-left: auto;
}

.group-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
  justify-content: center;
  border-left: 1px solid var(--border-subtle);
}

.btn {
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-sm { padding: 6px 12px; font-size: 0.8rem; }

.btn-ack {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
  border: 1px solid rgba(245, 158, 11, 0.3);
}

.btn-ack:hover:not(:disabled) { background: rgba(245, 158, 11, 0.25); }
.btn-ack:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-suppress {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.btn-suppress:hover:not(:disabled) { border-color: var(--border-strong); }
.btn-suppress:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-reactivate {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.btn-reactivate:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }

.empty-card {
  padding: 48px;
}

.empty-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
}

.empty-inner p {
  font-size: 0.875rem;
  color: var(--text-tertiary);
  margin: 0;
}
</style>
