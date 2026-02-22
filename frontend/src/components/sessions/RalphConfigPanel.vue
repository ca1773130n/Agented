<script setup lang="ts">
import { ref, computed } from 'vue';
import type { RalphConfig } from '../../services/api/grd';

const emit = defineEmits<{
  (e: 'start', config: RalphConfig): void;
  (e: 'cancel'): void;
}>();

const taskDescription = ref('');
const maxIterations = ref(50);
const completionPromise = ref('COMPLETE');
const noProgressThreshold = ref(3);

const isValid = computed(() => taskDescription.value.trim().length > 0);

function handleSubmit() {
  if (!isValid.value) return;
  emit('start', {
    task_description: taskDescription.value.trim(),
    max_iterations: maxIterations.value,
    completion_promise: completionPromise.value,
    no_progress_threshold: noProgressThreshold.value,
  });
}
</script>

<template>
  <div class="ralph-config">
    <h4 class="config-title">Configure Ralph Loop</h4>

    <form class="config-form" @submit.prevent="handleSubmit">
      <div class="form-group">
        <label class="form-label" for="ralph-task">Task Description</label>
        <textarea
          id="ralph-task"
          v-model="taskDescription"
          class="form-textarea"
          placeholder="Describe the task for Ralph to complete..."
          rows="3"
          required
        />
      </div>

      <div class="form-group">
        <label class="form-label" for="ralph-max-iter">Max Iterations</label>
        <input
          id="ralph-max-iter"
          v-model.number="maxIterations"
          type="number"
          class="form-input"
          min="1"
          max="500"
        />
      </div>

      <div class="form-group">
        <label class="form-label" for="ralph-promise">Completion Promise</label>
        <input
          id="ralph-promise"
          v-model="completionPromise"
          type="text"
          class="form-input"
          placeholder="COMPLETE"
        />
      </div>

      <div class="form-group">
        <label class="form-label" for="ralph-threshold">No Progress Threshold</label>
        <input
          id="ralph-threshold"
          v-model.number="noProgressThreshold"
          type="number"
          class="form-input"
          min="1"
          max="20"
        />
      </div>

      <div class="form-actions">
        <button type="button" class="btn-cancel" @click="$emit('cancel')">Cancel</button>
        <button type="submit" class="btn-start" :disabled="!isValid">Start Ralph Loop</button>
      </div>
    </form>
  </div>
</template>

<style scoped>
.ralph-config {
  padding: 16px;
}

.config-title {
  margin: 0 0 16px 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.config-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
}

.form-input,
.form-textarea {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 13px;
  font-family: inherit;
  outline: none;
  transition: border-color 0.15s;
}

.form-input:focus,
.form-textarea:focus {
  border-color: var(--accent-cyan);
}

.form-textarea {
  resize: vertical;
  min-height: 60px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}

.btn-cancel {
  background: transparent;
  color: var(--text-muted);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  padding: 6px 14px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-cancel:hover {
  color: var(--text-primary);
  border-color: var(--border-subtle);
}

.btn-start {
  background: var(--accent-cyan);
  color: #000;
  border: none;
  border-radius: 6px;
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s;
}

.btn-start:hover:not(:disabled) {
  opacity: 0.9;
}

.btn-start:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
