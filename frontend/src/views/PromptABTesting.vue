<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { triggerApi, analyticsApi, ApiError } from '../services/api';
import type { Trigger, ExecutionAnalyticsResponse } from '../services/api';
const showToast = useToast();

interface Variant {
  id: 'A' | 'B';
  triggerId: string;
  triggerName: string;
  prompt: string;
  runs: number;
  avgScore: number;
  avgTokens: number;
  winRate: number;
}

interface ABTest {
  id: string;
  baseTriggerName: string;
  status: 'running' | 'paused' | 'completed';
  startedAt: string;
  totalRuns: number;
  variants: [Variant, Variant];
}

const triggers = ref<Trigger[]>([]);
const tests = ref<ABTest[]>([]);
const selected = ref<ABTest | null>(null);
const isLoading = ref(false);
const loadError = ref('');
const isSaving = ref(false);
const isCreating = ref(false);

// Create new A/B test state
const showCreateDialog = ref(false);
const baseTriggerIdForCreate = ref('');
const variantPrompt = ref('');

onMounted(async () => {
  await loadTriggers();
});

async function loadTriggers() {
  isLoading.value = true;
  loadError.value = '';
  try {
    const res = await triggerApi.list();
    triggers.value = res.triggers;
    await buildTestsFromTriggers();
  } catch (e) {
    loadError.value = e instanceof ApiError ? e.message : 'Failed to load triggers';
  } finally {
    isLoading.value = false;
  }
}

async function buildTestsFromTriggers() {
  // Group triggers that share a name prefix (e.g. "PR Review" and "PR Review [Variant B]")
  const baseMap = new Map<string, Trigger[]>();
  for (const t of triggers.value) {
    const variantMatch = t.name.match(/^(.+?)\s*\[Variant [A-Z]\]$/);
    const baseName = variantMatch ? variantMatch[1].trim() : t.name;
    if (!baseMap.has(baseName)) baseMap.set(baseName, []);
    baseMap.get(baseName)!.push(t);
  }

  const builtTests: ABTest[] = [];
  for (const [baseName, group] of baseMap) {
    if (group.length < 2) continue;
    // Use first two as A and B
    const [a, b] = group;
    let analyticsA: ExecutionAnalyticsResponse | null = null;
    let analyticsB: ExecutionAnalyticsResponse | null = null;
    try {
      [analyticsA, analyticsB] = await Promise.all([
        analyticsApi.fetchExecutionAnalytics({ trigger_id: a.id }),
        analyticsApi.fetchExecutionAnalytics({ trigger_id: b.id }),
      ]);
    } catch {
      // Analytics may not be available
    }

    const runsA = analyticsA?.total_executions ?? 0;
    const runsB = analyticsB?.total_executions ?? 0;
    const totalRuns = runsA + runsB;
    const successA = analyticsA?.data.reduce((sum, d) => sum + d.success_count, 0) ?? 0;
    const successB = analyticsB?.data.reduce((sum, d) => sum + d.success_count, 0) ?? 0;
    const avgDurA = analyticsA?.data.length
      ? analyticsA.data.reduce((sum, d) => sum + (d.avg_duration_ms ?? 0), 0) / analyticsA.data.length
      : 0;
    const avgDurB = analyticsB?.data.length
      ? analyticsB.data.reduce((sum, d) => sum + (d.avg_duration_ms ?? 0), 0) / analyticsB.data.length
      : 0;

    const scoreA = runsA > 0 ? Math.round((successA / runsA) * 100) / 10 : 0;
    const scoreB = runsB > 0 ? Math.round((successB / runsB) * 100) / 10 : 0;

    builtTests.push({
      id: `ab-${a.id}-${b.id}`,
      baseTriggerName: baseName,
      status: a.enabled && b.enabled ? 'running' : 'paused',
      startedAt: a.created_at || new Date().toISOString(),
      totalRuns,
      variants: [
        {
          id: 'A',
          triggerId: a.id,
          triggerName: a.name,
          prompt: a.prompt_template,
          runs: runsA,
          avgScore: scoreA,
          avgTokens: Math.round(avgDurA / 10),
          winRate: totalRuns > 0 ? Math.round((runsA / totalRuns) * 100) : 50,
        },
        {
          id: 'B',
          triggerId: b.id,
          triggerName: b.name,
          prompt: b.prompt_template,
          runs: runsB,
          avgScore: scoreB,
          avgTokens: Math.round(avgDurB / 10),
          winRate: totalRuns > 0 ? Math.round((runsB / totalRuns) * 100) : 50,
        },
      ],
    });
  }
  tests.value = builtTests;
  if (builtTests.length > 0) selected.value = builtTests[0];
}

