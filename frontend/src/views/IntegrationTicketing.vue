<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

interface Integration {
  id: string;
  name: string;
  type: 'jira' | 'linear';
  enabled: boolean;
  host: string;
  apiKey: string;
  project: string;
  severityThreshold: 'critical' | 'high' | 'medium' | 'low';
}

interface Ticket {
  id: string;
  title: string;
  integration: string;
  severity: string;
  bot: string;
  createdAt: string;
  url: string;
}

const integrations = ref<Integration[]>([
  {
    id: 'int-jira',
    name: 'Jira',
    type: 'jira',
    enabled: true,
    host: 'https://myorg.atlassian.net',
    apiKey: '••••••••••••',
    project: 'SEC',
    severityThreshold: 'high',
  },
  {
    id: 'int-linear',
    name: 'Linear',
    type: 'linear',
    enabled: false,
    host: 'https://api.linear.app',
    apiKey: '',
    project: 'ENG',
    severityThreshold: 'critical',
  },
]);

const recentTickets = ref<Ticket[]>([
  { id: 'SEC-101', title: 'SQL injection vulnerability in user search', integration: 'Jira', severity: 'critical', bot: 'bot-security', createdAt: '2 hours ago', url: '#' },
  { id: 'SEC-100', title: 'Missing CORS headers on /api/export', integration: 'Jira', severity: 'high', bot: 'bot-security', createdAt: '1 day ago', url: '#' },
  { id: 'SEC-099', title: 'Outdated dependency: lodash 4.17.11', integration: 'Jira', severity: 'medium', bot: 'bot-security', createdAt: '3 days ago', url: '#' },
]);

const editingId = ref<string | null>(null);
const isSaving = ref(false);

function editIntegration(id: string) {
  editingId.value = editingId.value === id ? null : id;
}

async function saveIntegration(int: Integration) {
  isSaving.value = true;
  try {
    await new Promise(resolve => setTimeout(resolve, 800));
    editingId.value = null;
    showToast(`${int.name} integration saved`, 'success');
  } catch {
    showToast('Failed to save integration', 'error');
  } finally {
    isSaving.value = false;
  }
}

function toggleIntegration(int: Integration) {
  int.enabled = !int.enabled;
  showToast(`${int.name} ${int.enabled ? 'enabled' : 'disabled'}`, 'success');
}

function severityColor(s: string): string {
  const map: Record<string, string> = { critical: '#ef4444', high: '#f97316', medium: '#f59e0b', low: '#6b7280' };
  return map[s] ?? '#6b7280';
}
</script>

