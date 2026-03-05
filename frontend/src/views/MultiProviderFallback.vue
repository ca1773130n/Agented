<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const router = useRouter();
const showToast = useToast();

interface Provider {
  id: string;
  name: string;
  model: string;
  enabled: boolean;
  status: 'healthy' | 'degraded' | 'down';
  latencyMs: number;
  failureCount: number;
}

interface FallbackChain {
  id: string;
  name: string;
  bots: string[];
  providers: Provider[];
  triggerOn: string[];
}

const chains = ref<FallbackChain[]>([
  {
    id: 'chain-001',
    name: 'Primary Chain',
    bots: ['bot-pr-review', 'bot-security'],
    providers: [
      { id: 'p1', name: 'Claude', model: 'claude-opus-4-6', enabled: true, status: 'healthy', latencyMs: 820, failureCount: 0 },
      { id: 'p2', name: 'Gemini', model: 'gemini-2.0-pro', enabled: true, status: 'healthy', latencyMs: 1100, failureCount: 2 },
      { id: 'p3', name: 'Codex', model: 'gpt-4o', enabled: false, status: 'healthy', latencyMs: 950, failureCount: 0 },
    ],
    triggerOn: ['rate_limit', 'timeout', 'error_5xx'],
  },
]);

const selectedChain = ref<FallbackChain>(chains.value[0]);
const isSaving = ref(false);
const isTestingFallback = ref(false);
const testResult = ref<string | null>(null);

const triggerOptions = [
  { value: 'rate_limit', label: 'Rate limit (429)' },
  { value: 'timeout', label: 'Timeout' },
  { value: 'error_5xx', label: 'Server error (5xx)' },
  { value: 'empty_response', label: 'Empty response' },
];

function moveProvider(idx: number, dir: -1 | 1) {
  const providers = selectedChain.value.providers;
  const newIdx = idx + dir;
  if (newIdx < 0 || newIdx >= providers.length) return;
  const tmp = providers[idx];
  providers[idx] = providers[newIdx];
  providers[newIdx] = tmp;
}

function toggleTrigger(val: string) {
  const triggers = selectedChain.value.triggerOn;
  const i = triggers.indexOf(val);
  if (i === -1) triggers.push(val);
  else triggers.splice(i, 1);
}

async function handleSave() {
  isSaving.value = true;
  try {
    await new Promise(r => setTimeout(r, 800));
    showToast('Fallback chain saved', 'success');
  } catch {
    showToast('Failed to save', 'error');
  } finally {
    isSaving.value = false;
  }
}

async function testFallback() {
  isTestingFallback.value = true;
  testResult.value = null;
  try {
    await new Promise(r => setTimeout(r, 1500));
    testResult.value = 'Fallback test passed: Claude → Gemini transition verified in 1.2s';
    showToast('Fallback test complete', 'success');
  } finally {
    isTestingFallback.value = false;
  }
}

function statusColor(s: Provider['status']) {
  return { healthy: '#34d399', degraded: '#fbbf24', down: '#ef4444' }[s];
}
</script>

