<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { triggerApi, ApiError } from '../services/api';
import type { Trigger, PromptHistoryEntry } from '../services/api';

const router = useRouter();
const route = useRoute();
const showToast = useToast();

const botId = computed(() => (route.params.botId as string) || '');

// Trigger selection for when no botId is in the route
const triggers = ref<Trigger[]>([]);
const selectedTriggerId = ref('');
const isLoadingTriggers = ref(false);
const triggerLoadError = ref('');

interface PromptVersion {
  id: number;
  version: number;
  author: string;
  timestamp: string;
  message: string;
  prompt: string;
  tokensEstimate: number;
  tag?: string;
}

const versions = ref<PromptVersion[]>([]);
const isLoadingHistory = ref(false);
const historyError = ref('');

const selectedLeft = ref<string>('');
const selectedRight = ref<string>('');
const activeTab = ref<'list' | 'diff'>('list');
const isRollingBack = ref(false);

const leftVersion = computed(() => versions.value.find(v => String(v.id) === selectedLeft.value));
const rightVersion = computed(() => versions.value.find(v => String(v.id) === selectedRight.value));

const activeTrigId = computed(() => botId.value || selectedTriggerId.value);

onMounted(async () => {
  if (botId.value) {
    await loadHistory(botId.value);
  } else {
    await loadTriggers();
  }
});

async function loadTriggers() {
  isLoadingTriggers.value = true;
  triggerLoadError.value = '';
  try {
    const res = await triggerApi.list();
    triggers.value = res.triggers;
  } catch (e) {
    triggerLoadError.value = e instanceof ApiError ? e.message : 'Failed to load triggers';
  } finally {
    isLoadingTriggers.value = false;
  }
}

watch(selectedTriggerId, async (newId) => {
  if (newId) await loadHistory(newId);
});

async function loadHistory(triggerId: string) {
  isLoadingHistory.value = true;
  historyError.value = '';
  versions.value = [];
  try {
    const res = await triggerApi.getPromptHistory(triggerId);
    const history = res.history || [];

    // Also fetch the current trigger to show the current prompt
    const currentTrigger = await triggerApi.get(triggerId);

    // Build version list from history entries
    const versionList: PromptVersion[] = [];

    // Current version is always first
    versionList.push({
      id: 0, // special id for current
      version: history.length + 1,
      author: 'current',
      timestamp: currentTrigger.created_at || new Date().toISOString(),
      message: 'Current active version',
      prompt: currentTrigger.prompt_template || '',
      tokensEstimate: Math.round((currentTrigger.prompt_template || '').split(/\s+/).length * 1.3),
      tag: 'current',
    });

    // History entries (most recent first)
    history.forEach((entry: PromptHistoryEntry, idx: number) => {
      versionList.push({
        id: entry.id,
        version: history.length - idx,
        author: entry.author || 'unknown',
        timestamp: entry.changed_at,
        message: entry.diff_text ? `Changed: ${entry.diff_text.substring(0, 60)}...` : 'Prompt updated',
        prompt: entry.old_template,
        tokensEstimate: Math.round((entry.old_template || '').split(/\s+/).length * 1.3),
      });
    });

    versions.value = versionList;

    if (versionList.length >= 2) {
      selectedRight.value = String(versionList[0].id);
      selectedLeft.value = String(versionList[1].id);
    } else if (versionList.length === 1) {
      selectedRight.value = String(versionList[0].id);
      selectedLeft.value = String(versionList[0].id);
    }
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) {
      historyError.value = 'No prompt history found for this trigger.';
    } else {
      historyError.value = e instanceof ApiError ? e.message : 'Failed to load prompt history';
    }
  } finally {
    isLoadingHistory.value = false;
  }
}

interface DiffLine {
  type: 'added' | 'removed' | 'unchanged';
  content: string;
  leftLineNo?: number;
  rightLineNo?: number;
}

