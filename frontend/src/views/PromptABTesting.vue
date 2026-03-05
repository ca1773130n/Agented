<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

interface Variant {
  id: 'A' | 'B';
  prompt: string;
  runs: number;
  avgScore: number;
  avgTokens: number;
  winRate: number;
}

interface ABTest {
  id: string;
  botName: string;
  status: 'running' | 'paused' | 'completed';
  startedAt: string;
  totalRuns: number;
  variants: [Variant, Variant];
}

const tests = ref<ABTest[]>([
  {
    id: 'ab-001',
    botName: 'bot-pr-review',
    status: 'running',
    startedAt: '2026-03-01T00:00:00Z',
    totalRuns: 48,
    variants: [
      {
        id: 'A',
        prompt: 'You are a code reviewer. Review this pull request for bugs, security issues, and code quality. Be concise and actionable.',
        runs: 24,
        avgScore: 7.2,
        avgTokens: 1840,
        winRate: 54,
      },
      {
        id: 'B',
        prompt: 'You are a senior software engineer conducting a thorough code review. Examine the diff for: 1) Security vulnerabilities 2) Logic errors 3) Performance concerns 4) Code maintainability. Output structured findings.',
        runs: 24,
        avgScore: 8.1,
        avgTokens: 2340,
        winRate: 46,
      },
    ],
  },
]);

const selected = ref<ABTest>(tests.value[0]);
const isSaving = ref(false);

const winner = computed(() => {
  const [a, b] = selected.value.variants;
  if (a.avgScore === b.avgScore) return null;
  return a.avgScore > b.avgScore ? 'A' : 'B';
});

async function toggleTest() {
  isSaving.value = true;
  try {
    await new Promise(r => setTimeout(r, 600));
    selected.value.status = selected.value.status === 'running' ? 'paused' : 'running';
    showToast(`Test ${selected.value.status}`, 'success');
  } finally {
    isSaving.value = false;
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
    <AppBreadcrumb :items="[
      { label: 'Bots', action: () => router.push({ name: 'triggers' }) },
      { label: 'Prompt A/B Testing' },
    ]" />

    <PageHeader
      title="Prompt A/B Testing"
      subtitle="Run two prompt variants on alternating executions and compare output quality side-by-side."
    />

    <div class="layout">
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
          <div class="test-name">{{ t.botName }}</div>
          <div class="test-meta">{{ t.totalRuns }} runs · <span :class="['test-status', `s-${t.status}`]">{{ t.status }}</span></div>
        </div>
      </aside>

      <!-- Test detail -->
      <div class="test-detail">
        <div class="card detail-header-card">
          <div class="detail-top">
            <div>
              <div class="detail-bot">{{ selected.botName }}</div>
              <div class="detail-meta">Started {{ formatDate(selected.startedAt) }} · {{ selected.totalRuns }} total runs</div>
            </div>
            <div class="header-actions">
              <span :class="['status-badge', `s-${selected.status}`]">{{ selected.status }}</span>
              <button class="btn btn-ghost" :disabled="isSaving" @click="toggleTest">
                {{ selected.status === 'running' ? 'Pause' : 'Resume' }}
              </button>
              <button class="btn btn-primary" @click="showToast('Winner applied to production', 'success')">
                Apply Winner
              </button>
            </div>
          </div>
        </div>

        <div class="compare-grid">
          <div v-for="v in selected.variants" :key="v.id" class="variant-card card" :class="{ 'is-winner': winner === v.id }">
            <div class="variant-header">
              <div class="variant-badge">Variant {{ v.id }}</div>
              <div v-if="winner === v.id" class="winner-badge">🏆 Leading</div>
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
          <span class="winner-icon">🏆</span>
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
.winner-icon { font-size: 1.4rem; }
.winner-title { font-size: 0.88rem; font-weight: 600; color: #34d399; margin-bottom: 4px; }
.winner-sub { font-size: 0.78rem; color: var(--text-secondary); line-height: 1.5; }

.btn { display: flex; align-items: center; gap: 6px; padding: 7px 14px; border-radius: 7px; font-size: 0.82rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-ghost { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-ghost:hover:not(:disabled) { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.btn-ghost:disabled { opacity: 0.4; cursor: not-allowed; }

@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } .compare-grid { grid-template-columns: 1fr; } }
</style>
