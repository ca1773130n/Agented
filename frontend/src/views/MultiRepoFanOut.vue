<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { triggerApi } from '../services/api';
import type { Trigger } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

interface RepoMapping {
  id: string;
  repo: string;
  bot: string;
  events: string[];
  enabled: boolean;
}

const triggers = ref<Trigger[]>([]);
const selectedTriggerId = ref('');
const newRepo = ref('');
const newBot = ref('');
const newEvents = ref<string[]>(['push', 'pull_request']);
const isTesting = ref(false);
const isSaving = ref(false);

const mappings = ref<RepoMapping[]>([
  { id: 'm1', repo: 'org/api', bot: 'bot-pr-review', events: ['pull_request'], enabled: true },
  { id: 'm2', repo: 'org/frontend', bot: 'bot-pr-review', events: ['pull_request'], enabled: true },
  { id: 'm3', repo: 'org/infra', bot: 'bot-security', events: ['push', 'pull_request'], enabled: true },
  { id: 'm4', repo: 'org/shared-libs', bot: 'bot-security', events: ['push'], enabled: false },
]);

const EVENT_OPTIONS = ['push', 'pull_request', 'release', 'tag', 'workflow_run'];

async function loadTriggers() {
  try {
    const res = await triggerApi.list();
    triggers.value = res.triggers ?? [];
    if (triggers.value.length > 0) selectedTriggerId.value = triggers.value[0].id;
  } catch {
    // Non-critical
  }
}

function addMapping() {
  if (!newRepo.value.trim() || !newBot.value.trim()) {
    showToast('Repo and bot are required', 'info');
    return;
  }
  mappings.value.push({
    id: 'm' + Date.now(),
    repo: newRepo.value.trim(),
    bot: newBot.value.trim(),
    events: [...newEvents.value],
    enabled: true,
  });
  newRepo.value = '';
  newBot.value = '';
  newEvents.value = ['push', 'pull_request'];
  showToast('Repo mapping added', 'success');
}

function removeMapping(id: string) {
  mappings.value = mappings.value.filter(m => m.id !== id);
}

function toggleMapping(m: RepoMapping) {
  m.enabled = !m.enabled;
}

function toggleEvent(event: string) {
  if (newEvents.value.includes(event)) {
    newEvents.value = newEvents.value.filter(e => e !== event);
  } else {
    newEvents.value.push(event);
  }
}

async function handleTest() {
  isTesting.value = true;
  try {
    await new Promise(resolve => setTimeout(resolve, 1200));
    const enabled = mappings.value.filter(m => m.enabled);
    showToast(`Fan-out test: ${enabled.length} mappings would be triggered`, 'success');
  } finally {
    isTesting.value = false;
  }
}

async function handleSave() {
  isSaving.value = true;
  try {
    await new Promise(resolve => setTimeout(resolve, 700));
    showToast('Fan-out configuration saved', 'success');
  } finally {
    isSaving.value = false;
  }
}

onMounted(loadTriggers);
</script>

