<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

interface Secret {
  id: string;
  name: string;
  createdAt: string;
  lastUsed: string | null;
  rotationDue: string | null;
  usedBy: string[];
}

const secrets = ref<Secret[]>([
  { id: 'sec-1', name: 'GITHUB_TOKEN', createdAt: '2026-01-15', lastUsed: '5 minutes ago', rotationDue: null, usedBy: ['bot-pr-review', 'bot-security'] },
  { id: 'sec-2', name: 'JIRA_API_KEY', createdAt: '2026-02-01', lastUsed: '2 days ago', rotationDue: '2026-04-01', usedBy: ['bot-security'] },
  { id: 'sec-3', name: 'SLACK_WEBHOOK_URL', createdAt: '2026-01-20', lastUsed: '1 hour ago', rotationDue: null, usedBy: ['bot-pr-review', 'bot-security'] },
  { id: 'sec-4', name: 'PAGERDUTY_KEY', createdAt: '2025-12-10', lastUsed: null, rotationDue: '2026-03-10', usedBy: [] },
]);

const showAddForm = ref(false);
const newSecretName = ref('');
const newSecretValue = ref('');
const isAdding = ref(false);
const deletingId = ref<string | null>(null);
const copiedId = ref<string | null>(null);

async function handleAdd() {
  if (!newSecretName.value.trim()) {
    showToast('Secret name is required', 'info');
    return;
  }
  isAdding.value = true;
  try {
    await new Promise(resolve => setTimeout(resolve, 600));
    secrets.value.push({
      id: 'sec-' + Date.now(),
      name: newSecretName.value.toUpperCase().replace(/\s+/g, '_'),
      createdAt: new Date().toISOString().slice(0, 10),
      lastUsed: null,
      rotationDue: null,
      usedBy: [],
    });
    newSecretName.value = '';
    newSecretValue.value = '';
    showAddForm.value = false;
    showToast('Secret added securely', 'success');
  } catch {
    showToast('Failed to add secret', 'error');
  } finally {
    isAdding.value = false;
  }
}

async function handleDelete(s: Secret) {
  deletingId.value = s.id;
  try {
    await new Promise(resolve => setTimeout(resolve, 500));
    secrets.value = secrets.value.filter(sec => sec.id !== s.id);
    showToast(`Secret "${s.name}" deleted`, 'success');
  } catch {
    showToast('Failed to delete secret', 'error');
  } finally {
    deletingId.value = null;
  }
}

function secretRefSyntax(name: string): string {
  return `{{secrets.${name}}}`;
}

function copyRef(name: string, id: string) {
  const ref = `{{secrets.${name}}}`;
  navigator.clipboard.writeText(ref).then(() => {
    copiedId.value = id;
    showToast(`Copied reference: ${ref}`, 'success');
    setTimeout(() => { copiedId.value = null; }, 2000);
  });
}

function isRotationDue(s: Secret): boolean {
  if (!s.rotationDue) return false;
  return new Date(s.rotationDue) <= new Date();
}

function isRotationSoon(s: Secret): boolean {
  if (!s.rotationDue) return false;
  const due = new Date(s.rotationDue);
  const now = new Date();
  const diff = (due.getTime() - now.getTime()) / (1000 * 60 * 60 * 24);
  return diff >= 0 && diff <= 14;
}
</script>