const winner = computed(() => {
  if (!selected.value) return null;
  const [a, b] = selected.value.variants;
  if (a.avgScore === b.avgScore) return null;
  return a.avgScore > b.avgScore ? 'A' : 'B';
});

async function toggleTest() {
  if (!selected.value) return;
  isSaving.value = true;
  try {
    const newEnabled = selected.value.status === 'running' ? 0 : 1;
    await Promise.all([
      triggerApi.update(selected.value.variants[0].triggerId, { enabled: newEnabled }),
      triggerApi.update(selected.value.variants[1].triggerId, { enabled: newEnabled }),
    ]);
    selected.value.status = newEnabled ? 'running' : 'paused';
    showToast(`Test ${selected.value.status}`, 'success');
  } catch (e) {
    showToast(e instanceof ApiError ? e.message : 'Failed to toggle test', 'error');
  } finally {
    isSaving.value = false;
  }
}

async function applyWinner() {
  if (!selected.value || !winner.value) return;
  const winnerVariant = selected.value.variants.find(v => v.id === winner.value);
  const loserVariant = selected.value.variants.find(v => v.id !== winner.value);
  if (!winnerVariant || !loserVariant) return;
  try {
    await triggerApi.update(loserVariant.triggerId, {
      prompt_template: winnerVariant.prompt,
      enabled: 0,
    });
    showToast('Winner applied — loser variant disabled', 'success');
  } catch (e) {
    showToast(e instanceof ApiError ? e.message : 'Failed to apply winner', 'error');
  }
}

async function createVariant() {
  if (!baseTriggerIdForCreate.value || !variantPrompt.value.trim()) return;
  isCreating.value = true;
  try {
    const base = triggers.value.find(t => t.id === baseTriggerIdForCreate.value);
    if (!base) return;
    await triggerApi.create({
      name: `${base.name} [Variant B]`,
      prompt_template: variantPrompt.value,
      backend_type: base.backend_type,
      trigger_source: base.trigger_source,
    });
    showToast('Variant created. Reload to see the new A/B test.', 'success');
    showCreateDialog.value = false;
    variantPrompt.value = '';
    await loadTriggers();
  } catch (e) {
    showToast(e instanceof ApiError ? e.message : 'Failed to create variant', 'error');
  } finally {
    isCreating.value = false;
  }
}

