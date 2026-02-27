<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import type { Project, HarnessStatusResult, ProjectSkill, Hook, Command, Rule, Agent, ProjectInstallation } from '../services/api';
import { projectApi, grdApi, hookApi, commandApi, ruleApi, agentApi, teamApi, ApiError } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import EntityLayout from '../layouts/EntityLayout.vue';
import InteractiveSetup from '../components/projects/InteractiveSetup.vue';
import ProjectStatusCard from '../components/projects/ProjectStatusCard.vue';
import ProjectTeamsSection from '../components/projects/ProjectTeamsSection.vue';
import ProjectTeamCanvas from '../components/projects/ProjectTeamCanvas.vue';
import ProjectLibraryTabs from '../components/projects/ProjectLibraryTabs.vue';
import HarnessStatusSection from '../components/projects/HarnessStatusSection.vue';
import { useToast } from '../composables/useToast';
import { useFocusTrap } from '../composables/useFocusTrap';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const props = defineProps<{
  projectId?: string;
}>();

const route = useRoute();
const router = useRouter();
const projectId = computed(() => (route.params.projectId as string) || props.projectId || '');

const showToast = useToast();

const project = ref<Project | null>(null);
const harnessStatus = ref<HarnessStatusResult | null>(null);
const isLoadingHarness = ref(false);
const isDeployingHarness = ref(false);
const projectSkills = ref<ProjectSkill[]>([]);
const showAddSkillModal = ref(false);
const newSkillName = ref('');
const newSkillPath = ref('');

const addSkillModalRef = ref<HTMLElement | null>(null);
useFocusTrap(addSkillModalRef, showAddSkillModal);
const isAddingSkill = ref(false);

// Team run state
const teamRunMessages = ref<Record<string, string>>({});
const teamRunning = ref<Record<string, boolean>>({});

// Library state
const allAgents = ref<Agent[]>([]);
const allHooks = ref<Hook[]>([]);
const allCommands = ref<Command[]>([]);
const allRules = ref<Rule[]>([]);
const isLoadingLibrary = ref(false);

// Installation state
const installations = ref<ProjectInstallation[]>([]);
const isInstallingComponent = ref<Record<string, boolean>>({});

// GRD init status
const grdInitStatus = ref<string>('none');
let initPollInterval: ReturnType<typeof setInterval> | null = null;

// Interactive Setup state
const showSetup = ref(false);
const setupCommand = ref('');

// Team member data (fetched separately for OrgCanvas)
const teamMembersMap = ref<Record<string, any[]>>({});

// Compute all teams including owner team with "is_owner" flag and members
const allTeams = computed(() => {
  if (!project.value) return [];
  const teams: { id: string; name: string; color: string; is_owner: boolean; members?: any[] }[] = [];
  if (project.value.owner_team_id && project.value.owner_team_name) {
    teams.push({
      id: project.value.owner_team_id,
      name: project.value.owner_team_name,
      color: '#00d4ff',
      is_owner: true,
      members: teamMembersMap.value[project.value.owner_team_id] || [],
    });
  }
  if (project.value.teams) {
    for (const team of project.value.teams) {
      if (team.id !== project.value.owner_team_id) {
        teams.push({
          ...team,
          is_owner: false,
          members: teamMembersMap.value[team.id] || [],
        });
      }
    }
  }
  return teams;
});

const totalTeamCount = computed(() => {
  if (!project.value) return 0;
  let count = project.value.teams?.length || 0;
  if (project.value.owner_team_id) {
    const ownerInTeams = project.value.teams?.some(t => t.id === project.value!.owner_team_id);
    if (!ownerInTeams) count += 1;
  }
  return count;
});

useWebMcpTool({
  name: 'agented_project_dashboard_get_state',
  description: 'Returns the current state of the ProjectDashboard',
  page: 'ProjectDashboard',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'ProjectDashboard',
        projectId: project.value?.id ?? null,
        projectName: project.value?.name ?? null,
        isLoadingHarness: isLoadingHarness.value,
        isDeployingHarness: isDeployingHarness.value,
        teamCount: totalTeamCount.value,
        skillsCount: projectSkills.value.length,
        installationsCount: installations.value.length,
        showSetup: showSetup.value,
        harnessStatus: harnessStatus.value ? 'loaded' : null,
      }),
    }],
  }),
  deps: [project, isLoadingHarness, isDeployingHarness, totalTeamCount, projectSkills, installations, showSetup, harnessStatus],
});

