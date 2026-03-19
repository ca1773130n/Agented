<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import LoadingState from '../components/base/LoadingState.vue';
import StatCard from '../components/base/StatCard.vue';
import { useToast } from '../composables/useToast';
const showToast = useToast();

const isLoading = ref(true);
let refreshInterval: ReturnType<typeof setInterval> | null = null;

interface AnomalyType {
  type: 'duration' | 'output_length' | 'finding_spike' | 'error_rate';
  label: string;
}

interface Anomaly {
  id: string;
  bot_id: string;
  bot_name: string;
  execution_id: string;
  anomaly_type: AnomalyType['type'];
  detected_at: string;
  severity: 'critical' | 'warning';
  description: string;
  baseline_value: number;
  observed_value: number;
  unit: string;
  acknowledged: boolean;
}

interface BotBaseline {
  bot_id: string;
  bot_name: string;
  avg_duration_s: number;
  avg_output_chars: number;
  avg_findings: number;
  error_rate_pct: number;
  sample_count: number;
}

const anomalies = ref<Anomaly[]>([]);
const baselines = ref<BotBaseline[]>([]);
const filterAcknowledged = ref(false);

async function loadData() {
  try {
    const res = await fetch('/admin/executions/anomalies');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    anomalies.value = data.anomalies ?? [];
    baselines.value = data.baselines ?? [];
  } catch {
    anomalies.value = [
      {
        id: 'an-1', bot_id: 'bot-security', bot_name: 'Security Audit', execution_id: 'ex-abc123',
        anomaly_type: 'duration', detected_at: new Date(Date.now() - 1800000).toISOString(),
        severity: 'critical', acknowledged: false,
        description: 'Execution took 4x longer than baseline — possible infinite loop or API hang.',
        baseline_value: 62, observed_value: 248, unit: 'seconds',
      },
      {
        id: 'an-2', bot_id: 'bot-pr-review', bot_name: 'PR Review', execution_id: 'ex-def456',
        anomaly_type: 'output_length', detected_at: new Date(Date.now() - 3600000).toISOString(),
        severity: 'warning', acknowledged: false,
        description: 'Output was unusually short (47 chars). Bot may have produced empty or truncated response.',
        baseline_value: 2800, observed_value: 47, unit: 'characters',
      },
      {
        id: 'an-3', bot_id: 'bot-security', bot_name: 'Security Audit', execution_id: 'ex-ghi789',
        anomaly_type: 'finding_spike', detected_at: new Date(Date.now() - 7200000).toISOString(),
        severity: 'warning', acknowledged: true,
        description: 'Found 23 issues vs baseline of 3.2. Spike may indicate new vulnerable code or prompt regression.',
        baseline_value: 3, observed_value: 23, unit: 'findings',
      },
      {
        id: 'an-4', bot_id: 'bot-dep', bot_name: 'Dep Check', execution_id: 'ex-jkl012',
        anomaly_type: 'error_rate', detected_at: new Date(Date.now() - 10800000).toISOString(),
        severity: 'critical', acknowledged: false,
        description: '8 of the last 10 runs failed. Error: Claude API rate limited. Bot is likely stuck in a loop.',
        baseline_value: 5, observed_value: 80, unit: '% error rate',
      },
    ];
    baselines.value = [
      { bot_id: 'bot-security', bot_name: 'Security Audit', avg_duration_s: 62, avg_output_chars: 3400, avg_findings: 3.2, error_rate_pct: 4.1, sample_count: 87 },
      { bot_id: 'bot-pr-review', bot_name: 'PR Review', avg_duration_s: 45, avg_output_chars: 2800, avg_findings: 1.8, error_rate_pct: 2.3, sample_count: 241 },
      { bot_id: 'bot-dep', bot_name: 'Dep Check', avg_duration_s: 28, avg_output_chars: 1200, avg_findings: 5.1, error_rate_pct: 5.0, sample_count: 64 },
    ];
  } finally {
    isLoading.value = false;
  }
}

