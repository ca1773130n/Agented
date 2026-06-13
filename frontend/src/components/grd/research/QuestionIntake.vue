<script setup lang="ts">
import { ref, computed } from 'vue';
import { useI18n } from 'vue-i18n';

const props = defineProps<{
  status?: string;
}>();

const emit = defineEmits<{
  (e: 'submit', question: string, opts: { max_iterations?: number; no_gates?: boolean }): void;
}>();

const { t } = useI18n();

const question = ref('');
const maxIterations = ref<number | null>(null);
const noGates = ref(false);

const isRunning = computed(() => props.status === 'running' || props.status === 'waiting_input');
const canSubmit = computed(() => question.value.trim().length > 0 && !isRunning.value);

function submit() {
  if (!canSubmit.value) return;
  const opts: { max_iterations?: number; no_gates?: boolean } = {};
  if (maxIterations.value != null) opts.max_iterations = maxIterations.value;
  if (noGates.value) opts.no_gates = true;
  emit('submit', question.value.trim(), opts);
}
</script>

<template>
  <form class="question-intake" @submit.prevent="submit">
    <label class="intake-label" for="research-question">{{ t('surface.research.intake.prompt') }}</label>
    <textarea
      id="research-question"
      v-model="question"
      class="intake-input"
      :placeholder="t('surface.research.intake.placeholder')"
      rows="3"
    />
    <div class="intake-options">
      <label class="opt">
        {{ t('surface.research.intake.maxIterations') }}
        <input v-model.number="maxIterations" type="number" min="1" class="opt-num" />
      </label>
      <label class="opt">
        <input v-model="noGates" type="checkbox" />
        {{ t('surface.research.intake.noGates') }}
      </label>
    </div>
    <button class="btn btn-primary" type="submit" :disabled="!canSubmit">
      {{ t('surface.research.intake.submit') }}
    </button>
  </form>
</template>

<style scoped>
.question-intake {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
}
.intake-label {
  font-size: 0.85rem;
  color: var(--text-secondary);
}
.intake-input {
  resize: vertical;
  padding: 8px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-family: inherit;
  font-size: 0.9rem;
}
.intake-options {
  display: flex;
  gap: 16px;
  align-items: center;
  font-size: 0.8rem;
  color: var(--text-secondary);
}
.opt {
  display: flex;
  align-items: center;
  gap: 6px;
}
.opt-num {
  width: 64px;
  padding: 4px 6px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  color: var(--text-primary);
}
</style>
