<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { retentionApi } from '../services/api/retention';
import type { RetentionPolicy } from '../services/api/retention';

const showToast = useToast();

type DataCategory = 'execution_logs' | 'execution_outputs' | 'bot_memory' | 'audit_logs' | 'token_metrics';

const categoryMeta: Record<DataCategory, { label: string; icon: string; color: string }> = {
  execution_logs: { label: 'Execution Logs', icon: '📋', color: '#06b6d4' },
  execution_outputs: { label: 'Execution Outputs', icon: '📄', color: '#a78bfa' },
  bot_memory: { label: 'Bot Memory', icon: '🧠', color: '#34d399' },
  audit_logs: { label: 'Audit Logs', icon: '🔍', color: '#f59e0b' },
  token_metrics: { label: 'Token Metrics', icon: '📊', color: '#60a5fa' },
};

const policies = ref<RetentionPolicy[]>([]);
const loading = ref(false);

const showAddModal = ref(false);
const newCategory = ref<DataCategory>('execution_logs');
const newScope = ref<'global' | 'team' | 'bot'>('global');
const newScopeName = ref('All Teams');
const newDays = ref(90);
const newDeleteOnExpiry = ref(true);
const newArchiveOnExpiry = ref(false);

const totalEstimatedGB = computed(() =>
  policies.value.reduce((s, p) => s + (p.estimated_size_gb ?? 0), 0)
);
const policiesWithExpiry = computed(() => policies.value.filter(p => p.enabled));

const scopeOptions: Record<string, string[]> = {
  global: ['All Teams'],
  team: ['Security Team', 'Platform Team', 'Backend Team', 'Frontend Team'],
  bot: ['bot-security', 'bot-pr-review', 'bot-test-cov'],
};

function getCategoryMeta(category: string) {
  return categoryMeta[category as DataCategory] ?? { label: category, icon: '📁', color: '#9ca3af' };
}

async function loadPolicies() {
  loading.value = true;
  try {
    const data = await retentionApi.list();
    policies.value = data.policies;
  } catch {
    showToast('Failed to load retention policies', 'error');
  } finally {
    loading.value = false;
  }
}

function onScopeChange() {
  newScopeName.value = scopeOptions[newScope.value][0] ?? '';
}

async function toggleEnabled(policy: RetentionPolicy) {
  const newEnabled = !policy.enabled;
  try {
    await retentionApi.toggle(policy.id, Boolean(newEnabled));
    policy.enabled = newEnabled ? 1 : 0;
    showToast(`Policy ${newEnabled ? 'enabled' : 'disabled'}`, 'success');
  } catch {
    showToast('Failed to update policy', 'error');
  }
}

async function deletePolicy(id: string) {
  try {
    await retentionApi.delete(id);
    policies.value = policies.value.filter(p => p.id !== id);
    showToast('Retention policy removed', 'success');
  } catch {
    showToast('Failed to delete policy', 'error');
  }
}

async function runCleanup() {
  try {
    await retentionApi.runCleanup();
    showToast('Cleanup job queued — expired data will be removed within 5 minutes', 'success');
  } catch {
    showToast('Failed to queue cleanup job', 'error');
  }
}

async function savePolicy() {
  if (newDays.value < 1) {
    showToast('Retention period must be at least 1 day', 'error');
    return;
  }
  try {
    const created = await retentionApi.create({
      category: newCategory.value,
      scope: newScope.value,
      scope_name: newScopeName.value,
      retention_days: newDays.value,
      delete_on_expiry: newDeleteOnExpiry.value,
      archive_on_expiry: newArchiveOnExpiry.value,
      estimated_size_gb: 0,
    });
    policies.value.unshift(created);
    showAddModal.value = false;
    showToast('Retention policy added', 'success');
  } catch {
    showToast('Failed to add retention policy', 'error');
  }
}

onMounted(loadPolicies);
</script>