const diffLines = computed((): DiffLine[] => {
  if (!leftVersion.value || !rightVersion.value) return [];
  const leftLines = leftVersion.value.prompt.split('\n');
  const rightLines = rightVersion.value.prompt.split('\n');

  const result: DiffLine[] = [];
  let li = 0;
  let ri = 0;

  while (li < leftLines.length || ri < rightLines.length) {
    const l = leftLines[li];
    const r = rightLines[ri];

    if (l === undefined) {
      result.push({ type: 'added', content: r, rightLineNo: ri + 1 });
      ri++;
    } else if (r === undefined) {
      result.push({ type: 'removed', content: l, leftLineNo: li + 1 });
      li++;
    } else if (l === r) {
      result.push({ type: 'unchanged', content: l, leftLineNo: li + 1, rightLineNo: ri + 1 });
      li++;
      ri++;
    } else {
      result.push({ type: 'removed', content: l, leftLineNo: li + 1 });
      result.push({ type: 'added', content: r, rightLineNo: ri + 1 });
      li++;
      ri++;
    }
  }

  return result;
});

const addedCount = computed(() => diffLines.value.filter(l => l.type === 'added').length);
const removedCount = computed(() => diffLines.value.filter(l => l.type === 'removed').length);

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

function selectForDiff(versionId: number) {
  if (String(versionId) === selectedRight.value) return;
  selectedLeft.value = String(versionId);
  activeTab.value = 'diff';
}

async function rollbackTo(v: PromptVersion) {
  if (!activeTrigId.value) return;
  isRollingBack.value = true;
  try {
    if (v.id > 0) {
      await triggerApi.rollbackPrompt(activeTrigId.value, v.id);
    } else {
      // Rollback to current version doesn't make sense
      showToast('Already on current version', 'info');
      isRollingBack.value = false;
      return;
    }
    showToast(`Rolled back to v${v.version}. Prompt has been restored.`, 'success');
    activeTab.value = 'list';
    await loadHistory(activeTrigId.value);
  } catch (e) {
    showToast(e instanceof ApiError ? e.message : 'Rollback failed', 'error');
  } finally {
    isRollingBack.value = false;
  }
}
</script>

