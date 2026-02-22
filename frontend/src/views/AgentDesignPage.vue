<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import type { Agent } from '../services/api';
import { agentApi, skillsApi, ApiError } from '../services/api';
import PageLayout from '../components/base/PageLayout.vue';
import EntityLayout from '../layouts/EntityLayout.vue';
import ConfirmModal from '../components/base/ConfirmModal.vue';
import { useToast } from '../composables/useToast';
import { useUnsavedGuard } from '../composables/useUnsavedGuard';
import { useWebMcpTool } from '../composables/useWebMcpTool';
import { clearEntityCache } from '../router/guards';

interface SkillInfo {
  name: string;
  description?: string;
}

const props = defineProps<{
  agentId?: string;
}>();

const route = useRoute();
const router = useRouter();
const agentId = computed(() => (route.params.agentId as string) || props.agentId || '');

const showToast = useToast();

const agent = ref<Agent | null>(null);
const isSaving = ref(false);
const editMode = ref(false);

// Action state
const isRunning = ref(false);
const lastRunSuccess = ref(false);
const isDeleting = ref(false);
const isToggling = ref(false);
const showDeleteConfirm = ref(false);

// Editable fields
const editForm = ref({
  name: '',
  description: '',
  role: '',
  skills: [] as string[],
  context: '',
  system_prompt: '',
  goals: [] as string[],
  documents: '',
  preferred_model: '',
  effort_level: 'medium' as string,
  backend_type: 'claude' as string,
});

// Unsaved changes guard
const originalFormData = ref('');
const isDirty = computed(() => editMode.value && JSON.stringify(editForm.value) !== originalFormData.value);
useUnsavedGuard(isDirty);

useWebMcpTool({
  name: 'hive_agent_design_get_state',
  description: 'Returns the current state of the AgentDesignPage',
  page: 'AgentDesignPage',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'AgentDesignPage',
        agentId: agent.value?.id ?? null,
        agentName: agent.value?.name ?? null,
        editMode: editMode.value,
        isDirty: isDirty.value,
        isSaving: isSaving.value,
        isRunning: isRunning.value,
        isDeleting: isDeleting.value,
        showDeleteConfirm: showDeleteConfirm.value,
      }),
    }],
  }),
  deps: [agent, editMode, isDirty, isSaving, isRunning, isDeleting, showDeleteConfirm],
});

// Skill autocomplete state
const availableSkills = ref<SkillInfo[]>([]);
const skillInput = ref('');
const showSkillSuggestions = ref(false);
const filteredSkillSuggestions = computed(() => {
  if (!skillInput.value) return [];
  const query = skillInput.value.toLowerCase();
  return availableSkills.value
    .filter(s => s.name.toLowerCase().includes(query))
    .filter(s => !editForm.value.skills.includes(s.name))
    .slice(0, 8);
});

async function loadAvailableSkills() {
  try {
    const data = await skillsApi.list();
    availableSkills.value = (data.skills || []).map((s: { name: string; description?: string }) => ({
      name: s.name,
      description: s.description || '',
    }));
  } catch (e) {
    // Silent fail - skills suggestions are optional
  }
}

function handleSkillKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && skillInput.value.trim()) {
    e.preventDefault();
    addSkill(skillInput.value.trim());
  }
}

function hideSkillSuggestions() {
  window.setTimeout(() => {
    showSkillSuggestions.value = false;
  }, 200);
}

function addSkill(skillName: string) {
  if (!editForm.value.skills.includes(skillName)) {
    editForm.value.skills.push(skillName);
  }
  skillInput.value = '';
  showSkillSuggestions.value = false;
}

function removeSkill(index: number) {
  editForm.value.skills.splice(index, 1);
}

function populateEditForm(data: Agent) {
  editForm.value = {
    name: data.name || '',
    description: data.description || '',
    role: data.role || '',
    skills: Array.isArray(data.skills) ? data.skills : [],
    context: data.context || '',
    system_prompt: data.system_prompt || '',
    goals: Array.isArray(data.goals) ? [...data.goals] : [],
    documents: Array.isArray(data.documents) ? JSON.stringify(data.documents, null, 2) : '',
    preferred_model: data.preferred_model || '',
    effort_level: data.effort_level || 'medium',
    backend_type: data.backend_type || 'claude',
  };
  originalFormData.value = JSON.stringify(editForm.value);
}

