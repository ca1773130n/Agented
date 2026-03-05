<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  created: string;
  lastUsed: string;
  permissions: string[];
}

const existingKeys = ref<ApiKey[]>([
  {
    id: 'key-1',
    name: 'CI/CD Pipeline',
    prefix: 'agnt_sk_abc1...',
    created: '2026-01-15',
    lastUsed: '2 hours ago',
    permissions: ['Read Executions', 'Trigger Bots'],
  },
  {
    id: 'key-2',
    name: 'GitHub Actions Workflow',
    prefix: 'agnt_sk_def2...',
    created: '2026-02-03',
    lastUsed: '1 day ago',
    permissions: ['Read Executions', 'Trigger Bots', 'Manage Bots'],
  },
  {
    id: 'key-3',
    name: 'Internal Scripts',
    prefix: 'agnt_sk_ghi3...',
    created: '2026-02-20',
    lastUsed: '5 days ago',
    permissions: ['Read Executions'],
  },
]);

const showCreateForm = ref(false);
const newKeyName = ref('');
const newKeyExpiry = ref('');
const newKeyPermissions = ref<Record<string, boolean>>({
  'Read Executions': false,
  'Trigger Bots': false,
  'Manage Bots': false,
  'Admin Access': false,
});
const isGenerating = ref(false);
const generatedKey = ref<string | null>(null);

const selectedPermissions = computed(() =>
  Object.entries(newKeyPermissions.value)
    .filter(([, v]) => v)
    .map(([k]) => k)
);

const canGenerate = computed(
  () => newKeyName.value.trim().length > 0 && selectedPermissions.value.length > 0
);

function openCreateForm() {
  showCreateForm.value = true;
  generatedKey.value = null;
  newKeyName.value = '';
  newKeyExpiry.value = '';
  Object.keys(newKeyPermissions.value).forEach(k => {
    newKeyPermissions.value[k] = false;
  });
}

function cancelCreate() {
  showCreateForm.value = false;
  generatedKey.value = null;
}

async function generateKey() {
  if (!canGenerate.value) return;
  isGenerating.value = true;
  await new Promise(resolve => setTimeout(resolve, 900));

  const rand = Math.random().toString(36).slice(2, 6);
  const secret = Array.from({ length: 24 }, () =>
    'abcdefghijklmnopqrstuvwxyz0123456789'.charAt(Math.floor(Math.random() * 36))
  ).join('');
  generatedKey.value = `agnt_sk_${rand}_${secret}`;

  existingKeys.value.unshift({
    id: 'key-' + Date.now(),
    name: newKeyName.value.trim(),
    prefix: `agnt_sk_${rand}...`,
    created: new Date().toISOString().slice(0, 10),
    lastUsed: 'Never',
    permissions: [...selectedPermissions.value],
  });

  isGenerating.value = false;
}

async function copyKey() {
  if (!generatedKey.value) return;
  try {
    await navigator.clipboard.writeText(generatedKey.value);
    showToast('Copied to clipboard', 'success');
  } catch {
    showToast('Failed to copy', 'error');
  }
}

function revokeKey(key: ApiKey) {
  existingKeys.value = existingKeys.value.filter(k => k.id !== key.id);
  showToast(`Key "${key.name}" revoked`, 'info');
}

const curlExample = computed(
  () => `curl -X POST https://your-agented.example.com/api/bots/bot-security/trigger \\
  -H "Authorization: Bearer agnt_sk_xxxx_yyyyyyyyyyyy" \\
  -H "Content-Type: application/json" \\
  -d '{"message": "run weekly audit"}'`
);

async function copyCurlExample() {
  try {
    await navigator.clipboard.writeText(curlExample.value);
    showToast('Copied to clipboard', 'success');
  } catch {
    showToast('Failed to copy', 'error');
  }
}
</script>