async function loadData() {
  const [projectData, skillsData, installationsData] = await Promise.all([
    projectApi.get(projectId.value),
    projectApi.listSkills(projectId.value),
    projectApi.listInstallations(projectId.value),
  ]);
  project.value = projectData;
  projectSkills.value = skillsData.skills || [];
  installations.value = installationsData.installations || [];

  // Fetch team members for OrgCanvas display
  const teamIds: string[] = [];
  if (projectData.owner_team_id) teamIds.push(projectData.owner_team_id);
  if (projectData.teams) {
    for (const t of projectData.teams) {
      if (!teamIds.includes(t.id)) teamIds.push(t.id);
    }
  }
  if (teamIds.length > 0) {
    const teamDetails = await Promise.all(
      teamIds.map(id => teamApi.get(id).catch(() => null))
    );
    const membersMap: Record<string, any[]> = {};
    for (const td of teamDetails) {
      if (td) membersMap[td.id] = td.members || [];
    }
    teamMembersMap.value = membersMap;
  }

  if (project.value?.github_repo) await checkHarnessStatus();
  // Fire and forget library items load (non-critical)
  loadLibraryItems();
  loadGrdStatus();
  return project.value;
}

async function loadGrdStatus() {
  if (!projectId.value) return;
  try {
    const result = await grdApi.getPlanningStatus(projectId.value);
    grdInitStatus.value = result.grd_init_status;
  } catch {
    grdInitStatus.value = 'none';
  }
}

watch(grdInitStatus, (newVal, oldVal) => {
  if (newVal === 'initializing' && !initPollInterval) {
    initPollInterval = setInterval(loadGrdStatus, 5000);
  } else if (newVal !== 'initializing' && initPollInterval) {
    clearInterval(initPollInterval);
    initPollInterval = null;
  }
  if (oldVal === 'initializing' && newVal === 'ready') {
    showToast('GRD planning initialized successfully', 'success');
  } else if (oldVal === 'initializing' && newVal === 'failed') {
    showToast('GRD planning initialization failed', 'error');
  }
});

onUnmounted(() => {
  if (initPollInterval) clearInterval(initPollInterval);
});

async function addSkill() {
  if (!newSkillName.value.trim()) { showToast('Skill name is required', 'error'); return; }
  isAddingSkill.value = true;
  try {
    await projectApi.addSkill(projectId.value, {
      skill_name: newSkillName.value.trim(),
      skill_path: newSkillPath.value.trim() || undefined,
      source: 'manual',
    });
    showToast('Skill added successfully', 'success');
    showAddSkillModal.value = false;
    newSkillName.value = '';
    newSkillPath.value = '';
    const skillsData = await projectApi.listSkills(projectId.value);
    projectSkills.value = skillsData.skills || [];
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to add skill';
    showToast(message, 'error');
  } finally {
    isAddingSkill.value = false;
  }
}

async function removeSkill(skill: ProjectSkill) {
  try {
    await projectApi.removeSkill(projectId.value, skill.id);
    showToast('Skill removed', 'success');
    projectSkills.value = projectSkills.value.filter(s => s.id !== skill.id);
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to remove skill';
    showToast(message, 'error');
  }
}

async function loadLibraryItems() {
  isLoadingLibrary.value = true;
  try {
    const [agentsData, hooksData, commandsData, rulesData] = await Promise.all([
      agentApi.list(), hookApi.list(), commandApi.list(), ruleApi.list(),
    ]);
    allAgents.value = agentsData.agents || [];
    allHooks.value = hooksData.hooks || [];
    allCommands.value = commandsData.commands || [];
    allRules.value = rulesData.rules || [];
  } catch (err) {
    showToast('Failed to load library items', 'error');
  } finally {
    isLoadingLibrary.value = false;
  }
}

async function toggleHookForProject(hook: Hook) {
  try {
    const newProjectId = hook.project_id === projectId.value ? undefined : projectId.value;
    await hookApi.update(hook.id, { project_id: newProjectId });
    await loadLibraryItems();
    showToast(newProjectId ? 'Hook added to project' : 'Hook removed from project', 'success');
  } catch (err) { showToast('Failed to update hook', 'error'); }
}

