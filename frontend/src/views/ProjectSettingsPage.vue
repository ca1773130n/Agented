<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import type { Project, Team, Product } from '../services/api';
import { projectApi, teamApi, productApi, ApiError } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import ProjectMcpPanel from '../components/project/ProjectMcpPanel.vue';
import EntityLayout from '../layouts/EntityLayout.vue';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const props = defineProps<{
  projectId?: string;
}>();

const route = useRoute();
const router = useRouter();
const projectId = computed(() => (route.params.projectId as string) || props.projectId || '');

const showToast = useToast();

const project = ref<Project | null>(null);
const teams = ref<Team[]>([]);
const products = ref<Product[]>([]);
const isSaving = ref(false);
const selectedTeamIds = ref<string[]>([]);
const originalTeamIds = ref<string[]>([]);
const selectedProductId = ref<string>('');
const originalProductId = ref<string>('');
const selectedOwnerTeamId = ref<string>('');
const originalOwnerTeamId = ref<string>('');
const editLocalPath = ref<string>('');
const originalLocalPath = ref<string>('');
const editName = ref('');
const originalName = ref('');
const editDescription = ref('');
const originalDescription = ref('');
const cloneStatus = ref<string>('none');
const cloneError = ref<string>('');
const lastSyncedAt = ref<string>('');
const isSyncing = ref(false);
let clonePollTimer: ReturnType<typeof setInterval> | null = null;

// Filter out the owner team from the additional teams grid
const additionalTeams = computed(() => {
  return teams.value.filter(team => team.id !== selectedOwnerTeamId.value);
});

// Total team count including owner team
const totalTeamCount = computed(() => {
  let count = selectedTeamIds.value.length;
  if (selectedOwnerTeamId.value && !selectedTeamIds.value.includes(selectedOwnerTeamId.value)) {
    count += 1;
  }
  return count;
});

useWebMcpTool({
  name: 'agented_project_settings_get_state',
  description: 'Returns the current state of the ProjectSettingsPage',
  page: 'ProjectSettingsPage',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'ProjectSettingsPage',
        projectId: project.value?.id ?? null,
        projectName: project.value?.name ?? null,
        isSaving: isSaving.value,
        editName: editName.value,
        editDescription: editDescription.value,
        selectedTeamCount: selectedTeamIds.value.length,
        totalTeamCount: totalTeamCount.value,
        selectedProductId: selectedProductId.value,
        selectedOwnerTeamId: selectedOwnerTeamId.value,
      }),
    }],
  }),
  deps: [project, isSaving, editName, editDescription, selectedTeamIds, totalTeamCount, selectedProductId, selectedOwnerTeamId],
});

async function loadData() {
  const [projectData, teamsData, productsData] = await Promise.all([
    projectApi.get(projectId.value),
    teamApi.list(),
    productApi.list(),
  ]);
  project.value = projectData;
  teams.value = teamsData.teams || [];
  products.value = productsData.products || [];
  // Initialize selected teams from project's current teams
  const teamIds = project.value.teams?.map(t => t.id) || [];
  selectedTeamIds.value = [...teamIds];
  originalTeamIds.value = [...teamIds];
  // Initialize selected product
  selectedProductId.value = project.value.product_id || '';
  originalProductId.value = project.value.product_id || '';
  // Initialize owner team
  selectedOwnerTeamId.value = project.value.owner_team_id || '';
  originalOwnerTeamId.value = project.value.owner_team_id || '';
  // Initialize local path
  editLocalPath.value = project.value.local_path || '';
  originalLocalPath.value = project.value.local_path || '';
  // Initialize name and description
  editName.value = project.value.name;
  originalName.value = project.value.name;
  editDescription.value = project.value.description || '';
  originalDescription.value = project.value.description || '';
  // Initialize clone status
  cloneStatus.value = project.value.clone_status || 'none';
  cloneError.value = project.value.clone_error || '';
  lastSyncedAt.value = project.value.last_synced_at || '';
  if (cloneStatus.value === 'cloning') {
    startClonePoll();
  }
  return project.value;
}

