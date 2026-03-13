<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { executionApi } from '../services/api/triggers';
import type { Execution } from '../services/api/types';
const router = useRouter();

interface FileDiff {
  path: string;
  status: 'added' | 'modified' | 'deleted';
  additions: number;
  deletions: number;
  chunks: DiffChunk[];
}

interface DiffChunk {
  header: string;
  lines: DiffLine[];
}

interface DiffLine {
  type: 'context' | 'added' | 'removed';
  content: string;
  oldLineNo: number | null;
  newLineNo: number | null;
}

const executions = ref<Execution[]>([]);
const diffs = ref<FileDiff[]>([]);
const selectedExec = ref<Execution | null>(null);
const selectedFile = ref<FileDiff | null>(null);
const loadingExecs = ref(false);
const loadingDiffs = ref(false);

async function loadDiffs(executionId: string) {
  loadingDiffs.value = true;
  try {
    const result = await executionApi.getDiff(executionId);
    diffs.value = result.diffs as FileDiff[];
    selectedFile.value = diffs.value.length > 0 ? diffs.value[0] : null;
  } catch {
    diffs.value = [];
    selectedFile.value = null;
  } finally {
    loadingDiffs.value = false;
  }
}

async function selectExec(e: Execution) {
  selectedExec.value = e;
  await loadDiffs(e.execution_id);
}

function formatDate(ts: string) {
  return new Date(ts).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

const totalChanges = computed(() => ({
  additions: diffs.value.reduce((s, f) => s + f.additions, 0),
  deletions: diffs.value.reduce((s, f) => s + f.deletions, 0),
}));

onMounted(async () => {
  loadingExecs.value = true;
  try {
    const result = await executionApi.listAll({ limit: 20 });
    executions.value = result.executions;
    if (executions.value.length > 0) {
      selectedExec.value = executions.value[0];
      await loadDiffs(executions.value[0].execution_id);
    }
  } catch {
    executions.value = [];
  } finally {
    loadingExecs.value = false;
  }
});
</script>

<template>
  <div class="diff-viewer">
    <AppBreadcrumb :items="[
      { label: 'Executions', action: () => router.push({ name: 'execution-history' }) },
      { label: 'File Diff Viewer' },
    ]" />

    <PageHeader
      title="Execution File Diff Viewer"
      subtitle="Inspect all files created or modified by a bot run, with inline change explanations."
    />

    <div class="layout">
      <!-- Execution list -->
      <aside class="sidebar">
        <div class="sidebar-section">
          <div class="sidebar-title">Recent Executions</div>
          <div v-if="loadingExecs" class="sidebar-empty">Loading...</div>
          <div v-else-if="executions.length === 0" class="sidebar-empty">No executions found</div>
          <div
            v-for="e in executions"
            :key="e.execution_id"
            class="exec-item"
            :class="{ active: selectedExec?.execution_id === e.execution_id }"
            @click="selectExec(e)"
          >
            <div class="exec-bot">{{ e.trigger_name }}</div>
            <div class="exec-meta">
              <span class="exec-date">{{ formatDate(e.started_at) }}</span>
              <span class="exec-files">{{ selectedExec?.execution_id === e.execution_id ? diffs.length : '–' }} files</span>
            </div>
          </div>
        </div>

        <div class="sidebar-section">
          <div class="sidebar-title">Changed Files</div>
          <div v-if="loadingDiffs" class="sidebar-empty">Loading diffs...</div>
          <div v-else-if="diffs.length === 0" class="sidebar-empty">No diffs found</div>
          <div
            v-for="f in diffs"
            :key="f.path"
            class="file-item"
            :class="{ active: selectedFile?.path === f.path }"
            @click="selectedFile = f"
          >
            <span :class="['file-status', `status-${f.status}`]">{{ f.status[0].toUpperCase() }}</span>
            <span class="file-path">{{ f.path.split('/').pop() }}</span>
            <span class="file-stats">
              <span class="additions">+{{ f.additions }}</span>
              <span class="deletions">-{{ f.deletions }}</span>
            </span>
          </div>
        </div>
      </aside>

      <!-- Diff panel -->
      <main class="diff-main">
        <div v-if="selectedExec" class="diff-summary card">
          <div class="summary-item"><span class="summary-label">Execution</span><span class="summary-val">{{ selectedExec.execution_id }}</span></div>
          <div class="summary-item"><span class="summary-label">Bot</span><span class="summary-val">{{ selectedExec.trigger_name }}</span></div>
          <div class="summary-item"><span class="summary-label">Files changed</span><span class="summary-val">{{ diffs.length }}</span></div>
          <div class="summary-item"><span class="summary-label">Additions</span><span class="additions">+{{ totalChanges.additions }}</span></div>
          <div class="summary-item"><span class="summary-label">Deletions</span><span class="deletions">-{{ totalChanges.deletions }}</span></div>
        </div>

        <div v-if="selectedFile" class="diff-card card">
          <div class="diff-file-header">
            <span :class="['file-badge', `status-${selectedFile.status}`]">{{ selectedFile.status }}</span>
            <span class="diff-filename">{{ selectedFile.path }}</span>
          </div>

          <div v-for="(chunk, ci) in selectedFile.chunks" :key="ci" class="diff-chunk">
            <div class="chunk-header">{{ chunk.header }}</div>
            <div v-for="(line, li) in chunk.lines" :key="li" :class="['diff-line', `line-${line.type}`]">
              <span class="line-num">{{ line.oldLineNo ?? '' }}</span>
              <span class="line-num">{{ line.newLineNo ?? '' }}</span>
              <span class="line-content">{{ line.content }}</span>
            </div>
          </div>
        </div>

        <div v-else-if="!loadingDiffs && selectedExec" class="empty-state card">
          <p>No unified diff output found in this execution's logs.</p>
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.diff-viewer { display: flex; flex-direction: column; gap: 24px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.layout { display: grid; grid-template-columns: 240px 1fr; gap: 20px; align-items: start; }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }

