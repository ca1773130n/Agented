<!--
  SchedulingCard — extracted from SchedulingDashboard.vue for the Activity
  lane (Live ops block).

  WebMCP RISK: preserves the `agented_scheduling_get_rotation_status`
  useWebMcpTool registration — verification agents call into it. Don't
  drop the registration or rename the tool. See
  `cards/__tests__/SchedulingCard.test.ts` for the regression guard.

  ON-CALL MERGE: folds the OnCallEscalation page's static 4-row severity
  threshold reference + the unpersisted `escalationPolicy` text input
  into an "On-Call Policy" sub-card at the bottom. The input doesn't
  hit any backend; see the TODO comment.
-->
<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import {
  schedulerApi,
  rotationApi,
  triggerApi,
  type SchedulerStatus,
  type RotationDashboardStatus,
  type RotationEvent,
  type Trigger,
} from '../../../services/api';
import { useWebMcpTool } from '../../../composables/useWebMcpTool';
import RotationTimelineChart from '../../../components/monitoring/RotationTimelineChart.vue';
import StatCard from '../../../components/base/StatCard.vue';
import ErrorState from '../../../components/base/ErrorState.vue';

const emit = defineEmits<{ loaded: [slug: string] }>();
const { t } = useI18n();
const router = useRouter();

const schedulerStatus = ref<SchedulerStatus | null>(null);
const rotationStatus = ref<RotationDashboardStatus | null>(null);
const rotationHistory = ref<RotationEvent[]>([]);
const scheduledTriggers = ref<Trigger[]>([]);
const isLoading = ref(true);
const error = ref<string | null>(null);
const autoRefresh = ref(true);

// On-Call Policy (folded from OnCallEscalation). The input below is
// surfaced for parity with the deleted page but is not persisted
// anywhere — keep it as a placeholder until backend plumbing exists.
// TODO: persist policy — wire to a real escalation-policy backend.
const escalationPolicy = ref('');

const accountNameMap = computed(() => {
  const map: Record<number, string> = {};
  if (schedulerStatus.value?.sessions) {
    for (const s of schedulerStatus.value.sessions) {
      if (s.account_name) map[s.account_id] = s.account_name;
    }
  }
  return map;
});

function getAccountName(accountId: number | null): string {
  if (accountId === null) return '---';
  return accountNameMap.value[accountId] || String(accountId);
}

useWebMcpTool({
  name: 'agented_scheduling_get_rotation_status',
  description:
    'Returns the current rotation status including active sessions, recent rotation events, and countdown timers',
  page: 'SchedulingDashboard',
  execute: async () => {
    return {
      content: [
        {
          type: 'text' as const,
          text: JSON.stringify({
            page: 'SchedulingDashboard',
            loaded: !isLoading.value,
            has_error: !!error.value,
            scheduler: schedulerStatus.value
              ? {
                  session_count: schedulerStatus.value.sessions.length,
                  queued: schedulerStatus.value.global_summary.queued,
                  running: schedulerStatus.value.global_summary.running,
                  stopped: schedulerStatus.value.global_summary.stopped,
                }
              : null,
            rotation: rotationStatus.value
              ? {
                  active_sessions: rotationStatus.value.sessions.length,
                  evaluator_interval: rotationStatus.value.evaluator.evaluation_interval_seconds,
                  hysteresis_threshold: rotationStatus.value.evaluator.hysteresis_threshold,
                  active_evaluations: rotationStatus.value.evaluator.active_evaluations,
                }
              : null,
            rotation_history_count: rotationHistory.value.length,
            auto_refresh: autoRefresh.value,
          }),
        },
      ],
    };
  },
  deps: [schedulerStatus, rotationStatus, rotationHistory],
});

let statusInterval: ReturnType<typeof setInterval> | null = null;
let historyInterval: ReturnType<typeof setInterval> | null = null;

function formatTime(val: string | null | undefined): string {
  if (!val) return '—';
  try { return new Date(val).toLocaleString(); } catch { return val; }
}

async function refreshStatus() {
  try {
    const [sched, rot] = await Promise.all([
      schedulerApi.getStatus(),
      rotationApi.getStatus(),
    ]);
    schedulerStatus.value = sched;
    rotationStatus.value = rot;
    error.value = null;
  } catch (err) {
    error.value = t('schedulingCard.error.load');
  }
}

async function refreshHistory() {
  try {
    const data = await rotationApi.getHistory(undefined, 50);
    rotationHistory.value = data.events || [];
  } catch { /* non-critical */ }
}