<template>
  <div class="api-keys-page">
    <AppBreadcrumb
      :items="[
        { label: 'Settings', action: () => router.push({ name: 'settings' }) },
        { label: 'API Keys' },
      ]"
    />

    <PageHeader
      title="API Keys"
      subtitle="Generate API keys for programmatic access to Agented from CI/CD pipelines, scripts, and tools."
    />

    <!-- Existing Keys -->
    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>
          </svg>
          Active API Keys
        </h3>
        <button class="btn btn-primary" @click="openCreateForm">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          Create New API Key
        </button>
      </div>

      <!-- Keys Table -->
      <div class="table-wrap">
        <table class="keys-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Key Prefix</th>
              <th>Created</th>
              <th>Last Used</th>
              <th>Permissions</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="key in existingKeys" :key="key.id" class="key-row">
              <td class="key-name">{{ key.name }}</td>
              <td class="key-prefix">
                <code>{{ key.prefix }}</code>
              </td>
              <td class="key-date">{{ key.created }}</td>
              <td class="key-last-used">{{ key.lastUsed }}</td>
              <td class="key-perms">
                <span v-for="p in key.permissions" :key="p" class="perm-tag">{{ p }}</span>
              </td>
              <td class="key-actions">
                <button class="btn btn-revoke" @click="revokeKey(key)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
                    <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                  </svg>
                  Revoke
                </button>
              </td>
            </tr>
            <tr v-if="existingKeys.length === 0">
              <td colspan="6" class="table-empty">No API keys found.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Create Form -->
    <div v-if="showCreateForm" class="card create-card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
            <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
          </svg>
          Create New API Key
        </h3>
      </div>

      <div class="form-body">
        <!-- Generated Key Banner -->
        <div v-if="generatedKey" class="generated-banner">
          <div class="banner-header">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16" style="color: #34d399; flex-shrink: 0;">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            <span class="banner-title">Your API key has been generated</span>
          </div>
          <div class="banner-warning">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
              <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            Save this key now — it will not be shown again.
          </div>
          <div class="key-display-row">
            <code class="key-display">{{ generatedKey }}</code>
            <button class="btn btn-copy" @click="copyKey">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
              </svg>
              Copy
            </button>
          </div>
          <div class="banner-done">
            <button class="btn btn-ghost-sm" @click="cancelCreate">Done</button>
          </div>
        </div>

        <!-- Form Fields -->
        <template v-else>
          <div class="form-row">
            <label class="form-label">Key Name</label>
            <input
              v-model="newKeyName"
              type="text"
              class="text-input"
              placeholder="e.g. CI/CD Pipeline, GitHub Actions"
            />
          </div>

          <div class="form-row">
            <label class="form-label">Permissions</label>
            <div class="checkboxes">
              <label
                v-for="(_, perm) in newKeyPermissions"
                :key="perm"
                class="checkbox-label"
              >
                <input
                  type="checkbox"
                  v-model="newKeyPermissions[perm]"
                  class="checkbox"
                />
                <span class="checkbox-text">{{ perm }}</span>
                <span v-if="perm === 'Admin Access'" class="perm-warn">Full access</span>
              </label>
            </div>
          </div>

          <div class="form-row">
            <label class="form-label">Expiry Date <span class="label-opt">(optional)</span></label>
            <input
              v-model="newKeyExpiry"
              type="date"
              class="text-input text-input--date"
            />
          </div>

          <div class="form-actions">
            <button class="btn btn-ghost-sm" @click="cancelCreate">Cancel</button>
            <button
              class="btn btn-primary"
              :disabled="!canGenerate || isGenerating"
              @click="generateKey"
            >
              <svg v-if="isGenerating" class="spin-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>
              </svg>
              {{ isGenerating ? 'Generating…' : 'Generate Key' }}
            </button>
          </div>
        </template>
      </div>
    </div>

    <!-- Usage Examples -->
    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
          </svg>
          Usage Examples
        </h3>
      </div>
      <div class="usage-body">
        <p class="usage-desc">
          Pass your API key in the <code class="inline-code">Authorization</code> header as a Bearer token.
        </p>
        <div class="code-block-wrap">
          <div class="code-block-header">
            <span class="code-lang">curl</span>
            <button class="btn-copy-code" @click="copyCurlExample">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
              </svg>
              Copy
            </button>
          </div>
          <pre class="code-block"><code>{{ curlExample }}</code></pre>
        </div>
        <div class="usage-note">
          Replace <code class="inline-code">agnt_sk_xxxx_yyyyyyyyyyyy</code> with your actual API key, and adjust the bot ID and message as needed.
        </div>
      </div>
    </div>

    <!-- Security Tips -->
    <div class="card">
      <div class="card-header">
        <h3>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
          </svg>
          Security Tips
        </h3>
      </div>
      <div class="tips-body">
        <div class="tip-row">
          <div class="tip-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
          </div>
          <div>
            <div class="tip-title">Never commit keys to version control</div>
            <div class="tip-desc">Store API keys in environment variables or secret managers such as GitHub Secrets, Vault, or AWS Secrets Manager.</div>
          </div>
        </div>
        <div class="tip-row">
          <div class="tip-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
          </div>
          <div>
            <div class="tip-title">Use the minimum required permissions</div>
            <div class="tip-desc">Grant only the permissions your integration actually needs. Avoid using Admin Access keys in automated pipelines.</div>
          </div>
        </div>
        <div class="tip-row">
          <div class="tip-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
              <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
            </svg>
          </div>
          <div>
            <div class="tip-title">Rotate keys regularly</div>
            <div class="tip-desc">Set expiry dates on keys and rotate them periodically. Immediately revoke any key that may have been exposed.</div>
          </div>
        </div>
        <div class="tip-row">
          <div class="tip-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
            </svg>
          </div>
          <div>
            <div class="tip-title">Monitor key usage</div>
            <div class="tip-desc">Review the "Last Used" column regularly. Revoke keys that haven't been used in a long time.</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.api-keys-page {
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