async function loadAgent() {
  const data = await agentApi.get(agentId.value);
  agent.value = data;
  populateEditForm(data);
  // Fire-and-forget: load available skills for autocomplete
  loadAvailableSkills();
  return data;
}

function startEditing() {
  editMode.value = true;
}

function cancelEditing() {
  // Reset form to original values
  if (agent.value) {
    populateEditForm(agent.value);
  }
  editMode.value = false;
}

async function saveChanges() {
  if (!agent.value) return;

  isSaving.value = true;
  try {
    await agentApi.update(agent.value.id, {
      name: editForm.value.name,
      description: editForm.value.description,
      role: editForm.value.role,
      skills: JSON.stringify(editForm.value.skills),
      context: editForm.value.context,
      system_prompt: editForm.value.system_prompt,
      goals: JSON.stringify(editForm.value.goals),
      preferred_model: editForm.value.preferred_model || undefined,
      effort_level: editForm.value.effort_level as any,
      backend_type: editForm.value.backend_type as any,
    });
    showToast('Agent updated successfully', 'success');
    editMode.value = false;
    await loadAgent(); // Reload to get fresh data
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to update agent', 'error');
    }
  } finally {
    isSaving.value = false;
  }
}

async function runAgent() {
  if (!agent.value) return;
  isRunning.value = true;
  lastRunSuccess.value = false;
  try {
    const result = await agentApi.run(agent.value.id);
    showToast(`Agent started (execution: ${result.execution_id})`, 'success');
    lastRunSuccess.value = true;
  } catch (e) {
    showToast(e instanceof ApiError ? e.message : 'Failed to run agent', 'error');
  } finally {
    isRunning.value = false;
  }
}

async function deleteAgent() {
  if (!agent.value) return;
  isDeleting.value = true;
  try {
    await agentApi.delete(agent.value.id);
    showToast(`Agent "${agent.value.name}" deleted`, 'success');
    showDeleteConfirm.value = false;
    clearEntityCache();
    router.push({ name: 'agents' });
  } catch (e) {
    showToast(e instanceof ApiError ? e.message : 'Failed to delete agent', 'error');
  } finally {
    isDeleting.value = false;
  }
}

async function toggleEnabled() {
  if (!agent.value) return;
  isToggling.value = true;
  try {
    await agentApi.update(agent.value.id, { enabled: agent.value.enabled ? 0 : 1 });
    await loadAgent();
  } catch (e) {
    showToast('Failed to update agent', 'error');
  } finally {
    isToggling.value = false;
  }
}

</script>

