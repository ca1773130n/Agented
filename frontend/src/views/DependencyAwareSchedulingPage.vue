<script setup lang="ts">
import { ref, onMounted } from 'vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { schedulerApi, triggerApi, ApiError } from '../services/api';
import type { SchedulerStatus, Trigger } from '../services/api';

const showToast = useToast();

type DepStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'skipped';

interface ScheduledJob {
  id: string;
  name: string;
  schedule: string;
  dependsOn: string[];
  status: DepStatus;
  lastRun: string | null;
  nextRun: string;
  enabled: boolean;
}

const loading = ref(true);
const error = ref<string | null>(null);
const jobs = ref<ScheduledJob[]>([]);
const schedulerStatus = ref<SchedulerStatus | null>(null);
const triggers = ref<Trigger[]>([]);

async function loadData() {
  loading.value = true;
  error.value = null;
  try {
    const [status, sessionsResp, triggersResp] = await Promise.all([
      schedulerApi.getStatus(),
      schedulerApi.getSessions(),
      triggerApi.list(),
    ]);
    schedulerStatus.value = status;
    triggers.value = triggersResp.triggers ?? [];

    // Map triggers to scheduled jobs
    // Use running count from global summary to determine if anything is active
    const runningSessions = (sessionsResp.sessions ?? status.sessions ?? []).filter(s => s.state === 'running');
    jobs.value = triggers.value.map((t) => {
      let schedule = 'Manual';
      if (t.schedule_type) {
        schedule = t.schedule_time ? `${t.schedule_type} ${t.schedule_time}` : t.schedule_type;
      } else if (t.trigger_source === 'github') {
        schedule = 'GitHub event';
      } else if (t.trigger_source === 'webhook') {
        schedule = 'Webhook';
      }

      return {
        id: t.id,
        name: t.name,
        schedule,
        dependsOn: [],
        status: (runningSessions.length > 0 ? 'running' : t.enabled ? 'succeeded' : 'skipped') as DepStatus,
        lastRun: t.last_run_at ?? null,
        nextRun: schedule,
        enabled: !!t.enabled,
      };
    });
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

const statusColor: Record<DepStatus, string> = {
  pending: '#94a3b8',
  running: '#06b6d4',
  succeeded: '#34d399',
  failed: '#f87171',
  skipped: '#64748b',
};

const statusLabel: Record<DepStatus, string> = {
  pending: 'Pending',
  running: 'Running',
  succeeded: 'Succeeded',
  failed: 'Failed',
  skipped: 'Skipped',
};

function jobName(id: string) {
  return jobs.value.find(j => j.id === id)?.name ?? id;
}

async function toggleEnabled(job: ScheduledJob) {
  const prev = job.enabled;
  job.enabled = !job.enabled;
  try {
    await triggerApi.update(job.id, { enabled: job.enabled ? 1 : 0 });
    showToast(`${job.name} ${job.enabled ? 'enabled' : 'disabled'}`, 'success');
  } catch {
    job.enabled = prev;
    showToast('Failed to toggle trigger', 'error');
  }
}

async function triggerNow(job: ScheduledJob) {
  try {
    job.status = 'running';
    await triggerApi.run(job.id);
    showToast(`${job.name} triggered manually`, 'success');
  } catch (err) {
    job.status = 'failed';
    showToast(err instanceof ApiError ? err.message : 'Trigger failed', 'error');
  }
}

const showAddModal = ref(false);
const newJobName = ref('');
const newSchedule = ref('');
const newDeps = ref<string[]>([]);

function toggleDep(id: string) {
  const idx = newDeps.value.indexOf(id);
  if (idx === -1) newDeps.value.push(id);
  else newDeps.value.splice(idx, 1);
}

function saveJob() {
  if (!newJobName.value.trim()) {
    showToast('Job name is required', 'error');
    return;
  }
  jobs.value.push({
    id: `job-${Date.now()}`,
    name: newJobName.value.trim(),
    schedule: newDeps.value.length > 0 ? `After ${newDeps.value.map(jobName).join(', ')}` : newSchedule.value || 'Manual',
    dependsOn: [...newDeps.value],
    status: 'pending',
    lastRun: null,
    nextRun: newDeps.value.length > 0 ? `After ${newDeps.value.map(jobName).join(' + ')}` : newSchedule.value || 'Manual',
    enabled: true,
  });
  showAddModal.value = false;
  newJobName.value = '';
  newSchedule.value = '';
  newDeps.value = [];
  showToast('Job added', 'success');
}
</script>

<template>
  <div class="dep-scheduling">

    <PageHeader
      title="Dependency-Aware Scheduling"
      subtitle="Schedule bots to run only after other jobs or CI steps complete successfully."
    >
      <template #actions>
        <button class="btn btn-primary" @click="showAddModal = true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          Add Job
        </button>
      </template>
    </PageHeader>

    <!-- Loading state -->
    <div v-if="loading" class="card" style="text-align: center; padding: 60px 20px; color: var(--text-secondary);">
      <p>Loading scheduler and trigger data...</p>
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="card" style="text-align: center; padding: 60px 20px; color: var(--text-secondary);">
      <p>{{ error }}</p>
      <button class="btn btn-primary" style="margin-top: 12px" @click="loadData">Retry</button>
    </div>

    <template v-else>
      <!-- DAG visual summary -->
      <div class="card pipeline-card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18"><circle cx="12" cy="5" r="3"/><path d="M12 8v4"/><circle cx="6" cy="16" r="3"/><circle cx="18" cy="16" r="3"/><path d="M9.5 14l-3.5 0M14.5 14l3.5 0"/><path d="M10 10.5l-4 3M14 10.5l4 3"/></svg>
            Execution Pipeline
          </h3>
        </div>
        <div v-if="jobs.length === 0" style="padding: 30px; text-align: center; color: var(--text-tertiary);">
          No triggers found. Create a trigger to see the execution pipeline.
        </div>
        <div v-else class="pipeline-viz">
          <div v-for="job in jobs" :key="job.id" class="pipeline-node-row">
            <div class="dep-indent" :style="{ width: `${job.dependsOn.length * 16}px` }"></div>
            <div
              class="pipeline-node"
              :style="{ borderColor: statusColor[job.status] + '40', '--node-color': statusColor[job.status] }"
            >
              <span class="node-dot" :style="{ background: statusColor[job.status] }"></span>
              <span class="node-name">{{ job.name }}</span>
              <span class="node-status" :style="{ color: statusColor[job.status] }">
                {{ statusLabel[job.status] }}
              </span>
            </div>
            <div v-if="job.dependsOn.length > 0" class="dep-labels">
              <span v-for="depId in job.dependsOn" :key="depId" class="dep-label">
                after {{ jobName(depId) }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Jobs table -->
      <div class="card">
        <div class="card-header">
          <h3>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="18" height="18"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
            Scheduled Jobs
          </h3>
        </div>
        <div v-if="jobs.length === 0" style="padding: 30px; text-align: center; color: var(--text-tertiary);">
          No jobs to display.
        </div>
        <div v-else class="jobs-table">
          <div class="table-header">
            <span>Job</span>
            <span>Depends On</span>
            <span>Status</span>
            <span>Next Run</span>
            <span>Actions</span>
          </div>
          <div v-for="job in jobs" :key="job.id" class="table-row" :class="{ disabled: !job.enabled }">
            <div class="job-name-cell">
              <span class="job-name">{{ job.name }}</span>
              <span v-if="!job.enabled" class="disabled-badge">disabled</span>
            </div>
            <div class="deps-cell">
              <template v-if="job.dependsOn.length > 0">
                <span v-for="depId in job.dependsOn" :key="depId" class="dep-chip">
                  {{ jobName(depId) }}
                </span>
              </template>
              <span v-else class="no-dep">— (time-based)</span>
            </div>
            <div class="status-cell">
              <span class="status-dot" :style="{ background: statusColor[job.status] }"></span>
              <span :style="{ color: statusColor[job.status] }">{{ statusLabel[job.status] }}</span>
            </div>
            <div class="next-run-cell">{{ job.nextRun }}</div>
            <div class="actions-cell">
              <button class="btn btn-sm btn-secondary" @click="triggerNow(job)">Run now</button>
              <button class="toggle-btn" :class="{ active: job.enabled }" @click="toggleEnabled(job)">
                {{ job.enabled ? 'On' : 'Off' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- Add modal -->
    <div v-if="showAddModal" class="modal-overlay" @click.self="showAddModal = false">
      <div class="modal">
        <div class="modal-header">
          <h3>Add Scheduled Job</h3>
          <button class="icon-btn" @click="showAddModal = false">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="modal-body">
          <div class="field-group">
            <label class="field-label">Job Name</label>
            <input v-model="newJobName" type="text" class="text-input" placeholder="e.g. Release Audit Bot" />
          </div>
          <div class="field-group">
            <label class="field-label">Cron Schedule (if no dependencies)</label>
            <input v-model="newSchedule" type="text" class="text-input" placeholder="e.g. 0 9 * * 1-5" />
          </div>
          <div class="field-group">
            <label class="field-label">Run After (dependencies)</label>
            <div class="dep-options">
              <label v-for="job in jobs" :key="job.id" class="dep-option">
                <input type="checkbox" :checked="newDeps.includes(job.id)" @change="toggleDep(job.id)" />
                {{ job.name }}
              </label>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showAddModal = false">Cancel</button>
          <button class="btn btn-primary" @click="saveJob">Add Job</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dep-scheduling {
  display: flex;
  flex-direction: column;
  gap: 24px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; overflow: hidden; }

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-default);
}

.card-header h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-header h3 svg { color: var(--accent-cyan); }

.pipeline-viz {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.pipeline-node-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.dep-indent { flex-shrink: 0; }

.pipeline-node {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: var(--bg-tertiary);
  border: 1px solid;
  border-radius: 8px;
  min-width: 200px;
}

.node-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.node-name {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-primary);
  flex: 1;
}

.node-status {
  font-size: 0.72rem;
  font-weight: 500;
}

.dep-labels {
  display: flex;
  gap: 6px;
}

.dep-label {
  font-size: 0.72rem;
  color: var(--text-tertiary);
  font-style: italic;
}

.jobs-table { display: flex; flex-direction: column; }

.table-header {
  display: grid;
  grid-template-columns: 1.5fr 1.5fr 1fr 1.5fr 1fr;
  gap: 12px;
  padding: 10px 24px;
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-default);
}

.table-row {
  display: grid;
  grid-template-columns: 1.5fr 1.5fr 1fr 1.5fr 1fr;
  gap: 12px;
  padding: 12px 24px;
  align-items: center;
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.15s;
}

.table-row:last-child { border-bottom: none; }
.table-row:hover { background: var(--bg-tertiary); }
.table-row.disabled { opacity: 0.5; }

.job-name-cell { display: flex; align-items: center; gap: 8px; }

.job-name {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-primary);
}

.disabled-badge {
  font-size: 0.65rem;
  padding: 1px 5px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 3px;
  color: var(--text-tertiary);
}

.deps-cell { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }

.dep-chip {
  font-size: 0.72rem;
  padding: 2px 7px;
  background: rgba(6, 182, 212, 0.1);
  border: 1px solid rgba(6, 182, 212, 0.2);
  border-radius: 4px;
  color: var(--accent-cyan);
}

.no-dep { font-size: 0.75rem; color: var(--text-tertiary); }

.status-cell { display: flex; align-items: center; gap: 6px; font-size: 0.85rem; }

.status-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }

.next-run-cell { font-size: 0.8rem; color: var(--text-secondary); }

.actions-cell { display: flex; gap: 6px; align-items: center; }

.btn {
  display: flex;
  align-items: center;
  gap: 5px;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.btn-sm { padding: 5px 10px; font-size: 0.78rem; }
.btn:not(.btn-sm) { padding: 8px 16px; font-size: 0.875rem; }

.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover { opacity: 0.85; }

.btn-secondary {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.btn-secondary:hover { border-color: var(--accent-cyan); }

.toggle-btn {
  font-size: 0.72rem;
  padding: 4px 8px;
  border-radius: 4px;
  border: 1px solid var(--border-default);
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
  cursor: pointer;
}

.toggle-btn.active {
  background: rgba(52, 211, 153, 0.1);
  border-color: rgba(52, 211, 153, 0.3);
  color: #34d399;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.modal {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  width: 480px;
  max-width: 95vw;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-default);
}

.modal-header h3 { font-size: 1rem; font-weight: 600; color: var(--text-primary); margin: 0; }

.modal-body {
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 16px 24px;
  border-top: 1px solid var(--border-default);
}

.field-group { display: flex; flex-direction: column; gap: 6px; }

.field-label { font-size: 0.8rem; font-weight: 500; color: var(--text-secondary); }

.text-input {
  padding: 9px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.text-input:focus { outline: none; border-color: var(--accent-cyan); }

.dep-options { display: flex; flex-direction: column; gap: 8px; }

.dep-option {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.875rem;
  color: var(--text-secondary);
  cursor: pointer;
}

.icon-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 1px solid var(--border-default);
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

@media (max-width: 900px) {
  .table-header, .table-row { grid-template-columns: 1fr 1fr auto; }
  .table-header span:nth-child(4),
  .table-row .next-run-cell { display: none; }
}
</style>