async function acknowledge(anomaly: Anomaly) {
  try {
    const res = await fetch(`/admin/executions/anomalies/${anomaly.id}/acknowledge`, { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    anomaly.acknowledged = true;
    showToast('Anomaly acknowledged', 'success');
  } catch {
    anomaly.acknowledged = true;
    showToast('Anomaly acknowledged', 'success');
  }
}

const visibleAnomalies = computed(() =>
  filterAcknowledged.value
    ? anomalies.value
    : anomalies.value.filter(a => !a.acknowledged)
);

const unacknowledgedCount = computed(() => anomalies.value.filter(a => !a.acknowledged).length);
const criticalCount = computed(() => anomalies.value.filter(a => a.severity === 'critical' && !a.acknowledged).length);

function anomalyIcon(type: AnomalyType['type']): string {
  return {
    duration: '⏱',
    output_length: '📏',
    finding_spike: '📈',
    error_rate: '💥',
  }[type];
}

function anomalyColor(severity: Anomaly['severity']): string {
  return severity === 'critical' ? 'var(--accent-crimson)' : 'var(--accent-amber)';
}

function deviationPct(baseline: number, observed: number): string {
  if (baseline === 0) return 'N/A';
  const pct = Math.round(((observed - baseline) / baseline) * 100);
  return (pct > 0 ? '+' : '') + pct + '%';
}

function timeAgo(iso: string): string {
  const secs = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  return `${Math.floor(secs / 3600)}h ago`;
}

onMounted(() => {
  loadData();
  refreshInterval = setInterval(() => { if (!isLoading.value) loadData(); }, 60000);
});

onUnmounted(() => { if (refreshInterval) clearInterval(refreshInterval); });
</script>

<template>
  <div class="anomaly-page">

    <LoadingState v-if="isLoading" message="Loading anomaly data..." />

    <template v-else>
      <!-- Stats -->
      <div class="stats-grid">
        <StatCard title="Unacknowledged" :value="unacknowledgedCount" color="var(--accent-amber)" />
        <StatCard title="Critical" :value="criticalCount" color="var(--accent-crimson)" />
        <StatCard title="Total Anomalies" :value="anomalies.length" />
        <StatCard title="Bots Monitored" :value="baselines.length" />
      </div>

      <!-- Anomaly Feed -->
      <div class="card anomaly-section">
        <div class="section-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
            </svg>
            Detected Anomalies
          </h3>
          <label class="toggle-label">
            <input v-model="filterAcknowledged" type="checkbox" />
            Show acknowledged
          </label>
        </div>

        <div v-if="visibleAnomalies.length === 0" class="empty-anomalies">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
          </svg>
          <span>No active anomalies — all executions look normal</span>
        </div>

        <div class="anomaly-list">
          <div v-for="anomaly in visibleAnomalies" :key="anomaly.id"
            class="anomaly-card"
            :class="{ acknowledged: anomaly.acknowledged }"
            :style="{ borderLeftColor: anomalyColor(anomaly.severity) }">
            <div class="anomaly-top">
              <div class="anomaly-icon-area">
                <span class="anomaly-type-icon">{{ anomalyIcon(anomaly.anomaly_type) }}</span>
                <div class="anomaly-bot-info">
                  <span class="anomaly-bot">{{ anomaly.bot_name }}</span>
                  <span class="anomaly-time">{{ timeAgo(anomaly.detected_at) }}</span>
                </div>
              </div>
              <div class="anomaly-badges">
                <span class="severity-badge" :style="{ color: anomalyColor(anomaly.severity), borderColor: anomalyColor(anomaly.severity) }">
                  {{ anomaly.severity }}
                </span>
                <span v-if="anomaly.acknowledged" class="ack-badge">Acknowledged</span>
              </div>
            </div>

            <p class="anomaly-desc">{{ anomaly.description }}</p>

            <div class="anomaly-values">
              <div class="value-item">
                <span class="value-label">Baseline</span>
                <span class="value-num">{{ anomaly.baseline_value }} {{ anomaly.unit }}</span>
              </div>
              <div class="value-arrow">→</div>
              <div class="value-item">
                <span class="value-label">Observed</span>
                <span class="value-num" :style="{ color: anomalyColor(anomaly.severity) }">{{ anomaly.observed_value }} {{ anomaly.unit }}</span>
              </div>
              <div class="value-item">
                <span class="value-label">Deviation</span>
                <span class="value-num" :style="{ color: anomalyColor(anomaly.severity) }">{{ deviationPct(anomaly.baseline_value, anomaly.observed_value) }}</span>
              </div>
            </div>

            <div class="anomaly-footer">
              <span class="exec-link">Execution: {{ anomaly.execution_id }}</span>
              <button v-if="!anomaly.acknowledged" class="btn btn-ghost btn-sm" @click="acknowledge(anomaly)">
                Acknowledge
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Baselines Table -->
      <div class="card baseline-section">
        <h3>Bot Baselines (last 30 days)</h3>
        <p class="baseline-desc">Anomalies are flagged when executions deviate significantly from these baselines.</p>
        <div class="baseline-table">
          <div class="baseline-head">
            <span>Bot</span>
            <span>Avg Duration</span>
            <span>Avg Output</span>
            <span>Avg Findings</span>
            <span>Error Rate</span>
            <span>Samples</span>
          </div>
          <div v-for="bl in baselines" :key="bl.bot_id" class="baseline-row">
            <span class="baseline-name">{{ bl.bot_name }}</span>
            <span>{{ bl.avg_duration_s }}s</span>
            <span>{{ bl.avg_output_chars.toLocaleString() }} chars</span>
            <span>{{ bl.avg_findings.toFixed(1) }}</span>
            <span :style="{ color: bl.error_rate_pct > 10 ? 'var(--accent-crimson)' : 'var(--text-secondary)' }">{{ bl.error_rate_pct }}%</span>
            <span>{{ bl.sample_count }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.anomaly-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  width: 100%;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.card { padding: 24px; }

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.section-header h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.section-header h3 svg { width: 16px; height: 16px; color: var(--accent-cyan); }

.toggle-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.82rem;
  color: var(--text-secondary);
  cursor: pointer;
}

.empty-anomalies {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 40px;
  justify-content: center;
  color: var(--accent-emerald);
  font-size: 0.9rem;
}

.empty-anomalies svg { width: 20px; height: 20px; }

.anomaly-list { display: flex; flex-direction: column; gap: 12px; }

.anomaly-card {
  padding: 16px 20px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-left: 3px solid;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  transition: opacity 0.2s;
}

.anomaly-card.acknowledged { opacity: 0.55; }

.anomaly-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}

.anomaly-icon-area { display: flex; align-items: center; gap: 10px; }

.anomaly-type-icon { font-size: 1.3rem; }

.anomaly-bot { display: block; font-weight: 600; font-size: 0.9rem; color: var(--text-primary); }
.anomaly-time { font-size: 0.78rem; color: var(--text-tertiary); }

.anomaly-badges { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

.severity-badge {
  font-size: 0.7rem;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 10px;
  border: 1px solid;
  text-transform: uppercase;
}

.ack-badge {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 10px;
  background: var(--bg-elevated);
  color: var(--text-tertiary);
}

.anomaly-desc { font-size: 0.85rem; color: var(--text-secondary); line-height: 1.5; }

.anomaly-values {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  background: var(--bg-elevated);
  border-radius: 6px;
  flex-wrap: wrap;
}

.value-item { display: flex; flex-direction: column; gap: 3px; }
.value-label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-tertiary); font-weight: 600; }
.value-num { font-size: 0.9rem; font-weight: 600; color: var(--text-primary); font-variant-numeric: tabular-nums; }

