<script setup lang="ts">
import { ref } from 'vue';
import type { Team, TriggerSource } from '../../services/api';
import { teamApi, ApiError } from '../../services/api';
import { useToast } from '../../composables/useToast';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();

const props = defineProps<{
  team: Team;
}>();

const emit = defineEmits<{
  (e: 'updated'): void;
}>();

const showToast = useToast();

const editingTrigger = ref(false);
const editTriggerSource = ref<TriggerSource | null>(null);
const editTriggerConfig = ref<Record<string, string>>({});
const editEnabled = ref(1);
const isSavingTrigger = ref(false);

function getTriggerLabel(src?: string): string {
  if (!src) return t('teamTriggerCard.none');
  const labels: Record<string, string> = {
    webhook: 'Webhook',
    github: 'GitHub',
    manual: t('teamTriggerCard.manual'),
    scheduled: t('teamTriggerCard.scheduled'),
  };
  return labels[src] || src;
}

function startEditTrigger() {
  editTriggerSource.value = (props.team.trigger_source as TriggerSource) || null;
  editEnabled.value = props.team.enabled ?? 1;
  try {
    editTriggerConfig.value = props.team.trigger_config ? JSON.parse(props.team.trigger_config) : {};
  } catch {
    editTriggerConfig.value = {};
  }
  editingTrigger.value = true;
}

async function saveTrigger() {
  isSavingTrigger.value = true;
  try {
    await teamApi.updateTrigger(props.team.id, {
      trigger_source: editTriggerSource.value,
      trigger_config: JSON.stringify(editTriggerConfig.value),
      enabled: editEnabled.value,
    });
    showToast(t('teamTriggerCard.updated'), 'success');
    editingTrigger.value = false;
    emit('updated');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('teamTriggerCard.updateError');
    showToast(message, 'error');
  } finally {
    isSavingTrigger.value = false;
  }
}
</script>

<template>
  <div class="card">
    <div class="card-header">
      <div class="header-left">
        <h3>{{ t('teamTriggerCard.title') }}</h3>
        <span v-if="team.trigger_source" class="card-count">{{ getTriggerLabel(team.trigger_source) }}</span>
        <span v-else class="card-count">{{ t('teamTriggerCard.notConfigured') }}</span>
      </div>
      <button class="add-btn" @click="editingTrigger ? (editingTrigger = false) : startEditTrigger()">
        {{ editingTrigger ? t('common.cancel') : t('common.edit') }}
      </button>
    </div>
    <div v-if="editingTrigger" class="card-body">
      <div class="form-group">
        <label>{{ t('teamTriggerCard.triggerSource') }}</label>
        <select v-model="editTriggerSource" class="form-select">
          <option :value="null">{{ t('teamTriggerCard.none') }}</option>
          <option value="webhook">Webhook</option>
          <option value="github">GitHub</option>
          <option value="manual">{{ t('teamTriggerCard.manual') }}</option>
          <option value="scheduled">{{ t('teamTriggerCard.scheduled') }}</option>
        </select>
      </div>

      <!-- Webhook config fields -->
      <template v-if="editTriggerSource === 'webhook'">
        <div class="form-group">
          <label>{{ t('teamTriggerCard.matchFieldPath') }}</label>
          <input v-model="editTriggerConfig.match_field_path" type="text" class="form-input" placeholder="e.g., action" />
        </div>
        <div class="form-group">
          <label>{{ t('teamTriggerCard.matchFieldValue') }}</label>
          <input v-model="editTriggerConfig.match_field_value" type="text" class="form-input" placeholder="e.g., opened" />
        </div>
        <div class="form-group">
          <label>{{ t('teamTriggerCard.textFieldPath') }}</label>
          <input v-model="editTriggerConfig.text_field_path" type="text" class="form-input" placeholder="e.g., pull_request.body" />
        </div>
        <div class="form-group">
          <label>{{ t('teamTriggerCard.detectionKeyword') }}</label>
          <input v-model="editTriggerConfig.detection_keyword" type="text" class="form-input" placeholder="e.g., review" />
        </div>
      </template>

      <!-- Scheduled config fields -->
      <template v-if="editTriggerSource === 'scheduled'">
        <div class="form-group">
          <label>{{ t('teamTriggerCard.scheduleType') }}</label>
          <select v-model="editTriggerConfig.schedule_type" class="form-select">
            <option value="daily">{{ t('teamTriggerCard.daily') }}</option>
            <option value="weekly">{{ t('teamTriggerCard.weekly') }}</option>
            <option value="monthly">{{ t('teamTriggerCard.monthly') }}</option>
          </select>
        </div>
        <div class="form-group">
          <label>{{ t('teamTriggerCard.scheduleTime') }}</label>
          <input v-model="editTriggerConfig.schedule_time" type="time" class="form-input" />
        </div>
        <div v-if="editTriggerConfig.schedule_type === 'weekly'" class="form-group">
          <label>{{ t('teamTriggerCard.dayOfWeek') }}</label>
          <input v-model="editTriggerConfig.schedule_day" type="number" min="0" max="6" class="form-input" />
        </div>
        <div class="form-group">
          <label>{{ t('teamTriggerCard.timezone') }}</label>
          <input v-model="editTriggerConfig.schedule_timezone" type="text" class="form-input" :placeholder="'e.g., ' + Intl.DateTimeFormat().resolvedOptions().timeZone" />
        </div>
      </template>

      <div class="form-group">
        <label class="toggle-label">
          <input type="checkbox" :checked="editEnabled === 1" @change="editEnabled = ($event.target as HTMLInputElement).checked ? 1 : 0" />
          <span>{{ t('teamTriggerCard.enabled') }}</span>
        </label>
      </div>

      <div class="card-actions">
        <button class="action-btn primary compact" :disabled="isSavingTrigger" @click="saveTrigger">
          {{ isSavingTrigger ? t('teamTriggerCard.saving') : t('teamTriggerCard.saveTrigger') }}
        </button>
      </div>
    </div>
    <div v-else-if="!team.trigger_source" class="empty-state">
      <p>{{ t('teamTriggerCard.emptyTitle') }}</p>
      <span>{{ t('teamTriggerCard.emptyHint') }}</span>
    </div>
  </div>
</template>

<style scoped>
/* Cards */
.card {
  overflow: hidden;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.card-header h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.card-count {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
  padding: 4px 8px;
  border-radius: 4px;
}

.card-body {
  padding: 20px;
}

.card-actions {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

/* Header with button */
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.add-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.add-btn:hover {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}

/* Action Buttons */
.action-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 20px;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}

.action-btn.primary {
  background: linear-gradient(135deg, var(--accent-cyan, #00d4ff) 0%, var(--accent-emerald, #00ff88) 100%);
  color: var(--bg-primary);
}

.action-btn.primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 212, 255, 0.3);
}

.action-btn.primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.action-btn.compact {
  padding: 8px 16px;
  font-size: 0.85rem;
}

/* Form Elements */
.form-input,
.form-select {
  width: 100%;
  padding: 10px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.9rem;
  transition: border-color 0.2s;
}

.form-input:focus,
.form-select:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.form-select option {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.toggle-label input[type="checkbox"] {
  accent-color: var(--accent-cyan, #00d4ff);
}

/* Empty State */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
}

.empty-state span {
  font-size: 0.85rem;
  color: var(--text-tertiary);
}
</style>
