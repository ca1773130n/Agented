<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useRouter } from 'vue-router';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { executionApi } from '../services/api/triggers';
const router = useRouter();

interface ExecutionBar {
  id: string;
  botId: string;
  botName: string;
  status: 'success' | 'failed' | 'running' | 'queued';
  startTs: number; // ms from window start
  durationMs: number;
  trigger: string;
}

// Window: last 60 minutes
const windowMinutes = ref(60);
const windowMs = computed(() => windowMinutes.value * 60 * 1000);
const now = ref(Date.now());
const windowStart = computed(() => now.value - windowMs.value);

const executions = ref<ExecutionBar[]>([]);

async function fetchExecutions() {
  now.value = Date.now();
  const date_from = new Date(now.value - windowMs.value).toISOString();
  const result = await executionApi.listAll({ limit: 500, date_from });
  const ws = now.value - windowMs.value;
  executions.value = result.executions.map(e => {
    let status: ExecutionBar['status'];
    if (e.status === 'success') {
      status = 'success';
    } else if (e.status === 'failed' || e.status === 'timeout' || e.status === 'cancelled' || e.status === 'interrupted') {
      status = 'failed';
    } else if (e.status === 'running') {
      status = 'running';
    } else {
      status = 'queued';
    }
    return {
      id: e.execution_id,
      botId: e.trigger_id,
      botName: e.trigger_name,
      status,
      startTs: Date.parse(e.started_at) - ws,
      durationMs: e.duration_ms ?? 0,
      trigger: e.trigger_type,
    };
  });
}

onMounted(fetchExecutions);
watch(windowMinutes, fetchExecutions);

// Group by bot
const bots = computed(() => {
  const map = new Map<string, ExecutionBar[]>();
  for (const e of executions.value) {
    if (!map.has(e.botId)) map.set(e.botId, []);
    map.get(e.botId)!.push(e);
  }
  return Array.from(map.entries()).map(([botId, bars]) => ({
    botId,
    botName: bars[0].botName,
    bars: bars.sort((a, b) => a.startTs - b.startTs),
  }));
});

const timeLabels = computed(() => {
  const labels: { pct: number; label: string }[] = [];
  const steps = windowMinutes.value <= 60 ? 12 : 8;
  for (let i = 0; i <= steps; i++) {
    const pct = (i / steps) * 100;
    const ms = windowMs.value * (i / steps);
    const t = new Date(windowStart.value + ms);
    labels.push({
      pct,
      label: t.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false }),
    });
  }
  return labels;
});

const nowPct = computed(() => {
  const elapsed = now.value - windowStart.value;
  return Math.min(100, (elapsed / windowMs.value) * 100);
});

const windowOptions = [
  { label: '30 min', value: 30 },
  { label: '1 hr', value: 60 },
  { label: '3 hr', value: 180 },
  { label: '6 hr', value: 360 },
  { label: '24 hr', value: 1440 },
];

function barLeft(bar: ExecutionBar): number {
  return Math.max(0, (bar.startTs / windowMs.value) * 100);
}

function barWidth(bar: ExecutionBar): number {
  const dur = bar.status === 'queued' ? 2 * 60000 : bar.durationMs;
  const w = (dur / windowMs.value) * 100;
  return Math.max(0.5, Math.min(w, 100 - barLeft(bar)));
}

function barColor(status: ExecutionBar['status']): string {
  return { success: '#34d399', failed: '#ef4444', running: '#06b6d4', queued: '#6b7280' }[status];
}

function statusIcon(status: ExecutionBar['status']): string {
  return { success: '✓', failed: '✗', running: '⟳', queued: '…' }[status];
}

const selectedExec = ref<ExecutionBar | null>(null);

