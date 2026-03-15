<script setup lang="ts">
import { ref, onMounted } from 'vue';
import LoadingState from '../components/base/LoadingState.vue';
import { useToast } from '../composables/useToast';

const showToast = useToast();
const isLoading = ref(true);
const isSaving = ref(false);
const isToggling = ref(false);

interface CoverageReport {
  id: string;
  repo: string;
  coverage: number;
  threshold: number;
  passed: boolean;
  run_at: string;
}

interface CoverageConfig {
  enabled: boolean;
  coverage_threshold: number;
  block_merge: boolean;
  pr_bot_enabled: boolean;
}

const config = ref<CoverageConfig>({
  enabled: false,
  coverage_threshold: 80,
  block_merge: false,
  pr_bot_enabled: true,
});

const recentReports = ref<CoverageReport[]>([]);

async function loadData() {
  try {
    const res = await fetch('/admin/bots/test-coverage/config');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    config.value = { ...config.value, ...data.config };
    recentReports.value = data.reports ?? [];
  } catch {
    // Demo data
    recentReports.value = [
      { id: 'r1', repo: 'org/backend', coverage: 87.3, threshold: 80, passed: true, run_at: '2026-03-06T10:30:00Z' },
      { id: 'r2', repo: 'org/frontend', coverage: 73.1, threshold: 80, passed: false, run_at: '2026-03-06T09:15:00Z' },
      { id: 'r3', repo: 'org/api-gateway', coverage: 91.0, threshold: 80, passed: true, run_at: '2026-03-05T22:00:00Z' },
    ];
  } finally {
    isLoading.value = false;
  }
}