<template>
  <div class="prompt-version-history">

    <PageHeader
      title="Prompt Template Version History"
      subtitle="Every change to this bot's prompt template — with diffs, authors, and one-click rollback."
    />

    <!-- Trigger selector (when no botId in route) -->
    <div v-if="!botId">
      <div v-if="isLoadingTriggers" class="loading-msg">Loading triggers...</div>
      <div v-else-if="triggerLoadError" class="error-msg">{{ triggerLoadError }}</div>
      <div v-else class="trigger-selector">
        <label class="selector-label">Select Trigger:</label>
        <select v-model="selectedTriggerId" class="trigger-select">
          <option value="">Choose a trigger...</option>
          <option v-for="t in triggers" :key="t.id" :value="t.id">{{ t.name }} ({{ t.id }})</option>
        </select>
      </div>
    </div>

    <div v-if="isLoadingHistory" class="loading-msg">Loading prompt history...</div>
    <div v-else-if="historyError" class="error-msg">{{ historyError }}</div>
    <div v-else-if="versions.length === 0 && activeTrigId" class="empty-msg">No prompt history found for this trigger.</div>
    <div v-else-if="versions.length === 0 && !activeTrigId" class="empty-msg">Select a trigger to view its prompt history.</div>

    <template v-if="versions.length > 0">
      <div class="tab-row">
        <button class="tab-btn" :class="{ active: activeTab === 'list' }" @click="activeTab = 'list'">
          Version List
        </button>
        <button class="tab-btn" :class="{ active: activeTab === 'diff' }" @click="activeTab = 'diff'">
          Diff View
          <span v-if="addedCount || removedCount" class="diff-badge">
            <span class="added-badge">+{{ addedCount }}</span>
            <span class="removed-badge">-{{ removedCount }}</span>
          </span>
        </button>
      </div>

      <!-- Version list -->
      <div v-if="activeTab === 'list'" class="version-list card">
        <div
          v-for="v in versions"
          :key="v.id"
          class="version-row"
          :class="{ current: v.tag === 'current' }"
        >
          <div class="version-meta">
            <div class="version-number">v{{ v.version }}</div>
            <div v-if="v.tag" class="tag-badge tag-current">{{ v.tag }}</div>
          </div>
          <div class="version-info">
            <div class="version-message">{{ v.message }}</div>
            <div class="version-details">
              <span class="author">{{ v.author }}</span>
              <span class="sep">·</span>
              <span class="date">{{ fmtDate(v.timestamp) }}</span>
              <span class="sep">·</span>
              <span class="tokens">~{{ v.tokensEstimate }} tokens</span>
            </div>
          </div>
          <div class="version-actions">
            <button class="btn btn-xs btn-ghost" @click="selectForDiff(v.id)">
              Diff vs current
            </button>
            <button
              v-if="v.tag !== 'current'"
              class="btn btn-xs btn-ghost"
              :disabled="isRollingBack"
              @click="rollbackTo(v)"
            >
              Rollback
            </button>
            <button class="btn btn-xs btn-ghost" @click="activeTab = 'diff'; selectedLeft = String(v.id)">
              View
            </button>
          </div>
        </div>
      </div>

      <!-- Diff view -->
      <div v-else class="diff-view">
        <div class="diff-controls card">
          <div class="diff-select-row">
            <div class="diff-select-group">
              <label class="diff-label">Base (older)</label>
              <select v-model="selectedLeft" class="select">
                <option v-for="v in versions" :key="v.id" :value="String(v.id)">
                  v{{ v.version }} — {{ v.message }}
                </option>
              </select>
            </div>
            <div class="diff-arrow">&rarr;</div>
            <div class="diff-select-group">
              <label class="diff-label">Compare (newer)</label>
              <select v-model="selectedRight" class="select">
                <option v-for="v in versions" :key="v.id" :value="String(v.id)">
                  v{{ v.version }} — {{ v.message }}
                </option>
              </select>
            </div>
          </div>
          <div class="diff-summary">
            <span class="added-badge">+{{ addedCount }} added</span>
            <span class="removed-badge">-{{ removedCount }} removed</span>
          </div>
        </div>

        <div class="diff-panel card">
          <div class="diff-header">
            <div class="diff-col-header">
              <span class="diff-col-label">v{{ leftVersion?.version }} — {{ leftVersion?.message }}</span>
              <span class="diff-col-meta">{{ leftVersion ? fmtDate(leftVersion.timestamp) : '' }}</span>
            </div>
            <div class="diff-col-header">
              <span class="diff-col-label">v{{ rightVersion?.version }} — {{ rightVersion?.message }}</span>
              <span class="diff-col-meta">{{ rightVersion ? fmtDate(rightVersion.timestamp) : '' }}</span>
            </div>
          </div>
          <div class="diff-lines">
            <div
              v-for="(line, i) in diffLines"
              :key="i"
              class="diff-line"
              :class="line.type"
            >
              <span class="line-no">{{ line.type === 'removed' ? line.leftLineNo : line.type === 'added' ? line.rightLineNo : line.leftLineNo }}</span>
              <span class="line-prefix">{{ line.type === 'added' ? '+' : line.type === 'removed' ? '-' : ' ' }}</span>
              <span class="line-content">{{ line.content }}</span>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.prompt-version-history { display: flex; flex-direction: column; gap: 20px; animation: fadeIn 0.3s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

.loading-msg { font-size: 0.82rem; color: var(--text-tertiary); padding: 12px 0; }
.error-msg { font-size: 0.82rem; color: #ef4444; padding: 12px 0; }
.empty-msg { font-size: 0.82rem; color: var(--text-muted); padding: 24px 0; text-align: center; }

.trigger-selector { display: flex; align-items: center; gap: 12px; }
.selector-label { font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); }
.trigger-select { flex: 1; max-width: 400px; padding: 8px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.82rem; }

.tab-row { display: flex; gap: 4px; border-bottom: 1px solid var(--border-default); padding-bottom: 0; }
.tab-btn { padding: 8px 18px; font-size: 0.875rem; background: none; border: none; color: var(--text-secondary); cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -1px; transition: color 0.15s; display: flex; align-items: center; gap: 8px; }
.tab-btn:hover { color: var(--text-primary); }
.tab-btn.active { color: var(--accent-cyan); border-bottom-color: var(--accent-cyan); }

.diff-badge { display: flex; gap: 4px; }
.added-badge { font-size: 0.72rem; font-weight: 700; color: #34d399; background: rgba(52,211,153,0.12); padding: 1px 6px; border-radius: 4px; }
.removed-badge { font-size: 0.72rem; font-weight: 700; color: #f87171; background: rgba(248,113,113,0.12); padding: 1px 6px; border-radius: 4px; }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 10px; overflow: hidden; }

/* Version list */
.version-list { }
.version-row { display: flex; align-items: center; gap: 16px; padding: 16px 20px; border-bottom: 1px solid var(--border-default); transition: background 0.1s; }
.version-row:last-child { border-bottom: none; }
.version-row:hover { background: var(--bg-tertiary); }
.version-row.current { background: rgba(6,182,212,0.04); }

.version-meta { display: flex; flex-direction: column; align-items: center; gap: 4px; min-width: 52px; }
.version-number { font-size: 0.82rem; font-weight: 700; color: var(--text-secondary); font-family: monospace; }
.tag-badge { font-size: 0.65rem; font-weight: 600; text-transform: uppercase; padding: 2px 6px; border-radius: 4px; }
.tag-current { background: rgba(6,182,212,0.15); color: var(--accent-cyan); }

.version-info { flex: 1; min-width: 0; }
.version-message { font-size: 0.875rem; font-weight: 500; color: var(--text-primary); margin-bottom: 3px; }
.version-details { font-size: 0.78rem; color: var(--text-tertiary); display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.sep { color: var(--border-default); }

.version-actions { display: flex; gap: 6px; }
.btn { padding: 7px 14px; border-radius: 7px; font-size: 0.82rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-xs { padding: 4px 10px; font-size: 0.78rem; }
.btn-ghost { background: transparent; border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-ghost:hover:not(:disabled) { background: var(--bg-tertiary); color: var(--text-primary); }

/* Diff view */
.diff-view { display: flex; flex-direction: column; gap: 16px; }

.diff-controls { padding: 16px 20px; display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.diff-select-row { display: flex; align-items: center; gap: 12px; flex: 1; }
.diff-select-group { display: flex; flex-direction: column; gap: 4px; flex: 1; }
.diff-label { font-size: 0.72rem; font-weight: 500; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.04em; }
.diff-arrow { color: var(--text-tertiary); font-size: 1rem; }
.diff-summary { display: flex; gap: 8px; align-items: center; }

.select { padding: 7px 10px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.82rem; }

.diff-panel { }
.diff-header { display: grid; grid-template-columns: 1fr 1fr; border-bottom: 1px solid var(--border-default); }
.diff-col-header { padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; border-right: 1px solid var(--border-default); }
.diff-col-header:last-child { border-right: none; }
.diff-col-label { font-size: 0.82rem; font-weight: 500; color: var(--text-primary); }
.diff-col-meta { font-size: 0.75rem; color: var(--text-tertiary); }

.diff-lines { font-family: 'Geist Mono', 'JetBrains Mono', monospace; font-size: 0.8rem; max-height: 520px; overflow-y: auto; }
.diff-line { display: flex; align-items: baseline; gap: 0; min-height: 22px; border-bottom: 1px solid transparent; }
.diff-line.added { background: rgba(52,211,153,0.08); }
.diff-line.removed { background: rgba(248,113,113,0.08); }
.diff-line.unchanged { color: var(--text-secondary); }

.line-no { min-width: 40px; padding: 2px 10px 2px 8px; font-size: 0.72rem; color: var(--text-tertiary); text-align: right; user-select: none; border-right: 1px solid var(--border-default); background: var(--bg-tertiary); }
.line-prefix { min-width: 20px; padding: 2px 4px; font-weight: 700; }
.diff-line.added .line-prefix { color: #34d399; }
.diff-line.removed .line-prefix { color: #f87171; }
.line-content { padding: 2px 8px; white-space: pre-wrap; word-break: break-all; flex: 1; }
</style>