<template>
  <PageLayout :breadcrumbs="[{ label: 'Agents', action: () => router.push({ name: 'agents' }) }, { label: agent?.name || 'Agent' }]" fullHeight maxWidth="100%">
  <EntityLayout :load-entity="loadAgent" entity-label="agent">
    <template #default="{ reload: _reload }">
  <div class="design-page">
    <div class="design-header">
      <button class="btn-back" @click="router.push({ name: 'agents' })">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 12H5M12 19l-7-7 7-7"/>
        </svg>
        Back to Agents
      </button>
      <div class="header-title">
        <h1>{{ agent?.name || 'Agent Design' }}</h1>
        <p>View and refine your AI agent</p>
      </div>
      <div class="header-actions">
        <template v-if="!editMode && agent">
          <button class="btn btn-success btn-action" @click="runAgent" :disabled="!agent.enabled || isRunning">
            <span v-if="isRunning" class="spinner-small"></span>
            <svg v-else viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            {{ isRunning ? 'Running...' : 'Run' }}
          </button>
          <button v-if="lastRunSuccess" class="btn btn-action btn-view-log" @click="router.push({ name: 'execution-history' })">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
            </svg>
            View Log
          </button>
          <button class="btn btn-action" @click="toggleEnabled" :disabled="isToggling">
            {{ isToggling ? '...' : (agent.enabled ? 'Disable' : 'Enable') }}
          </button>
          <button class="btn btn-primary" @click="startEditing">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/>
              <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/>
            </svg>
            Edit
          </button>
          <button class="btn btn-danger btn-action" @click="showDeleteConfirm = true" :disabled="isDeleting">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
            </svg>
          </button>
        </template>
        <template v-else-if="editMode">
          <button class="btn btn-secondary" @click="cancelEditing" :disabled="isSaving">
            Cancel
          </button>
          <button class="btn btn-primary" @click="saveChanges" :disabled="isSaving">
            <svg v-if="!isSaving" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M20 6L9 17l-5-5"/>
            </svg>
            <span v-if="isSaving" class="spinner-small"></span>
            {{ isSaving ? 'Saving...' : 'Save Changes' }}
          </button>
        </template>
      </div>
    </div>

    <div v-if="agent" class="design-content">
      <div class="design-grid">
        <!-- Basic Info Card -->
        <div class="design-card">
          <div class="card-header">
            <h3>Basic Information</h3>
          </div>
          <div class="card-body">
            <div class="form-group">
              <label>Name</label>
              <input
                v-if="editMode"
                v-model="editForm.name"
                type="text"
                class="form-input"
                placeholder="Agent name"
              />
              <p v-else class="field-value">{{ agent.name }}</p>
            </div>
            <div class="form-group">
              <label>Description</label>
              <textarea
                v-if="editMode"
                v-model="editForm.description"
                class="form-textarea"
                placeholder="Brief description of what this agent does"
                rows="3"
              ></textarea>
              <p v-else class="field-value">{{ agent.description || 'No description' }}</p>
            </div>
            <div class="form-group">
              <label>Backend Type</label>
              <select v-if="editMode" v-model="editForm.backend_type" class="form-input">
                <option value="claude">Claude</option>
                <option value="opencode">OpenCode</option>
                <option value="gemini">Gemini</option>
                <option value="codex">Codex</option>
              </select>
              <p v-else class="field-value">
                <span class="backend-badge" :class="agent.backend_type">{{ agent.backend_type }}</span>
              </p>
            </div>
            <div class="form-group">
              <label>Status</label>
              <p class="field-value">
                <span class="status-badge" :class="{ enabled: agent.enabled }">
                  {{ agent.enabled ? 'Active' : 'Disabled' }}
                </span>
              </p>
            </div>
          </div>
        </div>

        <!-- Role Card -->
        <div class="design-card">
          <div class="card-header">
            <h3>Role</h3>
          </div>
          <div class="card-body">
            <div class="form-group">
              <label>Role</label>
              <textarea
                v-if="editMode"
                v-model="editForm.role"
                class="form-textarea"
                placeholder="The role this agent plays"
                rows="5"
              ></textarea>
              <p v-else class="field-value">{{ agent.role || 'No role defined' }}</p>
            </div>
          </div>
        </div>

        <!-- Goals Card -->
        <div class="design-card">
          <div class="card-header"><h3>Goals</h3></div>
          <div class="card-body">
            <div class="form-group">
              <label>Goals</label>
              <div v-if="editMode" class="goals-editor">
                <div v-for="(_goal, index) in editForm.goals" :key="index" class="goal-item">
                  <input v-model="editForm.goals[index]" type="text" class="form-input" placeholder="Enter a goal" />
                  <button type="button" class="remove-goal" @click="editForm.goals.splice(index, 1)">&times;</button>
                </div>
                <button type="button" class="btn btn-small" @click="editForm.goals.push('')">+ Add Goal</button>
              </div>
              <ul v-else-if="agent.goals && agent.goals.length > 0" class="goals-list">
                <li v-for="(goal, i) in agent.goals" :key="i">{{ goal }}</li>
              </ul>
              <p v-else class="field-value muted">No goals defined</p>
            </div>
          </div>
        </div>

        <!-- Skills & Context Card -->
        <div class="design-card">
          <div class="card-header">
            <h3>Skills & Context</h3>
          </div>
          <div class="card-body">
            <div class="form-group">
              <label>Skills</label>
              <div v-if="editMode" class="skills-input-container">
                <div class="skills-tags-row">
                  <span v-for="(skill, index) in editForm.skills" :key="index" class="skill-tag editable">
                    {{ skill }}
                    <button type="button" class="remove-tag" @click="removeSkill(index)">&times;</button>
                  </span>
                  <input
                    v-model="skillInput"
                    type="text"
                    class="skill-input"
                    placeholder="Type skill name and press Enter"
                    @keydown="handleSkillKeydown"
                    @focus="showSkillSuggestions = true"
                    @blur="hideSkillSuggestions()"
                  />
                </div>
                <div v-if="showSkillSuggestions && filteredSkillSuggestions.length > 0" class="suggestions-dropdown">
                  <div
                    v-for="skill in filteredSkillSuggestions"
                    :key="skill.name"
                    class="suggestion-item"
                    @mousedown="addSkill(skill.name)"
                  >
                    <span class="suggestion-name">{{ skill.name }}</span>
                    <span v-if="skill.description" class="suggestion-desc">{{ skill.description }}</span>
                  </div>
                </div>
              </div>
              <div v-else-if="agent.skills && agent.skills.length > 0" class="skills-list">
                <span v-for="(skill, index) in agent.skills" :key="index" class="skill-tag">{{ skill }}</span>
              </div>
              <p v-else class="field-value muted">No skills assigned</p>
            </div>
            <div class="form-group">
              <label>Context</label>
              <textarea
                v-if="editMode"
                v-model="editForm.context"
                class="form-textarea"
                placeholder="Additional context for the agent"
                rows="4"
              ></textarea>
              <p v-else class="field-value">{{ agent.context || 'No context defined' }}</p>
            </div>
          </div>
        </div>

        <!-- Configuration Card -->
        <div class="design-card">
          <div class="card-header"><h3>Configuration</h3></div>
          <div class="card-body">
            <div class="form-group">
              <label>Preferred Model</label>
              <input v-if="editMode" v-model="editForm.preferred_model" type="text" class="form-input" placeholder="e.g. opus, sonnet" />
              <p v-else class="field-value">{{ agent.preferred_model || 'Default' }}</p>
            </div>
            <div class="form-group">
              <label>Effort Level</label>
              <select v-if="editMode" v-model="editForm.effort_level" class="form-input">
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="max">Max</option>
              </select>
              <p v-else class="field-value">
                <span class="effort-badge">{{ agent.effort_level || 'medium' }}</span>
              </p>
            </div>
            <div class="form-group">
              <label>Documents</label>
              <textarea v-if="editMode" v-model="editForm.documents" class="form-textarea code" placeholder="JSON array of document objects" rows="4"></textarea>
              <pre v-else-if="agent.documents && agent.documents.length > 0" class="system-prompt-display">{{ JSON.stringify(agent.documents, null, 2) }}</pre>
              <p v-else class="field-value muted">No documents attached</p>
            </div>
          </div>
        </div>

        <!-- System Prompt Card -->
        <div class="design-card full-width">
          <div class="card-header">
            <h3>System Prompt</h3>
          </div>
          <div class="card-body">
            <div class="form-group">
              <textarea
                v-if="editMode"
                v-model="editForm.system_prompt"
                class="form-textarea code"
                placeholder="The system prompt that defines the agent's behavior"
                rows="10"
              ></textarea>
              <pre v-else-if="agent.system_prompt" class="system-prompt-display">{{ agent.system_prompt }}</pre>
              <p v-else class="field-value muted">No system prompt defined</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <ConfirmModal
    :open="showDeleteConfirm"
    title="Delete Agent"
    :message="`Delete \u201C${agent?.name}\u201D? This cannot be undone.`"
    confirm-label="Delete"
    cancel-label="Cancel"
    variant="danger"
    @confirm="deleteAgent"
    @cancel="showDeleteConfirm = false"
  />
    </template>
  </EntityLayout>
  </PageLayout>