<template>
  <div class="data-retention">
    <AppBreadcrumb :items="[{ label: 'Admin' }, { label: 'Data Retention' }]" />

    <PageHeader
      title="Data Retention Policies"
      subtitle="Configure how long execution logs, outputs, and metrics are stored per team or bot."
    >
      <template #actions>
        <button class="btn btn-secondary" @click="runCleanup">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-4.5"/></svg>
          Run Cleanup Now
        </button>
        <button class="btn btn-primary" @click="showAddModal = true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          Add Policy
        </button>
      </template>
    </PageHeader>

    <!-- Summary cards -->
    <div class="summary-row">
      <div class="stat-card">
        <span class="stat-value">{{ policies.length }}</span>
        <span class="stat-label">Active Policies</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{{ totalEstimatedGB.toFixed(1) }} GB</span>
        <span class="stat-label">Total Managed Data</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{{ policiesWithExpiry.length }}</span>
        <span class="stat-label">Policies Enforced</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{{ Math.round(totalEstimatedGB * 0.15 * 10) / 10 }} GB</span>
        <span class="stat-label">Est. Monthly Savings</span>
      </div>
    </div>

    <!-- Policies list -->
    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
          Retention Policies
        </h3>
      </div>
      <div v-if="loading" class="empty-row">Loading...</div>
      <div v-else class="policies-table">
        <div class="table-header">
          <span>Data Category</span>
          <span>Scope</span>
          <span>Retention</span>
          <span>On Expiry</span>
          <span>Est. Size</span>
          <span>Status</span>
          <span></span>
        </div>
        <div v-for="policy in policies" :key="policy.id" class="table-row" :class="{ disabled: !policy.enabled }">
          <div class="category-cell">
            <span class="cat-icon">{{ getCategoryMeta(policy.category).icon }}</span>
            <span class="cat-label" :style="{ color: getCategoryMeta(policy.category).color }">
              {{ getCategoryMeta(policy.category).label }}
            </span>
          </div>
          <div class="scope-cell">
            <span class="scope-badge" :class="policy.scope">{{ policy.scope }}</span>
            <span class="scope-name">{{ policy.scope_name }}</span>
          </div>
          <div class="retention-cell">
            <span class="days-value">{{ policy.retention_days }}d</span>
          </div>
          <div class="expiry-cell">
            <span v-if="policy.archive_on_expiry" class="expiry-tag archive">Archive</span>
            <span v-if="policy.delete_on_expiry" class="expiry-tag delete">Delete</span>
          </div>
          <div class="size-cell">{{ (policy.estimated_size_gb ?? 0).toFixed(2) }} GB</div>
          <div class="status-cell">
            <button class="toggle-btn" :class="{ active: policy.enabled }" @click="toggleEnabled(policy)">
              {{ policy.enabled ? 'Active' : 'Off' }}
            </button>
          </div>
          <div class="actions-cell">
            <button class="icon-btn" @click="deletePolicy(policy.id)" title="Remove policy">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
            </button>
          </div>
        </div>
        <div v-if="policies.length === 0" class="empty-row">No retention policies configured.</div>
      </div>
    </div>

    <!-- Add Modal -->
    <div v-if="showAddModal" class="modal-overlay" @click.self="showAddModal = false">
      <div class="modal">
        <div class="modal-header">
          <h3>Add Retention Policy</h3>
          <button class="icon-btn" @click="showAddModal = false">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="modal-body">
          <div class="field-group">
            <label class="field-label">Data Category</label>
            <select v-model="newCategory" class="select-input">
              <option v-for="(meta, cat) in categoryMeta" :key="cat" :value="cat">{{ meta.label }}</option>
            </select>
          </div>
          <div class="field-group">
            <label class="field-label">Scope</label>
            <select v-model="newScope" class="select-input" @change="onScopeChange">
              <option value="global">Global (all teams)</option>
              <option value="team">Specific Team</option>
              <option value="bot">Specific Bot</option>
            </select>
          </div>
          <div class="field-group">
            <label class="field-label">{{ newScope === 'global' ? 'Applies to' : newScope === 'team' ? 'Team' : 'Bot' }}</label>
            <select v-model="newScopeName" class="select-input">
              <option v-for="opt in scopeOptions[newScope]" :key="opt" :value="opt">{{ opt }}</option>
            </select>
          </div>
          <div class="field-group">
            <label class="field-label">Retention Period (days)</label>
            <input v-model.number="newDays" type="number" min="1" max="3650" class="text-input" />
          </div>
          <div class="field-group">
            <label class="field-label">On Expiry Action</label>
            <div class="checkbox-row">
              <label class="check-label">
                <input v-model="newDeleteOnExpiry" type="checkbox" />
                Delete permanently
              </label>
              <label class="check-label">
                <input v-model="newArchiveOnExpiry" type="checkbox" />
                Archive to cold storage
              </label>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showAddModal = false">Cancel</button>
          <button class="btn btn-primary" @click="savePolicy">Add Policy</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.data-retention {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.summary-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.stat-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 18px 22px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-value {
  font-size: 1.6rem;
  font-weight: 700;
  color: var(--accent-cyan);
}

.stat-label {
  font-size: 0.78rem;
  color: var(--text-tertiary);
}

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }

