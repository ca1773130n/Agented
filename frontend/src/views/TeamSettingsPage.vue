<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import type { Team, Agent } from '../services/api';
import { teamApi, agentApi, ApiError } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import EntityLayout from '../layouts/EntityLayout.vue';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const props = defineProps<{
  teamId?: string;
}>();

const route = useRoute();
const router = useRouter();
const teamId = computed(() => (route.params.teamId as string) || props.teamId || '');

const showToast = useToast();

const team = ref<Team | null>(null);
const agents = ref<Agent[]>([]);
const isSaving = ref(false);
const selectedLeaderId = ref<string>('');
const editName = ref('');
const editDescription = ref('');
const editColor = ref('#00d4ff');

useWebMcpTool({
  name: 'agented_team_settings_get_state',
  description: 'Returns the current state of the TeamSettingsPage',
  page: 'TeamSettingsPage',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'TeamSettingsPage',
        teamId: team.value?.id ?? null,
        teamName: team.value?.name ?? null,
        isSaving: isSaving.value,
        editName: editName.value,
        editDescription: editDescription.value,
        selectedLeaderId: selectedLeaderId.value,
        agentsCount: agents.value.length,
      }),
    }],
  }),
  deps: [team, isSaving, editName, editDescription, selectedLeaderId, agents],
});

async function loadData() {
  const [teamData, agentsData] = await Promise.all([
    teamApi.get(teamId.value),
    agentApi.list(),
  ]);
  team.value = teamData;
  agents.value = agentsData.agents || [];
  selectedLeaderId.value = team.value.leader_id || '';
  editName.value = team.value.name;
  editDescription.value = team.value.description || '';
  editColor.value = team.value.color || '#00d4ff';
  return team.value;
}

async function saveSettings() {
  if (!team.value) return;
  if (!editName.value.trim()) {
    showToast('Team name is required', 'error');
    return;
  }
  isSaving.value = true;
  try {
    await teamApi.update(teamId.value, {
      name: editName.value,
      description: editDescription.value,
      color: editColor.value,
      leader_id: selectedLeaderId.value || undefined,
    });
    showToast('Team settings saved', 'success');
    await loadData();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to save settings';
    showToast(message, 'error');
  } finally {
    isSaving.value = false;
  }
}


</script>

<template>
  <EntityLayout :load-entity="loadData" entity-label="team settings">
    <template #default="{ reload: _reload }">
  <div class="settings-page">
    <AppBreadcrumb :items="[
      { label: 'Teams', action: () => router.push({ name: 'teams' }) },
      { label: team?.name || 'Team', action: () => router.push({ name: 'team-dashboard', params: { teamId: teamId } }) },
      { label: 'Settings' },
    ]" />

    <template v-if="team">
      <PageHeader :title="(team?.name ?? '') + ' Settings'" subtitle="Configure team settings and leadership" />

      <!-- Basic Info Section -->
      <div class="card">
        <div class="card-header">
          <h3>Basic Information</h3>
        </div>
        <div class="card-body">
          <div class="form-group">
            <label>Team Name</label>
            <input v-model="editName" type="text" placeholder="Enter team name" />
          </div>
          <div class="form-group">
            <label>Description</label>
            <textarea v-model="editDescription" placeholder="Describe the team..."></textarea>
          </div>
          <div class="form-group">
            <label>Color</label>
            <div class="color-picker">
              <input v-model="editColor" type="color" />
              <span>{{ editColor }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Leader Section -->
      <div class="card">
        <div class="card-header">
          <h3>Team Leader</h3>
        </div>
        <div class="card-body">
          <p class="section-description">Select an agent to lead this team.</p>

          <div v-if="agents.length === 0" class="empty-state">
            <p>No agents available. Create agents first.</p>
          </div>

          <div v-else class="agents-grid">
            <div
              v-for="agent in agents"
              :key="agent.id"
              class="agent-option"
              :class="{ selected: selectedLeaderId === agent.id }"
              @click="selectedLeaderId = agent.id"
            >
              <div class="agent-radio">
                <div v-if="selectedLeaderId === agent.id" class="radio-dot"></div>
              </div>
              <div class="agent-avatar">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="8" r="4"/>
                  <path d="M20 21a8 8 0 1 0-16 0"/>
                </svg>
              </div>
              <div class="agent-info">
                <span class="agent-name">{{ agent.name }}</span>
                <span v-if="agent.role" class="agent-role">{{ agent.role }}</span>
              </div>
            </div>
          </div>

          <button
            v-if="selectedLeaderId"
            class="btn btn-text"
            @click="selectedLeaderId = ''"
          >
            Clear selection
          </button>
        </div>
      </div>

      <!-- Actions -->
      <div class="actions-row">
        <button class="btn btn-secondary" @click="router.push({ name: 'team-dashboard', params: { teamId: teamId } })">
          Cancel
        </button>
        <button class="btn btn-primary" :disabled="isSaving" @click="saveSettings">
          <span v-if="isSaving">Saving...</span>
          <span v-else>Save Settings</span>
        </button>
      </div>
    </template>
  </div>
    </template>
  </EntityLayout>
</template>

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  max-width: 800px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

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

.card-body {
  padding: 20px;
}

.section-description {
  color: var(--text-secondary);
  font-size: 0.9rem;
  margin-bottom: 16px;
}

/* Form Groups */

.form-group {
  margin-bottom: 16px;
}

.form-group:last-child {
  margin-bottom: 0;
}

.form-group label {
  display: block;
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.form-group input[type="text"],
.form-group textarea {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
}

.form-group textarea {
  resize: vertical;
  min-height: 60px;
  font-family: inherit;
}

.form-group input:focus,
.form-group textarea:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.color-picker {
  display: flex;
  align-items: center;
  gap: 12px;
}

.color-picker input[type="color"] {
  width: 44px;
  height: 44px;
  padding: 0;
  border: none;
  border-radius: 8px;
  cursor: pointer;
}

.color-picker span {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  color: var(--text-secondary);
}

/* Agents Grid */
.agents-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.agent-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--bg-tertiary);
  border: 2px solid transparent;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.agent-option:hover {
  border-color: var(--border-subtle);
}

.agent-option.selected {
  border-color: var(--accent-cyan);
  background: rgba(0, 212, 255, 0.05);
}

.agent-radio {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border-subtle);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s;
}

.agent-option.selected .agent-radio {
  border-color: var(--accent-cyan);
}

.radio-dot {
  width: 10px;
  height: 10px;
  background: var(--accent-cyan);
  border-radius: 50%;
}

.agent-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--accent-cyan, #00d4ff), var(--accent-emerald, #00ff88));
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.agent-avatar svg {
  width: 18px;
  height: 18px;
  color: var(--bg-primary);
}

.agent-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.agent-name {
  font-weight: 500;
  color: var(--text-primary);
}

.agent-role {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

/* Empty State */

/* Actions */
.actions-row {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 212, 255, 0.3);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-subtle);
}

.btn-secondary:hover {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}

.btn-text {
  background: none;
  color: var(--text-tertiary);
  padding: 8px 0;
}

.btn-text:hover {
  color: var(--accent-cyan);
}
</style>