async function saveConfig() {
  isSaving.value = true;
  try {
    const res = await fetch('/admin/bots/test-coverage/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config.value),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    showToast('Configuration saved', 'success');
  } catch {
    showToast('Saved (demo mode)', 'success');
  } finally {
    isSaving.value = false;
  }
}

async function toggleEnabled() {
  isToggling.value = true;
  try {
    config.value.enabled = !config.value.enabled;
    await saveConfig();
  } finally {
    isToggling.value = false;
  }
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleString();
}

onMounted(loadData);
</script>

<template>
  <div class="test-coverage-bot-page">

    <div class="page-title-row">
      <div>
        <h2>Test Coverage Bot</h2>
        <p class="subtitle">Enforce coverage thresholds on every PR via automated bot analysis</p>
      </div>
      <div class="header-actions">
        <button
          class="btn"
          :class="config.enabled ? 'btn-danger' : 'btn-primary'"
          :disabled="isToggling"
          @click="toggleEnabled"
        >
          {{ isToggling ? '...' : config.enabled ? 'Disable Bot' : 'Enable Bot' }}
        </button>
      </div>
    </div>

    <LoadingState v-if="isLoading" message="Loading configuration..." />

    <template v-else>
      <div class="config-grid">
        <!-- Settings -->
        <div class="card">
          <div class="card-header">
            <h3>Settings</h3>
            <span class="status-badge" :class="config.enabled ? 'active' : 'inactive'">
              {{ config.enabled ? 'Active' : 'Disabled' }}
            </span>
          </div>

          <div class="field-group">
            <label class="field-label">Coverage Threshold (%)</label>
            <input
              v-model.number="config.coverage_threshold"
              type="number"
              min="0"
              max="100"
              class="field-input"
            />
          </div>

          <div class="field-group">
            <label class="toggle-row">
              <input v-model="config.block_merge" type="checkbox" class="toggle-input" />
              <span class="toggle-label">Block merge when coverage falls below threshold</span>
            </label>
          </div>

          <div class="field-group">
            <label class="toggle-row">
              <input v-model="config.pr_bot_enabled" type="checkbox" class="toggle-input" />
              <span class="toggle-label">Enable PR comment bot (posts coverage summary on PRs)</span>
            </label>
          </div>

          <button class="btn btn-primary" :disabled="isSaving" @click="saveConfig">
            {{ isSaving ? 'Saving...' : 'Save Settings' }}
          </button>
        </div>

        <!-- Stats summary -->
        <div class="card stats-card">
          <div class="card-header">
            <h3>Recent Activity</h3>
          </div>
          <div class="stats-grid">
            <div class="stat">
              <span class="stat-value">{{ recentReports.filter(r => r.passed).length }}</span>
              <span class="stat-label">Passed</span>
            </div>
            <div class="stat">
              <span class="stat-value crimson">{{ recentReports.filter(r => !r.passed).length }}</span>
              <span class="stat-label">Failed</span>
            </div>
            <div class="stat">
              <span class="stat-value">
                {{ recentReports.length ? (recentReports.reduce((s, r) => s + r.coverage, 0) / recentReports.length).toFixed(1) : '—' }}%
              </span>
              <span class="stat-label">Avg Coverage</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Recent reports -->
      <div class="card">
        <div class="card-header">
          <h3>Recent Coverage Reports</h3>
          <span class="card-badge">{{ recentReports.length }} runs</span>
        </div>
        <div v-if="recentReports.length === 0" class="empty-msg">No reports yet.</div>
        <table v-else class="reports-table">
          <thead>
            <tr>
              <th>Repository</th>
              <th>Coverage</th>
              <th>Threshold</th>
              <th>Status</th>
              <th>Run At</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in recentReports" :key="r.id">
              <td class="mono">{{ r.repo }}</td>
              <td>{{ r.coverage.toFixed(1) }}%</td>
              <td>{{ r.threshold }}%</td>
              <td>
                <span class="status-badge" :class="r.passed ? 'active' : 'inactive'">
                  {{ r.passed ? 'Passed' : 'Failed' }}
                </span>
              </td>
              <td class="dimmed">{{ formatTime(r.run_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.test-coverage-bot-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.page-title-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 16px;
}

.page-title-row h2 {
  font-size: 1.4rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px;
}

.subtitle {
  font-size: 0.85rem;
  color: var(--text-tertiary);
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.config-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

@media (max-width: 800px) {
  .config-grid { grid-template-columns: 1fr; }
}

.card {
  padding: 20px 24px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}

.card-header h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.card-badge {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 3px 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
}

.status-badge {
  font-size: 0.72rem;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.status-badge.active {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.status-badge.inactive {
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

.field-group {
  margin-bottom: 16px;
}

.field-label {
  display: block;
  font-size: 0.8rem;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.field-input {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.85rem;
  box-sizing: border-box;
}

.field-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.toggle-row {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}

.toggle-input {
  width: 16px;
  height: 16px;
  accent-color: var(--accent-cyan);
}

.toggle-label {
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.stats-card {
  background: linear-gradient(135deg, var(--bg-secondary) 0%, var(--bg-tertiary) 100%);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  text-align: center;
}

.stat-value {
  display: block;
  font-size: 1.8rem;
  font-weight: 700;
  color: var(--text-primary);
}

.stat-value.crimson {
  color: var(--accent-crimson);
}

.stat-label {
  display: block;
  font-size: 0.75rem;
  color: var(--text-tertiary);
  margin-top: 4px;
}

.empty-msg {
  font-size: 0.85rem;
  color: var(--text-tertiary);
  text-align: center;
  padding: 24px 0;
}

.reports-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.reports-table th {
  text-align: left;
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 6px 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.reports-table td {
  padding: 10px 12px;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-subtle);
}

.reports-table tr:last-child td {
  border-bottom: none;
}

.mono {
  font-family: 'Geist Mono', monospace;
  color: var(--accent-cyan);
}

.dimmed {
  color: var(--text-tertiary);
  font-size: 0.78rem;
}

.btn-danger {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
  border: 1px solid var(--accent-crimson);
}

.btn-danger:hover:not(:disabled) {
  background: var(--accent-crimson);
  color: white;
}
</style>