.sidebar { display: flex; flex-direction: column; gap: 16px; }

.sidebar-section { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }

.sidebar-title {
  padding: 12px 16px; font-size: 0.72rem; font-weight: 600; color: var(--text-tertiary);
  text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid var(--border-default);
}

.sidebar-empty { padding: 12px 16px; font-size: 0.75rem; color: var(--text-muted); }

.exec-item {
  padding: 10px 16px; cursor: pointer; border-bottom: 1px solid var(--border-subtle);
  transition: background 0.1s;
}
.exec-item:hover { background: var(--bg-tertiary); }
.exec-item.active { background: rgba(6,182,212,0.08); border-left: 2px solid var(--accent-cyan); }
.exec-item:last-child { border-bottom: none; }
.exec-bot { font-size: 0.78rem; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.exec-meta { display: flex; justify-content: space-between; }
.exec-date { font-size: 0.7rem; color: var(--text-muted); }
.exec-files { font-size: 0.7rem; color: var(--text-tertiary); }

.file-item {
  display: flex; align-items: center; gap: 8px; padding: 8px 16px;
  cursor: pointer; border-bottom: 1px solid var(--border-subtle); transition: background 0.1s;
}
.file-item:hover { background: var(--bg-tertiary); }
.file-item.active { background: rgba(6,182,212,0.08); border-left: 2px solid var(--accent-cyan); }
.file-item:last-child { border-bottom: none; }
.file-status { font-size: 0.7rem; font-weight: 700; padding: 2px 5px; border-radius: 3px; }
.status-added { background: rgba(52,211,153,0.15); color: #34d399; }
.status-modified { background: rgba(251,191,36,0.15); color: #fbbf24; }
.status-deleted { background: rgba(239,68,68,0.15); color: #ef4444; }
.file-path { flex: 1; font-size: 0.75rem; color: var(--text-secondary); font-family: monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-stats { display: flex; gap: 6px; font-size: 0.7rem; }
.additions { color: #34d399; }
.deletions { color: #ef4444; }

.diff-main { display: flex; flex-direction: column; gap: 16px; }

.diff-summary { display: flex; gap: 0; }
.summary-item { flex: 1; padding: 14px 16px; border-right: 1px solid var(--border-subtle); }
.summary-item:last-child { border-right: none; }
.summary-label { display: block; font-size: 0.7rem; color: var(--text-tertiary); margin-bottom: 4px; }
.summary-val { font-size: 0.88rem; font-weight: 600; color: var(--text-primary); }

.diff-file-header {
  display: flex; align-items: center; gap: 10px; padding: 14px 20px;
  border-bottom: 1px solid var(--border-default); background: var(--bg-tertiary);
}
.file-badge { font-size: 0.72rem; font-weight: 700; padding: 3px 8px; border-radius: 4px; text-transform: capitalize; }
.diff-filename { font-family: monospace; font-size: 0.82rem; color: var(--text-primary); }

.diff-chunk { }
.chunk-header {
  padding: 8px 16px; background: rgba(6,182,212,0.06); border-bottom: 1px solid var(--border-subtle);
  font-family: monospace; font-size: 0.75rem; color: var(--accent-cyan);
}

.diff-line {
  display: flex; align-items: flex-start; flex-wrap: wrap; font-family: monospace; font-size: 0.78rem;
  border-bottom: 1px solid var(--border-subtle);
}
.line-added { background: rgba(52,211,153,0.07); }
.line-removed { background: rgba(239,68,68,0.07); }
.line-context { }
.line-num { width: 36px; padding: 4px 8px; color: var(--text-muted); text-align: right; user-select: none; flex-shrink: 0; }
.line-content { flex: 1; padding: 4px 8px; color: var(--text-secondary); white-space: pre-wrap; word-break: break-all; }

.empty-state { padding: 32px 24px; text-align: center; color: var(--text-muted); font-size: 0.85rem; }

@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } }
</style>
