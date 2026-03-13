<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';
import { secretsApi, ApiError } from '../services/api';
import type { SecretMetadata } from '../services/api';

const router = useRouter();
const showToast = useToast();

const secrets = ref<SecretMetadata[]>([]);
const isLoading = ref(true);
const loadError = ref<string | null>(null);
const vaultConfigured = ref(true);

const showAddForm = ref(false);
const newSecretName = ref('');
const newSecretValue = ref('');
const newSecretDescription = ref('');
const isAdding = ref(false);
const deletingId = ref<string | null>(null);
const copiedId = ref<string | null>(null);

const revealedValues = ref<Record<string, string>>({});
const revealingId = ref<string | null>(null);

async function loadSecrets() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const statusRes = await secretsApi.getStatus();
    vaultConfigured.value = statusRes.configured;
    if (!statusRes.configured) {
      secrets.value = [];
      return;
    }
    const data = await secretsApi.list();
    secrets.value = data.secrets;
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load secrets';
    loadError.value = message;
  } finally {
    isLoading.value = false;
  }
}

async function handleAdd() {
  if (!newSecretName.value.trim()) {
    showToast('Secret name is required', 'info');
    return;
  }
  if (!newSecretValue.value) {
    showToast('Secret value is required', 'info');
    return;
  }
  isAdding.value = true;
  try {
    const created = await secretsApi.create({
      name: newSecretName.value.toUpperCase().replace(/\s+/g, '_'),
      value: newSecretValue.value,
      description: newSecretDescription.value || undefined,
    });
    secrets.value.unshift(created);
    newSecretName.value = '';
    newSecretValue.value = '';
    newSecretDescription.value = '';
    showAddForm.value = false;
    showToast('Secret added securely', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to add secret';
    showToast(message, 'error');
  } finally {
    isAdding.value = false;
  }
}

async function handleDelete(s: SecretMetadata) {
  deletingId.value = s.id;
  try {
    await secretsApi.delete(s.id);
    secrets.value = secrets.value.filter(sec => sec.id !== s.id);
    delete revealedValues.value[s.id];
    showToast(`Secret "${s.name}" deleted`, 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to delete secret';
    showToast(message, 'error');
  } finally {
    deletingId.value = null;
  }
}

async function handleReveal(s: SecretMetadata) {
  if (revealedValues.value[s.id]) {
    delete revealedValues.value[s.id];
    return;
  }
  revealingId.value = s.id;
  try {
    const data = await secretsApi.reveal(s.id);
    revealedValues.value[s.id] = data.value;
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to reveal secret';
    showToast(message, 'error');
  } finally {
    revealingId.value = null;
  }
}

function secretRefSyntax(name: string): string {
  return `{{secrets.${name}}}`;
}

function copyRef(name: string, id: string) {
  const refStr = `{{secrets.${name}}}`;
  navigator.clipboard.writeText(refStr).then(() => {
    copiedId.value = id;
    showToast(`Copied reference: ${refStr}`, 'success');
    setTimeout(() => { copiedId.value = null; }, 2000);
  });
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return 'never';
  const d = new Date(dateStr);
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

onMounted(loadSecrets);
</script>

<template>
  <div class="secrets-vault">
    <AppBreadcrumb :items="[
      { label: 'Admin', action: () => router.push({ name: 'admin' }) },
      { label: 'Secrets Vault' },
    ]" />

    <PageHeader title="Secrets Vault" subtitle="Manage encrypted secrets used by your bots. Values are encrypted at rest and audit-logged on access.">
      <template #actions>
        <button class="btn btn-primary" @click="showAddForm = !showAddForm" :disabled="!vaultConfigured">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          Add Secret
        </button>
      </template>
    </PageHeader>

    <LoadingState v-if="isLoading" message="Loading secrets vault..." />

    <div v-else-if="loadError" class="card error-card">
      <div class="error-inner">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="32" height="32" style="color: #ef4444; opacity: 0.7">
          <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        <p>{{ loadError }}</p>
        <button class="btn btn-ghost" @click="loadSecrets">Retry</button>
      </div>
    </div>

    <div v-else-if="!vaultConfigured" class="card error-card">
      <div class="error-inner">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="32" height="32" style="color: #f59e0b; opacity: 0.7">
          <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
          <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
        <p>Secrets vault not configured. Set the <code>AGENTED_VAULT_KEYS</code> environment variable to enable encrypted secret storage.</p>
      </div>
    </div>

    <template v-else>
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
              <span class="field-hint">Value is encrypted at rest</span>
            </div>
          </div>
          <div class="field-group">
            <label class="field-label">Description <span class="field-optional">(optional)</span></label>
            <input v-model="newSecretDescription" type="text" class="text-input" placeholder="What this secret is used for..." />
          </div>
          <div class="form-actions">
            <button class="btn btn-ghost" @click="showAddForm = false">Cancel</button>
            <button class="btn btn-primary" :disabled="isAdding || !newSecretName.trim() || !newSecretValue" @click="handleAdd">
              {{ isAdding ? 'Saving...' : 'Save Secret' }}
            </button>
          </div>
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
        <div v-if="secrets.length === 0" class="list-empty">
          No secrets stored yet. Click "Add Secret" to create one.
        </div>
        <div v-else class="secrets-list">
          <div v-for="s in secrets" :key="s.id" class="secret-row">
            <div class="secret-info">
              <div class="secret-name-row">
                <span class="secret-name">{{ s.name }}</span>
                <span v-if="s.scope !== 'global'" class="scope-badge">{{ s.scope }}</span>
              </div>
              <div class="secret-meta">
                <span>Created {{ formatDate(s.created_at) }}</span>
                <template v-if="s.description">
                  <span class="meta-sep">&middot;</span>
                  <span>{{ s.description }}</span>
                </template>
                <template v-if="s.last_accessed_at">
                  <span class="meta-sep">&middot;</span>
                  <span>Last accessed: {{ formatDate(s.last_accessed_at) }}</span>
                </template>
              </div>
            </div>

            <div class="secret-value-display">
              <span v-if="revealedValues[s.id]" class="revealed-value">{{ revealedValues[s.id] }}</span>
              <span v-else class="masked-value">&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;</span>
            </div>

            <div class="secret-ref">
              <code class="ref-syntax">{{ secretRefSyntax(s.name) }}</code>
            </div>

            <div class="secret-actions">
              <button
                class="btn btn-sm btn-reveal"
                :disabled="revealingId === s.id"
                @click="handleReveal(s)"
              >
                <svg v-if="!revealedValues[s.id]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
                </svg>
                <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
                  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                  <line x1="1" y1="1" x2="23" y2="23"/>
                </svg>
                {{ revealingId === s.id ? '...' : revealedValues[s.id] ? 'Hide' : 'Reveal' }}
              </button>
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
    </template>
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

.error-card {
  padding: 48px;
}

.error-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
}

.error-inner p {
  font-size: 0.875rem;
  color: var(--text-tertiary);
  margin: 0;
}

.error-inner code {
  font-family: 'Geist Mono', monospace;
  background: var(--bg-tertiary);
  padding: 2px 6px;
  border-radius: 4px;
  color: var(--accent-cyan);
  font-size: 0.82rem;
}

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

.field-optional {
  font-weight: 400;
  color: var(--text-muted);
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

.list-empty {
  padding: 32px 24px;
  text-align: center;
  font-size: 0.875rem;
  color: var(--text-tertiary);
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

.scope-badge {
  font-size: 0.65rem;
  font-weight: 700;
  padding: 2px 6px;
  background: rgba(6, 182, 212, 0.15);
  color: var(--accent-cyan);
  border-radius: 3px;
  text-transform: uppercase;
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

.revealed-value {
  font-family: 'Geist Mono', monospace;
  font-size: 0.82rem;
  color: #34d399;
  background: rgba(52, 211, 153, 0.1);
  padding: 3px 8px;
  border-radius: 4px;
  word-break: break-all;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
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

.btn-reveal {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.btn-reveal:hover:not(:disabled) { border-color: #34d399; color: #34d399; }
.btn-reveal:disabled { opacity: 0.4; cursor: not-allowed; }

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