async function toggleCommandForProject(command: Command) {
  try {
    const newProjectId = command.project_id === projectId.value ? undefined : projectId.value;
    await commandApi.update(command.id, { project_id: newProjectId });
    await loadLibraryItems();
    showToast(newProjectId ? 'Command added to project' : 'Command removed from project', 'success');
  } catch (err) { showToast('Failed to update command', 'error'); }
}

async function toggleRuleForProject(rule: Rule) {
  try {
    const newProjectId = rule.project_id === projectId.value ? undefined : projectId.value;
    await ruleApi.update(rule.id, { project_id: newProjectId });
    await loadLibraryItems();
    showToast(newProjectId ? 'Rule added to project' : 'Rule removed from project', 'success');
  } catch (err) { showToast('Failed to update rule', 'error'); }
}

async function installToProject(componentType: string, componentId: string, componentName: string) {
  const key = `${componentType}-${componentId}`;
  isInstallingComponent.value[key] = true;
  try {
    const result = await projectApi.installComponent(projectId.value, { component_type: componentType, component_id: componentId });
    if (result.installed) {
      showToast(`Installed ${componentName} to .claude/`, 'success');
      const data = await projectApi.listInstallations(projectId.value);
      installations.value = data.installations || [];
    } else if (result.error) { showToast(result.error, 'error'); }
  } catch (err) {
    const message = err instanceof ApiError ? err.message : `Failed to install ${componentName}`;
    showToast(message, 'error');
  } finally { isInstallingComponent.value[key] = false; }
}

async function uninstallFromProject(componentType: string, componentId: string, componentName: string) {
  const key = `${componentType}-${componentId}`;
  isInstallingComponent.value[key] = true;
  try {
    const result = await projectApi.uninstallComponent(projectId.value, { component_type: componentType, component_id: componentId });
    if (result.uninstalled) {
      showToast(`Uninstalled ${componentName} from .claude/`, 'success');
      const data = await projectApi.listInstallations(projectId.value);
      installations.value = data.installations || [];
    } else if (result.error) { showToast(result.error, 'error'); }
  } catch (err) {
    const message = err instanceof ApiError ? err.message : `Failed to uninstall ${componentName}`;
    showToast(message, 'error');
  } finally { isInstallingComponent.value[key] = false; }
}

async function checkHarnessStatus() {
  try { harnessStatus.value = await projectApi.getHarnessStatus(projectId.value); }
  catch { harnessStatus.value = null; }
}

async function loadHarness() {
  if (!project.value?.github_repo) { showToast('No GitHub repository configured', 'error'); return; }
  isLoadingHarness.value = true;
  try {
    const result = await projectApi.loadHarness(projectId.value);
    if (result.error) { showToast(result.error, 'error'); }
    else {
      const counts = result.counts || {};
      const summary = Object.entries(counts).filter(([, v]) => v > 0).map(([k, v]) => `${v} ${k}`).join(', ');
      showToast(`Loaded harness settings: ${summary || 'no items'}`, 'success');
    }
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to load harness';
    showToast(message, 'error');
  } finally { isLoadingHarness.value = false; }
}

async function deployHarness() {
  if (!project.value?.github_repo) { showToast('No GitHub repository configured', 'error'); return; }
  isDeployingHarness.value = true;
  try {
    const result = await projectApi.deployHarness(projectId.value);
    if (result.error) { showToast(result.error, 'error'); }
    else if (result.pr_url) { showToast(`Created PR: ${result.pr_url}`, 'success'); }
    else { showToast(result.message || 'Deploy completed', 'success'); }
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to deploy harness';
    showToast(message, 'error');
  } finally { isDeployingHarness.value = false; }
}

async function runTeamInProject(teamId: string) {
  teamRunning.value[teamId] = true;
  try {
    const result = await projectApi.runTeamInProject(projectId.value, teamId, { message: teamRunMessages.value[teamId] || undefined });
    showToast(result.message || 'Team execution started', 'success');
    teamRunMessages.value[teamId] = '';
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to run team';
    showToast(message, 'error');
  } finally { teamRunning.value[teamId] = false; }
}

function openSetup(command?: string) {
  setupCommand.value = command || '';
  showSetup.value = true;
}

