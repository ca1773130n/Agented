<script setup lang="ts">
/**
 * GoalLoopStatusBanner
 *
 * Live status strip shown above the chat input in goal_loop
 * sessions. Reads the live `iteration` / `verdict` / `reason`
 * from the parent's reactive state (which is fed by
 * useProjectSession's onGoalIterationStarted /
 * onGoalIterationCompleted / onGoalLoopEnded SSE handlers).
 *
 * Stateless — pure presentation. The panel owns the state so
 * the banner can be unmounted/remounted across session switches
 * without losing context.
 *
 * v0.7.74.
 */
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { GoalIterationCompletedPayload } from '../../composables/useProjectSession';

const { t } = useI18n();

const props = defineProps<{
  goal: string;
  iteration: number;
  maxIterations: number;
  lastVerdict: GoalIterationCompletedPayload | null;
  endedReason: string | null;
  endedDetail: string | null;
  judging: boolean;
}>();

const progressLabel = computed(() => {
  if (props.endedReason) return t('goalLoopStatusBanner.done');
  if (props.judging) return t('goalLoopStatusBanner.judging');
  return t('goalLoopStatusBanner.iter', {
    current: props.iteration,
    max: props.maxIterations,
  });
});

const verdictTone = computed(() => {
  if (props.endedReason === 'met') return 'good';
  if (
    props.endedReason === 'iteration_cap' ||
    props.endedReason === 'wall_time_cap'
  )
    return 'warn';
  if (props.endedReason === 'stopped') return 'neutral';
  if (props.lastVerdict?.verdict === 'met') return 'good';
  if (props.lastVerdict?.verdict === 'not_met') return 'neutral';
  return 'neutral';
});

const endedLabel = computed(() => {
  if (!props.endedReason) return null;
  const reasons: Record<string, string> = {
    met: t('goalLoopStatusBanner.reasonMet'),
    iteration_cap: t('goalLoopStatusBanner.reasonIterationCap'),
    wall_time_cap: t('goalLoopStatusBanner.reasonWallTimeCap'),
    stopped: t('goalLoopStatusBanner.reasonStopped'),
  };
  return reasons[props.endedReason] ?? props.endedReason;
});
</script>

<template>
  <div class="goal-banner" :data-tone="verdictTone">
    <div class="goal-banner-line goal-banner-head">
      <span class="goal-banner-label">{{ t('goalLoopStatusBanner.goalLabel') }}</span>
      <span class="goal-banner-goal">{{ props.goal }}</span>
      <span class="goal-banner-progress">{{ progressLabel }}</span>
    </div>
    <div v-if="endedLabel" class="goal-banner-line goal-banner-ended">
      <span class="goal-banner-flag">{{ endedLabel }}</span>
      <span v-if="endedDetail" class="goal-banner-reason">
        {{ endedDetail }}
      </span>
    </div>
    <div
      v-else-if="lastVerdict"
      class="goal-banner-line goal-banner-verdict"
    >
      <span class="goal-banner-source">{{ lastVerdict.source }}</span>
      <span class="goal-banner-flag">{{ lastVerdict.verdict }}</span>
      <span class="goal-banner-reason">{{ lastVerdict.reason }}</span>
    </div>
  </div>
</template>

<style scoped>
.goal-banner {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 14px;
  border-top: 1px solid var(--border-default);
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
  font-family: 'Geist', system-ui, sans-serif;
  font-size: 12px;
}
.goal-banner[data-tone='good'] {
  border-left: 3px solid var(--accent-emerald, #00ff88);
}
.goal-banner[data-tone='warn'] {
  border-left: 3px solid var(--accent-amber, #ffb454);
}
.goal-banner[data-tone='neutral'] {
  border-left: 3px solid var(--accent-cyan);
}

.goal-banner-line {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.goal-banner-label {
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-tertiary);
  font-size: 10px;
  font-weight: 600;
}
.goal-banner-goal {
  flex: 1;
  color: var(--text-primary);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.goal-banner-progress {
  color: var(--text-secondary);
  font-family: 'Geist Mono', monospace;
  font-size: 11px;
}
.goal-banner-source {
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-tertiary);
  font-size: 10px;
  min-width: 70px;
}
.goal-banner-flag {
  color: var(--text-primary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-size: 11px;
  font-weight: 600;
}
.goal-banner-reason {
  color: var(--text-secondary);
  font-family: 'Geist Mono', monospace;
  font-size: 11px;
  flex: 1;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.goal-banner-ended .goal-banner-flag {
  color: var(--text-primary);
}
</style>
