<script setup lang="ts">
import { ref, computed } from 'vue';
import type { Trigger, ProjectPath, PathType, SkillInfo, Project, Team, BudgetLimit } from '../../services/api';
import { triggerApi, utilityApi, budgetApi, ApiError } from '../../services/api';
import FallbackChainEditor from './FallbackChainEditor.vue';

const props = defineProps<{
  selectedTrigger: Trigger;
  triggerPaths: ProjectPath[];
  projects: Project[];
  teams: Team[];
  availableBackends: Array<{ id: string; name: string; type: string }>;
  availableAccounts: Array<{ id: number; account_name: string; backend_id: string }>;
}>();

const emit = defineEmits<{
  (e: 'saved'): void;
  (e: 'pathChanged'): void;
}>();

const showToast = useToast();

// Edit form state
const editBackend = ref<'claude' | 'opencode'>('claude');
const editMatchFieldPath = ref('');
const editMatchFieldValue = ref('');
const editTextFieldPath = ref('text');
const editKeyword = ref('');
const editPrompt = ref('');
const editSkillCommand = ref('');
const editSkillSearchQuery = ref('');
const editAvailableSkills = ref<SkillInfo[]>([]);
const showEditSkillDropdown = ref(false);
const isLoadingEditSkills = ref(false);
const editExecutionMode = ref<'direct' | 'team'>('direct');
const editTeamId = ref<string | null>(null);

// Path input state
const newPathInput = ref('');
const newGitHubUrl = ref('');
const pathInputMode = ref<PathType>('local');
const selectedProjectId = ref('');

// Budget state
const triggerBudget = ref<BudgetLimit | null>(null);
const budgetPeriod = ref<'daily' | 'weekly' | 'monthly'>('monthly');
const budgetSoftLimit = ref('');
const budgetHardLimit = ref('');
const isSavingBudget = ref(false);
const showBudgetForm = ref(false);

const filteredEditSkills = computed(() => {
  const q = editSkillSearchQuery.value.toLowerCase();
  if (!q) return editAvailableSkills.value;
  return editAvailableSkills.value.filter(
    s => s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q)
  );
});

const showEditSkillField = computed(() => editBackend.value === 'claude');

function initFromTrigger(trig: Trigger) {
  editBackend.value = trig.backend_type;
  editMatchFieldPath.value = trig.match_field_path || '';
  editMatchFieldValue.value = trig.match_field_value || '';
  editTextFieldPath.value = trig.text_field_path || 'text';
  editKeyword.value = trig.detection_keyword;
  editPrompt.value = trig.prompt_template;
  editSkillCommand.value = trig.skill_command || '';
  editSkillSearchQuery.value = trig.skill_command || '';
  editExecutionMode.value = trig.execution_mode || 'direct';
  editTeamId.value = trig.team_id || null;
  loadTriggerBudget(trig.id);
  if (trig.backend_type === 'claude') loadEditSkills(trig.id);
}

// Initialize on first render
initFromTrigger(props.selectedTrigger);

// Watch for trigger changes
import { watch } from 'vue';
import { useToast } from '../../composables/useToast';
watch(() => props.selectedTrigger, (trig) => {
  if (trig) initFromTrigger(trig);
});

async function loadEditSkills(triggerId?: string) {
  isLoadingEditSkills.value = true;
  try {
    const data = await utilityApi.discoverSkills(triggerId);
    editAvailableSkills.value = data.skills || [];
  } catch { editAvailableSkills.value = []; }
  finally { isLoadingEditSkills.value = false; }
}

function selectEditSkill(skill: SkillInfo) {
  editSkillCommand.value = skill.name;
  editSkillSearchQuery.value = skill.name;
  showEditSkillDropdown.value = false;
}

function clearEditSkill() { editSkillCommand.value = ''; editSkillSearchQuery.value = ''; }

function onEditSkillInputFocus() {
  showEditSkillDropdown.value = true;
  if (editAvailableSkills.value.length === 0 && props.selectedTrigger.id) loadEditSkills(props.selectedTrigger.id);
}

function onEditSkillInputBlur() { setTimeout(() => { showEditSkillDropdown.value = false; }, 200); }