<template>
  <div class="multi-repo">
    <AppBreadcrumb :items="[
      { label: 'Triggers', action: () => router.push({ name: 'triggers' }) },
      { label: 'Multi-Repo Fan-Out' },
    ]" />

    <PageHeader title="Multi-Repo Fan-Out" subtitle="Configure a single trigger watching multiple repos with per-repo bot routing.">
      <template #actions>
        <button class="btn btn-secondary" :disabled="isTesting" @click="handleTest">
          <svg v-if="isTesting" class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
          </svg>
          {{ isTesting ? 'Testing...' : 'Test Fan-Out' }}
        </button>
        <button class="btn btn-primary" :disabled="isSaving" @click="handleSave">
          {{ isSaving ? 'Saving...' : 'Save Configuration' }}
        </button>
      </template>
    </PageHeader>

    <div class="card trigger-card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
          </svg>
          Base Trigger
        </h3>
      </div>
      <div class="trigger-body">
        <div class="field-group">
          <label class="field-label">Select Trigger to Fan-Out</label>
          <select v-model="selectedTriggerId" class="select-input">
            <option value="">-- Select trigger --</option>
            <option v-for="t in triggers" :key="t.id" :value="t.id">{{ t.name }}</option>
          </select>
        </div>
        <div class="trigger-info">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14" style="color: var(--accent-cyan)">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 8v4l3 3"/>
          </svg>
          When this trigger fires, the payload will be routed to each matching repo's bot based on the mappings below.
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/>
            <path d="M18 9a9 9 0 0 1-9 9"/>
          </svg>
          Fan-Out Rules
        </h3>
        <span class="card-badge">{{ mappings.filter(m => m.enabled).length }} active</span>
      </div>

      <!-- Add new mapping -->
      <div class="add-mapping">
        <div class="add-row">
          <input v-model="newRepo" type="text" class="text-input" placeholder="org/repo-name" />
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16" style="color: var(--text-muted)">
            <line x1="5" y1="12" x2="19" y2="12"/>
            <polyline points="12 5 19 12 12 19"/>
          </svg>
          <input v-model="newBot" type="text" class="text-input" placeholder="bot-name" />
          <button class="btn btn-primary" @click="addMapping">Add</button>
        </div>
        <div class="event-filters">
          <span class="filter-label">Events:</span>
          <button
            v-for="ev in EVENT_OPTIONS"
            :key="ev"
            class="event-btn"
            :class="{ active: newEvents.includes(ev) }"
            @click="toggleEvent(ev)"
          >
            {{ ev }}
          </button>
        </div>
      </div>

      <div class="mappings-list">
        <div v-for="m in mappings" :key="m.id" class="mapping-row" :class="{ 'is-disabled': !m.enabled }">
          <div class="mapping-repo">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14" style="color: var(--text-tertiary)">
              <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/>
            </svg>
            <span class="repo-name">{{ m.repo }}</span>
          </div>
          <div class="mapping-arrow">→</div>
          <div class="mapping-bot">
            <span class="bot-name">{{ m.bot }}</span>
          </div>
          <div class="mapping-events">
            <span v-for="ev in m.events" :key="ev" class="event-tag">{{ ev }}</span>
          </div>
          <div class="mapping-actions">
            <label class="toggle-wrap">
              <input type="checkbox" :checked="m.enabled" class="toggle-input" @change="toggleMapping(m)" />
              <span class="toggle-track" :class="{ active: m.enabled }">
                <span class="toggle-thumb" />
              </span>
            </label>
            <button class="btn-icon-sm" @click="removeMapping(m.id)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
        </div>
        <div v-if="mappings.length === 0" class="mappings-empty">
          No fan-out rules configured. Add a repo mapping above.
        </div>
      </div>
    </div>

    <div class="card overview-card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 8v4l3 3"/>
          </svg>
          Fan-Out Overview
        </h3>
      </div>
      <div class="overview-body">
        <div class="overview-stats">
          <div class="ov-stat">
            <span class="ov-num">{{ mappings.length }}</span>
            <span class="ov-lbl">Total repos</span>
          </div>
          <div class="ov-stat">
            <span class="ov-num" style="color: #34d399">{{ mappings.filter(m => m.enabled).length }}</span>
            <span class="ov-lbl">Active</span>
          </div>
          <div class="ov-stat">
            <span class="ov-num">{{ [...new Set(mappings.map(m => m.bot))].length }}</span>
            <span class="ov-lbl">Unique bots</span>
          </div>
        </div>
        <div class="bots-summary">
          <div v-for="bot in [...new Set(mappings.map(m => m.bot))]" :key="bot" class="bot-summary-row">
            <span class="bot-sum-name">{{ bot }}</span>
            <span class="bot-sum-count">{{ mappings.filter(m => m.bot === bot && m.enabled).length }} repos</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.multi-repo {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
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

.card-header h3 svg { color: var(--accent-cyan); }

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

.trigger-body {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 0.83rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.select-input {
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
  max-width: 400px;
}

.select-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.trigger-info {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 0.83rem;
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
  padding: 10px 14px;
  border-radius: 8px;
}

.add-mapping {
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  gap: 10px;
  background: var(--bg-tertiary);
}

.add-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.text-input {
  flex: 1;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.875rem;
  font-family: monospace;
}

.text-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.event-filters {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.filter-label {
  font-size: 0.78rem;
  color: var(--text-tertiary);
  font-weight: 500;
}

.event-btn {
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 0.72rem;
  font-weight: 500;
  cursor: pointer;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
  transition: all 0.12s;
}

.event-btn.active {
  background: rgba(6, 182, 212, 0.1);
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}

.mappings-list {
  display: flex;
  flex-direction: column;
}

.mapping-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 24px;
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.1s;
}

.mapping-row:hover { background: var(--bg-tertiary); }
.mapping-row:last-child { border-bottom: none; }
.mapping-row.is-disabled { opacity: 0.5; }

.mapping-repo {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 160px;
}

.repo-name {
  font-family: monospace;
  font-size: 0.85rem;
  color: var(--text-primary);
}

.mapping-arrow {
  color: var(--text-muted);
  font-size: 1rem;
}

.mapping-bot .bot-name {
  font-family: monospace;
  font-size: 0.85rem;
  color: var(--accent-cyan);
  min-width: 140px;
  display: block;
}

.mapping-events {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  flex: 1;
}

.event-tag {
  font-size: 0.7rem;
  padding: 2px 7px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 3px;
  color: var(--text-tertiary);
}

.mapping-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.mappings-empty {
  padding: 32px 24px;
  text-align: center;
  font-size: 0.875rem;
  color: var(--text-tertiary);
}

.overview-body { padding: 20px 24px; display: flex; flex-direction: column; gap: 16px; }

.overview-stats {
  display: flex;
  gap: 32px;
}

.ov-stat {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.ov-num {
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--text-primary);
}

.ov-lbl {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.bots-summary {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.bot-summary-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.85rem;
}

.bot-sum-name { font-family: monospace; color: var(--text-primary); }
.bot-sum-count { color: var(--text-tertiary); }

.toggle-wrap {
  display: flex;
  align-items: center;
  cursor: pointer;
}

.toggle-input { display: none; }

.toggle-track {
  width: 30px;
  height: 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  display: flex;
  align-items: center;
  padding: 2px;
  transition: all 0.2s;
}

.toggle-track.active { background: rgba(6, 182, 212, 0.2); border-color: var(--accent-cyan); }

.toggle-thumb {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--text-tertiary);
  transition: all 0.2s;
}

.toggle-track.active .toggle-thumb { background: var(--accent-cyan); transform: translateX(14px); }

.btn-icon-sm {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.1s;
}

.btn-icon-sm:hover { border-color: #ef4444; color: #ef4444; }

.btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: 7px;
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-secondary {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.btn-secondary:hover:not(:disabled) { border-color: var(--accent-cyan); color: var(--text-primary); }
.btn-secondary:disabled { opacity: 0.4; cursor: not-allowed; }

.spinner { animation: spin 1s linear infinite; }

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
