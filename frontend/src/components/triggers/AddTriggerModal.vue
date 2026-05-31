<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { triggerApi, utilityApi, teamApi, ApiError, CLAUDE_MODELS, OPENCODE_MODELS, type TriggerSource, type ScheduleType, type SkillInfo, type Team } from '../../services/api';
import { useToast } from '../../composables/useToast';
import { useFocusTrap } from '../../composables/useFocusTrap';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'created'): void;
}>();

const showToast = useToast();

const triggerModalRef = ref<HTMLElement | null>(null);
const alwaysOpen = ref(true);
useFocusTrap(triggerModalRef, alwaysOpen);

const name = ref('');
const backend = ref<'claude' | 'opencode'>('claude');
const model = ref<string>('');
const triggerSource = ref<TriggerSource>('webhook');
const keyword = ref('');
const prompt = ref('');
const isSubmitting = ref(false);

// Model options based on backend
const modelOptions = computed(() => {
  return backend.value === 'claude' ? CLAUDE_MODELS : OPENCODE_MODELS;
});

// Schedule configuration
const scheduleType = ref<ScheduleType>('daily');
const scheduleTime = ref('09:00');
const scheduleDay = ref(1); // Monday for weekly, 1st for monthly

// Skill/command autocomplete
const skillCommand = ref('');
const skillSearchQuery = ref('');
const availableSkills = ref<SkillInfo[]>([]);
const showSkillDropdown = ref(false);
const isLoadingSkills = ref(false);

const filteredSkills = computed(() => {
  const q = skillSearchQuery.value.toLowerCase();
  if (!q) return availableSkills.value;
  return availableSkills.value.filter(
    s => s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q)
  );
});

const showSkillField = computed(() => backend.value === 'claude');

async function loadSkills() {
  if (backend.value !== 'claude') return;
  isLoadingSkills.value = true;
  try {
    const data = await utilityApi.discoverSkills();
    availableSkills.value = data.skills || [];
  } catch {
    availableSkills.value = [];
  } finally {
    isLoadingSkills.value = false;
  }
}

function selectSkill(skill: SkillInfo) {
  skillCommand.value = skill.name;
  skillSearchQuery.value = skill.name;
  showSkillDropdown.value = false;
}

function clearSkill() {
  skillCommand.value = '';
  skillSearchQuery.value = '';
}

function onSkillInputFocus() {
  showSkillDropdown.value = true;
  if (availableSkills.value.length === 0) {
    loadSkills();
  }
}

function onSkillInputBlur() {
  // Delay to allow click on dropdown items
  setTimeout(() => { showSkillDropdown.value = false; }, 200);
}

watch(backend, () => {
  // Clear model when backend changes since models are backend-specific
  model.value = '';
  if (backend.value === 'claude' && availableSkills.value.length === 0) {
    loadSkills();
  }
});

onMounted(() => {
  if (backend.value === 'claude') {
    loadSkills();
  }
  loadTeams();
});

// Execution mode and team
const executionMode = ref<'direct' | 'team'>('direct');
const teamId = ref<string | null>(null);
const teams = ref<Team[]>([]);

async function loadTeams() {
  try {
    const data = await teamApi.list();
    teams.value = data.teams || [];
  } catch {
    teams.value = [];
  }
}

// Webhook matching configuration
const matchFieldPath = ref('');
const matchFieldValue = ref('');
const textFieldPath = ref('text');

// Show webhook-specific fields only for webhook trigger
const showWebhookFields = computed(() => triggerSource.value === 'webhook');
const showScheduleFields = computed(() => triggerSource.value === 'scheduled');

// Generate time options (00:00 to 23:00)
const timeOptions = Array.from({ length: 24 }, (_, i) => {
  const hour = i.toString().padStart(2, '0');
  return `${hour}:00`;
});

// Day of week options (for weekly)
const weekdayOptions = computed(() => [
  { value: 0, label: t('addTriggerModal.weekday.monday') },
  { value: 1, label: t('addTriggerModal.weekday.tuesday') },
  { value: 2, label: t('addTriggerModal.weekday.wednesday') },
  { value: 3, label: t('addTriggerModal.weekday.thursday') },
  { value: 4, label: t('addTriggerModal.weekday.friday') },
  { value: 5, label: t('addTriggerModal.weekday.saturday') },
  { value: 6, label: t('addTriggerModal.weekday.sunday') },
]);