async function saveSettings() {
  if (!project.value) return;
  isSaving.value = true;
  try {
    // Update product, owner team, local path, name, and description if changed
    const updateData: { name?: string; description?: string; product_id?: string; owner_team_id?: string; local_path?: string } = {};
    if (editName.value !== originalName.value) updateData.name = editName.value;
    if (editDescription.value !== originalDescription.value) updateData.description = editDescription.value;
    if (selectedProductId.value !== originalProductId.value) {
      updateData.product_id = selectedProductId.value;
    }
    if (selectedOwnerTeamId.value !== originalOwnerTeamId.value) {
      updateData.owner_team_id = selectedOwnerTeamId.value;
    }
    if (editLocalPath.value !== originalLocalPath.value) {
      updateData.local_path = editLocalPath.value;
    }
    if (Object.keys(updateData).length > 0) {
      await projectApi.update(projectId.value, updateData);
      originalName.value = editName.value;
      originalDescription.value = editDescription.value;
      originalProductId.value = selectedProductId.value;
      originalOwnerTeamId.value = selectedOwnerTeamId.value;
      originalLocalPath.value = editLocalPath.value;
    }

    // Find teams to add (in selected but not in original)
    const teamsToAdd = selectedTeamIds.value.filter(id => !originalTeamIds.value.includes(id));
    // Find teams to remove (in original but not in selected)
    const teamsToRemove = originalTeamIds.value.filter(id => !selectedTeamIds.value.includes(id));

    // Execute all assignment/unassignment operations
    const operations = [
      ...teamsToAdd.map(teamId => projectApi.assignTeam(projectId.value, teamId)),
      ...teamsToRemove.map(teamId => projectApi.unassignTeam(projectId.value, teamId)),
    ];

    await Promise.all(operations);

    // Update original to match current selection
    originalTeamIds.value = [...selectedTeamIds.value];

    showToast('Project settings saved', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to save settings';
    showToast(message, 'error');
  } finally {
    isSaving.value = false;
  }
}

function toggleTeam(teamId: string) {
  const index = selectedTeamIds.value.indexOf(teamId);
  if (index === -1) {
    selectedTeamIds.value.push(teamId);
  } else {
    selectedTeamIds.value.splice(index, 1);
  }
}

function isTeamSelected(teamId: string): boolean {
  return selectedTeamIds.value.includes(teamId);
}

async function pollCloneStatus() {
  if (!project.value) return;
  try {
    const data = await projectApi.getCloneStatus(projectId.value);
    cloneStatus.value = data.clone_status || 'none';
    cloneError.value = data.clone_error || '';
    lastSyncedAt.value = data.last_synced_at || '';
    if (data.clone_status !== 'cloning') {
      stopClonePoll();
    }
  } catch {
    stopClonePoll();
  }
}

function startClonePoll() {
  stopClonePoll();
  clonePollTimer = setInterval(pollCloneStatus, 3000);
}

function stopClonePoll() {
  if (clonePollTimer) {
    clearInterval(clonePollTimer);
    clonePollTimer = null;
  }
}

onUnmounted(() => stopClonePoll());

async function syncNow() {
  if (!project.value) return;
  isSyncing.value = true;
  try {
    const result = await projectApi.syncRepo(projectId.value);
    if (result.status === 'ok') {
      showToast('Repository synced successfully', 'success');
      await pollCloneStatus();
    } else {
      showToast(result.error || 'Sync failed', 'error');
    }
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Sync failed';
    showToast(message, 'error');
  } finally {
    isSyncing.value = false;
  }
}

async function retryClone() {
  if (!project.value) return;
  cloneStatus.value = 'cloning';
  cloneError.value = '';
  try {
    await projectApi.syncRepo(projectId.value);
    startClonePoll();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Retry failed';
    showToast(message, 'error');
    cloneStatus.value = 'error';
  }
}

</script>

<template>
  <EntityLayout :load-entity="loadData" entity-label="project settings">
    <template #default="{ reload: _reload }">
  <div class="settings-page">
    <AppBreadcrumb :items="[
      { label: 'Projects', action: () => router.push({ name: 'projects' }) },
      { label: project?.name || 'Project', action: () => router.push({ name: 'project-dashboard', params: { projectId: projectId } }) },
      { label: 'Settings' },
    ]" />

    <template v-if="project">
      <PageHeader :title="(project?.name ?? '') + ' Settings'" subtitle="Configure project settings and team assignments" />

      <!-- Project Details Section -->
      <div class="card">
        <div class="card-header">
          <h3>Project Details</h3>
        </div>
        <div class="card-body">
          <div class="form-group">
            <label>Name</label>
            <input v-model="editName" type="text" class="settings-input" placeholder="Project name" />
          </div>
          <div class="form-group">
            <label>Description</label>
            <textarea v-model="editDescription" class="settings-textarea" placeholder="Project description..." rows="3"></textarea>
          </div>
        </div>
      </div>

      <!-- Product Section -->
      <div class="card">
        <div class="card-header">
          <h3>Product Assignment</h3>
        </div>
        <div class="card-body">
          <p class="section-description">Assign this project to a product for organization.</p>

          <div class="product-select-wrapper">
            <select v-model="selectedProductId" class="product-select">
              <option value="">No product assigned</option>
              <option v-for="prod in products" :key="prod.id" :value="prod.id">
                {{ prod.name }}
              </option>
            </select>
            <svg class="select-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M6 9l6 6 6-6"/>
            </svg>
          </div>

          <p v-if="selectedProductId && selectedProductId !== originalProductId" class="change-hint">
            Product assignment will be updated when you save.
          </p>
        </div>
      </div>

      <!-- Owner Team Section -->
      <div class="card">
        <div class="card-header">
          <h3>Owner Team</h3>
          <span v-if="selectedOwnerTeamId" class="owner-badge">Primary</span>
        </div>
        <div class="card-body">
          <p class="section-description">Select the primary team responsible for this project. This team has ownership and primary responsibility.</p>

          <div class="product-select-wrapper">
            <select v-model="selectedOwnerTeamId" class="product-select">
              <option value="">No owner team assigned</option>
              <option v-for="team in teams" :key="team.id" :value="team.id">
                {{ team.name }}
              </option>
            </select>
            <svg class="select-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M6 9l6 6 6-6"/>
            </svg>
          </div>

          <p v-if="selectedOwnerTeamId !== originalOwnerTeamId" class="change-hint">
            Owner team will be updated when you save.
          </p>
        </div>
      </div>

      <!-- Repository Section -->
      <div v-if="project?.github_repo" class="card">
        <div class="card-header">
          <h3>Repository</h3>
          <span class="clone-badge" :class="cloneStatus">
            {{ cloneStatus === 'none' ? 'Not Cloned' : cloneStatus === 'cloning' ? 'Cloning...' : cloneStatus === 'cloned' ? 'Cloned' : 'Error' }}
          </span>
        </div>
        <div class="card-body">
          <p class="section-description">GitHub repository: <strong>{{ project.github_repo }}</strong></p>

          <!-- Cloning spinner -->
          <div v-if="cloneStatus === 'cloning'" class="clone-info">
            <span class="spinner"></span>
            <span>Cloning repository in background...</span>
          </div>

          <!-- Error state -->
          <div v-else-if="cloneStatus === 'error'" class="clone-info clone-error-box">
            <span class="error-text">{{ cloneError }}</span>
            <button class="btn btn-sm" @click="retryClone">Retry Clone</button>
          </div>

          <!-- Cloned state -->
          <div v-else-if="cloneStatus === 'cloned'" class="clone-info">
            <span v-if="lastSyncedAt" class="sync-time">Last synced: {{ new Date(lastSyncedAt).toLocaleString() }}</span>
            <span v-else class="sync-time">Never synced</span>
            <button class="btn btn-sm" :disabled="isSyncing" @click="syncNow">
              <span v-if="isSyncing">Syncing...</span>
              <span v-else>Sync Now</span>
            </button>
          </div>
        </div>
      </div>

      <!-- Project Path Section -->
      <div class="card">
        <div class="card-header">
          <h3>Project Path</h3>
        </div>
        <div class="card-body">
          <p class="section-description">Local path to the project directory for team execution. When teams run in this project's context, they use this directory as their working directory.</p>

          <div class="form-group">
            <label>Local Path</label>
            <input
              v-model="editLocalPath"
              type="text"
              class="settings-input"
              placeholder="e.g., /home/user/projects/my-app"
            />
          </div>

          <p v-if="editLocalPath !== originalLocalPath" class="change-hint">
            Local path will be updated when you save.
          </p>
        </div>
      </div>

      <!-- Teams Section -->
      <div class="card">
        <div class="card-header">
          <h3>Additional Teams</h3>
          <span class="card-count">{{ totalTeamCount }} total ({{ selectedTeamIds.length }} additional)</span>
        </div>
        <div class="card-body">
          <p class="section-description">Select additional teams that will collaborate on this project. The owner team is shown separately above.</p>

          <div v-if="additionalTeams.length === 0" class="empty-state">
            <p v-if="teams.length === 0">No teams available. Create teams first.</p>
            <p v-else>All teams are assigned as owner. Add more teams to select additional collaborators.</p>
          </div>

          <div v-else class="teams-grid">
            <div
              v-for="team in additionalTeams"
              :key="team.id"
              class="team-option"
              :class="{ selected: isTeamSelected(team.id) }"
              @click="toggleTeam(team.id)"
            >
              <div class="team-checkbox">
                <svg v-if="isTeamSelected(team.id)" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                  <path d="M5 12l5 5L20 7"/>
                </svg>
              </div>
              <div class="team-icon" :style="{ background: team.color }">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                  <circle cx="9" cy="7" r="4"/>
                </svg>
              </div>
              <div class="team-info">
                <span class="team-name">{{ team.name }}</span>
                <span class="team-members">{{ team.member_count }} members</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- MCP Servers Section -->
      <div class="card" v-if="project">
        <div class="card-header">
          <h3>MCP Servers</h3>
        </div>
        <div class="card-body">
          <ProjectMcpPanel :projectId="projectId" />
        </div>
      </div>

      <!-- Actions -->
      <div class="actions-row">
        <button class="btn btn-secondary" @click="router.push({ name: 'project-dashboard', params: { projectId: projectId } })">
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