/* Table */
.table-wrap {
  overflow-x: auto;
}

.keys-table {
  width: 100%;
  border-collapse: collapse;
}

.keys-table th {
  padding: 10px 16px;
  text-align: left;
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-tertiary);
}

.key-row td {
  padding: 13px 16px;
  border-bottom: 1px solid var(--border-subtle);
  vertical-align: middle;
}

.key-row:last-child td {
  border-bottom: none;
}

.key-row:hover td {
  background: var(--bg-tertiary);
}

.key-name {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}

.key-prefix code {
  font-size: 0.78rem;
  font-family: 'Geist Mono', monospace;
  color: var(--accent-cyan);
  background: rgba(0, 212, 255, 0.07);
  padding: 3px 8px;
  border-radius: 4px;
}

.key-date,
.key-last-used {
  font-size: 0.82rem;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.key-perms {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.perm-tag {
  font-size: 0.68rem;
  font-weight: 500;
  padding: 2px 8px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.table-empty {
  text-align: center;
  padding: 32px;
  font-size: 0.875rem;
  color: var(--text-tertiary);
}

/* Create Form */
.create-card {
  border-color: var(--accent-cyan);
}

.form-body {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-label {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-secondary);
}

.label-opt {
  font-weight: 400;
  color: var(--text-muted);
}

.text-input {
  padding: 9px 13px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 7px;
  color: var(--text-primary);
  font-size: 0.875rem;
  font-family: inherit;
  transition: border-color 0.15s;
}

.text-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.text-input--date {
  color-scheme: dark;
  max-width: 220px;
}

.checkboxes {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  font-size: 0.875rem;
  color: var(--text-primary);
}

.checkbox {
  width: 16px;
  height: 16px;
  accent-color: var(--accent-cyan);
  cursor: pointer;
}

.checkbox-text {
  flex: 1;
}

.perm-warn {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 2px 7px;
  background: rgba(239, 68, 68, 0.12);
  color: #ef4444;
  border-radius: 4px;
}

.form-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  padding-top: 4px;
}

/* Generated Key Banner */
.generated-banner {
  background: rgba(52, 211, 153, 0.06);
  border: 1px solid rgba(52, 211, 153, 0.3);
  border-radius: 10px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.banner-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.banner-title {
  font-size: 0.9rem;
  font-weight: 600;
  color: #34d399;
}

.banner-warning {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 0.82rem;
  color: #f59e0b;
  background: rgba(245, 158, 11, 0.1);
  border: 1px solid rgba(245, 158, 11, 0.25);
  border-radius: 6px;
  padding: 8px 12px;
}

.key-display-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.key-display {
  flex: 1;
  font-family: 'Geist Mono', monospace;
  font-size: 0.85rem;
  color: var(--accent-cyan);
  background: var(--bg-tertiary);
  padding: 10px 14px;
  border-radius: 7px;
  border: 1px solid var(--border-default);
  word-break: break-all;
  letter-spacing: 0.03em;
}

.banner-done {
  display: flex;
  justify-content: flex-end;
}

/* Usage */
.usage-body {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.usage-desc {
  font-size: 0.875rem;
  color: var(--text-secondary);
  margin: 0;
}

.inline-code {
  font-family: 'Geist Mono', monospace;
  font-size: 0.82rem;
  background: var(--bg-tertiary);
  color: var(--accent-cyan);
  padding: 2px 6px;
  border-radius: 4px;
}

.code-block-wrap {
  border: 1px solid var(--border-default);
  border-radius: 8px;
  overflow: hidden;
}

.code-block-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-subtle);
}

.code-lang {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.code-block {
  margin: 0;
  padding: 16px 18px;
  font-family: 'Geist Mono', monospace;
  font-size: 0.78rem;
  color: var(--text-secondary);
  line-height: 1.7;
  white-space: pre;
  overflow-x: auto;
  background: var(--bg-secondary);
}

.code-block code {
  font-family: inherit;
}

.usage-note {
  font-size: 0.8rem;
  color: var(--text-muted);
}

/* Security Tips */
.tips-body {
  padding: 8px 0;
  display: flex;
  flex-direction: column;
}

.tip-row {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-subtle);
}

.tip-row:last-child {
  border-bottom: none;
}

.tip-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: rgba(0, 212, 255, 0.08);
  border-radius: 8px;
  color: var(--accent-cyan);
  flex-shrink: 0;
  margin-top: 1px;
}

.tip-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 3px;
}

.tip-desc {
  font-size: 0.82rem;
  color: var(--text-tertiary);
  line-height: 1.5;
}

/* Buttons */
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
  font-family: inherit;
}

.btn-primary {
  background: var(--accent-cyan);
  color: #000;
}

.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-revoke {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
  border: 1px solid rgba(239, 68, 68, 0.25);
  padding: 5px 11px;
  font-size: 0.78rem;
}

.btn-revoke:hover { background: rgba(239, 68, 68, 0.2); }

.btn-copy {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  white-space: nowrap;
}

.btn-copy:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }

.btn-copy-code {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: 5px;
  color: var(--text-muted);
  font-size: 0.72rem;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;
}

.btn-copy-code:hover { color: var(--accent-cyan); border-color: var(--accent-cyan); }

.btn-ghost-sm {
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  font-size: 0.82rem;
  cursor: pointer;
  padding: 7px 12px;
  border-radius: 6px;
  font-family: inherit;
  font-weight: 500;
}

.btn-ghost-sm:hover { color: var(--text-primary); background: var(--bg-tertiary); }

/* Spin animation for loading */
@keyframes spin {
  to { transform: rotate(360deg); }
}

.spin-icon {
  animation: spin 0.8s linear infinite;
}
</style>
