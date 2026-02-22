<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import type { BudgetLimit } from '../../services/api';
import { budgetApi } from '../../services/api';
import { useFocusTrap } from '../../composables/useFocusTrap';

const props = withDefaults(defineProps<{
  mode?: 'create' | 'edit';
  existingLimit?: BudgetLimit | null;
  agents?: { id: string; name: string }[];
  teams?: { id: string; name: string }[];
  triggers?: { id: string; name: string }[];
}>(), {
  mode: 'create',
  existingLimit: null,
  agents: () => [],
  teams: () => [],
  triggers: () => [],
});

const emit = defineEmits<{
  (e: 'saved'): void;
  (e: 'cancelled'): void;
}>();

const budgetModalRef = ref<HTMLElement | null>(null);
const alwaysOpen = ref(true);
useFocusTrap(budgetModalRef, alwaysOpen);

// Form state
const entityType = ref<'agent' | 'team' | 'trigger'>('agent');
const entityId = ref('');
const period = ref<'daily' | 'weekly' | 'monthly'>('monthly');
const softLimit = ref<string>('');
const hardLimit = ref<string>('');
const isSubmitting = ref(false);
const errorMessage = ref('');
const fieldErrors = ref<Record<string, string>>({});

// Pre-populate in edit mode
function populateFromExisting() {
  if (props.existingLimit && props.mode === 'edit') {
    entityType.value = props.existingLimit.entity_type as 'agent' | 'team' | 'trigger';
    entityId.value = props.existingLimit.entity_id;
    period.value = props.existingLimit.period as 'daily' | 'weekly' | 'monthly';
    softLimit.value = props.existingLimit.soft_limit_usd != null ? String(props.existingLimit.soft_limit_usd) : '';
    hardLimit.value = props.existingLimit.hard_limit_usd != null ? String(props.existingLimit.hard_limit_usd) : '';
  }
}

watch(() => props.existingLimit, populateFromExisting, { immediate: true });

// Entity options based on type
const entityOptions = computed(() => {
  if (entityType.value === 'agent') return props.agents;
  if (entityType.value === 'trigger') return props.triggers;
  return props.teams;
});

// Entity name for display in edit mode
const entityDisplayName = computed(() => {
  if (!entityId.value) return '';
  const options = entityType.value === 'agent' ? props.agents : (entityType.value === 'trigger' ? props.triggers : props.teams);
  const found = options.find(o => o.id === entityId.value);
  return found ? `${found.name} (${entityId.value})` : entityId.value;
});

// Validation
function validate(): boolean {
  fieldErrors.value = {};
  errorMessage.value = '';

  if (!entityId.value) {
    fieldErrors.value.entity = 'Please select an entity';
  }

  const soft = softLimit.value.trim() ? parseFloat(softLimit.value) : null;
  const hard = hardLimit.value.trim() ? parseFloat(hardLimit.value) : null;

  if (soft == null && hard == null) {
    fieldErrors.value.limits = 'At least one limit (alert or halt threshold) must be set';
  }

  if (soft != null && (isNaN(soft) || soft <= 0)) {
    fieldErrors.value.soft = 'Alert threshold must be a positive number';
  }

  if (hard != null && (isNaN(hard) || hard <= 0)) {
    fieldErrors.value.hard = 'Halt threshold must be a positive number';
  }

  if (soft != null && hard != null && !isNaN(soft) && !isNaN(hard) && hard < soft) {
    fieldErrors.value.hard = 'Halt threshold must be >= alert threshold';
  }

  return Object.keys(fieldErrors.value).length === 0;
}

async function handleSubmit() {
  if (!validate()) return;

  isSubmitting.value = true;
  errorMessage.value = '';

  try {
    const data: {
      entity_type: string;
      entity_id: string;
      period: string;
      soft_limit_usd?: number;
      hard_limit_usd?: number;
    } = {
      entity_type: entityType.value,
      entity_id: entityId.value,
      period: period.value,
    };

    const soft = softLimit.value.trim() ? parseFloat(softLimit.value) : null;
    const hard = hardLimit.value.trim() ? parseFloat(hardLimit.value) : null;

    if (soft != null) data.soft_limit_usd = soft;
    if (hard != null) data.hard_limit_usd = hard;

    await budgetApi.setLimit(data);
    emit('saved');
  } catch (err: any) {
    errorMessage.value = err?.message || 'Failed to save budget limit';
  } finally {
    isSubmitting.value = false;
  }
}
</script>

