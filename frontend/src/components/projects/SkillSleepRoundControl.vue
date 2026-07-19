<script setup lang="ts">
/**
 * SkillSleepRoundControl — trigger one autonomous Skill-Sleep round for a
 * chosen skill: Reflect proposes a candidate → gate → measure → STAGE (never
 * auto-written; an operator adopts from the review drawer). Surfaces a
 * transient, status-keyed result line and emits `completed` so the parent
 * reloads the runs card.
 *
 * Optionals (n / seed / measure / edit_budget) are spread into the request
 * body only when set (the triggers.ts pattern). The "Run round" button is
 * disabled with no skill selected or while a round is in flight.
 */
import { computed, onBeforeUnmount, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { ApiError, skillSleepApi } from '../../services/api';
import type { SkillSleepVerdict } from '../../services/api';

const props = defineProps<{
  projectId: string;
  skills: { skill_name: string }[];
}>();
const emit = defineEmits<{ completed: [] }>();
const { t } = useI18n();

const selectedSkill = ref('');
const nInput = ref('');
const seedInput = ref('');
const measure = ref(true);
const editBudgetInput = ref('');

const inFlight = ref(false);
const resultLine = ref<string | null>(null);
const resultClass = ref<'ok' | 'neutral' | 'error'>('neutral');

const canRun = computed(() => !!selectedSkill.value && !inFlight.value);

function numOrUndef(v: string): number | undefined {
  const n = Number(v);
  return v.trim() !== '' && Number.isFinite(n) ? n : undefined;
}

function formatDelta(val: number | null | undefined): string {
  if (val === null || val === undefined) return '—';
  const sign = val >= 0 ? '+' : '';
  return `${sign}${(val * 100).toFixed(0)}%`;
}

function describe(v: SkillSleepVerdict): { line: string; cls: 'ok' | 'neutral' | 'error' } {
  switch (v.status) {
    case 'accepted':
      return { line: t('skillSleep.roundAccepted', { delta: formatDelta(v.delta) }), cls: 'ok' };
    case 'no_candidate':
      return { line: t('skillSleep.roundNoCandidate'), cls: 'neutral' };
    case 'rejected':
      return { line: t('skillSleep.roundRejected'), cls: 'neutral' };
    case 'abstained':
      return { line: t('skillSleep.roundAbstained'), cls: 'neutral' };
    default:
      return { line: t('skillSleep.roundFailed'), cls: 'error' };
  }
}

// A round runs in the background (minutes; up to a 600s codex Reflect). We kick
// it off, then POLL for the verdict rather than holding one long request — so
// the operator can leave the page (polling stops on unmount; the backend round
// still finishes and persists its run).
const POLL_MS = 3000;
let pollTimer: ReturnType<typeof setTimeout> | null = null;

function stopPolling() {
  if (pollTimer !== null) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}
onBeforeUnmount(stopPolling);

function finishWith(verdict: SkillSleepVerdict) {
  const d = describe(verdict);
  resultLine.value = d.line;
  resultClass.value = d.cls;
  inFlight.value = false;
  emit('completed');
}

function failWith(message: string) {
  resultLine.value = message;
  resultClass.value = 'error';
  inFlight.value = false;
  // No `completed` emit on error — nothing was staged.
}

function pollJob(jobId: string) {
  stopPolling();
  pollTimer = setTimeout(async () => {
    pollTimer = null;
    try {
      const job = await skillSleepApi.roundStatus(props.projectId, selectedSkill.value, jobId);
      if (job.status === 'running') {
        pollJob(jobId);
      } else if (job.status === 'done' && job.verdict) {
        finishWith(job.verdict);
      } else {
        failWith(job.error || t('skillSleep.roundFailed'));
      }
    } catch (err) {
      failWith(err instanceof ApiError ? err.message : t('skillSleep.roundError'));
    }
  }, POLL_MS);
}

async function runRound() {
  if (!canRun.value) return;
  inFlight.value = true;
  resultLine.value = null;
  try {
    const body: { n?: number; seed?: number; measure?: boolean; edit_budget?: number } = {
      measure: measure.value,
    };
    const n = numOrUndef(nInput.value);
    if (n !== undefined) body.n = n;
    const seed = numOrUndef(seedInput.value);
    if (seed !== undefined) body.seed = seed;
    const eb = numOrUndef(editBudgetInput.value);
    if (eb !== undefined) body.edit_budget = eb;

    const { job_id } = await skillSleepApi.runRound(props.projectId, selectedSkill.value, body);
    // inFlight stays true while polling; the button shows "running".
    pollJob(job_id);
  } catch (err) {
    failWith(err instanceof ApiError ? err.message : t('skillSleep.roundError'));
  }
}
</script>

<template>
  <div class="ss-round">
    <h4 class="ss-round__title">{{ t('skillSleep.roundTitle') }}</h4>
    <div class="ss-round__row">
      <select v-model="selectedSkill" class="ss-round__select" data-testid="ss-round-skill">
        <option value="" disabled>{{ t('skillSleep.selectSkill') }}</option>
        <option v-for="s in props.skills" :key="s.skill_name" :value="s.skill_name">
          {{ s.skill_name }}
        </option>
      </select>

      <label class="ss-round__opt">
        {{ t('skillSleep.optQuestions') }}
        <input v-model="nInput" type="number" min="1" class="ss-round__num" />
      </label>
      <label class="ss-round__opt">
        {{ t('skillSleep.optSeed') }}
        <input v-model="seedInput" type="number" class="ss-round__num" />
      </label>
      <label class="ss-round__opt">
        {{ t('skillSleep.optEditBudget') }}
        <input v-model="editBudgetInput" type="number" min="0" class="ss-round__num" />
      </label>
      <label class="ss-round__opt ss-round__check">
        <input v-model="measure" type="checkbox" />
        {{ t('skillSleep.optMeasure') }}
      </label>

      <button
        class="btn btn-primary"
        data-testid="ss-round-run"
        :disabled="!canRun"
        @click="runRound"
      >
        {{ inFlight ? t('skillSleep.running') : t('skillSleep.runRound') }}
      </button>
    </div>

    <p
      v-if="resultLine"
      :class="['ss-round__result', `ss-round__result--${resultClass}`]"
      data-testid="ss-round-result"
    >
      {{ resultLine }}
    </p>
  </div>
</template>

<style scoped>
.ss-round__title {
  margin: 0 0 10px;
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted, #999);
}

.ss-round__row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 12px;
}

.ss-round__select {
  min-width: 160px;
  padding: 6px 8px;
}

.ss-round__opt {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.72rem;
  color: var(--text-muted, #999);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.ss-round__check {
  flex-direction: row;
  align-items: center;
  gap: 6px;
  text-transform: none;
}

.ss-round__num {
  width: 80px;
  padding: 6px 8px;
}

.ss-round__result {
  margin: 10px 0 0;
  font-size: 0.85rem;
}

.ss-round__result--ok {
  color: var(--accent-green, #4ade80);
}
.ss-round__result--neutral {
  color: var(--text-muted, #999);
}
.ss-round__result--error {
  color: var(--accent-crimson, #f87171);
}
</style>
