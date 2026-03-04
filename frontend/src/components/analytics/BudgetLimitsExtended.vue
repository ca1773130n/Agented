<script setup lang="ts">
import { ref, watch } from 'vue';

const props = withDefaults(defineProps<{
  entityType: string;
  entityId: string;
  existingLimits?: {
    max_execution_time?: number | null;
    max_monthly_runs?: number | null;
  } | null;
}>(), {
  existingLimits: null,
});

const emit = defineEmits<{
  save: [limits: { max_execution_time: number | null; max_monthly_runs: number | null }];
}>();

const maxExecutionTime = ref<string>('');
const maxMonthlyRuns = ref<string>('');
const fieldErrors = ref<Record<string, string>>({});
const isSaving = ref(false);

function populateFromExisting() {
  if (props.existingLimits) {
    maxExecutionTime.value = props.existingLimits.max_execution_time != null
      ? String(props.existingLimits.max_execution_time) : '';
    maxMonthlyRuns.value = props.existingLimits.max_monthly_runs != null
      ? String(props.existingLimits.max_monthly_runs) : '';
  }
}

watch(() => props.existingLimits, populateFromExisting, { immediate: true });

function validate(): boolean {
  fieldErrors.value = {};

  const execTime = maxExecutionTime.value.trim();
  if (execTime) {
    const val = parseInt(execTime, 10);
    if (isNaN(val) || val <= 0) {
      fieldErrors.value.maxExecutionTime = 'Must be a positive integer or empty';
    }
  }

  const monthlyRuns = maxMonthlyRuns.value.trim();
  if (monthlyRuns) {
    const val = parseInt(monthlyRuns, 10);
    if (isNaN(val) || val <= 0) {
      fieldErrors.value.maxMonthlyRuns = 'Must be a positive integer or empty';
    }
  }

  return Object.keys(fieldErrors.value).length === 0;
}

function handleSave() {
  if (!validate()) return;

  isSaving.value = true;
  const execTime = maxExecutionTime.value.trim();
  const monthlyRuns = maxMonthlyRuns.value.trim();

  emit('save', {
    max_execution_time: execTime ? parseInt(execTime, 10) : null,
    max_monthly_runs: monthlyRuns ? parseInt(monthlyRuns, 10) : null,
  });

  isSaving.value = false;
}
</script>

<template>
  <div class="budget-limits-extended">
    <div class="section-header">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <circle cx="12" cy="12" r="10"/>
        <polyline points="12 6 12 12 16 14"/>
      </svg>
      <div>
        <h4>Execution Limits</h4>
        <p class="section-subtitle">Set guardrails for execution time and monthly run count</p>
      </div>
    </div>

    <div class="form-fields">
      <!-- Max Execution Time -->
      <div class="form-group">
        <label>Maximum execution time per run (seconds)</label>
        <input
          type="number"
          v-model="maxExecutionTime"
          min="1"
          step="1"
          placeholder="No limit"
          :class="{ error: fieldErrors.maxExecutionTime }"
        >
        <div class="field-hint">Execution will be gracefully cancelled if it exceeds this limit. Leave empty for no limit.</div>
        <div v-if="fieldErrors.maxExecutionTime" class="field-error">{{ fieldErrors.maxExecutionTime }}</div>
      </div>

      <!-- Max Monthly Runs -->
      <div class="form-group">
        <label>Maximum executions per month</label>
        <input
          type="number"
          v-model="maxMonthlyRuns"
          min="1"
          step="1"
          placeholder="No limit"
          :class="{ error: fieldErrors.maxMonthlyRuns }"
        >
        <div class="field-hint">New executions will be blocked after reaching this limit. Leave empty for no limit.</div>
        <div v-if="fieldErrors.maxMonthlyRuns" class="field-error">{{ fieldErrors.maxMonthlyRuns }}</div>
      </div>
    </div>

    <div class="form-actions">
      <button class="btn btn-primary" :disabled="isSaving" @click="handleSave">
        {{ isSaving ? 'Saving...' : 'Save Limits' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.budget-limits-extended {
  padding: 20px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
}

.section-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 20px;
}

.section-header svg {
  width: 20px;
  height: 20px;
  color: var(--accent-violet);
  flex-shrink: 0;
  margin-top: 2px;
}

.section-header h4 {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 2px;
}

.section-subtitle {
  font-size: 0.8rem;
  color: var(--text-tertiary);
}

.form-fields {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group label {
  font-size: 0.8rem;
  color: var(--text-secondary);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.form-group input {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  font-size: 0.9rem;
  font-family: var(--font-mono);
  background: var(--bg-primary);
  color: var(--text-primary);
  transition: all var(--transition-fast);
}

.form-group input:focus {
  border-color: var(--primary-color);
  outline: none;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
}

.form-group input.error {
  border-color: #ef4444;
}

.form-group input.error:focus {
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.15);
}

.form-group input::placeholder {
  color: var(--text-muted);
}

.field-hint {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.field-error {
  font-size: 0.75rem;
  color: #ef4444;
}

.form-actions {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.btn-primary {
  background: var(--primary-color);
  color: white;
  border: none;
  padding: 8px 18px;
  border-radius: 8px;
  font-weight: 600;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-primary:hover:not(:disabled) {
  background: var(--primary-hover);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
