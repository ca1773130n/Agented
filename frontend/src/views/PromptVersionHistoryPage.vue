<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const route = useRoute();
const showToast = useToast();

const botId = computed(() => (route.params.botId as string) || '');

interface PromptVersion {
  id: string;
  version: number;
  author: string;
  timestamp: string;
  message: string;
  prompt: string;
  tokensEstimate: number;
  tag?: string;
}

const versions = ref<PromptVersion[]>([
  {
    id: 'pv-001',
    version: 7,
    author: 'alice@example.com',
    timestamp: '2026-03-06T10:14:00Z',
    message: 'Tighten severity classification criteria',
    tag: 'current',
    prompt: `You are a security audit expert. Analyze the provided code for vulnerabilities.

For each finding, assign a severity: critical, high, medium, or low.
- critical: Remote code execution, auth bypass, SQL injection
- high: XSS, SSRF, insecure deserialization
- medium: CSRF, open redirect, missing rate limiting
- low: Information disclosure, verbose error messages

Output findings as structured JSON with keys: severity, title, file, line, description, remediation.
Limit output to the top 10 most impactful findings.`,
    tokensEstimate: 142,
  },
  {
    id: 'pv-002',
    version: 6,
    author: 'bob@example.com',
    timestamp: '2026-03-04T16:22:00Z',
    message: 'Add remediation field to output schema',
    prompt: `You are a security audit expert. Analyze the provided code for vulnerabilities.

For each finding, assign a severity: critical, high, medium, or low.
- critical: Remote code execution, auth bypass, SQL injection
- high: XSS, SSRF, insecure deserialization
- medium: CSRF, open redirect, missing rate limiting
- low: Information disclosure, verbose error messages

Output findings as structured JSON with keys: severity, title, file, line, description.
Limit output to the top 10 most impactful findings.`,
    tokensEstimate: 128,
  },
  {
    id: 'pv-003',
    version: 5,
    author: 'alice@example.com',
    timestamp: '2026-03-01T09:05:00Z',
    message: 'Reduce output verbosity — cap at 10 findings',
    prompt: `You are a security audit expert. Analyze the provided code for vulnerabilities.

For each finding, assign a severity: critical, high, medium, or low.
Use the OWASP Top 10 as a reference.

Output findings as structured JSON with keys: severity, title, file, line, description.`,
    tokensEstimate: 98,
  },
  {
    id: 'pv-004',
    version: 4,
    author: 'carol@example.com',
    timestamp: '2026-02-26T14:40:00Z',
    message: 'Switch to OWASP-aligned severity scale',
    prompt: `You are a security audit expert. Analyze the provided code for security issues.

Classify each finding as: blocker, warning, or info.
Reference OWASP Top 10 for guidance.

Return JSON: [{severity, title, file, line, description}]`,
    tokensEstimate: 82,
  },
  {
    id: 'pv-005',
    version: 3,
    author: 'bob@example.com',
    timestamp: '2026-02-20T11:30:00Z',
    message: 'Initial structured JSON output format',
    prompt: `You are a code security reviewer. Look for bugs and vulnerabilities in the code.

Return a list of issues in JSON format with severity, title, file, and description.`,
    tokensEstimate: 64,
  },
]);

const selectedLeft = ref<string>(versions.value[1].id);
const selectedRight = ref<string>(versions.value[0].id);
const activeTab = ref<'list' | 'diff'>('list');
const isRollingBack = ref(false);

const leftVersion = computed(() => versions.value.find(v => v.id === selectedLeft.value));
const rightVersion = computed(() => versions.value.find(v => v.id === selectedRight.value));

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

  // Simple line-by-line diff (LCS-based would be ideal; this is a visual approximation)
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

function selectForDiff(versionId: string) {
  if (versionId === selectedRight.value) return;
  selectedLeft.value = versionId;
  activeTab.value = 'diff';
}

async function rollbackTo(v: PromptVersion) {
  isRollingBack.value = true;
  try {
    await new Promise(r => setTimeout(r, 900));
    const newVersion: PromptVersion = {
      id: `pv-${Date.now()}`,
      version: versions.value[0].version + 1,
      author: 'you@example.com',
      timestamp: new Date().toISOString(),
      message: `Rollback to v${v.version}: ${v.message}`,
      prompt: v.prompt,
      tokensEstimate: v.tokensEstimate,
      tag: 'current',
    };
    const prev = versions.value.find(x => x.tag === 'current');
    if (prev) delete prev.tag;
    versions.value.unshift(newVersion);
    selectedRight.value = newVersion.id;
    showToast(`Rolled back to v${v.version}. A new version v${newVersion.version} was created.`, 'success');
    activeTab.value = 'list';
  } finally {
    isRollingBack.value = false;
  }
}
</script>

<template>
  <div class="prompt-version-history">
    <AppBreadcrumb :items="[
      { label: 'Bots', action: () => router.push({ name: 'triggers' }) },
      { label: 'Bot', action: () => router.push({ name: 'trigger-dashboard', params: { triggerId: botId } }) },
      { label: 'Prompt Version History' },
    ]" />

    <PageHeader
      title="Prompt Template Version History"
      subtitle="Every change to this bot's prompt template — with diffs, authors, and one-click rollback."
    />

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
          <button class="btn btn-xs btn-ghost" @click="activeTab = 'diff'; selectedLeft = v.id">
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
              <option v-for="v in versions" :key="v.id" :value="v.id">
                v{{ v.version }} — {{ v.message }}
              </option>
            </select>
          </div>
          <div class="diff-arrow">→</div>
          <div class="diff-select-group">
            <label class="diff-label">Compare (newer)</label>
            <select v-model="selectedRight" class="select">
              <option v-for="v in versions" :key="v.id" :value="v.id">
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
  </div>
</template>

<style scoped>
.prompt-version-history { display: flex; flex-direction: column; gap: 20px; animation: fadeIn 0.3s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

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