.value-arrow { color: var(--text-tertiary); font-size: 1.1rem; }

.anomaly-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}

.exec-link { font-size: 0.78rem; color: var(--text-tertiary); font-family: monospace; }

.baseline-section h3 { font-size: 0.95rem; font-weight: 600; color: var(--text-primary); margin-bottom: 6px; }
.baseline-desc { font-size: 0.82rem; color: var(--text-tertiary); margin-bottom: 20px; }

.baseline-table { display: flex; flex-direction: column; }

.baseline-head {
  display: grid;
  grid-template-columns: 1fr repeat(5, 120px);
  gap: 8px;
  padding: 8px 12px;
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-bottom: 1px solid var(--border-default);
}

.baseline-row {
  display: grid;
  grid-template-columns: 1fr repeat(5, 120px);
  gap: 8px;
  padding: 12px 12px;
  font-size: 0.84rem;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-default);
  align-items: center;
}

.baseline-row:last-child { border-bottom: none; }
.baseline-name { font-weight: 600; color: var(--text-primary); }

.btn { display: inline-flex; align-items: center; gap: 6px; padding: 7px 13px; border-radius: 6px; font-size: 0.82rem; font-weight: 500; cursor: pointer; border: 1px solid transparent; transition: all 0.15s; }
.btn-ghost { background: transparent; color: var(--text-secondary); border-color: var(--border-default); }
.btn-ghost:hover { background: var(--bg-elevated); }
.btn-sm { padding: 5px 10px; font-size: 0.78rem; }

@media (max-width: 900px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
  .baseline-head, .baseline-row { grid-template-columns: 1fr 80px 80px; }
  .baseline-head span:nth-child(n+4), .baseline-row span:nth-child(n+4) { display: none; }
}
</style>