// Day of month options (1-31)
const monthDayOptions = Array.from({ length: 31 }, (_, i) => i + 1);

// Get help text based on trigger source
const triggerHelpText = computed(() => {
  switch (triggerSource.value) {
    case 'webhook':
      return t('addTriggerModal.help.webhook');
    case 'github':
      return t('addTriggerModal.help.github');
    case 'manual':
      return t('addTriggerModal.help.manual');
    case 'scheduled':
      return t('addTriggerModal.help.scheduled');
    default:
      return '';
  }
});

async function createTrigger() {
  if (!name.value.trim() || !prompt.value.trim()) {
    showToast(t('addTriggerModal.toast.nameAndPromptRequired'), 'error');
    return;
  }

  // Validate webhook-specific fields
  if (triggerSource.value === 'webhook') {
    // Both match_field_path and match_field_value must be provided together or neither
    if (Boolean(matchFieldPath.value.trim()) !== Boolean(matchFieldValue.value.trim())) {
      showToast(t('addTriggerModal.toast.matchFieldPairRequired'), 'error');
      return;
    }
  }

  // Validate schedule-specific fields
  if (triggerSource.value === 'scheduled') {
    if (!scheduleType.value || !scheduleTime.value) {
      showToast(t('addTriggerModal.toast.scheduleRequired'), 'error');
      return;
    }
  }

  isSubmitting.value = true;
  try {
    const createData: Parameters<typeof triggerApi.create>[0] = {
      name: name.value.trim(),
      backend_type: backend.value,
      trigger_source: triggerSource.value,
      prompt_template: prompt.value.trim(),
      skill_command: skillCommand.value.trim() || undefined,
      model: model.value || undefined,
      execution_mode: executionMode.value,
      team_id: executionMode.value === 'team' ? teamId.value : null,
    };

    // Add webhook-specific fields
    if (triggerSource.value === 'webhook') {
      if (matchFieldPath.value.trim()) {
        createData.match_field_path = matchFieldPath.value.trim();
        createData.match_field_value = matchFieldValue.value.trim();
      }
      createData.text_field_path = textFieldPath.value.trim() || 'text';
      createData.detection_keyword = keyword.value.trim();
    }

    // Add schedule fields for scheduled trigger
    if (triggerSource.value === 'scheduled') {
      createData.schedule_type = scheduleType.value;
      createData.schedule_time = scheduleTime.value;
      createData.schedule_day = scheduleDay.value;
      createData.schedule_timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    }

    await triggerApi.create(createData);
    showToast(t('addTriggerModal.toast.created'), 'success');
    emit('created');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('addTriggerModal.toast.createFailed');
    showToast(message, 'error');
  } finally {
    isSubmitting.value = false;
  }
}
</script>

