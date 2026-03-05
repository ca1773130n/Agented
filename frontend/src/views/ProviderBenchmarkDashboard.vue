<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

interface BenchmarkResult {
  provider: string;
  model: string;
  quality: number;
  latencyMs: number;
  costPer1k: number;
  tokensIn: number;
  tokensOut: number;
  status: 'complete' | 'running' | 'failed';
}

interface Benchmark {
  id: string;
  name: string;
  prompt: string;
  runAt: string;
  results: BenchmarkResult[];
}

const benchmarks = ref<Benchmark[]>([
  {
    id: 'bm-001',
    name: 'PR Review Quality',
    prompt: 'Review this pull request for security issues and code quality: [PR diff excerpt]',
    runAt: '2026-03-06T10:00:00Z',
    results: [
      { provider: 'Claude', model: 'claude-opus-4-6', quality: 9.1, latencyMs: 820, costPer1k: 15.0, tokensIn: 4200, tokensOut: 680, status: 'complete' },
      { provider: 'Gemini', model: 'gemini-2.0-pro', quality: 8.3, latencyMs: 1100, costPer1k: 7.0, tokensIn: 4200, tokensOut: 720, status: 'complete' },
      { provider: 'GPT-4', model: 'gpt-4o', quality: 8.7, latencyMs: 950, costPer1k: 10.0, tokensIn: 4200, tokensOut: 640, status: 'complete' },
    ],
  },
]);

const selected = ref<Benchmark>(benchmarks.value[0]);
const isRunning = ref(false);

const sorted = computed(() => [...selected.value.results].sort((a, b) => b.quality - a.quality));
const bestQuality = computed(() => sorted.value[0]);
const bestCost = computed(() => [...selected.value.results].sort((a, b) => a.costPer1k - b.costPer1k)[0]);
const bestSpeed = computed(() => [...selected.value.results].sort((a, b) => a.latencyMs - b.latencyMs)[0]);

async function handleRerun() {
  isRunning.value = true;
  try {
    await new Promise(r => setTimeout(r, 2000));
    showToast('Benchmark complete', 'success');
  } finally {
    isRunning.value = false;
  }
}

function barWidth(val: number, max: number) {
  return `${(val / max) * 100}%`;
}

function formatDate(ts: string) {
  return new Date(ts).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}
</script>

<template>
  <div class="benchmark-page">
    <AppBreadcrumb :items="[
      { label: 'Backends', action: () => router.push({ name: 'ai-backends' }) },
      { label: 'Provider Benchmarks' },
    ]" />

    <PageHeader
      title="Provider Benchmarking Dashboard"
      subtitle="Run the same bot against multiple AI providers simultaneously and compare quality, latency, and cost."
    />

    <div class="layout">
      <aside class="sidebar card">
        <div class="sidebar-header">Benchmarks</div>
        <div
          v-for="b in benchmarks"
          :key="b.id"
          class="bm-item"
          :class="{ active: selected.id === b.id }"
          @click="selected = b"
        >
          <div class="bm-name">{{ b.name }}</div>
          <div class="bm-meta">{{ b.results.length }} providers · {{ formatDate(b.runAt) }}</div>
        </div>
      </aside>

      <div class="detail">
        <!-- Winner summary -->
        <div class="winners-row">
          <div class="winner-chip card">
            <div class="winner-chip-label">Best Quality</div>
            <div class="winner-chip-provider">{{ bestQuality.provider }}</div>
            <div class="winner-chip-val">{{ bestQuality.quality }}/10</div>
          </div>
          <div class="winner-chip card">
            <div class="winner-chip-label">Fastest</div>
            <div class="winner-chip-provider">{{ bestSpeed.provider }}</div>
            <div class="winner-chip-val">{{ bestSpeed.latencyMs }}ms</div>
          </div>
          <div class="winner-chip card">
            <div class="winner-chip-label">Cheapest</div>
            <div class="winner-chip-provider">{{ bestCost.provider }}</div>
            <div class="winner-chip-val">${{ bestCost.costPer1k }}/1k tokens</div>
          </div>
        </div>

        <!-- Comparison table -->
        <div class="card results-card">
          <div class="results-header">
            <span>Comparison Results</span>
            <button class="btn btn-primary btn-sm" :disabled="isRunning" @click="handleRerun">
              {{ isRunning ? 'Running...' : '▶ Re-run All' }}
            </button>
          </div>
          <div class="results-table">
            <div class="table-head">
              <span>Provider</span><span>Quality</span><span>Latency</span><span>Cost /1k</span><span>Tokens Out</span>
            </div>
            <div v-for="(r, i) in sorted" :key="r.provider" class="table-row" :class="{ 'row-first': i === 0 }">
              <div class="col-provider">
                <span class="provider-rank">{{ i + 1 }}</span>
                <div>
                  <div class="provider-name">{{ r.provider }}</div>
                  <div class="provider-model">{{ r.model }}</div>
                </div>
              </div>
              <div class="col-metric">
                <div class="bar-wrap">
                  <div class="bar-fill bar-quality" :style="{ width: barWidth(r.quality, 10) }"></div>
                </div>
                <span class="metric-val">{{ r.quality }}</span>
              </div>
              <div class="col-metric">
                <div class="bar-wrap">
                  <div class="bar-fill bar-latency" :style="{ width: barWidth(1500 - r.latencyMs, 1500) }"></div>
                </div>
                <span class="metric-val">{{ r.latencyMs }}ms</span>
              </div>
              <div class="col-metric">
                <span class="metric-val">${{ r.costPer1k }}</span>
              </div>
              <div class="col-metric">
                <span class="metric-val">{{ r.tokensOut.toLocaleString() }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Prompt card -->
        <div class="card prompt-card">
          <div class="prompt-header">Benchmark Prompt</div>
          <div class="prompt-body">{{ selected.prompt }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.benchmark-page { display: flex; flex-direction: column; gap: 24px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.layout { display: grid; grid-template-columns: 220px 1fr; gap: 20px; align-items: start; }
.detail { display: flex; flex-direction: column; gap: 16px; }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }

.sidebar-header { padding: 14px 16px; font-size: 0.8rem; font-weight: 600; color: var(--text-secondary); border-bottom: 1px solid var(--border-default); }
.bm-item { padding: 12px 16px; cursor: pointer; border-bottom: 1px solid var(--border-subtle); transition: background 0.1s; }
.bm-item:hover { background: var(--bg-tertiary); }
.bm-item.active { background: rgba(6,182,212,0.08); border-left: 2px solid var(--accent-cyan); }
.bm-item:last-child { border-bottom: none; }
.bm-name { font-size: 0.82rem; font-weight: 600; color: var(--text-primary); margin-bottom: 3px; }
.bm-meta { font-size: 0.7rem; color: var(--text-muted); }

.winners-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.winner-chip { padding: 16px; text-align: center; }
.winner-chip-label { font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-tertiary); margin-bottom: 6px; }
.winner-chip-provider { font-size: 0.95rem; font-weight: 700; color: var(--text-primary); margin-bottom: 4px; }
.winner-chip-val { font-size: 0.78rem; color: var(--accent-cyan); }

.results-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 20px; border-bottom: 1px solid var(--border-default); font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); }

