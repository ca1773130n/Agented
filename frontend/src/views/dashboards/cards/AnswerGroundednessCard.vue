<!--
  AnswerGroundednessCard — shows the latest completed answer-eval run
  across ALL projects (QualityPage has no project context).
  Displays project name + three delta stats (groundedness/sufficiency/quality,
  pipeline − baseline) with up/down arrow styling.
-->
<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { answerEvalApi, ApiError } from '../../../services/api';
import type { AnswerEvalRun } from '../../../services/api';
import LoadingState from '../../../components/base/LoadingState.vue';
import EmptyState from '../../../components/base/EmptyState.vue';

const emit = defineEmits<{ loaded: [slug: string] }>();
const { t } = useI18n();

const isLoading = ref(true);
const loadError = ref<string | null>(null);
const latestRun = ref<AnswerEvalRun | null>(null);

async function loadData() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const res = await answerEvalApi.listRuns(undefined);
    const runs = (res?.runs ?? []) as AnswerEvalRun[];
    // Pick the latest completed run globally (sorted desc by id / created_at)
    const completed = runs.filter((r) => r.status === 'complete');
    latestRun.value = completed.length > 0 ? completed[0] : null;
  } catch (err) {
    loadError.value = err instanceof ApiError ? err.message : t('answerEval.loadError');
  } finally {
    isLoading.value = false;
    emit('loaded', 'answer-groundedness');
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

onMounted(loadData);
</script>

<template>
  <section id="answer-groundedness" class="lane-card answer-groundedness-card">
    <header class="lane-card__head">
      <div>
        <h2 class="lane-card__title">{{ t('answerEval.cardTitle') }}</h2>
        <p class="lane-card__subtitle">{{ t('answerEval.cardSubtitle') }}</p>
      </div>
    </header>

    <LoadingState v-if="isLoading" :message="t('answerEval.cardTitle')" />

    <div v-else-if="loadError" class="error-msg">{{ loadError }}</div>

    <template v-else-if="latestRun">
      <div class="run-meta">
        <span class="project-label">{{ t('answerEval.projectLabel') }}:</span>
        <span class="project-name">{{ latestRun.project_name ?? latestRun.project_id }}</span>
        <span class="run-status">{{ t(`answerEval.status${latestRun.status.charAt(0).toUpperCase() + latestRun.status.slice(1)}`) }}</span>
      </div>

      <div class="delta-grid">
        <!-- Groundedness -->
        <div class="delta-item">
          <span class="delta-label">{{ t('answerEval.groundedness') }}</span>
          <span :class="['delta-value', deltaClass(latestRun.delta_groundedness)]">
            {{ formatDelta(latestRun.delta_groundedness) }}
          </span>
        </div>
        <!-- Sufficiency -->
        <div class="delta-item">
          <span class="delta-label">{{ t('answerEval.sufficiency') }}</span>
          <span :class="['delta-value', deltaClass(latestRun.delta_sufficiency)]">
            {{ formatDelta(latestRun.delta_sufficiency) }}
          </span>
        </div>
        <!-- Quality -->
        <div class="delta-item">
          <span class="delta-label">{{ t('answerEval.quality') }}</span>
          <span :class="['delta-value', deltaClass(latestRun.delta_quality)]">
            {{ formatDelta(latestRun.delta_quality) }}
          </span>
        </div>
      </div>
    </template>

    <EmptyState
      v-else
      data-testid="answer-eval-empty"
      :message="t('answerEval.noRuns')"
      :hint="t('answerEval.noRunsHint')"
    />
  </section>
</template>

<style scoped>
.answer-groundedness-card {
  min-height: 120px;
}

.run-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.85rem;
  color: var(--text-muted, #999);
  margin-bottom: 16px;
}

.project-name {
  font-weight: 600;
  color: var(--text-primary, #eee);
}

.run-status {
  font-size: 0.75rem;
  background: var(--bg-chip, rgba(255,255,255,0.08));
  border-radius: 4px;
  padding: 2px 6px;
}

.delta-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.delta-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: var(--bg-card-inner, rgba(255,255,255,0.04));
  border-radius: 8px;
  padding: 10px 14px;
}

.delta-label {
  font-size: 0.75rem;
  color: var(--text-muted, #999);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.delta-value {
  font-size: 1.2rem;
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

.error-msg {
  color: var(--accent-crimson, #f87171);
  font-size: 0.9rem;
  padding: 12px 0;
}
</style>
