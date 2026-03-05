<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const route = useRoute();
const showToast = useToast();

const botId = route.params.botId as string;
const isLoading = ref(true);
const isRollingBack = ref<string | null>(null);
const selectedVersionA = ref<string | null>(null);
const selectedVersionB = ref<string | null>(null);
const showDiff = ref(false);

interface Version {
  id: string;
  version: number;
  author: string;
  timestamp: string;
  message: string;
  changes: string[];
  config: Record<string, unknown>;
  isCurrent: boolean;
}

const versions = ref<Version[]>([]);

const MOCK_VERSIONS: Version[] = [
  {
    id: 'v5',
    version: 5,
    author: 'alice@example.com',
    timestamp: '2026-03-05T14:22:00Z',
    message: 'Improve prompt clarity for security findings',
    changes: ['Updated prompt_template', 'Changed timeout to 600s'],
    config: { name: 'Security Bot v5', timeout: 600, model: 'claude-opus-4-5' },
    isCurrent: true,
  },
  {
    id: 'v4',
    version: 4,
    author: 'bob@example.com',
    timestamp: '2026-03-04T09:15:00Z',
    message: 'Add JSON output format requirement',
    changes: ['Updated prompt_template', 'Added output_format field'],
    config: { name: 'Security Bot v4', timeout: 300, model: 'claude-opus-4-5' },
    isCurrent: false,
  },
  {
    id: 'v3',
    version: 3,
    author: 'alice@example.com',
    timestamp: '2026-03-02T16:40:00Z',
    message: 'Switch model to Opus from Sonnet',
    changes: ['Changed model from claude-sonnet-4-5 to claude-opus-4-5'],
    config: { name: 'Security Bot v3', timeout: 300, model: 'claude-opus-4-5' },
    isCurrent: false,
  },
  {
    id: 'v2',
    version: 2,
    author: 'carol@example.com',
    timestamp: '2026-02-28T11:00:00Z',
    message: 'Update trigger to include push events',
    changes: ['Added push trigger', 'Removed manual trigger'],
    config: { name: 'Security Bot v2', timeout: 300, model: 'claude-sonnet-4-5' },
    isCurrent: false,
  },
  {
    id: 'v1',
    version: 1,
    author: 'alice@example.com',
    timestamp: '2026-02-25T08:00:00Z',
    message: 'Initial version',
    changes: ['Initial creation'],
    config: { name: 'Security Bot v1', timeout: 120, model: 'claude-sonnet-4-5' },
    isCurrent: false,
  },
];

async function loadVersions() {
  try {
    await new Promise(resolve => setTimeout(resolve, 600));
    versions.value = MOCK_VERSIONS;
  } catch {
    showToast('Failed to load version history', 'error');
  } finally {
    isLoading.value = false;
  }
}

async function handleRollback(v: Version) {
  isRollingBack.value = v.id;
  try {
    await new Promise(resolve => setTimeout(resolve, 1000));
    versions.value.forEach(ver => { ver.isCurrent = ver.id === v.id; });
    showToast(`Rolled back to version ${v.version}`, 'success');
  } catch {
    showToast('Rollback failed', 'error');
  } finally {
    isRollingBack.value = null;
  }
}

function toggleSelect(v: Version) {
  if (selectedVersionA.value === v.id) {
    selectedVersionA.value = null;
    showDiff.value = false;
    return;
  }
  if (selectedVersionB.value === v.id) {
    selectedVersionB.value = null;
    showDiff.value = false;
    return;
  }
  if (!selectedVersionA.value) {
    selectedVersionA.value = v.id;
  } else if (!selectedVersionB.value) {
    selectedVersionB.value = v.id;
    showDiff.value = true;
  } else {
    selectedVersionA.value = v.id;
    selectedVersionB.value = null;
    showDiff.value = false;
  }
}

function getVersionById(id: string): Version | undefined {
  return versions.value.find(v => v.id === id);
}