.table-head { display: grid; grid-template-columns: 200px 1fr 1fr 100px 100px; gap: 12px; padding: 10px 20px; font-size: 0.72rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-tertiary); border-bottom: 1px solid var(--border-subtle); }

.table-row { display: grid; grid-template-columns: 200px 1fr 1fr 100px 100px; gap: 12px; padding: 14px 20px; border-bottom: 1px solid var(--border-subtle); align-items: center; transition: background 0.1s; }
.table-row:hover { background: var(--bg-tertiary); }
.table-row.row-first { background: rgba(52,211,153,0.04); }
.table-row:last-child { border-bottom: none; }

.col-provider { display: flex; align-items: center; gap: 10px; }
.provider-rank { width: 22px; height: 22px; border-radius: 50%; background: var(--bg-tertiary); display: flex; align-items: center; justify-content: center; font-size: 0.72rem; font-weight: 700; color: var(--text-secondary); flex-shrink: 0; }
.row-first .provider-rank { background: rgba(52,211,153,0.15); color: #34d399; }
.provider-name { font-size: 0.85rem; font-weight: 600; color: var(--text-primary); }
.provider-model { font-size: 0.7rem; color: var(--text-muted); font-family: monospace; }

.col-metric { display: flex; align-items: center; gap: 8px; }
.bar-wrap { flex: 1; height: 6px; background: var(--bg-tertiary); border-radius: 3px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 3px; }
.bar-quality { background: var(--accent-cyan); }
.bar-latency { background: #34d399; }
.metric-val { font-size: 0.8rem; font-weight: 600; color: var(--text-primary); white-space: nowrap; min-width: 50px; }

.prompt-header { padding: 12px 20px; border-bottom: 1px solid var(--border-default); font-size: 0.78rem; font-weight: 600; color: var(--text-secondary); }
.prompt-body { padding: 16px 20px; font-size: 0.82rem; color: var(--text-secondary); line-height: 1.5; }

.btn { padding: 7px 14px; border-radius: 7px; font-size: 0.82rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-sm { padding: 5px 12px; font-size: 0.75rem; }

@media (max-width: 1000px) {
  .layout { grid-template-columns: 1fr; }
  .winners-row { grid-template-columns: 1fr; }
  .table-head, .table-row { grid-template-columns: 1fr 1fr 1fr; }
}
</style>