<template>
  <div ref="triggerModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-add-trigger" tabindex="-1" @click.self="emit('close')" @keydown.escape="emit('close')">
    <div class="modal">
      <div class="modal-header">
        <div class="modal-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="3" y="11" width="18" height="10" rx="2"/>
            <circle cx="12" cy="5" r="2"/>
            <path d="M12 7v4M7 15h.01M17 15h.01"/>
          </svg>
        </div>
        <div>
          <h3 id="modal-title-add-trigger">{{ t('addTriggerModal.title') }}</h3>
          <p class="modal-subtitle">{{ t('addTriggerModal.subtitle') }}</p>
        </div>
        <button class="close-btn" @click="emit('close')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 6L6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>

      <form @submit.prevent="createTrigger">
        <div class="form-group">
          <label>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
            {{ t('addTriggerModal.fields.name') }}
          </label>
          <input type="text" v-model="name" required :placeholder="t('addTriggerModal.placeholders.name')">
        </div>

        <div class="form-row">
          <div class="form-group">
            <label>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
              </svg>
              {{ t('addTriggerModal.fields.triggerSource') }}
            </label>
            <select v-model="triggerSource">
              <option value="webhook">{{ t('addTriggerModal.source.webhook') }}</option>
              <option value="github">{{ t('addTriggerModal.source.github') }}</option>
              <option value="manual">{{ t('addTriggerModal.source.manual') }}</option>
              <option value="scheduled">{{ t('addTriggerModal.source.scheduled') }}</option>
            </select>
          </div>
          <div class="form-group">
            <label>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <rect x="4" y="4" width="16" height="16" rx="2"/>
                <path d="M9 9h6M9 13h6M9 17h4"/>
              </svg>
              {{ t('addTriggerModal.fields.backend') }}
            </label>
            <select v-model="backend">
              <option value="claude">Claude CLI</option>
              <option value="opencode">OpenCode CLI</option>
            </select>
          </div>
        </div>

        <div class="form-group">
          <label>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M12 2L2 7l10 5 10-5-10-5z"/>
              <path d="M2 17l10 5 10-5"/>
              <path d="M2 12l10 5 10-5"/>
            </svg>
            {{ t('addTriggerModal.fields.model') }}
          </label>
          <select v-model="model">
            <option value="">{{ t('addTriggerModal.modelDefault') }}</option>
            <option v-for="m in modelOptions" :key="m" :value="m">{{ m }}</option>
          </select>
          <div class="field-hint">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="12" cy="12" r="10"/>
              <path d="M12 16v-4M12 8h.01"/>
            </svg>
            {{ t('addTriggerModal.hints.model') }}
          </div>
        </div>

        <!-- Execution Mode -->
        <div class="form-row">
          <div class="form-group">
            <label>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                <circle cx="9" cy="7" r="4"/>
                <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
                <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
              </svg>
              {{ t('addTriggerModal.fields.executionMode') }}
            </label>
            <select v-model="executionMode">
              <option value="direct">{{ t('addTriggerModal.execMode.direct') }}</option>
              <option value="team">{{ t('addTriggerModal.execMode.team') }}</option>
            </select>
          </div>
          <div v-if="executionMode === 'team'" class="form-group">
            <label>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                <circle cx="9" cy="7" r="4"/>
                <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
                <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
              </svg>
              {{ t('addTriggerModal.fields.targetTeam') }}
            </label>
            <select v-model="teamId">
              <option :value="null">{{ t('addTriggerModal.selectTeam') }}</option>
              <option v-for="t in teams" :key="t.id" :value="t.id">
                {{ t.name }} ({{ t.id }})
              </option>
            </select>
          </div>
        </div>

        <div v-if="triggerHelpText" class="trigger-hint">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 16v-4M12 8h.01"/>
          </svg>
          {{ triggerHelpText }}
        </div>

        <!-- Webhook Configuration -->
        <div v-if="showWebhookFields" class="webhook-config">
          <div class="form-row">
            <div class="form-group">
              <label>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M4 4h16v16H4z"/>
                  <path d="M9 9h6M9 13h6M9 17h4"/>
                </svg>
                {{ t('addTriggerModal.fields.matchFieldPath') }}
              </label>
              <input type="text" v-model="matchFieldPath" placeholder="event.type">
              <div class="field-hint">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <circle cx="12" cy="12" r="10"/>
                  <path d="M12 16v-4M12 8h.01"/>
                </svg>
                {{ t('addTriggerModal.hints.matchFieldPath') }}
              </div>
            </div>
            <div class="form-group">
              <label>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                  <polyline points="22 4 12 14.01 9 11.01"/>
                </svg>
                {{ t('addTriggerModal.fields.matchFieldValue') }}
              </label>
              <input type="text" v-model="matchFieldValue" placeholder="security_alert">
              <div class="field-hint">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <circle cx="12" cy="12" r="10"/>
                  <path d="M12 16v-4M12 8h.01"/>
                </svg>
                {{ t('addTriggerModal.hints.matchFieldValue') }}
              </div>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                  <path d="M14 2v6h6M16 13H8M16 17H8"/>
                </svg>
                {{ t('addTriggerModal.fields.textFieldPath') }}
              </label>
              <input type="text" v-model="textFieldPath" placeholder="text">
              <div class="field-hint">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <circle cx="12" cy="12" r="10"/>
                  <path d="M12 16v-4M12 8h.01"/>
                </svg>
                {{ t('addTriggerModal.hints.textFieldPath') }}
              </div>
            </div>
            <div class="form-group">
              <label>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <circle cx="11" cy="11" r="8"/>
                  <path d="M21 21l-4.35-4.35"/>
                </svg>
                {{ t('addTriggerModal.fields.detectionKeyword') }}
              </label>
              <input type="text" v-model="keyword" :placeholder="t('addTriggerModal.placeholders.keyword')">
              <div class="field-hint">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <circle cx="12" cy="12" r="10"/>
                  <path d="M12 16v-4M12 8h.01"/>
                </svg>
                {{ t('addTriggerModal.hints.detectionKeyword') }}
              </div>
            </div>
          </div>
        </div>

        <!-- Schedule Configuration -->
        <div v-if="showScheduleFields" class="schedule-config">
          <div class="form-row">
            <div class="form-group">
              <label>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <rect x="3" y="4" width="18" height="18" rx="2"/>
                  <path d="M16 2v4M8 2v4M3 10h18"/>
                </svg>
                {{ t('addTriggerModal.fields.frequency') }}
              </label>
              <select v-model="scheduleType">
                <option value="daily">{{ t('addTriggerModal.frequency.daily') }}</option>
                <option value="weekly">{{ t('addTriggerModal.frequency.weekly') }}</option>
                <option value="monthly">{{ t('addTriggerModal.frequency.monthly') }}</option>
              </select>
            </div>
            <div class="form-group">
              <label>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <circle cx="12" cy="12" r="10"/>
                  <polyline points="12 6 12 12 16 14"/>
                </svg>
                {{ t('addTriggerModal.fields.time') }}
              </label>
              <select v-model="scheduleTime">
                <option v-for="time in timeOptions" :key="time" :value="time">{{ time }}</option>
              </select>
            </div>
          </div>

          <div v-if="scheduleType === 'weekly'" class="form-group">
            <label>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <rect x="3" y="4" width="18" height="18" rx="2"/>
                <path d="M16 2v4M8 2v4M3 10h18"/>
              </svg>
              {{ t('addTriggerModal.fields.dayOfWeek') }}
            </label>
            <select v-model="scheduleDay">
              <option v-for="day in weekdayOptions" :key="day.value" :value="day.value">{{ day.label }}</option>
            </select>
          </div>

          <div v-if="scheduleType === 'monthly'" class="form-group">
            <label>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <rect x="3" y="4" width="18" height="18" rx="2"/>
                <path d="M16 2v4M8 2v4M3 10h18"/>
              </svg>
              {{ t('addTriggerModal.fields.dayOfMonth') }}
            </label>
            <select v-model="scheduleDay">
              <option v-for="day in monthDayOptions" :key="day" :value="day">{{ day }}</option>
            </select>
          </div>
        </div>

        <!-- Skills/Commands Selector (Claude only) -->
        <div v-if="showSkillField" class="form-group skill-autocomplete-group">
          <label>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M4 17l6-6-6-6M12 19h8"/>
            </svg>
            {{ t('addTriggerModal.fields.skills') }}
          </label>
          <div class="skill-input-wrapper">
            <input
              type="text"
              v-model="skillSearchQuery"
              :placeholder="t('addTriggerModal.placeholders.skillSearch')"
              @focus="onSkillInputFocus"
              @blur="onSkillInputBlur"
              @input="showSkillDropdown = true"
              autocomplete="off"
            >
            <button v-if="skillCommand" type="button" class="skill-clear-btn" @click="clearSkill" :title="t('addTriggerModal.clearSkill')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M18 6L6 18M6 6l12 12"/>
              </svg>
            </button>
          </div>
          <div v-if="showSkillDropdown && (filteredSkills.length > 0 || isLoadingSkills)" class="skill-dropdown">
            <div v-if="isLoadingSkills" class="skill-dropdown-loading">{{ t('addTriggerModal.skillScanning') }}</div>
            <div
              v-for="skill in filteredSkills"
              :key="skill.name"
              class="skill-dropdown-item"
              :class="{ selected: skillCommand === skill.name }"
              @mousedown.prevent="selectSkill(skill)"
            >
              <span class="skill-name">{{ skill.name }}</span>
              <span v-if="skill.description" class="skill-desc">{{ skill.description }}</span>
            </div>
            <div v-if="!isLoadingSkills && filteredSkills.length === 0" class="skill-dropdown-empty">
              {{ t('addTriggerModal.noSkills') }}
            </div>
          </div>
          <div class="field-hint">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="12" cy="12" r="10"/>
              <path d="M12 16v-4M12 8h.01"/>
            </svg>
            {{ t('addTriggerModal.hints.skills') }}
          </div>
        </div>

        <div class="form-group">
          <label>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
            {{ t('addTriggerModal.fields.promptTemplate') }}
          </label>
          <textarea v-model="prompt" required :placeholder="t('addTriggerModal.placeholders.promptTemplate')"></textarea>
          <div class="field-hint">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="12" cy="12" r="10"/>
              <path d="M12 16v-4M12 8h.01"/>
            </svg>
            {{ t('addTriggerModal.hints.promptBefore') }} <code>{paths}</code> {{ t('addTriggerModal.hints.promptMiddle') }} <code>{message}</code> {{ t('addTriggerModal.hints.promptAfter') }}
          </div>
        </div>

        <div class="modal-actions">
          <button type="button" class="btn btn-secondary" @click="emit('close')">{{ t('common.cancel') }}</button>
          <button type="submit" class="btn btn-primary" :disabled="isSubmitting">
            <svg v-if="isSubmitting" class="spinner" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
            </svg>
            {{ isSubmitting ? t('addTriggerModal.creating') : t('addTriggerModal.createButton') }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<style scoped>

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
  max-width: 520px;
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
  background: var(--accent-cyan-dim);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.modal-icon svg {
  width: 22px;
  height: 22px;
  color: var(--accent-cyan);
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

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.form-group label svg {
  width: 14px;
  height: 14px;
  color: var(--text-muted);
}

.form-group input,
.form-group select {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
}

.form-group input::placeholder,
.form-group textarea::placeholder {
  color: var(--text-muted);
}

.field-hint,
.trigger-hint {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 0.75rem;
  color: var(--text-tertiary);
  margin-top: 8px;
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border-radius: 6px;
}

.trigger-hint {
  margin-bottom: 16px;
}

.webhook-config,
.schedule-config {
  padding: 16px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  margin-bottom: 20px;
  border: 1px solid var(--border-subtle);
}

.webhook-config

.webhook-config .form-group:last-child {
  margin-bottom: 0;
}

.webhook-config .form-row {
  margin-bottom: 0;
}

.webhook-config .form-row

.schedule-config

.schedule-config .form-group:last-child {
  margin-bottom: 0;
}

.schedule-config .form-row {
  margin-bottom: 0;
}

.schedule-config .form-row

.trigger-hint svg {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  margin-top: 1px;
}

.field-hint svg {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  margin-top: 1px;
}

.field-hint code {
  font-family: var(--font-mono);
  background: var(--bg-primary);
  padding: 2px 6px;
  border-radius: 4px;
  color: var(--accent-cyan);
  font-size: 0.7rem;
}

.btn-primary:hover:not(:disabled) {
  background: var(--text-primary);
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

/* Skill Autocomplete */
.skill-autocomplete-group {
  position: relative;
}

.skill-input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.skill-input-wrapper input {
  width: 100%;
  padding-right: 36px;
  font-family: var(--font-mono);
}

.skill-clear-btn {
  position: absolute;
  right: 8px;
  width: 24px;
  height: 24px;
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: all var(--transition-fast);
}

.skill-clear-btn:hover {
  color: var(--accent-crimson);
  background: var(--accent-crimson-dim);
}

.skill-clear-btn svg {
  width: 14px;
  height: 14px;
}

.skill-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-top: none;
  border-radius: 0 0 8px 8px;
  max-height: 200px;
  overflow-y: auto;
  z-index: 10;
  box-shadow: var(--shadow-lg);
}

.skill-dropdown-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 16px;
  cursor: pointer;
  transition: background var(--transition-fast);
}

.skill-dropdown-item:hover {
  background: var(--bg-tertiary);
}

.skill-dropdown-item.selected {
  background: var(--accent-cyan-dim);
}

.skill-name {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--accent-cyan);
}

.skill-desc {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.skill-dropdown-loading,
.skill-dropdown-empty {
  padding: 12px 16px;
  font-size: 0.8rem;
  color: var(--text-muted);
  text-align: center;
}
</style>