async function refreshScheduledTriggers() {
  try {
    const data = await triggerApi.list();
    scheduledTriggers.value = (data.triggers || []).filter(t => t.trigger_source === 'scheduled');
  } catch { /* non-critical */ }
}

function formatDispatchType(type: string | undefined): string {
  if (type === 'super_agent') return t('schedulingCard.superAgent');
  return t('schedulingCard.bot');
}

async function refreshAll() {
  isLoading.value = true;
  await Promise.all([refreshStatus(), refreshHistory(), refreshScheduledTriggers()]);
  isLoading.value = false;
  emit('loaded', 'scheduling');
}

function startAutoRefresh() {
  stopAutoRefresh();
  if (autoRefresh.value) {
    statusInterval = setInterval(refreshStatus, 15_000);
    historyInterval = setInterval(refreshHistory, 60_000);
  }
}
function stopAutoRefresh() {
  if (statusInterval) { clearInterval(statusInterval); statusInterval = null; }
  if (historyInterval) { clearInterval(historyInterval); historyInterval = null; }
}

watch(autoRefresh, (val) => {
  if (val) startAutoRefresh();
  else stopAutoRefresh();
});

onMounted(() => {
  refreshAll();
  startAutoRefresh();
});
onUnmounted(() => {
  stopAutoRefresh();
});

const severityRows = computed<Array<[string, string, string]>>(() => [
  ['critical', t('schedulingCard.severity.critical'), '#ef4444'],
  ['high', t('schedulingCard.severity.high'), '#f97316'],
  ['medium', t('schedulingCard.severity.medium'), '#f59e0b'],
  ['low', t('schedulingCard.severity.low'), '#6b7280'],
]);
</script>

