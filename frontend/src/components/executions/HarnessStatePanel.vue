<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import type { ExecutionStateSnapshot } from '../../services/api';
import { executionApi } from '../../services/api';

const props = defineProps<{
  executionId: string;
}>();

const { t } = useI18n();
const snapshot = ref<ExecutionStateSnapshot | null>(null);
const error = ref(false);
let pollTimer: ReturnType<typeof setInterval> | null = null;

const isRunning = computed(() => snapshot.value?.execution.status === 'running');
const budgetRatio = computed(() => {
  const used = snapshot.value?.run?.budget_used ?? 0;
  const limit = snapshot.value?.per_run_limit_usd;
  return limit ? used / limit : null;
});
const budgetWarning = computed(() => budgetRatio.value !== null && budgetRatio.value >= 0.8);

async function fetchState() {
  try {
    snapshot.value = await executionApi.getState(props.executionId);
    error.value = false;
    if (!isRunning.value) stopPolling();
  } catch {
    error.value = true;
    stopPolling();
  }
}

function startPolling() {
  stopPolling();
  pollTimer = setInterval(fetchState, 5000);
}

function stopPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

onMounted(async () => {
  await fetchState();
  if (isRunning.value) startPolling();
});
onBeforeUnmount(stopPolling);
watch(() => props.executionId, async () => {
  stopPolling();
  await fetchState();
  if (isRunning.value) startPolling();
});
</script>

<template>
  <div class="harness-state-panel">
    <h4>{{ t('harnessState.title') }}</h4>
    <div v-if="error" class="harness-state-error">{{ t('harnessState.error') }}</div>
    <div v-else-if="!snapshot" class="harness-state-loading">{{ t('harnessState.loading') }}</div>
    <div v-else-if="!snapshot.run" class="harness-state-empty">{{ t('harnessState.noState') }}</div>
    <template v-else>
      <dl class="state-grid">
        <dt>{{ t('harnessState.runStatus') }}</dt>
        <dd>{{ snapshot.run.status }}</dd>
        <dt>{{ t('harnessState.stepCursor') }}</dt>
        <dd>{{ snapshot.run.step_cursor }}</dd>
        <dt>{{ t('harnessState.budget') }}</dt>
        <dd :class="{ 'budget-warning': budgetWarning }">
          ${{ snapshot.run.budget_used.toFixed(2) }}
          <span v-if="snapshot.per_run_limit_usd !== null">
            {{ t('harnessState.budgetOf', { limit: snapshot.per_run_limit_usd.toFixed(2) }) }}
          </span>
        </dd>
        <dt>{{ t('harnessState.lastCheckpoint') }}</dt>
        <dd>
          <template v-if="snapshot.latest_checkpoint">
            {{ t('harnessState.step', { step: snapshot.latest_checkpoint.step }) }}
            · {{ snapshot.latest_checkpoint.created_at }}
            ({{ snapshot.checkpoint_count }})
          </template>
          <template v-else>—</template>
        </dd>
      </dl>
      <div v-if="snapshot.verifications.length" class="verifications">
        <h5>{{ t('harnessState.verifications') }}</h5>
        <ul>
          <li v-for="v in snapshot.verifications" :key="v.id" :data-status="v.status">
            <span class="claim">{{ v.claim }}</span>
            <span class="status">{{ t(`harnessState.status_${v.status}`) }}</span>
          </li>
        </ul>
      </div>
    </template>
  </div>
</template>

<style scoped>
.harness-state-panel {
  padding: 0.75rem 1rem;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  margin-bottom: 0.75rem;
  font-size: 0.85rem;
}
.state-grid {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.25rem 1rem;
  margin: 0;
}
.state-grid dt { opacity: 0.7; }
.state-grid dd { margin: 0; }
.budget-warning { color: var(--warning); font-weight: 600; }
.verifications ul { list-style: none; padding: 0; margin: 0.25rem 0 0; }
.verifications li { display: flex; justify-content: space-between; gap: 1rem; }
.verifications li[data-status='failed'] .status { color: var(--danger); }
.verifications li[data-status='passed'] .status { color: var(--success); }
</style>