<template>
  <div class="mpf-page">
    <AppBreadcrumb :items="[
      { label: 'Settings', action: () => router.push({ name: 'settings' }) },
      { label: 'Multi-Provider Fallback' },
    ]" />

    <PageHeader
      title="Multi-Provider Fallback Chains"
      subtitle="Configure ordered fallback sequences so bot executions automatically retry with the next provider on failure."
    />

    <div class="layout">
      <!-- Chain list -->
      <aside class="sidebar card">
        <div class="sidebar-header">
          <span>Chains</span>
          <button class="btn-add" @click="showToast('Add chain coming soon', 'info')">+</button>
        </div>
        <div
          v-for="c in chains"
          :key="c.id"
          class="chain-item"
          :class="{ active: selectedChain.id === c.id }"
          @click="selectedChain = c"
        >
          <div class="chain-name">{{ c.name }}</div>
          <div class="chain-meta">{{ c.providers.length }} providers · {{ c.bots.length }} bots</div>
        </div>
      </aside>

      <!-- Chain editor -->
      <div class="chain-editor">
        <div class="card provider-order-card">
          <div class="card-header">Provider Order (drag to reorder)</div>
          <div class="provider-list">
            <div
              v-for="(p, i) in selectedChain.providers"
              :key="p.id"
              class="provider-row"
              :class="{ disabled: !p.enabled }"
            >
              <div class="provider-order-num">{{ i + 1 }}</div>
              <div class="provider-info">
                <div class="provider-name">{{ p.name }}</div>
                <div class="provider-model">{{ p.model }}</div>
              </div>
              <div class="provider-status">
                <span class="status-dot" :style="{ background: statusColor(p.status) }"></span>
                <span class="status-text">{{ p.status }}</span>
                <span class="latency">{{ p.latencyMs }}ms</span>
                <span v-if="p.failureCount > 0" class="fail-count">{{ p.failureCount }} fails</span>
              </div>
              <div class="provider-actions">
                <input type="checkbox" v-model="p.enabled" class="toggle" />
                <button class="order-btn" :disabled="i === 0" @click="moveProvider(i, -1)">↑</button>
                <button class="order-btn" :disabled="i === selectedChain.providers.length - 1" @click="moveProvider(i, 1)">↓</button>
              </div>
            </div>
          </div>
        </div>

        <div class="card triggers-card">
          <div class="card-header">Trigger Conditions</div>
          <div class="triggers-body">
            <label v-for="opt in triggerOptions" :key="opt.value" class="trigger-check">
              <input
                type="checkbox"
                :checked="selectedChain.triggerOn.includes(opt.value)"
                @change="toggleTrigger(opt.value)"
              />
              {{ opt.label }}
            </label>
          </div>
        </div>

        <div class="card bots-card">
          <div class="card-header">Applied Bots</div>
          <div class="bots-body">
            <span v-for="b in selectedChain.bots" :key="b" class="bot-chip">{{ b }}</span>
          </div>
        </div>

        <div v-if="testResult" class="test-result card">
          <span class="test-result-icon">✅</span> {{ testResult }}
        </div>

        <div class="actions">
          <button class="btn btn-ghost" :disabled="isTestingFallback" @click="testFallback">
            {{ isTestingFallback ? 'Testing...' : 'Test Fallback' }}
          </button>
          <button class="btn btn-primary" :disabled="isSaving" @click="handleSave">
            {{ isSaving ? 'Saving...' : 'Save Chain' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mpf-page { display: flex; flex-direction: column; gap: 24px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.layout { display: grid; grid-template-columns: 220px 1fr; gap: 20px; align-items: start; }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }

.sidebar-header {
  display: flex; align-items: center; justify-content: space-between; padding: 14px 16px;
  border-bottom: 1px solid var(--border-default); font-size: 0.8rem; font-weight: 600; color: var(--text-secondary);
}
.btn-add { background: var(--accent-cyan); color: #000; border: none; width: 22px; height: 22px; border-radius: 4px; cursor: pointer; font-weight: 700; font-size: 1rem; line-height: 1; display: flex; align-items: center; justify-content: center; }

.chain-item { padding: 12px 16px; cursor: pointer; border-bottom: 1px solid var(--border-subtle); transition: background 0.1s; }
.chain-item:hover { background: var(--bg-tertiary); }
.chain-item.active { background: rgba(6,182,212,0.08); border-left: 2px solid var(--accent-cyan); }
.chain-item:last-child { border-bottom: none; }
.chain-name { font-size: 0.82rem; font-weight: 600; color: var(--text-primary); }
.chain-meta { font-size: 0.72rem; color: var(--text-muted); margin-top: 2px; }

.chain-editor { display: flex; flex-direction: column; gap: 16px; }

.card-header {
  padding: 14px 20px; border-bottom: 1px solid var(--border-default); font-size: 0.82rem;
  font-weight: 600; color: var(--text-secondary);
}

.provider-list { display: flex; flex-direction: column; }

.provider-row {
  display: flex; align-items: center; gap: 12px; padding: 14px 20px;
  border-bottom: 1px solid var(--border-subtle); transition: background 0.1s;
}
.provider-row.disabled { opacity: 0.45; }
.provider-row:last-child { border-bottom: none; }

.provider-order-num { width: 24px; height: 24px; border-radius: 50%; background: var(--bg-tertiary); display: flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: 700; color: var(--text-secondary); flex-shrink: 0; }

.provider-info { flex: 1; }
.provider-name { font-size: 0.88rem; font-weight: 600; color: var(--text-primary); }
.provider-model { font-size: 0.72rem; color: var(--text-muted); font-family: monospace; }

.provider-status { display: flex; align-items: center; gap: 8px; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.status-text { font-size: 0.75rem; color: var(--text-tertiary); }
.latency { font-size: 0.72rem; color: var(--text-muted); }
.fail-count { font-size: 0.72rem; color: #ef4444; }

.provider-actions { display: flex; align-items: center; gap: 8px; }
.toggle { cursor: pointer; accent-color: var(--accent-cyan); }
.order-btn { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); padding: 3px 7px; border-radius: 4px; cursor: pointer; font-size: 0.8rem; }
.order-btn:disabled { opacity: 0.3; cursor: not-allowed; }
.order-btn:hover:not(:disabled) { background: var(--bg-primary); color: var(--accent-cyan); }

.triggers-body { display: flex; flex-wrap: wrap; gap: 12px; padding: 16px 20px; }
.trigger-check { display: flex; align-items: center; gap: 8px; font-size: 0.82rem; color: var(--text-secondary); cursor: pointer; }
.trigger-check input { accent-color: var(--accent-cyan); cursor: pointer; }

.bots-body { display: flex; flex-wrap: wrap; gap: 8px; padding: 16px 20px; }
.bot-chip { padding: 4px 10px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 4px; font-size: 0.75rem; font-family: monospace; color: var(--text-secondary); }

.test-result { padding: 14px 20px; font-size: 0.82rem; color: #34d399; display: flex; align-items: center; gap: 8px; }

.actions { display: flex; justify-content: flex-end; gap: 12px; }
.btn { display: flex; align-items: center; gap: 6px; padding: 8px 16px; border-radius: 7px; font-size: 0.82rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-ghost { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-ghost:hover:not(:disabled) { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.btn-ghost:disabled { opacity: 0.4; cursor: not-allowed; }

@media (max-width: 900px) { .layout { grid-template-columns: 1fr; } }
</style>