function selectBar(bar: ExecutionBar) {
  selectedExec.value = selectedExec.value?.id === bar.id ? null : bar;
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(0)}s`;
  const m = Math.floor(ms / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

const statusFilter = ref<string>('all');

const filteredBots = computed(() => {
  if (statusFilter.value === 'all') return bots.value;
  return bots.value.map(b => ({
    ...b,
    bars: b.bars.filter(bar => bar.status === statusFilter.value),
  })).filter(b => b.bars.length > 0);
});

const summary = computed(() => ({
  total: executions.value.length,
  success: executions.value.filter(e => e.status === 'success').length,
  failed: executions.value.filter(e => e.status === 'failed').length,
  running: executions.value.filter(e => e.status === 'running').length,
}));
</script>

<template>
  <div class="timeline-page">
    <AppBreadcrumb :items="[
      { label: 'Executions', action: () => router.push({ name: 'execution-search' }) },
      { label: 'Timeline' },
    ]" />

    <PageHeader
      title="Execution Timeline"
      subtitle="Gantt-style view of all bot executions in a time window — status, overlap, duration, and bottlenecks at a glance."
    />

    <!-- Summary bar -->
    <div class="summary-row">
      <div class="summary-chip total">{{ summary.total }} total</div>
      <div class="summary-chip success">{{ summary.success }} succeeded</div>
      <div class="summary-chip failed">{{ summary.failed }} failed</div>
      <div class="summary-chip running">{{ summary.running }} running</div>
    </div>

    <!-- Controls -->
    <div class="controls-row">
      <div class="window-tabs">
        <button
          v-for="opt in windowOptions"
          :key="opt.value"
          :class="['window-tab', { active: windowMinutes === opt.value }]"
          @click="windowMinutes = opt.value"
        >{{ opt.label }}</button>
      </div>
      <div class="status-filter">
        <select v-model="statusFilter" class="select">
          <option value="all">All statuses</option>
          <option value="success">Success</option>
          <option value="failed">Failed</option>
          <option value="running">Running</option>
          <option value="queued">Queued</option>
        </select>
      </div>
    </div>

    <!-- Gantt chart -->
    <div class="card gantt-card">
      <!-- Time ruler -->
      <div class="gantt-ruler">
        <div class="gantt-label-col"></div>
        <div class="gantt-track-area ruler-area">
          <div
            v-for="tick in timeLabels"
            :key="tick.pct"
            class="ruler-tick"
            :style="{ left: `${tick.pct}%` }"
          >
            <span class="tick-label">{{ tick.label }}</span>
          </div>
          <!-- Now indicator -->
          <div class="now-line" :style="{ left: `${nowPct}%` }">
            <span class="now-label">now</span>
          </div>
        </div>
      </div>

      <!-- Bot rows -->
      <div class="gantt-rows">
        <div v-if="filteredBots.length === 0" class="gantt-empty">No executions match the current filter.</div>
        <div v-for="bot in filteredBots" :key="bot.botId" class="gantt-row">
          <div class="gantt-label-col">
            <div class="gantt-bot-name">{{ bot.botName }}</div>
            <div class="gantt-bot-id">{{ bot.botId }}</div>
          </div>
          <div class="gantt-track-area">
            <div
              v-for="bar in bot.bars"
              :key="bar.id"
              class="exec-bar"
              :class="{ selected: selectedExec?.id === bar.id, queued: bar.status === 'queued' }"
              :style="{
                left: `${barLeft(bar)}%`,
                width: `${barWidth(bar)}%`,
                background: barColor(bar.status),
              }"
              :title="`${bar.id} · ${bar.status} · ${formatDuration(bar.durationMs)}`"
              @click="selectBar(bar)"
            >
              <span class="bar-icon">{{ statusIcon(bar.status) }}</span>
              <span class="bar-dur">{{ bar.status !== 'queued' ? formatDuration(bar.durationMs) : 'pending' }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Detail panel -->
    <div v-if="selectedExec" class="card detail-panel">
      <div class="detail-header">
        <span class="detail-id">{{ selectedExec.id }}</span>
        <button class="detail-close" @click="selectedExec = null">✕</button>
      </div>
      <div class="detail-body">
        <div class="detail-row">
          <span class="detail-key">Bot</span>
          <span class="detail-val">{{ selectedExec.botName }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-key">Status</span>
          <span class="detail-val status-badge" :style="{ color: barColor(selectedExec.status) }">
            {{ statusIcon(selectedExec.status) }} {{ selectedExec.status }}
          </span>
        </div>
        <div class="detail-row">
          <span class="detail-key">Trigger</span>
          <span class="detail-val">{{ selectedExec.trigger }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-key">Duration</span>
          <span class="detail-val">{{ formatDuration(selectedExec.durationMs) }}</span>
        </div>
        <div class="detail-actions">
          <button class="btn btn-ghost" @click="router.push({ name: 'live-execution-terminal' })">View Logs</button>
          <button class="btn btn-ghost" @click="router.push({ name: 'execution-replay-diff' })">Replay</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.timeline-page { display: flex; flex-direction: column; gap: 20px; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }

.summary-row { display: flex; gap: 10px; flex-wrap: wrap; }
.summary-chip { padding: 6px 14px; border-radius: 20px; font-size: 0.78rem; font-weight: 600; border: 1px solid transparent; }
.summary-chip.total { background: var(--bg-tertiary); color: var(--text-secondary); border-color: var(--border-default); }
.summary-chip.success { background: rgba(52,211,153,0.1); color: #34d399; border-color: rgba(52,211,153,0.3); }
.summary-chip.failed { background: rgba(239,68,68,0.1); color: #ef4444; border-color: rgba(239,68,68,0.3); }
.summary-chip.running { background: rgba(6,182,212,0.1); color: var(--accent-cyan); border-color: rgba(6,182,212,0.3); }

.controls-row { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.window-tabs { display: flex; border: 1px solid var(--border-default); border-radius: 8px; overflow: hidden; }
.window-tab { padding: 6px 14px; background: var(--bg-tertiary); border: none; color: var(--text-secondary); font-size: 0.78rem; font-weight: 500; cursor: pointer; transition: all 0.15s; }
.window-tab.active { background: var(--accent-cyan); color: #000; }
.window-tab:hover:not(.active) { color: var(--text-primary); }

.select { padding: 6px 12px; background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.78rem; cursor: pointer; }

/* Gantt */
.gantt-card { overflow-x: auto; }
.gantt-ruler { display: flex; border-bottom: 1px solid var(--border-default); background: var(--bg-tertiary); }
.gantt-label-col { width: 160px; min-width: 160px; padding: 8px 12px; font-size: 0.7rem; color: var(--text-muted); flex-shrink: 0; }
.gantt-track-area { flex: 1; position: relative; min-width: 0; }
.ruler-area { height: 30px; }
.ruler-tick { position: absolute; top: 0; transform: translateX(-50%); display: flex; flex-direction: column; align-items: center; }
.ruler-tick::before { content: ''; display: block; width: 1px; height: 6px; background: var(--border-default); }
.tick-label { font-size: 0.65rem; color: var(--text-muted); white-space: nowrap; margin-top: 2px; }
.now-line { position: absolute; top: 0; bottom: 0; width: 2px; background: var(--accent-cyan); opacity: 0.7; }
.now-label { position: absolute; top: 2px; left: 4px; font-size: 0.6rem; color: var(--accent-cyan); font-weight: 700; white-space: nowrap; }

.gantt-rows { display: flex; flex-direction: column; }
.gantt-empty { padding: 32px; text-align: center; color: var(--text-muted); font-size: 0.85rem; }
.gantt-row { display: flex; border-bottom: 1px solid var(--border-subtle); min-height: 52px; }
.gantt-row:last-child { border-bottom: none; }
.gantt-label-col { display: flex; flex-direction: column; justify-content: center; padding: 8px 12px; width: 160px; min-width: 160px; flex-shrink: 0; border-right: 1px solid var(--border-subtle); }
.gantt-bot-name { font-size: 0.8rem; font-weight: 600; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.gantt-bot-id { font-size: 0.68rem; color: var(--text-muted); font-family: monospace; }

.gantt-track-area { flex: 1; position: relative; padding: 8px 0; min-height: 36px; }

.exec-bar {
  position: absolute;
  top: 50%; transform: translateY(-50%);
  height: 28px;
  border-radius: 5px;
  display: flex; align-items: center; gap: 4px; padding: 0 7px;
  cursor: pointer;
  opacity: 0.88;
  transition: opacity 0.15s, box-shadow 0.15s;
  overflow: hidden;
  min-width: 4px;
}
.exec-bar:hover, .exec-bar.selected { opacity: 1; box-shadow: 0 0 0 2px rgba(255,255,255,0.3); }
.exec-bar.queued { opacity: 0.55; border: 1px dashed var(--border-default); }
.bar-icon { font-size: 0.7rem; color: rgba(0,0,0,0.7); flex-shrink: 0; }
.bar-dur { font-size: 0.68rem; color: rgba(0,0,0,0.75); font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* Detail panel */
.detail-panel { margin-top: 0; }
.detail-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 20px; border-bottom: 1px solid var(--border-default); }
.detail-id { font-family: monospace; font-size: 0.82rem; color: var(--accent-cyan); }
.detail-close { background: none; border: none; color: var(--text-muted); font-size: 1rem; cursor: pointer; }
.detail-body { padding: 16px 20px; display: flex; flex-direction: column; gap: 10px; }
.detail-row { display: flex; align-items: center; gap: 12px; }
.detail-key { font-size: 0.75rem; color: var(--text-muted); font-weight: 500; width: 80px; flex-shrink: 0; }
.detail-val { font-size: 0.85rem; color: var(--text-primary); }
.status-badge { font-weight: 600; }
.detail-actions { display: flex; gap: 10px; margin-top: 6px; }

.btn { padding: 7px 14px; border-radius: 7px; font-size: 0.8rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn-ghost { background: var(--bg-tertiary); border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-ghost:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }
</style>