<template>
  <div class="integration-ticketing">
    <AppBreadcrumb :items="[
      { label: 'Integrations', action: () => router.push({ name: 'integrations' }) },
      { label: 'Ticketing' },
    ]" />

    <PageHeader
      title="Ticketing Integrations"
      subtitle="Configure Jira and Linear to auto-create tickets from bot findings."
    />

    <div class="integrations-list">
      <div v-for="int in integrations" :key="int.id" class="card integration-card">
        <div class="int-header">
          <div class="int-logo" :class="int.type">
            <span>{{ int.type === 'jira' ? 'J' : 'L' }}</span>
          </div>
          <div class="int-title-area">
            <h3 class="int-name">{{ int.name }}</h3>
            <span class="int-host">{{ int.host || 'Not configured' }}</span>
          </div>
          <div class="int-controls">
            <label class="toggle-wrap">
              <input type="checkbox" :checked="int.enabled" class="toggle-input" @change="toggleIntegration(int)" />
              <span class="toggle-track" :class="{ active: int.enabled }">
                <span class="toggle-thumb" />
              </span>
            </label>
            <button class="btn btn-sm btn-secondary" @click="editIntegration(int.id)">
              {{ editingId === int.id ? 'Cancel' : 'Configure' }}
            </button>
          </div>
        </div>

        <div v-if="editingId === int.id" class="int-form">
          <div class="form-row">
            <div class="field-group">
              <label class="field-label">Host URL</label>
              <input v-model="int.host" type="text" class="text-input" placeholder="https://myorg.atlassian.net" />
            </div>
            <div class="field-group">
              <label class="field-label">API Key</label>
              <input v-model="int.apiKey" type="password" class="text-input" placeholder="Enter API key..." />
            </div>
          </div>
          <div class="form-row">
            <div class="field-group">
              <label class="field-label">Project Key</label>
              <input v-model="int.project" type="text" class="text-input" placeholder="e.g. SEC" />
            </div>
            <div class="field-group">
              <label class="field-label">Auto-create threshold</label>
              <select v-model="int.severityThreshold" class="select-input">
                <option value="critical">Critical only</option>
                <option value="high">High and above</option>
                <option value="medium">Medium and above</option>
                <option value="low">All findings</option>
              </select>
            </div>
          </div>
          <div class="form-actions">
            <button class="btn btn-primary" :disabled="isSaving" @click="saveIntegration(int)">
              {{ isSaving ? 'Saving...' : 'Save Integration' }}
            </button>
          </div>
        </div>

        <div v-else class="int-summary">
          <div class="summary-item">
            <span class="summary-label">Project</span>
            <span class="summary-val">{{ int.project }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">Auto-create</span>
            <span class="summary-val severity-val" :style="{ color: severityColor(int.severityThreshold) }">
              {{ int.severityThreshold }} and above
            </span>
          </div>
          <div class="summary-item">
            <span class="summary-label">Status</span>
            <span :class="['summary-val', int.enabled ? 'text-green' : 'text-muted']">
              {{ int.enabled ? 'Active' : 'Disabled' }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <path d="M14.5 10c-.83 0-1.5-.67-1.5-1.5v-5c0-.83.67-1.5 1.5-1.5s1.5.67 1.5 1.5v5c0 .83-.67 1.5-1.5 1.5z"/>
            <path d="M20.5 10H19V8.5c0-.83.67-1.5 1.5-1.5s1.5.67 1.5 1.5-.67 1.5-1.5 1.5z"/>
            <path d="M9.5 14c.83 0 1.5.67 1.5 1.5v5c0 .83-.67 1.5-1.5 1.5S8 21.33 8 20.5v-5c0-.83.67-1.5 1.5-1.5z"/>
            <path d="M3.5 14H5v1.5c0 .83-.67 1.5-1.5 1.5S2 16.33 2 15.5 2.67 14 3.5 14z"/>
            <path d="M14 14.5c0-.83.67-1.5 1.5-1.5h5c.83 0 1.5.67 1.5 1.5s-.67 1.5-1.5 1.5h-5c-.83 0-1.5-.67-1.5-1.5z"/>
            <path d="M15.5 19H14v1.5c0 .83.67 1.5 1.5 1.5s1.5-.67 1.5-1.5-.67-1.5-1.5-1.5z"/>
            <path d="M10 9.5C10 8.67 9.33 8 8.5 8h-5C2.67 8 2 8.67 2 9.5S2.67 11 3.5 11h5c.83 0 1.5-.67 1.5-1.5z"/>
            <path d="M8.5 5H10V3.5C10 2.67 9.33 2 8.5 2S7 2.67 7 3.5 7.67 5 8.5 5z"/>
          </svg>
          Recent Auto-Created Tickets
        </h3>
        <span class="card-badge">{{ recentTickets.length }} tickets</span>
      </div>
      <div class="tickets-list">
        <div v-for="t in recentTickets" :key="t.id" class="ticket-row">
          <div class="ticket-id">{{ t.id }}</div>
          <div class="ticket-title">{{ t.title }}</div>
          <div class="ticket-meta">
            <span class="ticket-sev" :style="{ color: severityColor(t.severity), background: severityColor(t.severity) + '20' }">
              {{ t.severity }}
            </span>
            <span class="ticket-bot">{{ t.bot }}</span>
            <span class="ticket-int">{{ t.integration }}</span>
            <span class="ticket-date">{{ t.createdAt }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.integration-ticketing {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.integrations-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
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

.card-badge {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 4px 10px;
  background: var(--bg-tertiary);
  border-radius: 4px;
}

.int-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-subtle);
}

.int-logo {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1rem;
  font-weight: 700;
  flex-shrink: 0;
}

.int-logo.jira { background: #0052CC; color: white; }
.int-logo.linear { background: #5E6AD2; color: white; }

.int-title-area {
  flex: 1;
}

.int-name {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 2px 0;
}

.int-host {
  font-size: 0.78rem;
  color: var(--text-tertiary);
}

.int-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

.toggle-wrap {
  display: flex;
  align-items: center;
  cursor: pointer;
}

.toggle-input { display: none; }

.toggle-track {
  width: 36px;
  height: 20px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  display: flex;
  align-items: center;
  padding: 2px;
  transition: all 0.2s;
}

.toggle-track.active {
  background: rgba(6, 182, 212, 0.2);
  border-color: var(--accent-cyan);
}

.toggle-thumb {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--text-tertiary);
  transition: all 0.2s;
}

.toggle-track.active .toggle-thumb {
  background: var(--accent-cyan);
  transform: translateX(16px);
}

.int-summary {
  display: flex;
  gap: 32px;
  padding: 14px 24px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.summary-label {
  font-size: 0.72rem;
  color: var(--text-tertiary);
  text-transform: uppercase;
  font-weight: 600;
  letter-spacing: 0.05em;
}

.summary-val {
  font-size: 0.875rem;
  color: var(--text-primary);
  font-weight: 500;
}

.text-green { color: #34d399 !important; }
.text-muted { color: var(--text-tertiary) !important; }

.int-form {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  border-top: 1px solid var(--border-subtle);
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.text-input, .select-input {
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.text-input:focus, .select-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.form-actions {
  display: flex;
  justify-content: flex-end;
}

.tickets-list {
  display: flex;
  flex-direction: column;
}

.ticket-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 24px;
  border-bottom: 1px solid var(--border-subtle);
}

.ticket-row:last-child { border-bottom: none; }

.ticket-id {
  font-family: monospace;
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--accent-cyan);
  min-width: 72px;
}

.ticket-title {
  flex: 1;
  font-size: 0.875rem;
  color: var(--text-primary);
}

.ticket-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ticket-sev {
  font-size: 0.7rem;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
}

.ticket-bot, .ticket-int, .ticket-date {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-sm { padding: 5px 10px; font-size: 0.8rem; }

.btn-primary {
  background: var(--accent-cyan);
  color: #000;
}

.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-secondary {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.btn-secondary:hover { border-color: var(--accent-cyan); color: var(--text-primary); }
</style>
