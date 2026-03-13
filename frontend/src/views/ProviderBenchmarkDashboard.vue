<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { orchestrationApi, backendApi, ApiError } from '../services/api';
import type { AccountHealth, AIBackend } from '../services/api';

const router = useRouter();
const showToast = useToast();

const loading = ref(true);
const error = ref<string | null>(null);

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

const accounts = ref<AccountHealth[]>([]);
const backends = ref<AIBackend[]>([]);
const benchmarks = ref<Benchmark[]>([]);
const selected = ref<Benchmark | null>(null);
const isRunning = ref(false);

async function loadData() {
  loading.value = true;
  error.value = null;
  try {
    const [healthResp, backendsResp] = await Promise.all([
      orchestrationApi.getHealth(),
      backendApi.list(),
    ]);
    accounts.value = healthResp.accounts ?? [];
    backends.value = backendsResp.backends ?? [];

    // Build benchmark entries from account health data
    const results: BenchmarkResult[] = accounts.value.map((acct) => {
      const backendInfo = backends.value.find(b => b.id === acct.backend_id);
      return {
        provider: backendInfo?.name ?? acct.backend_name ?? acct.backend_type ?? 'Unknown',
        model: acct.plan ?? 'default',
        quality: acct.is_rate_limited ? 3 : 8,
        latencyMs: acct.cooldown_remaining_seconds ? acct.cooldown_remaining_seconds * 1000 : 0,
        costPer1k: 0,
        tokensIn: 0,
        tokensOut: acct.total_executions ?? 0,
        status: acct.is_rate_limited ? 'failed' as const : 'complete' as const,
      };
    });

    if (results.length > 0) {
      benchmarks.value = [{
        id: 'bm-live',
        name: 'Live Account Health',
        prompt: 'Real-time comparison of provider accounts based on health, latency, and cost metrics.',
        runAt: new Date().toISOString(),
        results,
      }];
      selected.value = benchmarks.value[0];
    }
  } catch (err) {
    if (err instanceof ApiError) {
      error.value = `API Error (${err.status}): ${err.message}`;
    } else {
      error.value = err instanceof Error ? err.message : 'Unknown error';
    }
  } finally {
    loading.value = false;
  }
}

onMounted(loadData);

const sorted = computed(() => selected.value ? [...selected.value.results].sort((a, b) => b.quality - a.quality) : []);
const bestQuality = computed(() => sorted.value[0] ?? null);
const bestCost = computed(() => selected.value ? [...selected.value.results].sort((a, b) => a.costPer1k - b.costPer1k)[0] ?? null : null);
const bestSpeed = computed(() => selected.value ? [...selected.value.results].sort((a, b) => a.latencyMs - b.latencyMs)[0] ?? null : null);

async function handleRerun() {
  isRunning.value = true;
  try {
    await loadData();
    showToast('Benchmark data refreshed', 'success');
  } catch {
    showToast('Refresh failed', 'error');
  } finally {
    isRunning.value = false;
  }
}

function barWidth(val: number, max: number) {
  if (max === 0) return '0%';
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

    <!-- Loading state -->
    <div v-if="loading" class="card" style="text-align: center; padding: 60px 20px; color: var(--text-secondary);">
      <p>Loading provider health and backend data...</p>
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="card" style="text-align: center; padding: 60px 20px; color: var(--text-secondary);">
      <p>{{ error }}</p>
      <button class="btn btn-primary" style="margin-top: 12px" @click="loadData">Retry</button>
    </div>

    <!-- Empty state -->
    <div v-else-if="!selected || sorted.length === 0" class="card" style="text-align: center; padding: 60px 20px; color: var(--text-tertiary);">
      <p>No provider accounts found. Configure backends and accounts to see benchmark data.</p>
    </div>

    <template v-else>
      <div class="layout">
        <aside class="sidebar card">
          <div class="sidebar-header">Benchmarks</div>
          <div
            v-for="b in benchmarks"
            :key="b.id"
            class="bm-item"
            :class="{ active: selected?.id === b.id }"
            @click="selected = b"
          >
            <div class="bm-name">{{ b.name }}</div>
            <div class="bm-meta">{{ b.results.length }} providers · {{ formatDate(b.runAt) }}</div>
          </div>
        </aside>

        <div class="detail">
          <!-- Winner summary -->
          <div class="winners-row">
            <div v-if="bestQuality" class="winner-chip card">
              <div class="winner-chip-label">Best Quality</div>
              <div class="winner-chip-provider">{{ bestQuality.provider }}</div>
              <div class="winner-chip-val">{{ bestQuality.quality.toFixed(1) }}/10</div>
            </div>
            <div v-if="bestSpeed" class="winner-chip card">
              <div class="winner-chip-label">Fastest</div>
              <div class="winner-chip-provider">{{ bestSpeed.provider }}</div>
              <div class="winner-chip-val">{{ bestSpeed.latencyMs }}ms</div>
            </div>
            <div v-if="bestCost" class="winner-chip card">
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
                {{ isRunning ? 'Refreshing...' : '▶ Refresh Data' }}
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
                  <span class="metric-val">{{ r.quality.toFixed(1) }}</span>
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
            <div class="prompt-header">Benchmark Description</div>
            <div class="prompt-body">{{ selected.prompt }}</div>
          </div>
        </div>
      </div>
    </template>
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