.card-count {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
  padding: 4px 8px;
  border-radius: 4px;
}

.owner-badge {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--accent-amber);
  background: rgba(255, 170, 0, 0.15);
  padding: 4px 10px;
  border-radius: 4px;
}

.card-body {
  padding: 20px;
}

.section-description {
  color: var(--text-secondary);
  font-size: 0.9rem;
  margin-bottom: 16px;
}

/* Product Select */
.product-select-wrapper {
  position: relative;
  display: inline-block;
  min-width: 300px;
}

.product-select {
  width: 100%;
  padding: 12px 40px 12px 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.9rem;
  cursor: pointer;
  appearance: none;
  transition: border-color 0.2s;
}

.product-select:hover,
.product-select:focus {
  border-color: var(--accent-cyan);
  outline: none;
}

.select-arrow {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  width: 18px;
  height: 18px;
  color: var(--text-tertiary);
  pointer-events: none;
}

.change-hint {
  font-size: 0.8rem;
  color: var(--accent-cyan);
  margin-top: 8px;
}

/* Teams Grid */
.teams-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 12px;
}

.team-option {
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

.team-option:hover {
  border-color: var(--border-subtle);
}

.team-option.selected {
  border-color: var(--accent-cyan);
  background: rgba(0, 212, 255, 0.05);
}

.team-checkbox {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border-subtle);
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s;
}