function getWeekdayName(day: number): string {
  const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  return days[day] || 'Unknown';
}

function formatDate(dateStr: string | undefined): string {
  if (!dateStr) return '-';
  const date = new Date(dateStr);
  return date.toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

async function saveTrigger() {
  try {
    await triggerApi.update(props.selectedTrigger.id, {
      backend_type: editBackend.value,
      match_field_path: editMatchFieldPath.value || '',
      match_field_value: editMatchFieldValue.value || '',
      text_field_path: editTextFieldPath.value || 'text',
      detection_keyword: editKeyword.value,
      prompt_template: editPrompt.value,
      skill_command: editSkillCommand.value || '',
      execution_mode: editExecutionMode.value,
      team_id: editExecutionMode.value === 'team' ? editTeamId.value : null,
    });
    emit('saved');
    showToast('Trigger updated', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to update trigger';
    showToast(message, 'error');
  }
}

async function toggleAutoResolve() {
  const newValue = props.selectedTrigger.auto_resolve !== 1;
  try {
    await triggerApi.setAutoResolve(props.selectedTrigger.id, newValue);
    showToast(newValue ? 'Auto-resolve enabled' : 'Auto-resolve disabled', 'success');
    emit('saved');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to update auto-resolve';
    showToast(message, 'error');
  }
}

async function addPath() {
  const path = newPathInput.value.trim();
  if (!path) return;
  try {
    await triggerApi.addPath(props.selectedTrigger.id, path);
    newPathInput.value = '';
    emit('pathChanged');
    showToast('Path added', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to add path';
    showToast(message, 'error');
  }
}

async function addGitHubRepo() {
  const url = newGitHubUrl.value.trim();
  if (!url) return;
  try {
    await triggerApi.addGitHubRepo(props.selectedTrigger.id, url);
    newGitHubUrl.value = '';
    emit('pathChanged');
    showToast('GitHub repository added', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to add GitHub repo';
    showToast(message, 'error');
  }
}

function handleAddPathOrRepo() {
  if (pathInputMode.value === 'github') addGitHubRepo();
  else if (pathInputMode.value !== 'project') addPath();
}

async function addProject() {
  if (!selectedProjectId.value) return;
  try {
    await triggerApi.addProject(props.selectedTrigger.id, selectedProjectId.value);
    selectedProjectId.value = '';
    emit('pathChanged');
    showToast('Project added', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to add project';
    showToast(message, 'error');
  }
}

async function removePath(path: ProjectPath) {
  try {
    if (path.path_type === 'project' && path.project_id) {
      await triggerApi.removeProject(props.selectedTrigger.id, path.project_id);
    } else if (path.path_type === 'github' && path.github_repo_url) {
      await triggerApi.removeGitHubRepo(props.selectedTrigger.id, path.github_repo_url);
    } else {
      await triggerApi.removePath(props.selectedTrigger.id, path.local_project_path);
    }
    emit('pathChanged');
    showToast('Path removed', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to remove path';
    showToast(message, 'error');
  }
}

async function loadTriggerBudget(triggerId: string) {
  triggerBudget.value = null;
  showBudgetForm.value = false;
  try {
    const limit = await budgetApi.getLimit('trigger', triggerId);
    triggerBudget.value = limit;
    budgetPeriod.value = (limit.period as 'daily' | 'weekly' | 'monthly') || 'monthly';
    budgetSoftLimit.value = limit.soft_limit_usd != null ? String(limit.soft_limit_usd) : '';
    budgetHardLimit.value = limit.hard_limit_usd != null ? String(limit.hard_limit_usd) : '';
  } catch {
    triggerBudget.value = null;
    budgetPeriod.value = 'monthly';
    budgetSoftLimit.value = '';
    budgetHardLimit.value = '';
  }
}

async function saveTriggerBudget() {
  const soft = budgetSoftLimit.value.trim() ? parseFloat(budgetSoftLimit.value) : undefined;
  const hard = budgetHardLimit.value.trim() ? parseFloat(budgetHardLimit.value) : undefined;
  if (soft == null && hard == null) { showToast('Set at least one budget limit', 'error'); return; }
  isSavingBudget.value = true;
  try {
    await budgetApi.setLimit({ entity_type: 'trigger', entity_id: props.selectedTrigger.id, period: budgetPeriod.value, soft_limit_usd: soft, hard_limit_usd: hard });
    await loadTriggerBudget(props.selectedTrigger.id);
    showBudgetForm.value = false;
    showToast('Budget limit saved', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to save budget';
    showToast(message, 'error');
  } finally { isSavingBudget.value = false; }
}

async function deleteTriggerBudget() {
  try {
    await budgetApi.deleteLimit('trigger', props.selectedTrigger.id);
    triggerBudget.value = null;
    budgetSoftLimit.value = '';
    budgetHardLimit.value = '';
    showBudgetForm.value = false;
    showToast('Budget limit removed', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to remove budget';
    showToast(message, 'error');
  }
}
</script>

<template>
  <div class="detail-panel">
    <div class="detail-header">
      <h4>{{ selectedTrigger.name }}</h4>
      <span class="detail-id">{{ selectedTrigger.id }}</span>
      <span class="badge trigger-badge" :class="selectedTrigger.trigger_source">
        {{ selectedTrigger.trigger_source === 'webhook' ? 'JSON Webhook' : selectedTrigger.trigger_source === 'github' ? 'GitHub Webhook' : selectedTrigger.trigger_source === 'manual' ? 'Manual' : selectedTrigger.trigger_source === 'scheduled' ? 'Scheduled' : selectedTrigger.trigger_source }}
      </span>
    </div>

    <form @submit.prevent="saveTrigger" class="detail-form">
      <!-- Trigger-specific info panels -->
      <div v-if="selectedTrigger.trigger_source === 'github'" class="trigger-info">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/></svg>
        <span>This bot is triggered by GitHub webhooks. Configure your repository to send PR events to <code>/api/webhooks/github</code></span>
      </div>
      <div v-else-if="selectedTrigger.trigger_source === 'manual'" class="trigger-info">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>
        <span>This bot can only be triggered manually from the dashboard.</span>
      </div>
      <div v-else-if="selectedTrigger.trigger_source === 'scheduled'" class="trigger-info scheduled-info">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
        <div class="schedule-details">
          <span v-if="selectedTrigger.schedule_type">
            Runs <strong>{{ selectedTrigger.schedule_type }}</strong>
            <span v-if="selectedTrigger.schedule_type === 'weekly'"> on {{ getWeekdayName(selectedTrigger.schedule_day || 0) }}</span>
            <span v-if="selectedTrigger.schedule_type === 'monthly'"> on day {{ selectedTrigger.schedule_day || 1 }}</span>
            at <strong>{{ selectedTrigger.schedule_time || '00:00' }}</strong> KST
          </span>
          <span v-else>This bot runs on a schedule. Configure schedule in edit mode.</span>
          <div v-if="selectedTrigger.next_run_at" class="schedule-next">Next run: {{ formatDate(selectedTrigger.next_run_at) }}</div>
          <div v-if="selectedTrigger.last_run_at" class="schedule-last">Last run: {{ formatDate(selectedTrigger.last_run_at) }}</div>
        </div>
      </div>

      <!-- Webhook-specific fields -->
      <div v-if="selectedTrigger.trigger_source === 'webhook'" class="webhook-edit-config">
        <div class="form-row">
          <div class="form-group">
            <label><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 4h16v16H4z"/><path d="M9 9h6M9 13h6M9 17h4"/></svg> Match Field Path</label>
            <input type="text" v-model="editMatchFieldPath" placeholder="event.type">
          </div>
          <div class="form-group">
            <label><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg> Match Field Value</label>
            <input type="text" v-model="editMatchFieldValue" placeholder="security_alert">
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8"/></svg> Text Field Path</label>
            <input type="text" v-model="editTextFieldPath" placeholder="text">
          </div>
          <div class="form-group">
            <label><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg> Detection Keyword</label>
            <input type="text" v-model="editKeyword" placeholder="Optional keyword filter">
          </div>
        </div>
      </div>

      <!-- Common fields -->
      <div class="form-group">
        <label><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01"/></svg> Backend</label>
        <select v-model="editBackend"><option value="claude">Claude CLI</option><option value="opencode">OpenCode CLI</option></select>
      </div>

      <!-- Skill/Command Selector (Claude only) -->
      <div v-if="showEditSkillField" class="form-group skill-autocomplete-group">
        <label><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 17l6-6-6-6M12 19h8"/></svg> Skill / Command</label>
        <div class="skill-input-wrapper">
          <input type="text" v-model="editSkillSearchQuery" placeholder="Search skills (e.g. /weekly-security-audit)..." @focus="onEditSkillInputFocus" @blur="onEditSkillInputBlur" @input="showEditSkillDropdown = true" autocomplete="off">
          <button v-if="editSkillCommand" type="button" class="skill-clear-btn" @click="clearEditSkill" title="Clear skill">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>
        <div v-if="showEditSkillDropdown && (filteredEditSkills.length > 0 || isLoadingEditSkills)" class="skill-dropdown">
          <div v-if="isLoadingEditSkills" class="skill-dropdown-loading">Scanning for skills...</div>
          <div v-for="skill in filteredEditSkills" :key="skill.name" class="skill-dropdown-item" :class="{ selected: editSkillCommand === skill.name }" @mousedown.prevent="selectEditSkill(skill)">
            <span class="skill-name">{{ skill.name }}</span>
            <span v-if="skill.description" class="skill-desc">{{ skill.description }}</span>
          </div>
          <div v-if="!isLoadingEditSkills && filteredEditSkills.length === 0" class="skill-dropdown-empty">No skills found</div>
        </div>
        <div class="form-hint">Select a Claude skill to prepend to the prompt at execution time</div>
      </div>

      <div class="form-group">
        <label><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8"/></svg> Prompt Template</label>
        <textarea v-model="editPrompt" required></textarea>
        <div class="form-hint">Use {paths} for project paths, {message} for the original message</div>
      </div>

      <div v-if="selectedTrigger?.id === 'bot-security'" class="form-group auto-resolve-group">
        <label><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg> Auto-resolve &amp; PR</label>
        <label class="auto-resolve-toggle">
          <input type="checkbox" :checked="selectedTrigger.auto_resolve === 1" @change="toggleAutoResolve" />
          <span class="toggle-desc">Automatically resolve security issues and create pull requests for GitHub repos</span>
        </label>
      </div>

      <!-- Execution Mode -->
      <div class="form-group execution-mode-group">
        <label><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg> Execution Mode</label>
        <select v-model="editExecutionMode"><option value="direct">Direct (Orchestration)</option><option value="team">Team Delegation</option></select>
        <div class="form-hint">Direct mode uses orchestration fallback chain. Team mode delegates execution to a team.</div>
      </div>
      <div v-if="editExecutionMode === 'team'" class="form-group">
        <label><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg> Target Team</label>
        <select v-model="editTeamId">
          <option :value="null">Select a team...</option>
          <option v-for="team in teams" :key="team.id" :value="team.id">{{ team.name }} ({{ team.id }})</option>
        </select>
      </div>

      <button type="submit" class="btn btn-primary">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><polyline points="17,21 17,13 7,13 7,21"/><polyline points="7,3 7,8 15,8"/></svg>
        Save Changes
      </button>
    </form>

    <!-- Harness Configuration -->
    <div class="harness-config-section">
      <div class="section-header">
        <h5><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg> Harness Configuration</h5>
      </div>
      <p class="section-description">Configure fallback chain and budget limits for this trigger.</p>
      <FallbackChainEditor :triggerId="selectedTrigger.id" :availableBackends="availableBackends" :availableAccounts="availableAccounts" />

      <!-- Budget Limit -->
      <div class="budget-section">
        <div class="budget-header">
          <h6>Budget Limit</h6>
          <button v-if="!showBudgetForm && !triggerBudget" class="btn btn-secondary btn-sm" @click="showBudgetForm = true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg> Set Budget
          </button>
        </div>
        <div v-if="triggerBudget && !showBudgetForm" class="budget-display">
          <div class="budget-info-row"><span class="budget-label">Period:</span><span class="budget-value">{{ triggerBudget.period }}</span></div>
          <div v-if="triggerBudget.soft_limit_usd != null" class="budget-info-row"><span class="budget-label">Alert threshold:</span><span class="budget-value">${{ triggerBudget.soft_limit_usd.toFixed(2) }}</span></div>
          <div v-if="triggerBudget.hard_limit_usd != null" class="budget-info-row"><span class="budget-label">Halt threshold:</span><span class="budget-value">${{ triggerBudget.hard_limit_usd.toFixed(2) }}</span></div>
          <div class="budget-actions">
            <button class="btn btn-secondary btn-sm" @click="showBudgetForm = true">Edit</button>
            <button class="btn-icon btn-delete" @click="deleteTriggerBudget" title="Remove budget">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3,6 5,6 21,6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
            </button>
          </div>
        </div>
        <div v-if="showBudgetForm" class="budget-form">
          <div class="form-group"><label>Period</label><select v-model="budgetPeriod"><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></select></div>
          <div class="form-row">
            <div class="form-group"><label>Alert Threshold (USD)</label><input type="number" v-model="budgetSoftLimit" step="0.01" min="0" placeholder="e.g. 5.00"></div>
            <div class="form-group"><label>Halt Threshold (USD)</label><input type="number" v-model="budgetHardLimit" step="0.01" min="0" placeholder="e.g. 10.00"></div>
          </div>
          <div class="budget-form-actions">
            <button class="btn btn-secondary btn-sm" @click="showBudgetForm = false">Cancel</button>
            <button class="btn btn-primary btn-sm" :disabled="isSavingBudget" @click="saveTriggerBudget">{{ isSavingBudget ? 'Saving...' : 'Save Budget' }}</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Paths Section -->
    <div class="paths-section">
      <div class="section-header">
        <h5><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg> Project Paths</h5>
        <span class="paths-count">{{ triggerPaths.length }} configured</span>
      </div>
      <div class="path-list">
        <div v-if="triggerPaths.length === 0" class="empty-paths">No paths configured</div>
        <div v-for="path in triggerPaths" :key="path.id" class="path-item">
          <span class="path-type-badge" :class="path.path_type || 'local'">{{ path.path_type === 'project' ? 'PROJECT' : (path.path_type === 'github' ? 'GitHub' : 'LOCAL') }}</span>
          <span class="path-text">
            <template v-if="path.path_type === 'project'">{{ path.project_name }} <span class="path-arrow">&rarr;</span> {{ path.project_github_repo }}</template>
            <template v-else-if="path.path_type === 'github'">{{ path.github_repo_url }}</template>
            <template v-else>{{ path.local_project_path }}</template>
          </span>
          <button class="btn-icon btn-delete" @click="removePath(path)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>
      </div>
      <div class="add-path-form">
        <div class="path-type-toggle">
          <button class="toggle-btn" :class="{ active: pathInputMode === 'local' }" @click="pathInputMode = 'local'">Local</button>
          <button class="toggle-btn" :class="{ active: pathInputMode === 'github' }" @click="pathInputMode = 'github'">GitHub</button>
          <button class="toggle-btn" :class="{ active: pathInputMode === 'project' }" @click="pathInputMode = 'project'">Project</button>
        </div>
        <input v-if="pathInputMode === 'local'" type="text" v-model="newPathInput" placeholder="/path/to/project" @keydown.enter="handleAddPathOrRepo">
        <input v-else-if="pathInputMode === 'github'" type="text" v-model="newGitHubUrl" placeholder="https://github.com/owner/repo" @keydown.enter="handleAddPathOrRepo">
        <select v-else v-model="selectedProjectId" @change="addProject">
          <option value="">Select a project...</option>
          <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }} ({{ p.github_repo }})</option>
        </select>
        <button v-if="pathInputMode !== 'project'" class="btn btn-secondary" @click="handleAddPathOrRepo">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg> Add
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.detail-panel { margin-top: 24px; padding-top: 24px; border-top: 1px solid var(--border-subtle); }
.detail-header { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; }
.detail-header h4 { font-size: 1.1rem; font-weight: 600; color: var(--text-primary); }
.detail-id { font-family: var(--font-mono); font-size: 0.75rem; color: var(--text-muted); padding: 4px 8px; background: var(--bg-tertiary); border-radius: 4px; }
.badge { display: inline-flex; align-items: center; padding: 3px 8px; border-radius: 4px; font-size: 0.65rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em; }
.badge.trigger-badge.webhook { background: var(--accent-cyan-dim); color: var(--accent-cyan); }
.badge.trigger-badge.github { background: var(--accent-violet-dim); color: var(--accent-violet); }
.badge.trigger-badge.manual { background: var(--accent-amber-dim); color: var(--accent-amber); }
.badge.trigger-badge.scheduled { background: var(--accent-emerald-dim); color: var(--accent-emerald); }
.detail-form { margin-bottom: 32px; }
.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.form-group label svg { width: 14px; height: 14px; color: var(--text-tertiary); }
.trigger-info { display: flex; align-items: flex-start; gap: 12px; padding: 14px 16px; background: var(--bg-tertiary); border: 1px solid var(--border-subtle); border-radius: 8px; margin-bottom: 20px; font-size: 0.85rem; color: var(--text-secondary); line-height: 1.5; }
.trigger-info svg { width: 18px; height: 18px; flex-shrink: 0; color: var(--text-tertiary); margin-top: 2px; }
.trigger-info code { font-family: var(--font-mono); background: var(--bg-primary); padding: 2px 6px; border-radius: 4px; font-size: 0.8rem; color: var(--accent-cyan); }
.trigger-info.scheduled-info { flex-direction: row; align-items: flex-start; }
.schedule-details { display: flex; flex-direction: column; gap: 6px; }
.schedule-details strong { color: var(--accent-emerald); }
.schedule-next, .schedule-last { font-size: 0.75rem; color: var(--text-tertiary); font-family: var(--font-mono); }
.schedule-next { color: var(--accent-cyan); }
.btn-secondary { background: var(--bg-tertiary); color: var(--text-secondary); border: 1px solid var(--border-default); }
.btn-secondary:hover { background: var(--bg-elevated); color: var(--text-primary); }
/* Skill Autocomplete */
.skill-autocomplete-group { position: relative; }
.skill-input-wrapper { position: relative; display: flex; align-items: center; }
.skill-input-wrapper input { width: 100%; padding-right: 36px; font-family: var(--font-mono); }
.skill-clear-btn { position: absolute; right: 8px; width: 24px; height: 24px; background: transparent; border: none; color: var(--text-muted); cursor: pointer; display: flex; align-items: center; justify-content: center; border-radius: 4px; transition: all var(--transition-fast); }
.skill-clear-btn:hover { color: var(--accent-crimson); background: var(--accent-crimson-dim); }
.skill-clear-btn svg { width: 14px; height: 14px; }
.skill-dropdown { position: absolute; top: 100%; left: 0; right: 0; background: var(--bg-primary); border: 1px solid var(--border-default); border-top: none; border-radius: 0 0 8px 8px; max-height: 200px; overflow-y: auto; z-index: 10; box-shadow: var(--shadow-lg); }
.skill-dropdown-item { display: flex; flex-direction: column; gap: 2px; padding: 10px 16px; cursor: pointer; transition: background var(--transition-fast); }
.skill-dropdown-item:hover { background: var(--bg-tertiary); }
.skill-dropdown-item.selected { background: var(--accent-cyan-dim); }
.skill-name { font-family: var(--font-mono); font-size: 0.85rem; font-weight: 600; color: var(--accent-cyan); }
.skill-desc { font-size: 0.75rem; color: var(--text-tertiary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.skill-dropdown-loading, .skill-dropdown-empty { padding: 12px 16px; font-size: 0.8rem; color: var(--text-muted); text-align: center; }
.execution-mode-group { border-top: 1px solid var(--border-subtle); padding-top: 16px; }
.auto-resolve-group { border-top: 1px solid var(--border-subtle); padding-top: 16px; }
.auto-resolve-toggle { display: flex; align-items: center; gap: 10px; cursor: pointer; padding: 10px 14px; border-radius: 8px; background: var(--bg-secondary); border: 1px solid var(--border-default); transition: all var(--transition-fast); }
.auto-resolve-toggle:hover { border-color: var(--accent-cyan); }
.auto-resolve-toggle input[type="checkbox"] { width: 16px; height: 16px; accent-color: var(--accent-cyan); cursor: pointer; flex-shrink: 0; }
.toggle-desc { font-size: 0.8rem; color: var(--text-secondary); }
/* Harness Configuration */
.harness-config-section { margin-top: 24px; margin-bottom: 24px; padding: 20px; background: var(--bg-primary); border: 1px solid var(--border-subtle); border-radius: 10px; }
.section-description { font-size: 0.8rem; color: var(--text-tertiary); margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.section-header h5 { display: flex; align-items: center; gap: 8px; font-size: 0.9rem; font-weight: 600; color: var(--text-primary); }
.section-header h5 svg { width: 16px; height: 16px; color: var(--accent-cyan); }
/* Budget */
.budget-section { margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border-subtle); }
.budget-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.budget-header h6 { font-size: 0.85rem; font-weight: 600; color: var(--text-primary); }
.budget-display { padding: 12px 16px; background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 8px; }
.budget-info-row { display: flex; justify-content: space-between; align-items: center; padding: 4px 0; }
.budget-label { font-size: 0.8rem; color: var(--text-tertiary); }
.budget-value { font-size: 0.85rem; font-weight: 600; color: var(--text-primary); font-family: var(--font-mono); }
.budget-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px; padding-top: 8px; border-top: 1px solid var(--border-subtle); }
.budget-form { padding: 16px; background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 8px; }
.budget-form-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px; }
.btn-sm { padding: 6px 12px; font-size: 0.8rem; }
/* Paths */
.paths-section { background: var(--bg-primary); border: 1px solid var(--border-subtle); border-radius: 10px; padding: 20px; }
.paths-count { font-size: 0.75rem; color: var(--text-tertiary); }
.path-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
.empty-paths { text-align: center; padding: 24px; color: var(--text-muted); font-size: 0.85rem; }
.path-item { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 8px; }
.path-text { font-family: var(--font-mono); font-size: 0.85rem; color: var(--text-secondary); }
.path-type-badge { display: inline-flex; align-items: center; padding: 2px 7px; border-radius: 4px; font-size: 0.6rem; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; flex-shrink: 0; }
.path-type-badge.local { background: var(--accent-cyan-dim); color: var(--accent-cyan); }
.path-type-badge.github { background: var(--accent-violet-dim); color: var(--accent-violet); }
.path-type-badge.project { background: var(--accent-emerald-dim); color: var(--accent-emerald); }
.path-arrow { color: var(--text-tertiary); margin: 0 4px; }
.path-type-toggle { display: flex; border: 1px solid var(--border-default); border-radius: 8px; overflow: hidden; flex-shrink: 0; }
.toggle-btn { padding: 10px 14px; border: none; background: var(--bg-secondary); color: var(--text-tertiary); font-size: 0.8rem; font-weight: 500; cursor: pointer; transition: all var(--transition-fast); }
.toggle-btn.active { background: var(--accent-cyan-dim); color: var(--accent-cyan); }
.toggle-btn:hover:not(.active) { background: var(--bg-tertiary); color: var(--text-secondary); }
.add-path-form { display: flex; gap: 12px; align-items: stretch; }
.add-path-form input { flex: 1; padding: 12px 16px; border: 1px solid var(--border-default); border-radius: 8px; font-size: 0.9rem; background: var(--bg-secondary); color: var(--text-primary); font-family: var(--font-mono); }
.add-path-form input:focus { border-color: var(--accent-cyan); outline: none; }
.btn-icon { width: 36px; height: 36px; border-radius: 8px; border: none; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all var(--transition-fast); background: var(--bg-tertiary); color: var(--text-secondary); }
.btn-icon:hover { background: var(--bg-elevated); }
.btn-icon svg { width: 16px; height: 16px; }
.btn-icon.btn-delete { color: var(--accent-crimson); }
.btn-icon.btn-delete:hover { background: var(--accent-crimson-dim); }
@media (max-width: 768px) { .form-row { grid-template-columns: 1fr; } }
</style>