function onSetupCompleted() {
  showToast('Setup completed successfully', 'success');
  showSetup.value = false;
  loadData();
}


</script>

<template>
  <EntityLayout :load-entity="loadData" entity-label="project">
    <template #default="{ reload: _reload }">
  <div class="project-dashboard">
    <AppBreadcrumb :items="[{ label: 'Projects', action: () => router.push({ name: 'projects' }) }, { label: project?.name || 'Project' }]" />

    <template v-if="project">
      <ProjectStatusCard
        :project="project"
        @navigateToProductDashboard="(id: string) => router.push({ name: 'product-dashboard', params: { productId: id } })"
      />

      <!-- Quick Actions -->
      <div class="actions-row">
        <button class="action-btn secondary" @click="router.push({ name: 'projects' })">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
          All Projects
        </button>
        <button class="action-btn secondary" @click="router.push({ name: 'project-settings', params: { projectId: projectId } })">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
          Edit Project
        </button>
        <button class="action-btn planning-btn" @click="router.push({ name: 'project-planning', params: { projectId: projectId } })">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
          Planning
          <span v-if="grdInitStatus === 'initializing'" class="init-badge init-badge--loading" title="GRD initializing...">...</span>
          <span v-else-if="grdInitStatus === 'ready'" class="init-badge init-badge--ready" title="Planning ready">&#10003;</span>
          <span v-else-if="grdInitStatus === 'failed'" class="init-badge init-badge--failed" title="Initialization failed">!</span>
        </button>
        <button class="action-btn secondary" @click="router.push({ name: 'project-management', params: { projectId: projectId } })">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
          Management
        </button>
        <button v-if="project.github_repo" class="action-btn harness-btn" :disabled="isLoadingHarness || !harnessStatus?.exists" @click="loadHarness">
          <svg v-if="isLoadingHarness" class="spinner-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10" stroke-opacity="0.3"/><path d="M12 2a10 10 0 0 1 10 10"/></svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          {{ isLoadingHarness ? 'Loading...' : 'Load Harness' }}
        </button>
        <button v-if="project.github_repo" class="action-btn primary" :disabled="isDeployingHarness" @click="deployHarness">
          <svg v-if="isDeployingHarness" class="spinner-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10" stroke-opacity="0.3"/><path d="M12 2a10 10 0 0 1 10 10"/></svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
          {{ isDeployingHarness ? 'Deploying...' : 'Deploy Harness' }}
        </button>
        <button v-if="project.github_repo || project.local_path" class="action-btn setup-btn" @click="openSetup()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
          Run Setup
        </button>
      </div>

      <InteractiveSetup v-if="showSetup" :projectId="projectId" :initialCommand="setupCommand" @close="showSetup = false" @completed="onSetupCompleted" />

      <HarnessStatusSection :project="project" :totalTeamCount="totalTeamCount" />

      <ProjectTeamsSection
        :projectId="projectId"
        :allTeams="allTeams"
        :totalTeamCount="totalTeamCount"
        :teamRunMessages="teamRunMessages"
        :teamRunning="teamRunning"
        @runTeam="runTeamInProject"
        @navigateToTeamDashboard="(id: string) => router.push({ name: 'team-dashboard', params: { teamId: id } })"
        @update:teamRunMessages="(v: Record<string, string>) => teamRunMessages = v"
        @refresh="loadData"
      />

      <ProjectTeamCanvas
        v-if="allTeams.length >= 1"
        :projectId="projectId"
        :teams="allTeams"
        class="section-spacing"
        @drill-down="(id: string) => router.push({ name: 'team-dashboard', params: { teamId: id } })"
      />

      <ProjectLibraryTabs
        :projectId="projectId"
        :allAgents="allAgents"
        :projectSkills="projectSkills"
        :allHooks="allHooks"
        :allCommands="allCommands"
        :allRules="allRules"
        :installations="installations"
        :isInstallingComponent="isInstallingComponent"
        @install="installToProject"
        @uninstall="uninstallFromProject"
        @addSkill="showAddSkillModal = true"
        @removeSkill="removeSkill"
        @toggleHook="toggleHookForProject"
        @toggleCommand="toggleCommandForProject"
        @toggleRule="toggleRuleForProject"
      />
    </template>

    <!-- Add Skill Modal -->
    <Teleport to="body">
      <div v-if="showAddSkillModal" ref="addSkillModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-add-skill" tabindex="-1" @click.self="showAddSkillModal = false" @keydown.escape="showAddSkillModal = false">
        <div class="modal">
          <div class="modal-header">
            <h3 id="modal-title-add-skill">Add Skill to Project</h3>
            <button class="modal-close" @click="showAddSkillModal = false">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label for="skill-name">Skill Name *</label>
              <input id="skill-name" v-model="newSkillName" type="text" placeholder="e.g., code-review, test-generator" />
            </div>
            <div class="form-group">
              <label for="skill-path">Skill Path (optional)</label>
              <input id="skill-path" v-model="newSkillPath" type="text" placeholder="e.g., .claude/skills/code-review/SKILL.md" />
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn-secondary" @click="showAddSkillModal = false">Cancel</button>
            <button class="btn-primary" @click="addSkill" :disabled="isAddingSkill || !newSkillName.trim()">
              {{ isAddingSkill ? 'Adding...' : 'Add Skill' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
    </template>
  </EntityLayout>
</template>

<style scoped>
.project-dashboard { display: flex; flex-direction: column; gap: 24px; width: 100%; animation: fadeIn 0.4s ease; }
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}
.actions-row { display: flex; gap: 12px; }
.action-btn { display: flex; align-items: center; gap: 8px; padding: 12px 20px; border-radius: 8px; font-size: 0.9rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.2s; }
.action-btn svg { width: 18px; height: 18px; }
.action-btn.secondary { background: var(--bg-tertiary); color: var(--text-primary); border: 1px solid var(--border-subtle); }
.action-btn.secondary:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.action-btn.primary { background: var(--accent-cyan); color: #000; border: 1px solid var(--accent-cyan); }
.action-btn.primary:hover { background: #00c4ee; border-color: #00c4ee; }
.action-btn.harness-btn { background: var(--accent-violet-dim); color: var(--accent-violet); border: 1px solid transparent; }
.action-btn.harness-btn:hover:not(:disabled) { border-color: var(--accent-violet); }
.action-btn.planning-btn { background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid transparent; }
.action-btn.planning-btn:hover { border-color: #10b981; }
.action-btn.setup-btn { background: var(--accent-amber-dim, rgba(255, 170, 0, 0.15)); color: var(--accent-amber, #ffaa00); border: 1px solid transparent; }
.action-btn.setup-btn:hover:not(:disabled) { border-color: var(--accent-amber, #ffaa00); }
.init-badge { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border-radius: 50%; font-size: 10px; margin-left: 2px; }
.init-badge--loading { background: var(--color-warning, #f59e0b); color: #000; animation: pulse 1.5s ease-in-out infinite; }
.init-badge--ready { background: var(--color-success, #10b981); color: #fff; }
.init-badge--failed { background: var(--color-error, #ef4444); color: #fff; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
.action-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.spinner-icon { animation: spin 1s linear infinite; }
.modal { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 12px; width: 90%; max-width: 450px; max-height: 90vh; display: flex; flex-direction: column; }
.modal-header h3 { margin: 0; font-size: 1rem; color: var(--text-primary); }
.modal-close { width: 28px; height: 28px; background: transparent; border: none; border-radius: 6px; display: flex; align-items: center; justify-content: center; cursor: pointer; color: var(--text-tertiary); transition: all 0.15s; }
.modal-close:hover { background: var(--bg-tertiary); color: var(--text-primary); }
.modal-close svg { width: 16px; height: 16px; }
.form-group input { padding: 10px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 6px; color: var(--text-primary); font-size: 0.9rem; }
.form-group input::placeholder { color: var(--text-tertiary); }
.btn-secondary { padding: 8px 16px; background: var(--bg-tertiary); border: none; border-radius: 6px; color: var(--text-secondary); font-size: 0.9rem; font-weight: 500; cursor: pointer; transition: all 0.15s; }
.btn-secondary:hover { background: var(--bg-elevated); color: var(--text-primary); }
.btn-primary { padding: 8px 16px; background: var(--accent-violet); border: none; border-radius: 6px; color: #fff; font-size: 0.9rem; font-weight: 500; cursor: pointer; transition: all 0.15s; }
.btn-primary:hover:not(:disabled) { background: #9966ff; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
