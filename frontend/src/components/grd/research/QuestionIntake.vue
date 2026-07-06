<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useI18n } from 'vue-i18n';

const props = defineProps<{
  status?: string;
}>();

const emit = defineEmits<{
  (
    e: 'submit',
    question: string,
    opts: { max_iterations?: number; no_gates?: boolean; deep?: boolean; ultracode?: boolean },
  ): void;
  // Fires on mode toggle so the page can swap panels immediately (browse deep
  // reports without first running a deep-research), not only on submit.
  (e: 'modeChange', deep: boolean): void;
}>();

const { t } = useI18n();

const question = ref('');
const maxIterations = ref<number | null>(null);
const noGates = ref(false);
const mode = ref<'loop' | 'deep'>('loop');
const ultracode = ref(false);

watch(mode, (m) => emit('modeChange', m === 'deep'));

const isRunning = computed(() => props.status === 'running' || props.status === 'waiting_input');
const canSubmit = computed(() => question.value.trim().length > 0 && !isRunning.value);

function submit() {
  if (!canSubmit.value) return;
  const opts: { max_iterations?: number; no_gates?: boolean; deep?: boolean; ultracode?: boolean } =
    {};
  if (mode.value === 'deep') {
    // Deep-research ignores the loop knobs; carry only deep + ultracode.
    opts.deep = true;
    if (ultracode.value) opts.ultracode = true;
  } else {
    if (maxIterations.value != null) opts.max_iterations = maxIterations.value;
    if (noGates.value) opts.no_gates = true;
  }
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
    <div class="intake-mode">
      <span class="mode-label">{{ t('surface.research.intake.modeLabel') }}</span>
      <div class="mode-seg" role="tablist">
        <button
          type="button"
          class="seg-btn"
          :class="{ active: mode === 'loop' }"
          role="tab"
          :aria-selected="mode === 'loop'"
          @click="mode = 'loop'"
        >
          {{ t('surface.research.intake.modeLoop') }}
        </button>
        <button
          type="button"
          class="seg-btn"
          :class="{ active: mode === 'deep' }"
          role="tab"
          :aria-selected="mode === 'deep'"
          @click="mode = 'deep'"
        >
          {{ t('surface.research.intake.modeDeep') }}
        </button>
      </div>
    </div>

    <div v-if="mode === 'loop'" class="intake-options">
      <label class="opt">
        {{ t('surface.research.intake.maxIterations') }}
        <input v-model.number="maxIterations" type="number" min="1" class="opt-num" />
      </label>
      <label class="opt">
        <input v-model="noGates" type="checkbox" />
        {{ t('surface.research.intake.noGates') }}
      </label>
    </div>

    <div v-else class="intake-deep">
      <p class="deep-helper">{{ t('surface.research.intake.deepHelper') }}</p>
      <label class="opt">
        <input v-model="ultracode" type="checkbox" />
        {{ t('surface.research.intake.ultracode') }}
      </label>
      <p class="deep-helper deep-warn">{{ t('surface.research.intake.ultracodeHelper') }}</p>
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
.intake-mode {
  display: flex;
  align-items: center;
  gap: 10px;
}
.mode-label {
  font-size: 0.8rem;
  color: var(--text-secondary);
}
.mode-seg {
  display: inline-flex;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  padding: 2px;
  gap: 2px;
}
.seg-btn {
  padding: 4px 12px;
  font-size: 0.8rem;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}
.seg-btn.active {
  background: var(--accent-cyan);
  color: var(--text-on-accent);
}
.intake-deep {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.deep-helper {
  margin: 0;
  font-size: 0.78rem;
  color: var(--text-secondary);
  line-height: 1.4;
}
.deep-warn {
  color: var(--text-tertiary);
}
</style>
