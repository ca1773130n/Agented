<script setup lang="ts">
import { reactive, computed, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import type {
  PendingCheckpoint,
  CheckpointAnswer,
} from '../../../services/api/research';

const props = defineProps<{
  checkpoint: PendingCheckpoint;
  /** Disables the submit button while a resume is in flight. */
  submitting?: boolean;
}>();

const emit = defineEmits<{
  (e: 'submit', answers: CheckpointAnswer[]): void;
}>();

const { t } = useI18n();

/** Per-question working state: the chosen option label + optional free text. */
interface AnswerDraft {
  label: string;
  text: string;
}

const drafts = reactive<Record<string, AnswerDraft>>({});

/** Seed each question with its recommended option (if any) and empty text. */
function seedDrafts(cp: PendingCheckpoint) {
  for (const key of Object.keys(drafts)) delete drafts[key];
  for (const q of cp.questions) {
    const recommended = q.options.find((o) => o.recommended);
    drafts[q.id] = { label: recommended?.label ?? '', text: '' };
  }
}

seedDrafts(props.checkpoint);
watch(
  () => props.checkpoint,
  (cp) => seedDrafts(cp),
);

/** A friendly, localized label for the checkpoint stage. */
const pointLabel = computed(() => {
  const key = `researchCheckpoint.point.${props.checkpoint.point}`;
  const translated = t(key);
  return translated === key ? props.checkpoint.point : translated;
});

function isAnswered(questionId: string, freeform?: boolean): boolean {
  const draft = drafts[questionId];
  if (!draft || !draft.label) return false;
  if (freeform && draft.text.trim().length === 0) return false;
  return true;
}

const canSubmit = computed(
  () =>
    !props.submitting &&
    props.checkpoint.questions.every((q) => isAnswered(q.id, q.freeform)),
);

function submit() {
  if (!canSubmit.value) return;
  const answers: CheckpointAnswer[] = props.checkpoint.questions.map((q) => {
    const draft = drafts[q.id];
    const answer: CheckpointAnswer = { question_id: q.id, label: draft.label };
    if (q.freeform && draft.text.trim().length > 0) answer.text = draft.text.trim();
    return answer;
  });
  emit('submit', answers);
}
</script>

<template>
  <section class="checkpoint-panel" data-testid="checkpoint-panel">
    <header class="cp-header">
      <span class="cp-badge">{{ t('researchCheckpoint.pausedBadge') }}</span>
      <span class="cp-point">{{ pointLabel }}</span>
    </header>
    <p v-if="checkpoint.context" class="cp-context">{{ checkpoint.context }}</p>

    <form class="cp-form" @submit.prevent="submit">
      <fieldset
        v-for="question in checkpoint.questions"
        :key="question.id"
        class="cp-question"
      >
        <legend class="cp-ask">{{ question.ask }}</legend>

        <div class="cp-options" role="radiogroup">
          <label
            v-for="(option, oIdx) in question.options"
            :key="`${question.id}-${oIdx}`"
            class="cp-option"
            :for="`cp-${question.id}-${oIdx}`"
          >
            <input
              :id="`cp-${question.id}-${oIdx}`"
              v-model="drafts[question.id].label"
              type="radio"
              :name="`cp-${question.id}`"
              :value="option.label"
            />
            <span class="cp-option-body">
              <span class="cp-option-label">
                {{ option.label }}
                <span v-if="option.recommended" class="cp-recommended">
                  {{ t('researchCheckpoint.recommended') }}
                </span>
              </span>
              <span v-if="option.description" class="cp-option-desc">
                {{ option.description }}
              </span>
            </span>
          </label>
        </div>

        <div v-if="question.freeform" class="cp-freeform">
          <label :for="`cp-${question.id}-text`" class="cp-freeform-label">
            {{ t('researchCheckpoint.freeformLabel') }}
          </label>
          <textarea
            :id="`cp-${question.id}-text`"
            v-model="drafts[question.id].text"
            class="cp-textarea"
            rows="3"
            :placeholder="t('researchCheckpoint.freeformPlaceholder')"
          />
          <p
            v-if="!drafts[question.id].text.trim()"
            class="cp-required"
          >
            {{ t('researchCheckpoint.required') }}
          </p>
        </div>
      </fieldset>

      <button class="btn btn-primary cp-submit" type="submit" :disabled="!canSubmit">
        {{ t('researchCheckpoint.submit') }}
      </button>
    </form>
  </section>
</template>

<style scoped>
.checkpoint-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: var(--content-padding, 16px);
  background: var(--bg-secondary);
  border: 1px solid color-mix(in srgb, var(--accent-color, var(--accent-cyan)) 40%, var(--border-default));
  border-radius: 8px;
  transition: border-color var(--transition-base, 0.2s ease);
}
.cp-header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.cp-badge {
  padding: 3px 10px;
  border-radius: 10px;
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--text-on-accent, #fff);
  background: var(--accent-color, var(--accent-cyan));
}
.cp-point {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
}
.cp-context {
  margin: 0;
  font-size: 0.85rem;
  line-height: 1.5;
  color: var(--text-secondary);
}
.cp-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.cp-question {
  margin: 0;
  padding: 12px;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  background: var(--bg-tertiary);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.cp-ask {
  padding: 0 4px;
  font-size: 0.88rem;
  font-weight: 600;
  color: var(--text-primary);
}
.cp-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.cp-option {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--border-subtle, var(--border-default));
  border-radius: 6px;
  cursor: pointer;
  transition: border-color var(--transition-fast, 0.15s ease);
}
.cp-option:hover {
  border-color: var(--accent-color, var(--accent-cyan));
}
.cp-option input[type='radio'] {
  margin-top: 3px;
  accent-color: var(--accent-color, var(--accent-cyan));
}
.cp-option-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.cp-option-label {
  font-size: 0.85rem;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 6px;
}
.cp-recommended {
  font-size: 0.68rem;
  font-weight: 600;
  text-transform: uppercase;
  padding: 1px 6px;
  border-radius: 8px;
  color: var(--accent-color, var(--accent-cyan));
  background: color-mix(in srgb, var(--accent-color, var(--accent-cyan)) 15%, transparent);
}
.cp-option-desc {
  font-size: 0.78rem;
  color: var(--text-tertiary);
  line-height: 1.4;
}
.cp-freeform {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.cp-freeform-label {
  font-size: 0.8rem;
  color: var(--text-secondary);
}
.cp-textarea {
  resize: vertical;
  padding: 8px 10px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-family: var(--font, inherit);
  font-size: 0.85rem;
}
.cp-required {
  margin: 0;
  font-size: 0.75rem;
  color: var(--danger, var(--accent-crimson));
}
.cp-submit {
  align-self: flex-start;
}
</style>