<template>
  <div ref="budgetModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-budget-limit" tabindex="-1" @click.self="emit('cancelled')" @keydown.escape="emit('cancelled')">
    <div class="modal">
      <div class="modal-header">
        <div class="modal-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M12 1v22M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/>
          </svg>
        </div>
        <div>
          <h3 id="modal-title-budget-limit">{{ mode === 'edit' ? 'Edit Budget Limit' : 'Add Budget Limit' }}</h3>
          <p class="modal-subtitle">Set spending guardrails for an agent, team, or trigger</p>
        </div>
        <button class="close-btn" @click="emit('cancelled')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 6L6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>

      <form @submit.prevent="handleSubmit">
        <!-- Entity Type -->
        <div class="form-group">
          <label>Entity Type</label>
          <div class="radio-group">
            <label class="radio-option" :class="{ active: entityType === 'agent', disabled: mode === 'edit' }">
              <input type="radio" v-model="entityType" value="agent" :disabled="mode === 'edit'">
              <span>Agent</span>
            </label>
            <label class="radio-option" :class="{ active: entityType === 'team', disabled: mode === 'edit' }">
              <input type="radio" v-model="entityType" value="team" :disabled="mode === 'edit'">
              <span>Team</span>
            </label>
            <label class="radio-option" :class="{ active: entityType === 'trigger', disabled: mode === 'edit' }">
              <input type="radio" v-model="entityType" value="trigger" :disabled="mode === 'edit'">
              <span>Trigger</span>
            </label>
          </div>
        </div>

        <!-- Entity Picker -->
        <div class="form-group">
          <label>
            {{ entityType === 'agent' ? 'Agent' : (entityType === 'trigger' ? 'Trigger' : 'Team') }}
          </label>
          <div v-if="mode === 'edit'" class="entity-readonly">
            {{ entityDisplayName }}
          </div>
          <select v-else v-model="entityId" :class="{ error: fieldErrors.entity }">
            <option value="">Select {{ entityType === 'agent' ? 'an agent' : (entityType === 'trigger' ? 'a trigger' : 'a team') }}...</option>
            <option
              v-for="option in entityOptions"
              :key="option.id"
              :value="option.id"
            >
              {{ option.name }} ({{ option.id }})
            </option>
          </select>
          <div v-if="fieldErrors.entity" class="field-error">{{ fieldErrors.entity }}</div>
        </div>

        <!-- Period -->
        <div class="form-group">
          <label>Period</label>
          <select v-model="period">
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
          </select>
        </div>

        <!-- Soft Limit -->
        <div class="form-group">
          <label>Alert Threshold</label>
          <div class="currency-input">
            <span class="currency-prefix">$</span>
            <input
              type="number"
              v-model="softLimit"
              step="0.01"
              min="0"
              placeholder="e.g., 10.00"
              :class="{ error: fieldErrors.soft }"
            >
          </div>
          <div class="field-hint">You'll receive a warning when spending reaches this amount.</div>
          <div v-if="fieldErrors.soft" class="field-error">{{ fieldErrors.soft }}</div>
        </div>

        <!-- Hard Limit -->
        <div class="form-group">
          <label>Halt Threshold</label>
          <div class="currency-input">
            <span class="currency-prefix">$</span>
            <input
              type="number"
              v-model="hardLimit"
              step="0.01"
              min="0"
              placeholder="e.g., 50.00"
              :class="{ error: fieldErrors.hard }"
            >
          </div>
          <div class="field-hint">Executions will be blocked when spending reaches this amount.</div>
          <div v-if="fieldErrors.hard" class="field-error">{{ fieldErrors.hard }}</div>
        </div>

        <!-- General limit error -->
        <div v-if="fieldErrors.limits" class="form-error">{{ fieldErrors.limits }}</div>

        <!-- Submit error -->
        <div v-if="errorMessage" class="form-error">{{ errorMessage }}</div>

        <!-- Actions -->
        <div class="modal-actions">
          <button type="button" class="btn btn-secondary" @click="emit('cancelled')">Cancel</button>
          <button type="submit" class="btn btn-primary" :disabled="isSubmitting">
            <svg v-if="isSubmitting" class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
            </svg>
            {{ isSubmitting ? 'Saving...' : 'Save' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<style scoped>

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: overlayFadeIn 0.3s ease;
}

@keyframes overlayFadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.modal {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 16px;
  padding: 0;
  width: 90%;
  max-width: 500px;
  max-height: 90vh;
  overflow-y: auto;
  animation: modalSlideIn 0.3s ease;
  box-shadow: var(--shadow-lg);
}

@keyframes modalSlideIn {
  from { opacity: 0; transform: translateY(-20px) scale(0.95); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.modal-icon {
  width: 44px;
  height: 44px;
  background: var(--accent-violet-dim);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.modal-icon svg {
  width: 22px;
  height: 22px;
  color: var(--accent-violet);
}

.modal-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 24px 24px 0;
}

.modal-header h3 {
  font-family: var(--font-mono);
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.modal-subtitle {
  font-size: 0.85rem;
  color: var(--text-tertiary);
}

.close-btn {
  margin-left: auto;
  width: 32px;
  height: 32px;
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all var(--transition-fast);
  color: var(--text-tertiary);
}

.close-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border-color: var(--border-default);
}

.close-btn svg {
  width: 16px;
  height: 16px;
}

form {
  padding: 24px;
}

.form-group {
  margin-bottom: 20px;
}

.form-group > label {
  display: block;
  font-size: 0.8rem;
  color: var(--text-secondary);
  margin-bottom: 8px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.form-group select,
.form-group input {
  width: 100%;
  padding: 12px 16px;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  font-size: 0.9rem;
  background: var(--bg-primary);
  color: var(--text-primary);
  transition: all var(--transition-fast);
}

.form-group select:focus,
.form-group input:focus {
  border-color: var(--primary-color);
  outline: none;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
}

.form-group select.error,
.form-group input.error {
  border-color: #ef4444;
}

.form-group select.error:focus,
.form-group input.error:focus {
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.15);
}

.form-group input::placeholder {
  color: var(--text-muted);
}

/* Radio group */
.radio-group {
  display: flex;
  gap: 8px;
}

.radio-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  cursor: pointer;
  transition: all var(--transition-fast);
  flex: 1;
  justify-content: center;
  font-size: 0.9rem;
  color: var(--text-secondary);
}

.radio-option input[type="radio"] {
  display: none;
}

.radio-option:hover:not(.disabled) {
  border-color: var(--border-strong);
  color: var(--text-primary);
}

.radio-option.active {
  border-color: var(--accent-cyan);
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.radio-option.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Entity readonly */
.entity-readonly {
  padding: 12px 16px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-size: 0.9rem;
}

/* Currency input */
.currency-input {
  position: relative;
  display: flex;
  align-items: center;
}

.currency-prefix {
  position: absolute;
  left: 16px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 0.9rem;
  z-index: 1;
}

.currency-input input {
  padding-left: 32px;
  font-family: var(--font-mono);
}

/* Field hints and errors */
.field-hint {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-top: 6px;
  padding: 0 2px;
}

.field-error {
  font-size: 0.75rem;
  color: #ef4444;
  margin-top: 6px;
  padding: 0 2px;
}

.form-error {
  padding: 10px 14px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 8px;
  color: #ef4444;
  font-size: 0.85rem;
  margin-bottom: 16px;
}

/* Actions */
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 16px;
  border-top: 1px solid var(--border-subtle);
  margin-top: 8px;
}

.btn-primary {
  background: var(--primary-color);
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-primary:hover:not(:disabled) {
  background: var(--primary-hover);
  color: white;
}

.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
}

.btn-secondary:hover {
  background: var(--bg-elevated);
  color: var(--text-primary);
}

.spinner {
  width: 16px;
  height: 16px;
  animation: spin 1s linear infinite;
}

</style>