<template>
  <div class="secrets-vault">
    <AppBreadcrumb :items="[
      { label: 'Admin', action: () => router.push({ name: 'admin' }) },
      { label: 'Secrets Vault' },
    ]" />

    <PageHeader title="Secrets Vault" subtitle="Manage encrypted secrets used by your bots. Values are never shown after creation.">
      <template #actions>
        <button class="btn btn-primary" @click="showAddForm = !showAddForm">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          Add Secret
        </button>
      </template>
    </PageHeader>

    <div v-if="showAddForm" class="card add-form">
      <div class="card-header">
        <h3>Add New Secret</h3>
        <button class="btn-icon" @click="showAddForm = false">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>
      <div class="form-body">
        <div class="form-row">
          <div class="field-group">
            <label class="field-label">Secret Name</label>
            <input v-model="newSecretName" type="text" class="text-input" placeholder="GITHUB_TOKEN" />
            <span class="field-hint">Will be uppercased and spaces replaced with underscores</span>
          </div>
          <div class="field-group">
            <label class="field-label">Secret Value</label>
            <input v-model="newSecretValue" type="password" class="text-input" placeholder="Enter secret value..." autocomplete="new-password" />
            <span class="field-hint">Value is encrypted at rest and never shown again</span>
          </div>
        </div>
        <div class="form-actions">
          <button class="btn btn-ghost" @click="showAddForm = false">Cancel</button>
          <button class="btn btn-primary" :disabled="isAdding || !newSecretName.trim()" @click="handleAdd">
            {{ isAdding ? 'Saving...' : 'Save Secret' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="secrets.filter(isRotationDue).length > 0 || secrets.filter(isRotationSoon).length > 0" class="rotation-alerts">
      <div v-for="s in secrets.filter(s => isRotationDue(s) || isRotationSoon(s))" :key="s.id" class="rotation-alert" :class="isRotationDue(s) ? 'alert-overdue' : 'alert-soon'">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
          <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
          <line x1="12" y1="9" x2="12" y2="13"/>
          <line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
        <strong>{{ s.name }}</strong>
        <span>{{ isRotationDue(s) ? 'rotation overdue' : `rotation due ${s.rotationDue}` }}</span>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
            <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
          </svg>
          Secrets
        </h3>
        <span class="card-badge">{{ secrets.length }} secrets</span>
      </div>
      <div class="secrets-list">
        <div v-for="s in secrets" :key="s.id" class="secret-row">
          <div class="secret-info">
            <div class="secret-name-row">
              <span class="secret-name">{{ s.name }}</span>
              <span v-if="isRotationDue(s)" class="badge-overdue">Overdue</span>
              <span v-else-if="isRotationSoon(s)" class="badge-soon">Due {{ s.rotationDue }}</span>
            </div>
            <div class="secret-meta">
              <span>Created {{ s.createdAt }}</span>
              <span class="meta-sep">·</span>
              <span>Last used: {{ s.lastUsed ?? 'never' }}</span>
              <template v-if="s.usedBy.length > 0">
                <span class="meta-sep">·</span>
                <span>Used by: {{ s.usedBy.join(', ') }}</span>
              </template>
            </div>
          </div>

          <div class="secret-value-display">
            <span class="masked-value">••••••••••••••••</span>
          </div>

          <div class="secret-ref">
            <code class="ref-syntax">{{ secretRefSyntax(s.name) }}</code>
          </div>

          <div class="secret-actions">
            <button
              class="btn btn-sm btn-copy"
              :class="{ copied: copiedId === s.id }"
              @click="copyRef(s.name, s.id)"
              :title="'Copy reference syntax'"
            >
              <svg v-if="copiedId !== s.id" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
              {{ copiedId === s.id ? 'Copied!' : 'Copy ref' }}
            </button>
            <button
              class="btn btn-sm btn-delete"
              :disabled="deletingId === s.id"
              @click="handleDelete(s)"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
                <polyline points="3 6 5 6 21 6"/>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
              </svg>
              {{ deletingId === s.id ? '...' : 'Delete' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.secrets-vault {
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

.add-form { }

.form-body {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
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

.field-hint {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.text-input {
  padding: 9px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.text-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.form-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}

.rotation-alerts {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rotation-alert {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  border-radius: 8px;
  font-size: 0.85rem;
}

.alert-overdue {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: #ef4444;
}

.alert-soon {
  background: rgba(245, 158, 11, 0.1);
  border: 1px solid rgba(245, 158, 11, 0.3);
  color: #f59e0b;
}

.secrets-list {
  display: flex;
  flex-direction: column;
}

.secret-row {
  display: grid;
  grid-template-columns: 1fr auto auto auto;
  gap: 16px;
  align-items: center;
  padding: 14px 24px;
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.1s;
}

.secret-row:hover { background: var(--bg-tertiary); }
.secret-row:last-child { border-bottom: none; }

.secret-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.secret-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.secret-name {
  font-family: 'Geist Mono', monospace;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
}

.badge-overdue {
  font-size: 0.65rem;
  font-weight: 700;
  padding: 2px 6px;
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
  border-radius: 3px;
  text-transform: uppercase;
}

.badge-soon {
  font-size: 0.65rem;
  font-weight: 700;
  padding: 2px 6px;
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
  border-radius: 3px;
}

.secret-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.meta-sep { opacity: 0.5; }

.secret-value-display {
  display: flex;
  align-items: center;
}

.masked-value {
  font-family: monospace;
  font-size: 1rem;
  color: var(--text-tertiary);
  letter-spacing: 0.1em;
}

.secret-ref {
  display: flex;
  align-items: center;
}

.ref-syntax {
  font-family: 'Geist Mono', monospace;
  font-size: 0.75rem;
  color: var(--accent-cyan);
  background: rgba(6, 182, 212, 0.1);
  padding: 3px 8px;
  border-radius: 4px;
  border: 1px solid rgba(6, 182, 212, 0.2);
}

.secret-actions {
  display: flex;
  gap: 8px;
}

.btn {
  display: flex;
  align-items: center;
  gap: 5px;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-primary {
  padding: 8px 16px;
  font-size: 0.875rem;
  background: var(--accent-cyan);
  color: #000;
}

.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-sm { padding: 5px 10px; font-size: 0.78rem; }

.btn-copy {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.btn-copy:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.btn-copy.copied { background: rgba(52, 211, 153, 0.1); border-color: #34d399; color: #34d399; }

.btn-delete {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-tertiary);
}

.btn-delete:hover:not(:disabled) { border-color: #ef4444; color: #ef4444; }
.btn-delete:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-ghost {
  padding: 8px 14px;
  font-size: 0.875rem;
  background: transparent;
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 8px;
}

.btn-ghost:hover { border-color: var(--accent-cyan); color: var(--text-primary); }

.btn-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
}

.btn-icon:hover { border-color: var(--accent-cyan); color: var(--text-primary); }
</style>
