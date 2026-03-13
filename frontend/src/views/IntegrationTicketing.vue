<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { integrationApi, ApiError } from '../services/api';
import type { Integration } from '../services/api';

const router = useRouter();
const showToast = useToast();

interface TicketingIntegration {
  id: string;
  name: string;
  type: 'jira' | 'linear';
  enabled: boolean;
  host: string;
  apiKey: string;
  project: string;
  severityThreshold: 'critical' | 'high' | 'medium' | 'low';
}

const loading = ref(true);
const error = ref('');
const integrations = ref<TicketingIntegration[]>([]);
const editingId = ref<string | null>(null);
const isSaving = ref(false);

function rawToTicketing(int: Integration): TicketingIntegration {
  const config = int.config || {};
  const intType = (int.type || '').toLowerCase();
  return {
    id: int.id,
    name: int.name,
    type: intType.includes('linear') ? 'linear' : 'jira',
    enabled: int.enabled,
    host: (config.host as string) || '',
    apiKey: (config.api_key as string) || '',
    project: (config.project as string) || '',
    severityThreshold: (config.severity_threshold as TicketingIntegration['severityThreshold']) || 'high',
  };
}

function ticketingToRaw(t: TicketingIntegration): Partial<Integration> {
  return {
    name: t.name,
    type: t.type,
    enabled: t.enabled,
    config: {
      host: t.host,
      api_key: t.apiKey,
      project: t.project,
      severity_threshold: t.severityThreshold,
    },
  };
}

async function fetchIntegrations() {
  loading.value = true;
  error.value = '';
  try {
    const all = await integrationApi.list();
    integrations.value = (all || [])
      .filter((i) => {
        const t = (i.type || '').toLowerCase();
        return t.includes('ticket') || t.includes('jira') || t.includes('linear');
      })
      .map(rawToTicketing);
  } catch (err) {
    if (err instanceof ApiError) {
      error.value = `Failed to load ticketing integrations: ${err.message}`;
    } else {
      error.value = 'Failed to load ticketing integrations';
    }
  } finally {
    loading.value = false;
  }
}

onMounted(fetchIntegrations);

function editIntegration(id: string) {
  editingId.value = editingId.value === id ? null : id;
}

async function saveIntegration(int: TicketingIntegration) {
  isSaving.value = true;
  try {
    await integrationApi.update(int.id, ticketingToRaw(int));
    editingId.value = null;
    showToast(`${int.name} integration saved`, 'success');
  } catch (err) {
    showToast(err instanceof ApiError ? err.message : 'Failed to save integration', 'error');
  } finally {
    isSaving.value = false;
  }
}

async function toggleIntegration(int: TicketingIntegration) {
  const prev = int.enabled;
  int.enabled = !int.enabled;
  try {
    await integrationApi.update(int.id, { enabled: int.enabled });
    showToast(`${int.name} ${int.enabled ? 'enabled' : 'disabled'}`, 'success');
  } catch (err) {
    int.enabled = prev;
    showToast(err instanceof ApiError ? err.message : 'Failed to toggle integration', 'error');
  }
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

    <!-- Loading state -->
    <div v-if="loading" class="card" style="padding: 48px; text-align: center;">
      <div style="color: var(--text-tertiary); font-size: 0.875rem;">Loading ticketing integrations...</div>
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="card" style="padding: 48px; text-align: center;">
      <div style="color: #ef4444; font-size: 0.875rem; margin-bottom: 12px;">{{ error }}</div>
      <button class="btn btn-secondary" @click="fetchIntegrations">Retry</button>
    </div>

    <!-- Empty state -->
    <div v-else-if="integrations.length === 0" class="card" style="padding: 48px; text-align: center;">
      <div style="color: var(--text-tertiary); font-size: 0.875rem;">No ticketing integrations configured yet.</div>
    </div>

    <template v-else>
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
              <span class="summary-val">{{ int.project || 'Not set' }}</span>
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
    </template>
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