.card-header {
  display: flex;
  align-items: center;
  padding: 18px 24px;
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

.policies-table { display: flex; flex-direction: column; }

.table-header {
  display: grid;
  grid-template-columns: 1.5fr 1.2fr 0.7fr 0.8fr 0.6fr 0.6fr 40px;
  gap: 12px;
  padding: 10px 24px;
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-default);
}

.table-row {
  display: grid;
  grid-template-columns: 1.5fr 1.2fr 0.7fr 0.8fr 0.6fr 0.6fr 40px;
  gap: 12px;
  padding: 12px 24px;
  align-items: center;
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.15s;
}

.table-row:last-child { border-bottom: none; }
.table-row:hover { background: var(--bg-tertiary); }
.table-row.disabled { opacity: 0.5; }

.category-cell { display: flex; align-items: center; gap: 8px; }

.cat-icon { font-size: 0.9rem; }

.cat-label { font-size: 0.85rem; font-weight: 500; }

.scope-cell { display: flex; flex-direction: column; gap: 2px; }

.scope-badge {
  font-size: 0.65rem;
  padding: 1px 5px;
  border-radius: 3px;
  font-weight: 600;
  text-transform: uppercase;
  width: fit-content;
}

.scope-badge.global { background: rgba(6, 182, 212, 0.1); color: var(--accent-cyan); border: 1px solid rgba(6, 182, 212, 0.2); }
.scope-badge.team { background: rgba(167, 139, 250, 0.1); color: #a78bfa; border: 1px solid rgba(167, 139, 250, 0.2); }
.scope-badge.bot { background: rgba(52, 211, 153, 0.1); color: #34d399; border: 1px solid rgba(52, 211, 153, 0.2); }

.scope-name { font-size: 0.75rem; color: var(--text-secondary); }

.days-value { font-size: 0.875rem; font-weight: 600; color: var(--text-primary); }

.expiry-cell { display: flex; gap: 4px; flex-wrap: wrap; }

.expiry-tag {
  font-size: 0.65rem;
  padding: 2px 6px;
  border-radius: 3px;
  font-weight: 500;
}

.expiry-tag.archive {
  background: rgba(96, 165, 250, 0.1);
  border: 1px solid rgba(96, 165, 250, 0.2);
  color: #60a5fa;
}

.expiry-tag.delete {
  background: rgba(248, 113, 113, 0.1);
  border: 1px solid rgba(248, 113, 113, 0.2);
  color: #f87171;
}

.size-cell { font-size: 0.8rem; color: var(--text-secondary); font-variant-numeric: tabular-nums; }

.toggle-btn {
  font-size: 0.72rem;
  padding: 4px 8px;
  border-radius: 5px;
  border: 1px solid var(--border-default);
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all 0.15s;
}

.toggle-btn.active {
  background: rgba(52, 211, 153, 0.1);
  border-color: rgba(52, 211, 153, 0.3);
  color: #34d399;
}

.actions-cell { display: flex; justify-content: center; }

.empty-row {
  padding: 40px;
  text-align: center;
  font-size: 0.875rem;
  color: var(--text-tertiary);
}

.icon-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 1px solid var(--border-default);
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.icon-btn:hover { border-color: #f87171; color: #f87171; }

.btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 8px 16px;
  border-radius: 7px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover { opacity: 0.85; }

.btn-secondary {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.btn-secondary:hover { border-color: var(--accent-cyan); }

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.modal {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  width: 480px;
  max-width: 95vw;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-default);
}

.modal-header h3 { font-size: 1rem; font-weight: 600; color: var(--text-primary); margin: 0; }

.modal-body {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 16px 24px;
  border-top: 1px solid var(--border-default);
}

.field-group { display: flex; flex-direction: column; gap: 6px; }

.field-label { font-size: 0.8rem; font-weight: 500; color: var(--text-secondary); }

.text-input, .select-input {
  padding: 9px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.text-input:focus, .select-input:focus { outline: none; border-color: var(--accent-cyan); }

.checkbox-row { display: flex; gap: 20px; }

.check-label {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 0.875rem;
  color: var(--text-secondary);
  cursor: pointer;
}

@media (max-width: 900px) {
  .summary-row { grid-template-columns: repeat(2, 1fr); }
  .table-header, .table-row { grid-template-columns: 1.5fr 1fr 0.6fr auto; }
  .table-header span:nth-child(4),
  .table-header span:nth-child(5),
  .table-row .expiry-cell,
  .table-row .size-cell { display: none; }
}
</style>
