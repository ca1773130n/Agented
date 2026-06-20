<script setup lang="ts">
/** LoopTracePanel — v0.6.0 sub-project #3 (observability + control).
 *  Renders the per-iteration trace for a goal-loop / ralph session (one row
 *  per iteration: #, verdict, confidence, judge source/version, tokens, cost),
 *  a control bar (pause / resume / stop / intervene), and a human-gate card
 *  shown while the runner is blocked awaiting an operator decision. Trace data
 *  comes from ``grdApi.listGoalIterations``; control actions reuse the existing
 *  pause/resume/stop session endpoints plus the new intervene / gate-decision
 *  routes. */
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { grdApi } from '../../services/api';

const props = defineProps<{
  projectId: string;
  sessionId: string;
  awaitingHuman: boolean;
  gateReason?: string | null;
}>();

const { t } = useI18n();

interface TraceRow {
  iteration: number;
  verdict?: string | null;
  confidence?: number | null;
  judge_source?: string | null;
  judge_version?: string | null;
  cost_usd?: number | null;
  tokens_total?: number | null;
  tokens_in?: number | null;
  tokens_out?: number | null;
}

const rows = ref<TraceRow[]>([]);
const busy = ref(false);
const interveneNote = ref('');
const gateNote = ref('');

async function loadTrace(): Promise<void> {
  try {
    const audit = (await grdApi.listGoalIterations(props.projectId, props.sessionId)) as {
      iterations?: TraceRow[];
    } | null;
    rows.value = audit?.iterations ?? [];
  } catch {
    /* best-effort — leave the trace empty if the audit is unavailable */
  }
}

onMounted(loadTrace);

async function onPause(): Promise<void> {
  busy.value = true;
  try {
    await grdApi.pauseSession(props.projectId, props.sessionId);
  } finally {
    busy.value = false;
  }
}

async function onResume(): Promise<void> {
  busy.value = true;
  try {
    await grdApi.resumeSession(props.projectId, props.sessionId);
  } finally {
    busy.value = false;
  }
}

async function onStop(): Promise<void> {
  busy.value = true;
  try {
    await grdApi.stopSession(props.projectId, props.sessionId);
  } finally {
    busy.value = false;
  }
}

async function onIntervene(): Promise<void> {
  const msg = interveneNote.value.trim();
  if (!msg) return;
  await grdApi.interveneLoop(props.projectId, props.sessionId, msg);
  interveneNote.value = '';
}

async function onGate(decision: 'continue' | 'modify' | 'abort'): Promise<void> {
  const msg = decision === 'modify' ? gateNote.value.trim() || undefined : undefined;
  await grdApi.gateDecision(props.projectId, props.sessionId, decision, msg);
  gateNote.value = '';
}

function tokensOf(r: TraceRow): number | null {
  if (typeof r.tokens_total === 'number') return r.tokens_total;
  const inT = r.tokens_in ?? 0;
  const outT = r.tokens_out ?? 0;
  return inT || outT ? inT + outT : null;
}

function num(n: number | null | undefined, digits = 2): string {
  return typeof n === 'number' ? n.toFixed(digits) : '—';
}
</script>