function formatDate(ts: string): string {
  return new Date(ts).toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function initials(email: string): string {
  return email.split('@')[0].split(/[._-]/).map(p => p[0].toUpperCase()).slice(0, 2).join('');
}

onMounted(loadVersions);
</script>

<template>
  <div class="version-history">
    <AppBreadcrumb :items="[
      { label: 'Bots', action: () => router.push({ name: 'bots' }) },
      { label: botId || 'Bot', action: () => router.push({ name: 'bot-detail', params: { botId } }) },
      { label: 'Version History' },
    ]" />

    <PageHeader
      :title="`Version History`"
      :subtitle="`Configuration history for bot: ${botId}`"
    />

    <LoadingState v-if="isLoading" message="Loading version history..." />

    <template v-else>
      <div v-if="selectedVersionA && selectedVersionB && showDiff" class="card diff-card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <line x1="5" y1="12" x2="19" y2="12"/>
              <polyline points="12 5 19 12 12 19"/>
            </svg>
            Diff: v{{ getVersionById(selectedVersionA)?.version }} → v{{ getVersionById(selectedVersionB)?.version }}
          </h3>
          <button class="btn-icon" @click="showDiff = false; selectedVersionA = null; selectedVersionB = null">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="diff-body">
          <div class="diff-cols">
            <div class="diff-col">
              <div class="diff-col-label">v{{ getVersionById(selectedVersionA)?.version }}</div>
              <pre class="diff-pre">{{ JSON.stringify(getVersionById(selectedVersionA)?.config, null, 2) }}</pre>
            </div>
            <div class="diff-col">
              <div class="diff-col-label">v{{ getVersionById(selectedVersionB)?.version }}</div>
              <pre class="diff-pre">{{ JSON.stringify(getVersionById(selectedVersionB)?.config, null, 2) }}</pre>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12 6 12 12 16 14"/>
            </svg>
            Versions
          </h3>
          <span class="card-hint">Click two versions to compare</span>
        </div>
        <div class="version-list">
          <div
            v-for="v in versions"
            :key="v.id"
            class="version-row"
            :class="{
              'is-current': v.isCurrent,
              'is-selected-a': selectedVersionA === v.id,
              'is-selected-b': selectedVersionB === v.id,
            }"
          >
            <div class="version-selector" @click="toggleSelect(v)">
              <span class="version-num">v{{ v.version }}</span>
              <span v-if="v.isCurrent" class="current-badge">Current</span>
              <span v-if="selectedVersionA === v.id" class="sel-badge sel-a">A</span>
              <span v-if="selectedVersionB === v.id" class="sel-badge sel-b">B</span>
            </div>

            <div class="version-meta">
              <span class="author-avatar">{{ initials(v.author) }}</span>
              <div class="version-info">
                <span class="version-message">{{ v.message }}</span>
                <div class="version-details">
                  <span class="detail-author">{{ v.author }}</span>
                  <span class="detail-sep">·</span>
                  <span class="detail-date">{{ formatDate(v.timestamp) }}</span>
                </div>
              </div>
            </div>

            <div class="version-changes">
              <span v-for="ch in v.changes" :key="ch" class="change-tag">{{ ch }}</span>
            </div>

            <div class="version-actions">
              <button
                v-if="!v.isCurrent"
                class="btn btn-rollback"
                :disabled="isRollingBack === v.id"
                @click="handleRollback(v)"
              >
                <svg v-if="isRollingBack === v.id" class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                  <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
                </svg>
                {{ isRollingBack === v.id ? '...' : 'Rollback' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.version-history {
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

.card-hint {
  font-size: 0.78rem;
  color: var(--text-tertiary);
}

.version-list {
  display: flex;
  flex-direction: column;
}

.version-row {
  display: grid;
  grid-template-columns: 80px 1fr 1fr auto;
  gap: 16px;
  align-items: center;
  padding: 14px 24px;
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.1s;
}

.version-row:hover { background: var(--bg-tertiary); }
.version-row:last-child { border-bottom: none; }
.version-row.is-current { background: rgba(52, 211, 153, 0.04); }
.version-row.is-selected-a { background: rgba(6, 182, 212, 0.06); }
.version-row.is-selected-b { background: rgba(139, 92, 246, 0.06); }

.version-selector {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.version-num {
  font-family: monospace;
  font-size: 0.9rem;
  font-weight: 700;
  color: var(--text-primary);
}

.current-badge {
  font-size: 0.65rem;
  font-weight: 700;
  padding: 2px 6px;
  background: rgba(52, 211, 153, 0.2);
  color: #34d399;
  border-radius: 3px;
  text-transform: uppercase;
}

.sel-badge {
  font-size: 0.65rem;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 3px;
}

.sel-a { background: rgba(6, 182, 212, 0.2); color: var(--accent-cyan); }
.sel-b { background: rgba(139, 92, 246, 0.2); color: #a78bfa; }

.version-meta {
  display: flex;
  align-items: center;
  gap: 12px;
}

.author-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--bg-elevated);
  border: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.65rem;
  font-weight: 700;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.version-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.version-message {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-primary);
}

.version-details {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

.detail-sep { opacity: 0.5; }

.version-changes {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.change-tag {
  font-size: 0.7rem;
  padding: 2px 8px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  color: var(--text-tertiary);
}

.version-actions {
  display: flex;
  justify-content: flex-end;
}

.btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-rollback {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.btn-rollback:hover:not(:disabled) { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.btn-rollback:disabled { opacity: 0.4; cursor: not-allowed; }

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
  transition: all 0.15s;
}

.btn-icon:hover { border-color: var(--accent-cyan); color: var(--text-primary); }

.diff-card { }

.diff-body { padding: 24px; }

.diff-cols {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.diff-col {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.diff-col-label {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.diff-pre {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 16px;
  font-family: 'Geist Mono', monospace;
  font-size: 0.78rem;
  color: var(--text-secondary);
  overflow: auto;
  max-height: 300px;
  white-space: pre-wrap;
  margin: 0;
}

.spinner { animation: spin 1s linear infinite; }

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@media (max-width: 900px) {
  .version-row { grid-template-columns: 1fr; }
  .diff-cols { grid-template-columns: 1fr; }
}
</style>