<template>
  <section id="scheduling" class="scheduling-dashboard lane-card">
    <header class="lane-card__head">
      <div>
        <h2 class="lane-card__title">{{ t('schedulingCard.title') }}</h2>
        <p class="lane-card__subtitle">{{ t('schedulingCard.subtitle') }}</p>
      </div>
      <div class="head-actions">
        <label class="auto-refresh-toggle">
          <input type="checkbox" v-model="autoRefresh" />
          <span>{{ t('schedulingCard.autoRefresh') }}</span>
        </label>
        <button class="refresh-btn" @click="refreshAll" :disabled="isLoading">
          <svg :class="{ spinning: isLoading }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M23 4v6h-6M1 20v-6h6"/>
            <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
          </svg>
          {{ t('schedulingCard.refresh') }}
        </button>
      </div>
    </header>

    <ErrorState
      v-if="error"
      :title="t('schedulingCard.connectionError')"
      :message="error"
      @retry="refreshAll"
    />

    <!-- Summary cards -->
    <div class="stats-grid">
      <StatCard :title="t('schedulingCard.stat.activeSessions')" :value="rotationStatus?.sessions.length ?? 0" />
      <StatCard :title="t('schedulingCard.stat.queued')" :value="schedulerStatus?.global_summary.queued ?? 0" color="var(--accent-amber)" />
      <StatCard :title="t('schedulingCard.stat.running')" :value="schedulerStatus?.global_summary.running ?? 0" color="var(--accent-emerald)" />
      <StatCard :title="t('schedulingCard.stat.stopped')" :value="schedulerStatus?.global_summary.stopped ?? 0" color="var(--accent-crimson)" />
    </div>

    <section class="dashboard-section">
      <h2 class="section-header">{{ t('schedulingCard.schedulerSessions') }}</h2>
      <div v-if="!schedulerStatus || schedulerStatus.sessions.length === 0" class="empty-state">
        <p>{{ t('schedulingCard.empty.schedulerSessions') }}</p>
      </div>
      <div v-else class="table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th>{{ t('schedulingCard.th.accountId') }}</th><th>{{ t('schedulingCard.th.state') }}</th><th>{{ t('schedulingCard.th.stopReason') }}</th>
              <th>{{ t('schedulingCard.th.resumeEstimate') }}</th><th>{{ t('schedulingCard.th.safePolls') }}</th><th>{{ t('schedulingCard.th.updated') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="session in schedulerStatus.sessions" :key="session.account_id">
              <td class="mono">{{ session.account_name || session.account_id }}</td>
              <td><span class="state-badge" :class="session.state">{{ session.state }}</span></td>
              <td>{{ session.stop_reason || '—' }}</td>
              <td class="mono">{{ formatTime(session.resume_estimate) }}</td>
              <td class="mono">{{ session.consecutive_safe_polls }}</td>
              <td class="mono">{{ formatTime(session.updated_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="dashboard-section">
      <h2 class="section-header">{{ t('schedulingCard.activeRotationSessions') }}</h2>
      <div v-if="!rotationStatus || rotationStatus.sessions.length === 0" class="empty-state">
        <p>{{ t('schedulingCard.empty.rotationSessions') }}</p>
      </div>
      <div v-else class="rotation-cards">
        <div v-for="session in rotationStatus.sessions" :key="session.execution_id" class="rotation-card">
          <div class="rotation-card-header">
            <span class="mono execution-id">{{ session.execution_id }}</span>
            <span class="badge" :class="session.backend_type ?? ''">{{ session.backend_type ?? t('schedulingCard.unknown') }}</span>
          </div>
          <div class="rotation-card-body">
            <div class="rotation-field"><span class="field-label">{{ t('schedulingCard.field.account') }}</span><span class="mono">{{ getAccountName(session.account_id) }}</span></div>
            <div class="rotation-field"><span class="field-label">{{ t('schedulingCard.field.trigger') }}</span><span class="mono">{{ session.trigger_id ?? '—' }}</span></div>
            <div class="rotation-field"><span class="field-label">{{ t('schedulingCard.field.started') }}</span><span class="mono">{{ formatTime(session.started_at) }}</span></div>
          </div>
        </div>
      </div>
    </section>

    <section class="dashboard-section">
      <h2 class="section-header">{{ t('schedulingCard.rotationEvaluator') }}</h2>
      <div v-if="!rotationStatus" class="empty-state">
        <p>{{ t('schedulingCard.empty.evaluator') }}</p>
      </div>
      <div v-else class="evaluator-grid">
        <div class="evaluator-stat"><span class="field-label">{{ t('schedulingCard.field.interval') }}</span><span class="mono">{{ rotationStatus.evaluator.evaluation_interval_seconds }}s</span></div>
        <div class="evaluator-stat"><span class="field-label">{{ t('schedulingCard.field.hysteresisThreshold') }}</span><span class="mono">{{ rotationStatus.evaluator.hysteresis_threshold }}</span></div>
        <div class="evaluator-stat"><span class="field-label">{{ t('schedulingCard.field.activeEvaluations') }}</span><span class="mono">{{ rotationStatus.evaluator.active_evaluations }}</span></div>
        <div v-if="Object.keys(rotationStatus.evaluator.evaluation_states).length > 0" class="evaluator-states">
          <h3 class="subsection-header">{{ t('schedulingCard.evaluationStates') }}</h3>
          <div v-for="(state, execId) in rotationStatus.evaluator.evaluation_states" :key="execId" class="eval-state-row">
            <span class="mono execution-id">{{ execId }}</span>
            <span class="field-label">{{ t('schedulingCard.consecutivePolls') }} <span class="mono">{{ state.consecutive_rotate_polls }}</span></span>
            <span class="field-label">{{ t('schedulingCard.last') }} <span class="mono">{{ formatTime(state.last_evaluated) }}</span></span>
          </div>
        </div>
      </div>
    </section>

    <section class="dashboard-section">
      <h2 class="section-header">{{ t('schedulingCard.scheduledTriggers') }}</h2>
      <div v-if="scheduledTriggers.length === 0" class="empty-state">
        <p>{{ t('schedulingCard.empty.scheduledTriggers') }}</p>
      </div>
      <div v-else class="table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th>{{ t('schedulingCard.th.name') }}</th><th>{{ t('schedulingCard.th.dispatchType') }}</th><th>{{ t('schedulingCard.th.schedule') }}</th>
              <th>{{ t('schedulingCard.th.nextRun') }}</th><th>{{ t('schedulingCard.th.lastRun') }}</th><th>{{ t('schedulingCard.th.status') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="trigger in scheduledTriggers" :key="trigger.id">
              <td>
                <span class="trigger-name-link" @click="router.push({ name: 'trigger-dashboard', params: { triggerId: trigger.id } })">
                  {{ trigger.name }}
                </span>
              </td>
              <td>
                <span class="dispatch-badge" :class="trigger.dispatch_type || 'bot'">
                  {{ formatDispatchType(trigger.dispatch_type) }}
                </span>
              </td>
              <td class="mono">
                {{ trigger.schedule_type || '---' }}
                <span v-if="trigger.schedule_time"> {{ t('schedulingCard.at') }} {{ trigger.schedule_time }}</span>
              </td>
              <td class="mono">{{ formatTime(trigger.next_run_at) }}</td>
              <td class="mono">{{ formatTime(trigger.last_run_at) }}</td>
              <td>
                <span class="state-badge" :class="trigger.enabled === 1 ? 'running' : 'stopped'">
                  {{ trigger.enabled === 1 ? t('schedulingCard.enabled') : t('schedulingCard.disabled') }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="dashboard-section">
      <h2 class="section-header">{{ t('schedulingCard.rotationEventTimeline') }}</h2>
      <RotationTimelineChart :events="rotationHistory" />
    </section>

    <!-- On-Call Policy sub-card — folded from the deleted OnCallEscalation page.
         The escalationPolicy input is NOT persisted (see TODO above). -->
    <section class="dashboard-section on-call-policy" :aria-label="t('schedulingCard.onCallPolicy')">
      <h2 class="section-header">{{ t('schedulingCard.onCallPolicy') }}</h2>
      <p class="section-subtitle">
        {{ t('schedulingCard.onCallPolicySubtitle') }}
      </p>

      <div class="threshold-list">
        <div v-for="[sev, desc, color] in severityRows" :key="sev" class="threshold-row">
          <div class="thresh-sev" :style="{ color, background: `${color}15` }">{{ sev }}</div>
          <div class="thresh-desc">{{ desc }}</div>
          <label class="toggle-wrap-sm">
            <input type="checkbox" :checked="sev !== 'low'" class="toggle-input" />
            <span class="toggle-track-sm" :class="{ active: sev !== 'low' }">
              <span class="toggle-thumb-sm" />
            </span>
          </label>
        </div>
      </div>

      <div class="field-group">
        <label class="field-label" for="escalation-policy-input">{{ t('schedulingCard.escalationPolicy') }}</label>
        <input
          id="escalation-policy-input"
          v-model="escalationPolicy"
          type="text"
          class="text-input"
          :placeholder="t('schedulingCard.escalationPolicyPlaceholder')"
          data-testid="on-call-policy-input"
        />
        <p class="field-hint">
          {{ t('schedulingCard.escalationPolicyHint') }}
        </p>
      </div>
    </section>
  </section>
</template>

<style scoped>
.lane-card { padding: 20px; border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1)); border-radius: 10px; background: var(--bg-secondary, rgba(255, 255, 255, 0.02)); display: flex; flex-direction: column; gap: 16px; }
.lane-card__head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; }
.lane-card__title { font-size: 16px; font-weight: 600; margin: 0; color: var(--text-primary); }
.lane-card__subtitle { font-size: 12px; color: var(--text-tertiary); margin: 4px 0 0; }
.head-actions { display: flex; align-items: center; gap: 12px; }

.scheduling-dashboard { width: 100%; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
.stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; }
.auto-refresh-toggle { display: flex; align-items: center; gap: 0.5rem; font-size: 0.8125rem; color: var(--text-secondary); cursor: pointer; user-select: none; }
.auto-refresh-toggle input[type="checkbox"] { width: 14px; height: 14px; accent-color: var(--accent-cyan); }
.refresh-btn { display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.5rem 1rem; background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 6px; color: var(--text-primary); font-size: 0.8125rem; font-weight: 500; cursor: pointer; transition: all var(--transition-fast); }
.refresh-btn:hover:not(:disabled) { background: var(--bg-tertiary); border-color: var(--border-strong); }
.refresh-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.refresh-btn svg { width: 14px; height: 14px; }
.refresh-btn svg.spinning { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.dashboard-section { background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 12px; padding: 1.25rem 1.5rem; }
.section-header { margin: 0 0 1rem; font-size: 1rem; font-weight: 600; color: var(--text-primary); }
.section-subtitle { font-size: 0.8125rem; color: var(--text-tertiary); margin: 0 0 0.875rem; }
.subsection-header { margin: 0.75rem 0 0.5rem; font-size: 0.85rem; font-weight: 600; color: var(--text-secondary); }
.empty-state { text-align: center; padding: 2rem; color: var(--text-muted); font-size: 0.85rem; }
.empty-state p { margin: 0; }
.mono { font-family: var(--font-mono); font-size: 0.8125rem; }

.table-wrapper { overflow-x: auto; }
.data-table { width: 100%; border-collapse: collapse; font-size: 0.8125rem; }
.data-table th { text-align: left; padding: 0.5rem 0.75rem; color: var(--text-tertiary); font-weight: 500; text-transform: uppercase; font-size: 0.6875rem; letter-spacing: 0.05em; border-bottom: 1px solid var(--border-subtle); }
.data-table td { padding: 0.6rem 0.75rem; color: var(--text-secondary); border-bottom: 1px solid var(--border-subtle); }
.data-table tbody tr:last-child td { border-bottom: none; }
.data-table tbody tr:hover { background: var(--bg-tertiary); }

.state-badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em; }
.state-badge.queued { background: rgba(234, 179, 8, 0.15); color: #eab308; }
.state-badge.running { background: rgba(34, 197, 94, 0.15); color: #22c55e; }
.state-badge.stopped { background: rgba(239, 68, 68, 0.15); color: #ef4444; }

.rotation-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 0.75rem; }
.rotation-card { background: var(--bg-tertiary); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 0.75rem 1rem; }
.rotation-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }
.execution-id { font-size: 0.75rem; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 180px; }
.badge { display: inline-block; padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.6875rem; font-weight: 600; text-transform: uppercase; background: var(--bg-secondary); color: var(--text-tertiary); }
.badge.claude { background: rgba(139, 92, 246, 0.15); color: var(--accent-violet); }
.badge.opencode { background: rgba(34, 197, 94, 0.15); color: var(--accent-emerald); }
.badge.gemini { background: rgba(6, 182, 212, 0.15); color: var(--accent-cyan); }
.badge.codex { background: rgba(234, 179, 8, 0.15); color: var(--accent-amber); }
.rotation-card-body { display: flex; flex-direction: column; gap: 0.25rem; }
.rotation-field { display: flex; justify-content: space-between; align-items: center; }
.field-label { font-size: 0.75rem; color: var(--text-tertiary); }

.evaluator-grid { display: flex; flex-wrap: wrap; gap: 1.5rem; }
.evaluator-stat { display: flex; flex-direction: column; gap: 0.25rem; }
.evaluator-states { width: 100%; }
.eval-state-row { display: flex; align-items: center; gap: 1rem; padding: 0.35rem 0; border-bottom: 1px solid var(--border-subtle); }
.eval-state-row:last-child { border-bottom: none; }

.trigger-name-link { color: var(--accent-cyan); cursor: pointer; font-weight: 500; transition: color 0.15s; }
.trigger-name-link:hover { color: var(--text-primary); text-decoration: underline; }
.dispatch-badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em; }
.dispatch-badge.bot { background: rgba(0, 212, 255, 0.15); color: var(--accent-cyan); }
.dispatch-badge.super_agent { background: rgba(139, 92, 246, 0.15); color: var(--accent-violet); }

/* On-Call Policy (folded from OnCallEscalation) */
.on-call-policy { border-color: var(--border-default); }
.threshold-list { display: flex; flex-direction: column; gap: 0.5rem; }
.threshold-row { display: flex; align-items: center; gap: 0.75rem; padding: 0.6rem 0.75rem; background: var(--bg-tertiary); border: 1px solid var(--border-subtle); border-radius: 6px; }
.thresh-sev { padding: 2px 10px; border-radius: 4px; font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; min-width: 70px; text-align: center; }
.thresh-desc { flex: 1; font-size: 0.85rem; color: var(--text-secondary); }
.toggle-wrap-sm { position: relative; display: inline-flex; align-items: center; cursor: pointer; }
.toggle-input { position: absolute; opacity: 0; }
.toggle-track-sm { display: inline-block; width: 30px; height: 16px; background: var(--bg-elevated); border: 1px solid var(--border-default); border-radius: 999px; position: relative; transition: background 0.2s; }
.toggle-track-sm.active { background: var(--accent-cyan-dim); border-color: var(--accent-cyan); }
.toggle-thumb-sm { position: absolute; top: 1px; left: 1px; width: 12px; height: 12px; background: var(--text-tertiary); border-radius: 50%; transition: transform 0.2s, background 0.2s; }
.toggle-track-sm.active .toggle-thumb-sm { transform: translateX(14px); background: var(--accent-cyan); }

.field-group { display: flex; flex-direction: column; gap: 6px; margin-top: 1rem; }
.text-input { padding: 8px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 6px; color: var(--text-primary); font-size: 0.875rem; max-width: 320px; }
.text-input:focus { outline: none; border-color: var(--accent-cyan); }
.field-hint { font-size: 0.75rem; color: var(--text-muted); margin: 0; }
</style>
