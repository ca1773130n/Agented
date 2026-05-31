<script setup lang="ts">
/**
 * Render an ``AskUserQuestion`` payload from claude as clickable
 * options (v0.7.63). Mirrors the claude TUI prompt: each question
 * shows a header chip, the question prompt, and either radio-style
 * options (when ``multiSelect`` is false) or checkbox-style options.
 *
 * On submit, parent emits ``confirm`` with the ``{question → answer}``
 * map. The ProjectSessionPanel forwards that to
 * ``grdApi.answerSessionQuestion`` which wraps it as a ``tool_result``
 * for claude.
 */
import { ref, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { AskUserQuestionItem } from '../../composables/useProjectSession';

const { t } = useI18n();

const props = defineProps<{
  questions: AskUserQuestionItem[];
}>();

const emit = defineEmits<{
  (e: 'confirm', answers: Record<string, string | string[]>): void;
  (e: 'cancel'): void;
}>();

// Per-question selection state. Single-select stores a string (the
// label); multi-select stores an array of labels. Initialized empty
// so the submit button stays disabled until the user picks.
const selections = ref<Record<string, string | string[]>>({});

function isSelected(q: AskUserQuestionItem, label: string): boolean {
  const v = selections.value[q.question];
  if (q.multiSelect) return Array.isArray(v) && v.includes(label);
  return v === label;
}

function toggle(q: AskUserQuestionItem, label: string) {
  if (q.multiSelect) {
    const arr = Array.isArray(selections.value[q.question])
      ? [...(selections.value[q.question] as string[])]
      : [];
    const idx = arr.indexOf(label);
    if (idx >= 0) arr.splice(idx, 1);
    else arr.push(label);
    selections.value = { ...selections.value, [q.question]: arr };
  } else {
    selections.value = { ...selections.value, [q.question]: label };
  }
}

const canSubmit = computed(() =>
  props.questions.every((q) => {
    const v = selections.value[q.question];
    if (q.multiSelect) return Array.isArray(v) && v.length > 0;
    return typeof v === 'string' && v.length > 0;
  }),
);

function onSubmit() {
  if (!canSubmit.value) return;
  emit('confirm', selections.value);
}
</script>

<template>
  <div class="iq-card">
    <div class="iq-card-header">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="16" x2="12" y2="12" />
        <line x1="12" y1="8" x2="12.01" y2="8" />
      </svg>
      <span>{{ t('interactiveQuestionCard.header') }}</span>
    </div>

    <div class="iq-questions">
      <section v-for="q in questions" :key="q.question" class="iq-question">
        <div class="iq-question-meta">
          <span v-if="q.header" class="iq-chip">{{ q.header }}</span>
          <span v-if="q.multiSelect" class="iq-multi">{{ t('interactiveQuestionCard.pickAll') }}</span>
        </div>
        <p class="iq-prompt">{{ q.question }}</p>
        <div class="iq-options">
          <button
            v-for="opt in q.options"
            :key="opt.label"
            type="button"
            class="iq-option"
            :class="{ selected: isSelected(q, opt.label) }"
            @click="toggle(q, opt.label)"
          >
            <span class="iq-option-marker" aria-hidden="true">
              <span v-if="isSelected(q, opt.label)" class="iq-option-dot" />
            </span>
            <span class="iq-option-body">
              <span class="iq-option-label">{{ opt.label }}</span>
              <span v-if="opt.description" class="iq-option-desc">
                {{ opt.description }}
              </span>
            </span>
          </button>
        </div>
      </section>
    </div>

    <div class="iq-actions">
      <button type="button" class="iq-btn iq-btn-secondary" @click="emit('cancel')">
        {{ t('common.skip') }}
      </button>
      <button
        type="button"
        class="iq-btn iq-btn-primary"
        :disabled="!canSubmit"
        @click="onSubmit"
      >
        {{ t('interactiveQuestionCard.sendAnswer') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.iq-card {
  margin: 12px 0;
  border: 1px solid var(--accent-cyan, #00bcd4);
  border-radius: 10px;
  background: linear-gradient(
    to bottom,
    rgba(0, 188, 212, 0.06),
    var(--bg-secondary)
  );
  overflow: hidden;
}

.iq-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: rgba(0, 188, 212, 0.1);
  border-bottom: 1px solid rgba(0, 188, 212, 0.2);
  font-size: 12px;
  font-weight: 600;
  color: var(--accent-cyan, #00bcd4);
  letter-spacing: 0.02em;
}
.iq-card-header svg {
  width: 14px;
  height: 14px;
}

.iq-questions {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 16px;
}

.iq-question-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.iq-chip {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}
.iq-multi {
  font-size: 11px;
  font-style: italic;
  color: var(--text-muted);
}
.iq-prompt {
  margin: 0 0 10px;
  font-size: 14px;
  line-height: 1.45;
  color: var(--text-primary);
}

.iq-options {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.iq-option {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  text-align: left;
  cursor: pointer;
  font-family: inherit;
  font-size: 13px;
  color: var(--text-primary);
  transition: border-color 0.12s, background 0.12s;
}
.iq-option:hover {
  border-color: var(--accent-cyan, #00bcd4);
}
.iq-option.selected {
  border-color: var(--accent-cyan, #00bcd4);
  background: rgba(0, 188, 212, 0.08);
}

.iq-option-marker {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 1.5px solid var(--border-default);
  background: var(--bg-primary);
  flex-shrink: 0;
  margin-top: 1px;
}
.iq-option.selected .iq-option-marker {
  border-color: var(--accent-cyan, #00bcd4);
}
.iq-option-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent-cyan, #00bcd4);
}

.iq-option-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}
.iq-option-label {
  font-weight: 600;
  color: var(--text-primary);
}
.iq-option-desc {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.4;
}

.iq-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--border-default);
  background: var(--bg-primary);
}
.iq-btn {
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid var(--border-default);
  background: var(--bg-tertiary);
  color: var(--text-primary);
  font-family: inherit;
  font-size: 13px;
  cursor: pointer;
}
.iq-btn-primary {
  background: var(--accent-cyan, #00bcd4);
  color: #002;
  border-color: var(--accent-cyan, #00bcd4);
  font-weight: 600;
}
.iq-btn-primary:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.iq-btn-secondary:hover {
  background: var(--bg-secondary);
}
</style>
