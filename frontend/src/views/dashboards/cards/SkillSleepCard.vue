<!--
  SkillSleepCard — project-scoped list of Skill-Sleep optimization runs.
  Each row shows the skill, a verdict badge, the judge delta, the disjoint-split
  outcome delta, and (for an accepted, un-adopted run) a Review affordance that
  emits `open-run` so the parent opens the review-then-adopt drawer.
  Mirrors AnswerGroundednessCard.vue (load + delta styling + states).
-->
<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { ApiError, skillSleepApi } from '../../../services/api';
import type { SkillSleepRun, SkillSleepStatus } from '../../../services/api';
import LoadingState from '../../../components/base/LoadingState.vue';
import EmptyState from '../../../components/base/EmptyState.vue';
import StatusBadge from '../../../components/base/StatusBadge.vue';

const props = defineProps<{ projectId: string }>();
const emit = defineEmits<{ 'open-run': [run: SkillSleepRun] }>();
const { t } = useI18n();

const isLoading = ref(true);
const loadError = ref<string | null>(null);
const runs = ref<SkillSleepRun[]>([]);

async function reload() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const res = await skillSleepApi.listRuns(props.projectId);
    runs.value = res?.runs ?? [];
  } catch (err) {
    loadError.value = err instanceof ApiError ? err.message : t('skillSleep.loadError');
  } finally {
    isLoading.value = false;
  }
}

function formatDelta(val: number | null | undefined): string {
  if (val === null || val === undefined) return '—';
  const sign = val >= 0 ? '+' : '';
  return `${sign}${(val * 100).toFixed(0)}%`;
}

function deltaClass(val: number | null | undefined): string {
  if (val === null || val === undefined) return 'delta--neutral';
  if (val > 0) return 'delta--up';
  if (val < 0) return 'delta--down';
  return 'delta--neutral';
}

const _statusVariant: Record<SkillSleepStatus, 'success' | 'danger' | 'neutral'> = {
  accepted: 'success',
  rejected: 'danger',
  failed: 'danger',
  abstained: 'neutral',
  no_candidate: 'neutral',
};
function statusVariant(s: SkillSleepStatus) {
  return _statusVariant[s] ?? 'neutral';
}

const _statusKey: Record<SkillSleepStatus, string> = {
  accepted: 'skillSleep.statusAccepted',
  rejected: 'skillSleep.statusRejected',
  abstained: 'skillSleep.statusAbstained',
  failed: 'skillSleep.statusFailed',
  no_candidate: 'skillSleep.statusNoCandidate',
};
function statusLabel(s: SkillSleepStatus) {
  return t(_statusKey[s] ?? 'skillSleep.statusFailed');
}

/** A reviewable row: accepted by the gate and not yet adopted to disk. */
function isReviewable(run: SkillSleepRun): boolean {
  return run.status === 'accepted' && !run.adopted_at;
}

function shortTime(iso: string): string {
  // SQLite "YYYY-MM-DD HH:MM:SS" (UTC, space-separated) → date portion.
  return (iso || '').slice(0, 10);
}

defineExpose({ reload });
onMounted(reload);
</script>

<template>
  <section class="lane-card skill-sleep-card">
    <header class="lane-card__head">
      <div>
        <h2 class="lane-card__title">{{ t('skillSleep.cardTitle') }}</h2>
        <p class="lane-card__subtitle">{{ t('skillSleep.cardSubtitle') }}</p>
      </div>
    </header>

    <LoadingState v-if="isLoading" :message="t('skillSleep.cardTitle')" />

    <div v-else-if="loadError" class="error-msg">{{ loadError }}</div>

    <div v-else-if="runs.length" class="rows">
      <div v-for="run in runs" :key="run.id" class="row" data-testid="skill-sleep-row">
        <span class="row__skill">{{ run.skill_name }}</span>
        <StatusBadge :label="statusLabel(run.status)" :variant="statusVariant(run.status)" />
        <span class="row__delta">
          <span class="row__delta-label">{{ t('skillSleep.judgeDelta') }}</span>
          <span :class="['delta-value', deltaClass(run.delta)]">{{ formatDelta(run.delta) }}</span>
        </span>
        <span class="row__delta">
          <span class="row__delta-label">{{ t('skillSleep.outcomeDelta') }}</span>
          <span :class="['delta-value', deltaClass(run.outcome_delta)]">
            {{ formatDelta(run.outcome_delta) }}
          </span>
        </span>
        <span class="row__time">{{ shortTime(run.created_at) }}</span>
        <span class="row__action">
          <button
            v-if="isReviewable(run)"
            class="btn btn-small"
            data-testid="skill-sleep-review"
            @click="emit('open-run', run)"
          >
            {{ t('skillSleep.review') }}
          </button>
          <StatusBadge
            v-else-if="run.adopted_at"
            :label="t('skillSleep.adopted')"
            variant="info"
          />
        </span>
      </div>
    </div>

    <EmptyState
      v-else
      data-testid="skill-sleep-empty"
      :title="t('skillSleep.noRuns')"
      :description="t('skillSleep.noRunsHint')"
    />
  </section>
</template>

<style scoped>
.skill-sleep-card {
  min-height: 120px;
}

.rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.row {
  display: flex;
  align-items: center;
  gap: 12px;
  background: var(--bg-card-inner, rgba(255, 255, 255, 0.04));
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 0.85rem;
}

.row__skill {
  font-weight: 600;
  color: var(--text-primary, #eee);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1 1 auto;
}

.row__delta {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
}

.row__delta-label {
  font-size: 0.7rem;
  color: var(--text-muted, #999);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.delta-value {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.delta--up {
  color: var(--accent-green, #4ade80);
}

.delta--down {
  color: var(--accent-crimson, #f87171);
}

.delta--neutral {
  color: var(--text-muted, #999);
}

.row__time {
  font-size: 0.75rem;
  color: var(--text-muted, #999);
  font-variant-numeric: tabular-nums;
}

.row__action {
  margin-left: auto;
}

.error-msg {
  color: var(--accent-crimson, #f87171);
  font-size: 0.9rem;
  padding: 12px 0;
}
</style>