</template>

<style scoped>
.design-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-height: 100vh;
  overflow: hidden;
}

.design-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.btn-back {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-back:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.btn-back svg {
  width: 18px;
  height: 18px;
}

.header-title {
  flex: 1;
}

.header-title h1 {
  margin: 0;
  font-size: 18px;
  color: var(--text-primary);
}

.header-title p {
  margin: 4px 0 0 0;
  font-size: 13px;
  color: var(--text-tertiary);
}

.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.btn-primary:hover:not(:disabled) {
  background: #00c4ee;
}

.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--bg-elevated);
  color: var(--text-primary);
}

.btn-success {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.btn-success:hover:not(:disabled) {
  background: rgba(0, 255, 136, 0.25);
}

.btn-danger {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.btn-danger:hover:not(:disabled) {
  background: rgba(255, 64, 129, 0.25);
}

.btn-action {
  padding: 8px 14px;
  font-size: 13px;
}

.btn-action svg {
  width: 16px;
  height: 16px;
}

.btn-view-log {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
  animation: viewLogFadeIn 0.3s ease;
}

.btn-view-log:hover {
  background: rgba(0, 212, 255, 0.25);
}

@keyframes viewLogFadeIn {
  from { opacity: 0; transform: translateX(-4px); }
  to { opacity: 1; transform: translateX(0); }
}

.btn-small {
  padding: 6px 12px;
  font-size: 13px;
}

.spinner-small {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.design-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.design-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: 20px;
}

.design-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.design-card.full-width {
  grid-column: 1 / -1;
}

.card-header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-tertiary);
}

