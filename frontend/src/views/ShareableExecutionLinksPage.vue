<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import type { Execution } from '../services/api';
import { executionApi, ApiError } from '../services/api';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

const executions = ref<Execution[]>([]);
const selectedExecId = ref('');
const shareScope = ref<'org' | 'public'>('org');
const expiryHours = ref(24);
const generatedLink = ref('');
const isLoading = ref(true);
const isGenerating = ref(false);
const copied = ref(false);

interface ShareLink {
  id: string;
  execution_id: string;
  url: string;
  scope: 'org' | 'public';
  expires_at: string;
  created_at: string;
  views: number;
}

const existingLinks = ref<ShareLink[]>([]);

const selectedExec = computed(() => executions.value.find(e => e.execution_id === selectedExecId.value));

const expiryOptions = [
  { value: 1, label: '1 hour' },
  { value: 4, label: '4 hours' },
  { value: 24, label: '24 hours' },
  { value: 72, label: '3 days' },
  { value: 168, label: '7 days' },
];

function generateLinkId(): string {
  return Math.random().toString(36).slice(2, 10);
}

async function handleGenerate() {
  if (!selectedExecId.value) return;
  isGenerating.value = true;
  try {
    await new Promise(r => setTimeout(r, 600));
    const linkId = generateLinkId();
    const baseUrl = window.location.origin;
    const link = `${baseUrl}/share/execution/${linkId}`;
    generatedLink.value = link;

    const expiresAt = new Date(Date.now() + expiryHours.value * 3600 * 1000).toISOString();
    existingLinks.value.unshift({
      id: linkId,
      execution_id: selectedExecId.value,
      url: link,
      scope: shareScope.value,
      expires_at: expiresAt,
      created_at: new Date().toISOString(),
      views: 0,
    });
    showToast('Shareable link generated', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to generate link';
    showToast(message, 'error');
  } finally {
    isGenerating.value = false;
  }
}

async function copyLink(url: string) {
  try {
    await navigator.clipboard.writeText(url);
    copied.value = true;
    showToast('Link copied to clipboard', 'success');
    setTimeout(() => { copied.value = false; }, 2000);
  } catch {
    showToast('Could not copy to clipboard', 'error');
  }
}

function revokeLink(id: string) {
  existingLinks.value = existingLinks.value.filter(l => l.id !== id);
  if (generatedLink.value.includes(id)) generatedLink.value = '';
  showToast('Link revoked', 'success');
}

function isExpired(expiresAt: string): boolean {
  return new Date(expiresAt) < new Date();
}

function formatExpiry(expiresAt: string): string {
  const diff = new Date(expiresAt).getTime() - Date.now();
  if (diff < 0) return 'Expired';
  const hours = Math.floor(diff / 3600000);
  const mins = Math.floor((diff % 3600000) / 60000);
  if (hours > 24) return `${Math.floor(hours / 24)}d remaining`;
  if (hours > 0) return `${hours}h ${mins}m remaining`;
  return `${mins}m remaining`;
}

function formatDate(d: string): string {
  return new Date(d).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function statusClass(status: string): string {
  const map: Record<string, string> = { success: 'tag-success', failed: 'tag-failed', running: 'tag-running' };
  return map[status] ?? 'tag-idle';
}

async function loadExecutions() {
  try {
    const res = await executionApi.listAll({ limit: 50 });
    executions.value = res.executions ?? [];
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load executions';
    showToast(message, 'error');
  } finally {
    isLoading.value = false;
  }
}

onMounted(loadExecutions);
</script>

<template>
  <div class="share-page">

    <PageHeader
      title="Shareable Execution Live Links"
      subtitle="Generate time-limited links to share in-progress or completed execution streams with teammates."
    />

    <LoadingState v-if="isLoading" message="Loading executions..." />

    <template v-else>
      <div class="layout">
        <div class="main-col">
          <!-- Generator card -->
          <div class="card">
            <div class="card-header">
              <h3>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
                  <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
                  <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
                </svg>
                Generate Share Link
              </h3>
            </div>
            <div class="form-body">
              <div class="field">
                <label class="field-label">Execution</label>
                <select v-model="selectedExecId" class="select-input">
                  <option value="">-- Select an execution --</option>
                  <option v-for="ex in executions.slice(0, 30)" :key="ex.execution_id" :value="ex.execution_id">
                    {{ ex.execution_id.slice(0, 12) }} — {{ ex.status }} — {{ formatDate(ex.started_at) }}
                  </option>
                </select>
              </div>

              <div v-if="selectedExec" class="exec-preview">
                <div class="exec-preview-row">
                  <span class="exec-preview-id">{{ selectedExec.execution_id.slice(0, 20) }}...</span>
                  <span :class="['exec-tag', statusClass(selectedExec.status)]">{{ selectedExec.status }}</span>
                </div>
                <div class="exec-preview-meta">Started {{ formatDate(selectedExec.started_at) }}</div>
              </div>

              <div class="field-row">
                <div class="field">
                  <label class="field-label">Access Scope</label>
                  <div class="scope-selector">
                    <button
                      :class="['scope-btn', { active: shareScope === 'org' }]"
                      @click="shareScope = 'org'"
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>
                        <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>
                      </svg>
                      Org-scoped
                    </button>
                    <button
                      :class="['scope-btn', { active: shareScope === 'public' }]"
                      @click="shareScope = 'public'"
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                        <circle cx="12" cy="12" r="10"/>
                        <line x1="2" y1="12" x2="22" y2="12"/>
                        <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
                      </svg>
                      Public
                    </button>
                  </div>
                  <p v-if="shareScope === 'public'" class="scope-warning">Anyone with the link can view this execution.</p>
                </div>
                <div class="field">
                  <label class="field-label">Expires After</label>
                  <select v-model="expiryHours" class="select-input">
                    <option v-for="o in expiryOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
                  </select>
                </div>
              </div>

              <button
                class="btn btn-primary"
                :disabled="!selectedExecId || isGenerating"
                @click="handleGenerate"
              >
                <svg v-if="isGenerating" class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                  <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
                </svg>
                <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14">
                  <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
                  <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
                </svg>
                {{ isGenerating ? 'Generating...' : 'Generate Link' }}
              </button>

              <!-- Result -->
              <div v-if="generatedLink" class="link-result">
                <div class="link-label">Shareable Link</div>
                <div class="link-row">
                  <input type="text" :value="generatedLink" readonly class="link-input" />
                  <button class="btn btn-secondary btn-sm" @click="copyLink(generatedLink)">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                      <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                    </svg>
                    {{ copied ? 'Copied!' : 'Copy' }}
                  </button>
                </div>
                <p class="link-note">Share this link in Slack to let teammates watch the execution in real time.</p>
              </div>
            </div>
          </div>

          <!-- Existing links -->
          <div v-if="existingLinks.length > 0" class="card">
            <div class="card-header">
              <h3>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
                  <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
                </svg>
                Active Links
              </h3>
              <span class="card-badge">{{ existingLinks.filter(l => !isExpired(l.expires_at)).length }} active</span>
            </div>
            <div class="links-list">
              <div v-for="link in existingLinks" :key="link.id" class="link-row-item" :class="{ expired: isExpired(link.expires_at) }">
                <div class="link-row-info">
                  <div class="link-url">{{ link.url }}</div>
                  <div class="link-meta">
                    <span :class="['scope-badge', `scope-${link.scope}`]">{{ link.scope }}</span>
                    <span class="meta-dot">·</span>
                    <span :class="['expiry-text', { 'text-expired': isExpired(link.expires_at) }]">{{ formatExpiry(link.expires_at) }}</span>
                    <span class="meta-dot">·</span>
                    <span class="views-count">{{ link.views }} views</span>
                  </div>
                </div>
                <div class="link-row-actions">
                  <button class="btn btn-secondary btn-xs" @click="copyLink(link.url)">Copy</button>
                  <button class="btn btn-danger btn-xs" @click="revokeLink(link.id)">Revoke</button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Info sidebar -->
        <div class="side-col">
          <div class="card info-card">
            <div class="card-header">
              <h3>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
                  <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
                Usage Guide
              </h3>
            </div>
            <div class="info-body">
              <div class="use-case">
                <div class="use-case-title">During debugging</div>
                <p>Generate a link while a bot is running and paste it in Slack — teammates see the live log stream without needing platform access.</p>
              </div>
              <div class="use-case">
                <div class="use-case-title">Async review</div>
                <p>Share completed execution output for async review by leads or security reviewers who don't have a dashboard account.</p>
              </div>
              <div class="use-case">
                <div class="use-case-title">Incident postmortem</div>
                <p>Preserve a time-limited link to a failed execution for postmortem documentation.</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.share-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.35s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.layout {
  display: grid;
  grid-template-columns: 1fr 300px;
  gap: 20px;
  align-items: start;
}

.main-col, .side-col { display: flex; flex-direction: column; gap: 16px; }

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
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-header h3 svg { color: var(--accent-cyan); }

.card-badge {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-tertiary);
  padding: 3px 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
}

.form-body {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.field { display: flex; flex-direction: column; gap: 6px; }
.field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }

.field-label { font-size: 0.8rem; font-weight: 500; color: var(--text-secondary); }

.select-input {
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
  cursor: pointer;
}

.exec-preview {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 12px 14px;
}

.exec-preview-row { display: flex; align-items: center; gap: 8px; }
.exec-preview-id { font-family: 'Geist Mono', monospace; font-size: 0.78rem; color: var(--text-secondary); }
.exec-preview-meta { font-size: 0.75rem; color: var(--text-tertiary); margin-top: 4px; }

.exec-tag {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
}

.tag-success { background: rgba(52, 211, 153, 0.15); color: #34d399; }
.tag-failed { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.tag-running { background: rgba(59, 130, 246, 0.15); color: #3b82f6; }
.tag-idle { background: rgba(156, 163, 175, 0.1); color: #6b7280; }

.scope-selector { display: flex; gap: 8px; }

.scope-btn {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
  transition: all 0.15s;
  flex: 1;
  justify-content: center;
}

.scope-btn.active { border-color: var(--accent-cyan); color: var(--accent-cyan); background: rgba(6, 182, 212, 0.08); }

.scope-warning { font-size: 0.75rem; color: #f59e0b; margin: 0; }

.btn {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
  align-self: flex-start;
}

.btn-sm { padding: 6px 12px; font-size: 0.8rem; }
.btn-xs { padding: 4px 10px; font-size: 0.75rem; }

.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-secondary { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-secondary:hover { border-color: var(--accent-cyan); color: var(--text-primary); }

.btn-danger { background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); color: #ef4444; }
.btn-danger:hover { background: rgba(239, 68, 68, 0.2); }

.link-result {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.link-label { font-size: 0.78rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.05em; }

.link-row { display: flex; gap: 8px; align-items: center; }

.link-input {
  flex: 1;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--accent-cyan);
  font-family: 'Geist Mono', monospace;
  font-size: 0.78rem;
  min-width: 0;
}

.link-note { font-size: 0.75rem; color: var(--text-tertiary); margin: 0; }

.links-list { display: flex; flex-direction: column; }

.link-row-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.1s;
}

.link-row-item:last-child { border-bottom: none; }
.link-row-item:hover { background: var(--bg-tertiary); }
.link-row-item.expired { opacity: 0.5; }

.link-row-info { flex: 1; min-width: 0; }

.link-url {
  font-family: 'Geist Mono', monospace;
  font-size: 0.75rem;
  color: var(--accent-cyan);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.link-meta { display: flex; align-items: center; gap: 6px; margin-top: 4px; }

.scope-badge {
  font-size: 0.68rem;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 4px;
  text-transform: uppercase;
}

.scope-org { background: rgba(99, 102, 241, 0.15); color: #818cf8; }
.scope-public { background: rgba(245, 158, 11, 0.15); color: #fbbf24; }

.meta-dot { color: var(--text-tertiary); font-size: 0.7rem; }
.expiry-text { font-size: 0.75rem; color: var(--text-tertiary); }
.text-expired { color: #ef4444; }
.views-count { font-size: 0.75rem; color: var(--text-tertiary); }

.link-row-actions { display: flex; gap: 6px; flex-shrink: 0; }

.info-body { padding: 16px 20px; display: flex; flex-direction: column; gap: 14px; }

.use-case-title { font-size: 0.82rem; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }

.use-case p { font-size: 0.78rem; color: var(--text-secondary); margin: 0; line-height: 1.5; }

.spinner { animation: spin 1s linear infinite; }

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (max-width: 900px) {
  .layout { grid-template-columns: 1fr; }
  .field-row { grid-template-columns: 1fr; }
}
</style>