function formatDate(ts: string) {
  return new Date(ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function scoreBar(score: number) {
  return `${(score / 10) * 100}%`;
}
</script>

<template>
  <div class="ab-testing">

    <PageHeader
      title="Prompt A/B Testing"
      subtitle="Run two prompt variants on alternating executions and compare output quality side-by-side."
    >
      <template #actions>
        <button class="btn btn-primary" @click="showCreateDialog = true">+ New A/B Test</button>
      </template>
    </PageHeader>

    <div v-if="isLoading" class="loading-msg">Loading triggers and analytics...</div>
    <div v-else-if="loadError" class="error-msg">{{ loadError }}</div>
    <div v-else-if="tests.length === 0" class="empty-msg">
      <p>No A/B tests found. Create variant triggers (name them with [Variant B] suffix) to start testing.</p>
      <button class="btn btn-primary" @click="showCreateDialog = true">+ Create Variant</button>
    </div>

    <!-- Create dialog -->
    <div v-if="showCreateDialog" class="card create-dialog">
      <div class="create-header">Create A/B Test Variant</div>
      <div class="create-body">
        <div class="create-field">
          <label class="create-label">Base Trigger</label>
          <select v-model="baseTriggerIdForCreate" class="select">
            <option value="">Select a trigger...</option>
            <option v-for="t in triggers" :key="t.id" :value="t.id">{{ t.name }}</option>
          </select>
        </div>
        <div class="create-field">
          <label class="create-label">Variant B Prompt</label>
          <textarea v-model="variantPrompt" class="variant-textarea" rows="6" placeholder="Enter the variant prompt..."></textarea>
        </div>
        <div class="create-actions">
          <button class="btn btn-ghost" @click="showCreateDialog = false">Cancel</button>
          <button class="btn btn-primary" :disabled="isCreating || !baseTriggerIdForCreate || !variantPrompt.trim()" @click="createVariant">
            {{ isCreating ? 'Creating...' : 'Create Variant' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="tests.length > 0 && selected" class="layout">
      <!-- Test list -->
      <aside class="sidebar card">
        <div class="sidebar-header">Active Tests</div>
        <div
          v-for="t in tests"
          :key="t.id"
          class="test-item"
          :class="{ active: selected.id === t.id }"
          @click="selected = t"
        >
          <div class="test-name">{{ t.baseTriggerName }}</div>
          <div class="test-meta">{{ t.totalRuns }} runs · <span :class="['test-status', `s-${t.status}`]">{{ t.status }}</span></div>
        </div>
      </aside>

      <!-- Test detail -->
      <div class="test-detail">
        <div class="card detail-header-card">
          <div class="detail-top">
            <div>
              <div class="detail-bot">{{ selected.baseTriggerName }}</div>
              <div class="detail-meta">Started {{ formatDate(selected.startedAt) }} · {{ selected.totalRuns }} total runs</div>
            </div>
            <div class="header-actions">
              <span :class="['status-badge', `s-${selected.status}`]">{{ selected.status }}</span>
              <button class="btn btn-ghost" :disabled="isSaving" @click="toggleTest">
                {{ selected.status === 'running' ? 'Pause' : 'Resume' }}
              </button>
              <button class="btn btn-primary" :disabled="!winner" @click="applyWinner">
                Apply Winner
              </button>
            </div>
          </div>
        </div>

        <div class="compare-grid">
          <div v-for="v in selected.variants" :key="v.id" class="variant-card card" :class="{ 'is-winner': winner === v.id }">
            <div class="variant-header">
              <div class="variant-badge">Variant {{ v.id }}</div>
              <div v-if="winner === v.id" class="winner-badge">Leading</div>
            </div>
            <div class="variant-prompt">
              <div class="prompt-label">Prompt</div>
              <pre class="prompt-text">{{ v.prompt }}</pre>
            </div>
            <div class="variant-metrics">
              <div class="metric">
                <div class="metric-label">Avg Score</div>
                <div class="score-bar-wrap">
                  <div class="score-bar-fill" :style="{ width: scoreBar(v.avgScore) }"></div>
                </div>
                <div class="metric-val">{{ v.avgScore }}/10</div>
              </div>
              <div class="metric">
                <div class="metric-label">Avg Tokens</div>
                <div class="metric-val">{{ v.avgTokens.toLocaleString() }}</div>
              </div>
              <div class="metric">
                <div class="metric-label">Runs</div>
                <div class="metric-val">{{ v.runs }}</div>
              </div>
              <div class="metric">
                <div class="metric-label">Win Rate</div>
                <div class="metric-val">{{ v.winRate }}%</div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="winner" class="winner-summary card">
          <div>
            <div class="winner-title">Variant {{ winner }} is leading</div>
            <div class="winner-sub">{{ Math.abs(selected.variants[0].avgScore - selected.variants[1].avgScore).toFixed(1) }} points higher average score with {{ selected.totalRuns }} total runs. Statistical significance improves with more data.</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ab-testing { display: flex; flex-direction: column; gap: 24px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.loading-msg, .error-msg, .empty-msg { font-size: 0.875rem; padding: 24px; text-align: center; }
.loading-msg { color: var(--text-tertiary); }
.error-msg { color: #ef4444; }
.empty-msg { color: var(--text-muted); display: flex; flex-direction: column; align-items: center; gap: 16px; }
.empty-msg p { margin: 0; }

.create-dialog { margin-bottom: 8px; }
.create-header { padding: 14px 20px; border-bottom: 1px solid var(--border-default); font-size: 0.88rem; font-weight: 600; color: var(--text-primary); }
.create-body { padding: 20px; display: flex; flex-direction: column; gap: 16px; }
.create-field { display: flex; flex-direction: column; gap: 6px; }
.create-label { font-size: 0.78rem; font-weight: 600; color: var(--text-secondary); }
.select { padding: 8px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.82rem; }
.variant-textarea { padding: 10px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 8px; color: var(--text-primary); font-family: monospace; font-size: 0.82rem; resize: vertical; }
.create-actions { display: flex; gap: 10px; justify-content: flex-end; }

.layout { display: grid; grid-template-columns: 220px 1fr; gap: 20px; align-items: start; }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }

.sidebar-header { padding: 14px 16px; font-size: 0.8rem; font-weight: 600; color: var(--text-secondary); border-bottom: 1px solid var(--border-default); }

.test-item { padding: 12px 16px; cursor: pointer; border-bottom: 1px solid var(--border-subtle); transition: background 0.1s; }
.test-item:hover { background: var(--bg-tertiary); }
.test-item.active { background: rgba(6,182,212,0.08); border-left: 2px solid var(--accent-cyan); }
.test-name { font-size: 0.82rem; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.test-meta { font-size: 0.72rem; color: var(--text-muted); }
.test-status { font-weight: 600; }
.s-running { color: #34d399; }
.s-paused { color: #fbbf24; }
.s-completed { color: var(--text-muted); }

.test-detail { display: flex; flex-direction: column; gap: 16px; }

.detail-top { display: flex; align-items: flex-start; justify-content: space-between; padding: 18px 20px; }
.detail-bot { font-size: 0.95rem; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.detail-meta { font-size: 0.75rem; color: var(--text-muted); }
.header-actions { display: flex; align-items: center; gap: 10px; }
.status-badge { font-size: 0.72rem; font-weight: 700; padding: 3px 8px; border-radius: 4px; text-transform: capitalize; }

.compare-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }

.variant-card { }
.variant-card.is-winner { border-color: rgba(52,211,153,0.4); }
.variant-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid var(--border-default); }
.variant-badge { font-size: 0.82rem; font-weight: 700; color: var(--text-primary); }
.winner-badge { font-size: 0.75rem; color: #34d399; }

.variant-prompt { padding: 16px 18px; border-bottom: 1px solid var(--border-subtle); }
.prompt-label { font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-tertiary); margin-bottom: 8px; }
.prompt-text { font-family: inherit; font-size: 0.78rem; color: var(--text-secondary); line-height: 1.5; white-space: pre-wrap; margin: 0; }

.variant-metrics { display: flex; flex-direction: column; gap: 12px; padding: 16px 18px; }
.metric { display: flex; align-items: center; gap: 10px; }
.metric-label { font-size: 0.72rem; color: var(--text-tertiary); width: 90px; flex-shrink: 0; }
.score-bar-wrap { flex: 1; height: 6px; background: var(--bg-tertiary); border-radius: 3px; overflow: hidden; }
.score-bar-fill { height: 100%; background: var(--accent-cyan); border-radius: 3px; transition: width 0.5s ease; }
.metric-val { font-size: 0.82rem; font-weight: 600; color: var(--text-primary); min-width: 60px; text-align: right; }

.winner-summary {
  display: flex; align-items: flex-start; gap: 16px; padding: 18px 20px;
  border-color: rgba(52,211,153,0.3); background: rgba(52,211,153,0.04);
}
.winner-title { font-size: 0.88rem; font-weight: 600; color: #34d399; margin-bottom: 4px; }
.winner-sub { font-size: 0.78rem; color: var(--text-secondary); line-height: 1.5; }

.btn { display: flex; align-items: center; gap: 6px; padding: 7px 14px; border-radius: 7px; font-size: 0.82rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-ghost { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-ghost:hover:not(:disabled) { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.btn-ghost:disabled { opacity: 0.4; cursor: not-allowed; }

@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } .compare-grid { grid-template-columns: 1fr; } }
</style>