.card-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.card-body {
  padding: 20px;
}

.form-group:last-child {
  margin-bottom: 0;
}

.form-input,
.form-textarea {
  width: 100%;
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 14px;
  transition: border-color 0.15s;
}

.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.form-textarea {
  resize: vertical;
  min-height: 80px;
  line-height: 1.5;
}

.form-textarea.code {
  font-family: var(--font-mono);
  font-size: 13px;
}

.field-value {
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.5;
  margin: 0;
}

.field-value.muted {
  color: var(--text-tertiary);
  font-style: italic;
}

.backend-badge {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  text-transform: uppercase;
}

.backend-badge.claude {
  background: rgba(255, 136, 0, 0.15);
  color: #ff8800;
}

.backend-badge.opencode {
  background: rgba(0, 136, 255, 0.15);
  color: #0088ff;
}

.backend-badge.gemini {
  background: rgba(66, 133, 244, 0.15);
  color: #4285f4;
}

.backend-badge.codex {
  background: rgba(16, 163, 127, 0.15);
  color: #10a37f;
}

.status-badge {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.status-badge.enabled {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.skills-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.skill-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
  border-radius: 4px;
  font-size: 13px;
}

.skill-tag.editable {
  padding-right: 6px;
}

.skill-tag .remove-tag {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  background: transparent;
  border: none;
  border-radius: 50%;
  color: var(--accent-cyan);
  font-size: 14px;
  cursor: pointer;
  opacity: 0.7;
  transition: all 0.15s;
}

.skill-tag .remove-tag:hover {
  opacity: 1;
  background: rgba(0, 212, 255, 0.2);
}

.skills-input-container {
  position: relative;
}

.skills-tags-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  min-height: 44px;
  align-items: center;
}

.skills-tags-row:focus-within {
  border-color: var(--accent-cyan);
}

.skill-input {
  flex: 1;
  min-width: 150px;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: 14px;
  outline: none;
}

.skill-input::placeholder {
  color: var(--text-tertiary);
}

.suggestions-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  margin-top: 4px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  max-height: 200px;
  overflow-y: auto;
  z-index: 100;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.suggestion-item {
  display: flex;
  flex-direction: column;
  padding: 10px 12px;
  cursor: pointer;
  transition: background 0.15s;
}

.suggestion-item:hover {
  background: var(--bg-tertiary);
}

.suggestion-name {
  font-size: 14px;
  color: var(--text-primary);
}

.suggestion-desc {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.goals-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.goal-item {
  display: flex;
  gap: 8px;
  align-items: center;
}

.goal-item .form-input {
  flex: 1;
}

.remove-goal {
  background: transparent;
  border: none;
  color: var(--accent-crimson);
  font-size: 18px;
  cursor: pointer;
  padding: 4px 8px;
}

.goals-list {
  list-style: disc;
  padding-left: 20px;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.8;
}

.effort-badge {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  text-transform: uppercase;
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.system-prompt-display {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 16px;
  margin: 0;
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 400px;
  overflow-y: auto;
}
</style>