.team-option.selected .team-checkbox {
  background: var(--accent-cyan);
  border-color: var(--accent-cyan);
}

.team-checkbox svg {
  width: 14px;
  height: 14px;
  color: var(--bg-primary);
}

.team-icon {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.team-icon svg {
  width: 18px;
  height: 18px;
  color: var(--bg-primary);
}

.team-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.team-name {
  font-weight: 500;
  color: var(--text-primary);
}

.team-members {
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

.settings-input {
  width: 100%;
  max-width: 500px;
  padding: 12px 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.9rem;
  transition: border-color 0.2s;
}

.settings-input:hover,
.settings-input:focus {
  border-color: var(--accent-cyan);
  outline: none;
}

.settings-textarea {
  width: 100%;
  max-width: 500px;
  padding: 12px 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.9rem;
  font-family: inherit;
  transition: border-color 0.2s;
  resize: vertical;
  min-height: 60px;
}

.settings-textarea:hover,
.settings-textarea:focus {
  border-color: var(--accent-cyan);
  outline: none;
}

/* Clone / Sync */
.clone-badge {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 4px 10px;
  border-radius: 4px;
}

.clone-badge.none {
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
}

.clone-badge.cloning {
  color: var(--accent-cyan);
  background: rgba(0, 212, 255, 0.15);
}

.clone-badge.cloned {
  color: var(--accent-green, #22c55e);
  background: rgba(34, 197, 94, 0.15);
}

.clone-badge.error {
  color: var(--accent-red, #ef4444);
  background: rgba(239, 68, 68, 0.15);
}

.clone-info {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
}

.clone-error-box {
  padding: 12px;
  background: rgba(239, 68, 68, 0.08);
  border-radius: 8px;
  border: 1px solid rgba(239, 68, 68, 0.2);
}

.error-text {
  color: var(--accent-red, #ef4444);
  font-size: 0.85rem;
  flex: 1;
}

.sync-time {
  color: var(--text-secondary);
  font-size: 0.85rem;
}

.btn-sm {
  padding: 6px 14px;
  font-size: 0.8rem;
  border-radius: 6px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-subtle);
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.btn-sm:hover:not(:disabled) {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}

.btn-sm:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--border-subtle);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

</style>