<template>
  <div class="loop-trace" data-testid="loop-trace-panel">
    <!-- Control bar -->
    <div class="lt-controls">
      <button class="btn" :disabled="busy" data-testid="loop-pause" @click="onPause">
        {{ t('loopControl.pause') }}
      </button>
      <button class="btn" :disabled="busy" data-testid="loop-resume" @click="onResume">
        {{ t('loopControl.resume') }}
      </button>
      <button class="btn btn-danger" :disabled="busy" data-testid="loop-stop" @click="onStop">
        {{ t('loopControl.stop') }}
      </button>
    </div>

    <div class="lt-intervene">
      <textarea
        v-model="interveneNote"
        class="lt-textarea"
        rows="2"
        data-testid="loop-intervene-note"
        :placeholder="t('loopControl.intervene')"
      ></textarea>
      <button
        class="btn"
        :disabled="!interveneNote.trim()"
        data-testid="loop-intervene-send"
        @click="onIntervene"
      >
        {{ t('loopControl.interveneSend') }}
      </button>
    </div>

    <!-- Human-gate card -->
    <div v-if="awaitingHuman" class="lt-gate" data-testid="loop-gate-card">
      <p class="lt-gate-title">
        {{ t('loopControl.awaitingHuman') }}
        <span v-if="gateReason" class="lt-gate-reason">{{ gateReason }}</span>
      </p>
      <textarea
        v-model="gateNote"
        class="lt-textarea"
        rows="2"
        data-testid="gate-note"
        :placeholder="t('loopControl.gateModify')"
      ></textarea>
      <div class="lt-gate-actions">
        <button class="btn btn-primary" data-testid="gate-continue" @click="onGate('continue')">
          {{ t('loopControl.gateContinue') }}
        </button>
        <button class="btn" data-testid="gate-modify" @click="onGate('modify')">
          {{ t('loopControl.gateModify') }}
        </button>
        <button class="btn btn-danger" data-testid="gate-abort" @click="onGate('abort')">
          {{ t('loopControl.gateAbort') }}
        </button>
      </div>
    </div>

    <!-- Per-iteration trace -->
    <ul v-if="rows.length" class="lt-list">
      <li
        v-for="r in rows"
        :key="r.iteration"
        class="lt-row"
        :class="{ met: r.verdict === 'met' }"
        data-testid="loop-iter-row"
      >
        <span class="lt-iter">{{ t('loopControl.iteration') }} {{ r.iteration }}</span>
        <span class="lt-verdict" :class="`v-${r.verdict ?? 'pending'}`">{{ r.verdict ?? '—' }}</span>
        <span class="lt-conf">{{ t('loopControl.confidence') }} {{ num(r.confidence) }}</span>
        <span class="lt-src">{{ r.judge_source ?? '—' }}<template v-if="r.judge_version"> · {{ r.judge_version }}</template></span>
        <span class="lt-tokens">{{ t('loopControl.tokens') }} {{ tokensOf(r) ?? '—' }}</span>
        <span class="lt-cost">{{ t('loopControl.cost') }} {{ num(r.cost_usd, 4) }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.loop-trace { display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }
.lt-controls { display: flex; gap: 6px; }
.lt-intervene { display: flex; gap: 6px; align-items: flex-start; }
.lt-textarea {
  flex: 1; min-width: 0; resize: vertical;
  background: var(--bg-tertiary, #1a1a24); color: var(--text-primary, #eee);
  border: 1px solid var(--border-subtle, #2a2a36); border-radius: 5px;
  padding: 4px 6px; font-size: 0.78rem; font-family: inherit;
}
.btn-danger { color: var(--accent-red, #ef4444); }
.lt-gate {
  border: 1px solid var(--accent-amber, #f59e0b); border-radius: 6px;
  padding: 8px; display: flex; flex-direction: column; gap: 6px;
  background: rgba(245, 158, 11, 0.08);
}
.lt-gate-title { margin: 0; font-size: 0.8rem; color: var(--accent-amber, #f59e0b); }
.lt-gate-reason { color: var(--text-tertiary, #888); margin-left: 6px; font-size: 0.72rem; }
.lt-gate-actions { display: flex; gap: 6px; }
.lt-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 3px; }
.lt-row {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
  padding: 4px 6px; background: var(--bg-tertiary, #1a1a24); border-radius: 5px;
  font-size: 0.78rem; font-variant-numeric: tabular-nums;
}
.lt-row.met { border: 1px solid var(--accent-emerald, #22c55e); }
.lt-iter { color: var(--accent-cyan, #00d4ff); font-weight: 600; }
.lt-verdict { padding: 1px 6px; border-radius: 4px; font-size: 0.68rem; }
.lt-verdict.v-met { background: rgba(34, 197, 94, 0.15); color: #22c55e; }
.lt-verdict.v-not_met { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.lt-conf, .lt-tokens, .lt-cost { color: var(--text-secondary, #aaa); }
.lt-src { color: var(--text-tertiary, #888); }
.lt-cost { margin-left: auto; }
</style>
