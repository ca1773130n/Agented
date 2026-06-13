<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import type { Project, HarnessStatusResult, ProjectSkill, Hook, Command, Rule, Agent, TeamMember, ProjectInstallation, SuperAgent, SuperAgentSession, ProjectSAInstance, SuperAgentActivityStatus, GrdHarnessSetupStep } from '../services/api';
import { projectApi, grdApi, hookApi, commandApi, ruleApi, agentApi, teamApi, superAgentApi, superAgentSessionApi, projectInstanceApi, ApiError } from '../services/api';
import EntityLayout from '../layouts/EntityLayout.vue';
import InteractiveSetup from '../components/projects/InteractiveSetup.vue';
import ProjectStatusCard from '../components/projects/ProjectStatusCard.vue';
import ProjectTeamLeaderChat from '../components/projects/ProjectTeamLeaderChat.vue';
import ProjectTeamsSection from '../components/projects/ProjectTeamsSection.vue';
import ProjectTeamCanvas from '../components/projects/ProjectTeamCanvas.vue';
import ProjectLibraryTabs from '../components/projects/ProjectLibraryTabs.vue';
import ProjectForgeBindingsPanel from '../components/project/ProjectForgeBindingsPanel.vue';
import HarnessStatusSection from '../components/projects/HarnessStatusSection.vue';
import { useToast } from '../composables/useToast';
import { useFocusTrap } from '../composables/useFocusTrap';
import { useWebMcpTool } from '../composables/useWebMcpTool';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();

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

// Project instances state
const projectInstances = ref<ProjectSAInstance[]>([]);
const isLoadingInstances = ref(false);

// Active sessions state
interface SessionInfo {
  session: SuperAgentSession;
  superAgent: SuperAgent;
}
interface GroupedSessions {
  superAgent: SuperAgent;
  sessions: SuperAgentSession[];
  instanceId?: string;
}
const activeSessions = ref<SessionInfo[]>([]);
const isLoadingSessions = ref(false);

const groupedSessions = computed<GroupedSessions[]>(() => {
  const groups = new Map<string, GroupedSessions>();
  for (const info of activeSessions.value) {
    const key = info.superAgent.id;
    if (!groups.has(key)) {
      const inst = projectInstances.value.find(i => i.template_sa_id === info.superAgent.id);
      groups.set(key, { superAgent: info.superAgent, sessions: [], instanceId: inst?.id });
    }
    groups.get(key)!.sessions.push(info.session);
  }
  return [...groups.values()];
});

// GRD init status
const grdInitStatus = ref<string>('none');
let initPollInterval: ReturnType<typeof setInterval> | null = null;

// v0.8.0 — one-click team harness setup (REQ-19 / SC1). Mirrors the
// grdInit wiring: a status string drives a button + chip, and step
// progress streams in over an EventSource into a step panel.
const harnessSetupStatus = ref<string>('none');
const harnessSetupSteps = ref<GrdHarnessSetupStep[]>([]);
let harnessSetupEventSource: { close: () => void } | null = null;

// SA activity-status snapshot, keyed by ``super_agent_id``. Powers the
// "working now" badge on each session card so the user can see at a
// glance which SAs are currently producing a response vs. just sitting
// on a long-lived session. Polled every 7s — same cadence as the SA
// list page so a backend-driven activity update lands within one tick
// of the next nearest poll regardless of which page the user opened.
const saActivityStatus = ref<Record<string, SuperAgentActivityStatus>>({});
let activityPollInterval: ReturnType<typeof setInterval> | null = null;
async function loadSaActivityStatus() {
  try {
    const data = await superAgentApi.activityStatus();
    saActivityStatus.value = data.statuses || {};
  } catch {
    // Silent — no toast for transient activity-status failures.
  }
}
function isSaWorking(saId: string): boolean {
  return Boolean(saActivityStatus.value[saId]?.is_streaming);
}

// Interactive Setup state
const showSetup = ref(false);
const setupCommand = ref('');

// Team member data (fetched separately for OrgCanvas)
const teamMembersMap = ref<Record<string, TeamMember[]>>({});

// Compute all teams including owner team with "is_owner" flag and members
const allTeams = computed(() => {
  if (!project.value) return [];
  const teams: { id: string; name: string; color: string; is_owner: boolean; members?: TeamMember[] }[] = [];
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
        instancesCount: projectInstances.value.length,
        showSetup: showSetup.value,
        harnessStatus: harnessStatus.value ? 'loaded' : null,
      }),
    }],
  }),
  deps: [project, isLoadingHarness, isDeployingHarness, totalTeamCount, projectSkills, installations, projectInstances, showSetup, harnessStatus],
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
    const membersMap: Record<string, TeamMember[]> = {};
    for (const td of teamDetails) {
      if (td) membersMap[td.id] = td.members || [];
    }
    teamMembersMap.value = membersMap;
  }

  if (project.value?.github_repo) await checkHarnessStatus();
  // Fire and forget library items load (non-critical)
  loadLibraryItems();
  loadGrdStatus();
  loadHarnessSetupStatus();
  loadActiveSessions();
  loadSaActivityStatus();
  activityPollInterval = setInterval(loadSaActivityStatus, 7000);
  loadProjectInstances();
  return project.value;
}

async function loadActiveSessions() {
  isLoadingSessions.value = true;
  try {
    // Collect all super agents from team members
    const teamIds: string[] = [];
    if (project.value?.owner_team_id) teamIds.push(project.value.owner_team_id);
    if (project.value?.teams) {
      for (const t of project.value.teams) {
        if (!teamIds.includes(t.id)) teamIds.push(t.id);
      }
    }
    // Fetch super agents that belong to these teams
    const saData = await superAgentApi.list();
    const teamSuperAgents = (saData.super_agents || []).filter(
      sa => sa.team_id && teamIds.includes(sa.team_id)
    );
    // Fetch sessions for all super agents in parallel
    const sessionInfos: SessionInfo[] = [];
    const results = await Promise.allSettled(
      teamSuperAgents.map(sa => superAgentSessionApi.list(sa.id))
    );
    for (let i = 0; i < teamSuperAgents.length; i++) {
      const result = results[i];
      if (result.status === 'fulfilled') {
        for (const sess of (result.value.sessions || [])) {
          if (sess.status === 'active') {
            sessionInfos.push({ session: sess, superAgent: teamSuperAgents[i] });
          }
        }
      }
    }
    activeSessions.value = sessionInfos;
  } catch { activeSessions.value = []; }
  finally { isLoadingSessions.value = false; }
}

async function loadProjectInstances() {
  isLoadingInstances.value = true;
  try {
    const data = await projectInstanceApi.list(projectId.value);
    projectInstances.value = data.instances || [];
  } catch {
    projectInstances.value = [];
  } finally {
    isLoadingInstances.value = false;
  }
}

function navToInstancePlayground(instanceId: string) {
  router.push({
    name: 'project-instance-playground',
    params: { projectId: projectId.value, instanceId },
  });
}

function openChat(superAgentId: string, sessionId: string, instanceId?: string) {
  if (instanceId) {
    router.push({
      name: 'project-instance-playground',
      params: { projectId: projectId.value, instanceId },
      query: { session: sessionId },
    });
  } else {
    router.push({
      name: 'super-agent-playground',
      params: { superAgentId },
      query: { session: sessionId },
    });
  }
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

async function loadHarnessSetupStatus() {
  if (!projectId.value) return;
  try {
    const result = await grdApi.getHarnessSetupStatus(projectId.value);
    harnessSetupStatus.value = result.harness_setup_status;
    harnessSetupSteps.value = result.steps || [];
    if (harnessSetupStatus.value === 'running' && !harnessSetupEventSource) {
      openHarnessSetupStream();
    }
  } catch {
    harnessSetupStatus.value = 'none';
  }
}

// The backend emits NAMED SSE events (`event: step` / `event: done` /
// `event: timeout`). The custom AuthenticatedEventSource only routes named
// events through addEventListener — `onmessage` fires for default/`message`
// frames only — so these must be subscribed by name (matching every other
// SSE consumer in this app, e.g. InteractiveSetup/LiveExecutionTerminal).
function onHarnessStepFrame(event: MessageEvent) {
  try {
    const payload = JSON.parse(event.data) as { step: string; status: string; detail?: string | null };
    const idx = harnessSetupSteps.value.findIndex((s) => s.step_key === payload.step);
    const row: GrdHarnessSetupStep = {
      step_key: payload.step,
      status: payload.status,
      detail: payload.detail ?? null,
    };
    if (idx >= 0) harnessSetupSteps.value.splice(idx, 1, row);
    else harnessSetupSteps.value.push(row);
  } catch {
    // Ignore malformed frames.
  }
}

function onHarnessDoneFrame(event: MessageEvent) {
  let status = '';
  try {
    status = (JSON.parse(event.data) as { status?: string }).status ?? '';
  } catch {
    // Fall through to re-fetch the authoritative status below.
  }
  if (status) harnessSetupStatus.value = status;
  closeHarnessSetupStream();
  loadHarnessSetupStatus();
  if (status === 'ready') {
    showToast(t('harnessSetup.toastReady'), 'success');
  } else if (status === 'failed') {
    showToast(t('harnessSetup.toastFailed'), 'error');
  }
}

function openHarnessSetupStream() {
  if (!projectId.value || harnessSetupEventSource) return;
  const es = grdApi.streamHarnessSetup(projectId.value);
  es.addEventListener('step', onHarnessStepFrame);
  es.addEventListener('done', onHarnessDoneFrame);
  // A max-duration timeout frame carries no terminal status — just stop the
  // stream and re-fetch the authoritative status from the DB.
  es.addEventListener('timeout', () => {
    closeHarnessSetupStream();
    loadHarnessSetupStatus();
  });
  es.onerror = () => {
    closeHarnessSetupStream();
  };
  harnessSetupEventSource = es;
}

function closeHarnessSetupStream() {
  if (harnessSetupEventSource) {
    harnessSetupEventSource.close();
    harnessSetupEventSource = null;
  }
}

async function triggerHarnessSetup() {
  if (!projectId.value) return;
  try {
    harnessSetupSteps.value = [];
    const result = await grdApi.triggerHarnessSetup(projectId.value);
    harnessSetupStatus.value = result.harness_setup_status;
    openHarnessSetupStream();
  } catch {
    harnessSetupStatus.value = 'failed';
    showToast(t('harnessSetup.toastFailed'), 'error');
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
    showToast(t('projectDashboard.grdInitSuccess'), 'success');
  } else if (oldVal === 'initializing' && newVal === 'failed') {
    showToast(t('projectDashboard.grdInitFailed'), 'error');
  }
});

onUnmounted(() => {
  if (initPollInterval) clearInterval(initPollInterval);
  if (activityPollInterval) clearInterval(activityPollInterval);
  closeHarnessSetupStream();
});

async function addSkill() {
  if (!newSkillName.value.trim()) { showToast(t('projectDashboard.skillNameRequired'), 'error'); return; }
  isAddingSkill.value = true;
  try {
    await projectApi.addSkill(projectId.value, {
      skill_name: newSkillName.value.trim(),
      skill_path: newSkillPath.value.trim() || undefined,
      source: 'manual',
    });
    showToast(t('projectDashboard.skillAdded'), 'success');
    showAddSkillModal.value = false;
    newSkillName.value = '';
    newSkillPath.value = '';
    const skillsData = await projectApi.listSkills(projectId.value);
    projectSkills.value = skillsData.skills || [];
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('projectDashboard.addSkillError');
    showToast(message, 'error');
  } finally {
    isAddingSkill.value = false;
  }
}

async function removeSkill(skill: ProjectSkill) {
  try {
    await projectApi.removeSkill(projectId.value, skill.id);
    showToast(t('projectDashboard.skillRemoved'), 'success');
    projectSkills.value = projectSkills.value.filter(s => s.id !== skill.id);
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('projectDashboard.removeSkillError');
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
    showToast(t('projectDashboard.loadLibraryError'), 'error');
  } finally {
    isLoadingLibrary.value = false;
  }
}

async function toggleHookForProject(hook: Hook) {
  try {
    const newProjectId = hook.project_id === projectId.value ? undefined : projectId.value;
    await hookApi.update(hook.id, { project_id: newProjectId });
    await loadLibraryItems();
    showToast(newProjectId ? t('projectDashboard.hookAdded') : t('projectDashboard.hookRemoved'), 'success');
  } catch (err) { showToast(t('projectDashboard.updateHookError'), 'error'); }
}

async function toggleCommandForProject(command: Command) {
  try {
    const newProjectId = command.project_id === projectId.value ? undefined : projectId.value;
    await commandApi.update(command.id, { project_id: newProjectId });
    await loadLibraryItems();
    showToast(newProjectId ? t('projectDashboard.commandAdded') : t('projectDashboard.commandRemoved'), 'success');
  } catch (err) { showToast(t('projectDashboard.updateCommandError'), 'error'); }
}

async function toggleRuleForProject(rule: Rule) {
  try {
    const newProjectId = rule.project_id === projectId.value ? undefined : projectId.value;
    await ruleApi.update(rule.id, { project_id: newProjectId });
    await loadLibraryItems();
    showToast(newProjectId ? t('projectDashboard.ruleAdded') : t('projectDashboard.ruleRemoved'), 'success');
  } catch (err) { showToast(t('projectDashboard.updateRuleError'), 'error'); }
}

async function installToProject(componentType: string, componentId: string, componentName: string) {
  const key = `${componentType}-${componentId}`;
  isInstallingComponent.value[key] = true;
  try {
    const result = await projectApi.installComponent(projectId.value, { component_type: componentType, component_id: componentId });
    if (result.installed) {
      showToast(t('projectDashboard.installed', { name: componentName }), 'success');
      const data = await projectApi.listInstallations(projectId.value);
      installations.value = data.installations || [];
    } else if (result.error) { showToast(result.error, 'error'); }
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('projectDashboard.installError', { name: componentName });
    showToast(message, 'error');
  } finally { isInstallingComponent.value[key] = false; }
}

async function uninstallFromProject(componentType: string, componentId: string, componentName: string) {
  const key = `${componentType}-${componentId}`;
  isInstallingComponent.value[key] = true;
  try {
    const result = await projectApi.uninstallComponent(projectId.value, { component_type: componentType, component_id: componentId });
    if (result.uninstalled) {
      showToast(t('projectDashboard.uninstalled', { name: componentName }), 'success');
      const data = await projectApi.listInstallations(projectId.value);
      installations.value = data.installations || [];
    } else if (result.error) { showToast(result.error, 'error'); }
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('projectDashboard.uninstallError', { name: componentName });
    showToast(message, 'error');
  } finally { isInstallingComponent.value[key] = false; }
}

async function checkHarnessStatus() {
  try { harnessStatus.value = await projectApi.getHarnessStatus(projectId.value); }
  catch { harnessStatus.value = null; }
}

async function loadHarness() {
  if (!project.value?.github_repo) { showToast(t('projectDashboard.noGithubRepo'), 'error'); return; }
  isLoadingHarness.value = true;
  try {
    const result = await projectApi.loadHarness(projectId.value);
    if (result.error) { showToast(result.error, 'error'); }
    else {
      const counts = result.counts || {};
      const summary = Object.entries(counts).filter(([, v]) => v > 0).map(([k, v]) => `${v} ${k}`).join(', ');
      showToast(t('projectDashboard.harnessLoaded', { summary: summary || t('projectDashboard.noItems') }), 'success');
    }
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('projectDashboard.loadHarnessError');
    showToast(message, 'error');
  } finally { isLoadingHarness.value = false; }
}

async function deployHarness() {
  if (!project.value?.github_repo) { showToast(t('projectDashboard.noGithubRepo'), 'error'); return; }
  isDeployingHarness.value = true;
  try {
    const result = await projectApi.deployHarness(projectId.value);
    if (result.error) { showToast(result.error, 'error'); }
    else if (result.pr_url) { showToast(t('projectDashboard.prCreated', { url: result.pr_url }), 'success'); }
    else { showToast(result.message || t('projectDashboard.deployCompleted'), 'success'); }
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('projectDashboard.deployHarnessError');
    showToast(message, 'error');
  } finally { isDeployingHarness.value = false; }
}

async function runTeamInProject(teamId: string) {
  teamRunning.value[teamId] = true;
  try {
    const result = await projectApi.runTeamInProject(projectId.value, teamId, { message: teamRunMessages.value[teamId] || undefined });
    showToast(result.message || t('projectDashboard.teamStarted'), 'success');
    teamRunMessages.value[teamId] = '';
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('projectDashboard.runTeamError');
    showToast(message, 'error');
  } finally { teamRunning.value[teamId] = false; }
}

function openSetup(command?: string) {
  setupCommand.value = command || '';
  showSetup.value = true;
}

function onSetupCompleted() {
  showToast(t('projectDashboard.setupCompleted'), 'success');
  showSetup.value = false;
  loadData();
}


</script>

<template>
  <EntityLayout :load-entity="loadData" entity-label="project">
    <template #default="{ reload: _reload }">
  <div class="project-dashboard">

    <template v-if="project">
      <ProjectStatusCard
        :project="project"
        @navigateToProductDashboard="(id: string) => router.push({ name: 'product-dashboard', params: { productId: id } })"
      />

      <!-- Quick Actions -->
      <div class="actions-row">
        <button class="action-btn secondary" @click="router.push({ name: 'projects' })">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
          {{ t('projectDashboard.allProjects') }}
        </button>
        <button class="action-btn secondary" @click="router.push({ name: 'project-settings', params: { projectId: projectId } })">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
          {{ t('projectDashboard.editProject') }}
        </button>
        <button class="action-btn planning-btn" @click="router.push({ name: 'project-planning', params: { projectId: projectId } })">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
          {{ t('projectDashboard.planning') }}
          <span v-if="grdInitStatus === 'initializing'" class="init-badge init-badge--loading" :title="t('projectDashboard.grdInitializing')">...</span>
          <span v-else-if="grdInitStatus === 'ready'" class="init-badge init-badge--ready" :title="t('projectDashboard.planningReady')">&#10003;</span>
          <span v-else-if="grdInitStatus === 'failed'" class="init-badge init-badge--failed" :title="t('projectDashboard.initFailed')">!</span>
        </button>
        <button class="action-btn secondary" @click="router.push({ name: 'project-management', params: { projectId: projectId } })">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
          {{ t('projectDashboard.management') }}
        </button>
        <button v-if="project.github_repo" class="action-btn harness-btn" :disabled="isLoadingHarness || !harnessStatus?.exists" @click="loadHarness">
          <svg v-if="isLoadingHarness" class="spinner-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10" stroke-opacity="0.3"/><path d="M12 2a10 10 0 0 1 10 10"/></svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          {{ isLoadingHarness ? t('projectDashboard.loadingShort') : t('projectDashboard.loadHarness') }}
        </button>
        <button v-if="project.github_repo" class="action-btn primary" :disabled="isDeployingHarness" @click="deployHarness">
          <svg v-if="isDeployingHarness" class="spinner-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10" stroke-opacity="0.3"/><path d="M12 2a10 10 0 0 1 10 10"/></svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
          {{ isDeployingHarness ? t('projectDashboard.deploying') : t('projectDashboard.deployHarness') }}
        </button>
        <button v-if="project.github_repo || project.local_path" class="action-btn setup-btn" @click="openSetup()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
          {{ t('projectDashboard.runSetup') }}
        </button>
        <!-- v0.8.0 — one-click team harness setup (REQ-19 / SC1) -->
        <button
          v-if="harnessSetupStatus === 'none' || harnessSetupStatus === 'failed'"
          class="action-btn harness-setup-btn"
          data-testid="harness-setup-btn"
          @click="triggerHarnessSetup()"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
          {{ harnessSetupStatus === 'failed' ? t('harnessSetup.retry') : t('harnessSetup.setupButton') }}
        </button>
        <span
          v-if="harnessSetupStatus === 'running'"
          class="harness-setup-chip harness-setup-chip--running"
          data-testid="harness-setup-chip"
        >{{ t('harnessSetup.chipRunning') }}</span>
        <span
          v-else-if="harnessSetupStatus === 'ready'"
          class="harness-setup-chip harness-setup-chip--ready"
          data-testid="harness-setup-chip"
        >{{ t('harnessSetup.chipReady') }}</span>
        <span
          v-else-if="harnessSetupStatus === 'failed'"
          class="harness-setup-chip harness-setup-chip--failed"
          data-testid="harness-setup-chip"
        >{{ t('harnessSetup.chipFailed') }}</span>
      </div>

      <!-- v0.8.0 — harness-setup step progress panel -->
      <div
        v-if="harnessSetupSteps.length > 0"
        class="harness-setup-panel"
        data-testid="harness-setup-panel"
      >
        <h4 class="harness-setup-panel__title">{{ t('harnessSetup.panelTitle') }}</h4>
        <ul class="harness-setup-panel__steps">
          <li
            v-for="step in harnessSetupSteps"
            :key="step.step_key"
            class="harness-setup-step"
            :class="`harness-setup-step--${step.status}`"
            data-testid="harness-setup-step"
          >
            <span class="harness-setup-step__key">{{ t(`harnessSetup.step.${step.step_key}`) }}</span>
            <span class="harness-setup-step__status">{{ t(`harnessSetup.stepStatus.${step.status}`) }}</span>
            <span v-if="step.detail" class="harness-setup-step__detail">{{ step.detail }}</span>
          </li>
        </ul>
      </div>

      <InteractiveSetup v-if="showSetup" :projectId="projectId" :initialCommand="setupCommand" @close="showSetup = false" @completed="onSetupCompleted" />

      <HarnessStatusSection :project="project" :totalTeamCount="totalTeamCount" />

      <ProjectTeamLeaderChat
        v-if="projectId && project?.manager_super_agent_id"
        :projectId="projectId"
      />

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

      <!-- Project Instances (Active Agents) -->
      <div v-if="projectInstances.length > 0 || isLoadingInstances" class="card instances-card">
        <div class="card-header-sessions">
          <h3>{{ t('projectDashboard.activeAgents') }}</h3>
          <span class="card-count">{{ t('projectDashboard.instanceCount', { count: projectInstances.length }) }}</span>
        </div>
        <div v-if="isLoadingInstances" class="sessions-loading">{{ t('projectDashboard.loadingInstances') }}</div>
        <div v-else-if="projectInstances.length === 0" class="sessions-empty">{{ t('projectDashboard.noInstances') }}</div>
        <div v-else class="instance-cards">
          <div v-for="inst in projectInstances" :key="inst.id" class="instance-card">
            <div class="instance-card-header">
              <span class="instance-agent-name">{{ inst.sa_name || inst.template_sa_id }}</span>
              <span class="instance-backend-badge">{{ inst.sa_backend_type || 'auto' }}</span>
            </div>
            <div class="instance-card-meta">
              <span class="instance-id-label">{{ inst.id }}</span>
              <span v-if="inst.worktree_path" class="instance-worktree" :title="t('projectDashboard.worktreePath')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>
                {{ t('projectDashboard.worktreeActive') }}
              </span>
              <span class="instance-mode-label">{{ t('projectDashboard.defaultMode', { mode: inst.default_chat_mode }) }}</span>
            </div>
            <button class="action-btn instance-chat-btn" @click="navToInstancePlayground(inst.id)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
              {{ t('projectDashboard.chat') }}
            </button>
          </div>
        </div>
      </div>

      <!-- Active Sessions (grouped by Super Agent) -->
      <div v-if="activeSessions.length > 0 || isLoadingSessions" class="card sessions-card">
        <div class="card-header-sessions">
          <h3>{{ t('projectDashboard.activeSessions') }}</h3>
          <span class="card-count">{{ t('projectDashboard.activeCount', { count: activeSessions.length }) }}</span>
        </div>
        <div v-if="isLoadingSessions" class="sessions-loading">{{ t('projectDashboard.loadingSessions') }}</div>
        <div v-else-if="groupedSessions.length === 0" class="sessions-empty">{{ t('projectDashboard.noActiveSessions') }}</div>
        <div v-else class="session-groups">
          <div v-for="group in groupedSessions" :key="group.superAgent.id" class="session-group">
            <div class="session-group-header">
              <span class="session-agent-name">{{ group.superAgent.name }}</span>
              <span
                v-if="isSaWorking(group.superAgent.id)"
                class="sa-working-pill"
                :title="t('projectDashboard.workingTooltip')"
              >
                <span class="sa-working-pill__dot" />
                {{ t('projectDashboard.working') }}
              </span>
              <span class="session-group-count">{{ t('projectDashboard.sessionCount', { count: group.sessions.length }) }}</span>
            </div>
            <div class="session-group-items">
              <div v-for="sess in group.sessions" :key="sess.id" class="session-card">
                <div class="session-card-meta">
                  <span class="session-id-label">{{ sess.id }}</span>
                  <span class="session-status-badge active">{{ t('projectDashboard.active') }}</span>
                  <span v-if="sess.started_at" class="session-time">{{ new Date(sess.started_at).toLocaleString() }}</span>
                </div>
                <button class="action-btn session-chat-btn" @click="openChat(group.superAgent.id, sess.id, group.instanceId)">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
                  {{ t('projectDashboard.chat') }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

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

      <!-- v0.7.70 — Forge context bindings surfaced on the dashboard
           too (not just settings) so the operator can see what's
           inherited into sessions without leaving the project's
           landing page. -->
      <div class="card forge-bindings-card">
        <div class="card-header-sessions">
          <h3>{{ t('projectDashboard.forgeBindings') }}</h3>
        </div>
        <div class="card-body-padded">
          <ProjectForgeBindingsPanel :projectId="projectId" />
        </div>
      </div>
    </template>

    <!-- Add Skill Modal -->
    <Teleport to="body">
      <div v-if="showAddSkillModal" ref="addSkillModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-add-skill" tabindex="-1" @click.self="showAddSkillModal = false" @keydown.escape="showAddSkillModal = false">
        <div class="modal">
          <div class="modal-header">
            <h3 id="modal-title-add-skill">{{ t('projectDashboard.addSkillTitle') }}</h3>
            <button class="modal-close" @click="showAddSkillModal = false">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label for="skill-name">{{ t('projectDashboard.skillNameLabel') }}</label>
              <input id="skill-name" v-model="newSkillName" type="text" :placeholder="t('projectDashboard.skillNamePlaceholder')" />
            </div>
            <div class="form-group">
              <label for="skill-path">{{ t('projectDashboard.skillPathLabel') }}</label>
              <input id="skill-path" v-model="newSkillPath" type="text" :placeholder="t('projectDashboard.skillPathPlaceholder')" />
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn-secondary" @click="showAddSkillModal = false">{{ t('common.cancel') }}</button>
            <button class="btn-primary" @click="addSkill" :disabled="isAddingSkill || !newSkillName.trim()">
              {{ isAddingSkill ? t('projectDashboard.adding') : t('projectDashboard.addSkill') }}
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
.action-btn.setup-btn { background: var(--accent-cyan-dim, rgba(0, 212, 255, 0.15)); color: var(--accent-cyan, #00d4ff); border: 1px solid transparent; }
.action-btn.setup-btn:hover:not(:disabled) { border-color: var(--accent-cyan, #00d4ff); }
.action-btn.harness-setup-btn { background: var(--accent-purple-dim, rgba(168, 85, 247, 0.15)); color: var(--accent-purple, #a855f7); border: 1px solid transparent; }
.action-btn.harness-setup-btn:hover:not(:disabled) { border-color: var(--accent-purple, #a855f7); }
.harness-setup-chip { display: inline-flex; align-items: center; padding: 2px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; }
.harness-setup-chip--running { background: rgba(0, 212, 255, 0.15); color: var(--accent-cyan, #00d4ff); }
.harness-setup-chip--ready { background: rgba(34, 197, 94, 0.15); color: var(--accent-green, #22c55e); }
.harness-setup-chip--failed { background: rgba(239, 68, 68, 0.15); color: var(--accent-red, #ef4444); }
.harness-setup-panel { margin-top: 12px; padding: 12px; border: 1px solid var(--border, rgba(255, 255, 255, 0.1)); border-radius: 8px; }
.harness-setup-panel__title { margin: 0 0 8px; font-size: 0.85rem; color: var(--text-muted, #888); }
.harness-setup-panel__steps { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.harness-setup-step { display: flex; gap: 12px; align-items: baseline; font-size: 0.85rem; }
.harness-setup-step__key { min-width: 160px; font-weight: 600; }
.harness-setup-step--ok .harness-setup-step__status { color: var(--accent-green, #22c55e); }
.harness-setup-step--failed .harness-setup-step__status { color: var(--accent-red, #ef4444); }
.harness-setup-step--skipped .harness-setup-step__status { color: var(--text-muted, #888); }
.harness-setup-step__detail { color: var(--text-muted, #888); }
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
/* Instances Section */
.instances-card { padding: 0; }
.instance-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; padding: 16px 20px; }
.instance-card { background: var(--bg-tertiary); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 14px 16px; display: flex; flex-direction: column; gap: 8px; }
.instance-card-header { display: flex; align-items: center; justify-content: space-between; }
.instance-agent-name { font-weight: 600; font-size: 0.9rem; color: var(--text-primary); }
.instance-backend-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.65rem; font-weight: 700; text-transform: uppercase; background: var(--accent-violet-dim, rgba(136, 85, 255, 0.15)); color: var(--accent-violet, #8855ff); }
.instance-card-meta { display: flex; flex-direction: column; gap: 2px; }
.instance-id-label { font-family: var(--font-mono); font-size: 0.7rem; color: var(--text-muted); }
.instance-worktree { display: flex; align-items: center; gap: 4px; font-size: 0.75rem; color: var(--accent-emerald, #00ff88); }
.instance-mode-label { font-size: 0.75rem; color: var(--text-tertiary); }
.instance-chat-btn { background: var(--accent-cyan-dim, rgba(0, 212, 255, 0.15)); color: var(--accent-cyan, #00d4ff); border: 1px solid transparent; padding: 8px 14px; font-size: 0.85rem; }
.instance-chat-btn:hover { border-color: var(--accent-cyan, #00d4ff); }
/* Sessions Section */
.sessions-card { padding: 0; }
/* v0.7.70 — Forge bindings card; same chrome as sessions-card so
   the heading sits at the top with a separator and the body has
   real breathing room. */
.forge-bindings-card { padding: 0; margin-top: 16px; }
.card-body-padded { padding: 16px 20px; }
.card-header-sessions { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid var(--border-subtle); }
.card-header-sessions h3 { font-size: 0.95rem; font-weight: 600; color: var(--text-primary); margin: 0; }
.card-count { font-size: 0.75rem; color: var(--text-tertiary); background: var(--bg-tertiary); padding: 4px 8px; border-radius: 4px; }
.sessions-loading, .sessions-empty { padding: 24px; text-align: center; color: var(--text-muted); font-size: 0.85rem; }
.session-groups { padding: 12px 20px; display: flex; flex-direction: column; gap: 16px; }
.session-group { border: 1px solid var(--border-subtle); border-radius: 8px; overflow: hidden; }
.session-group-header { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px; background: var(--bg-tertiary); border-bottom: 1px solid var(--border-subtle); gap: 8px; }
.session-agent-name { font-weight: 600; font-size: 0.9rem; color: var(--text-primary); }

/* "Working" pill on a session group when the SA is actively
   streaming a response right now. The dot pulses so it's visually
   distinct from the static session-status-badge. */
.sa-working-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
  background: rgba(245, 158, 11, 0.18);
  color: var(--accent-amber, #f59e0b);
  margin-right: auto;
}
.sa-working-pill__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 6px currentColor;
  animation: sa-working-pulse 1.4s ease-in-out infinite;
}
@keyframes sa-working-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}
.session-group-count { font-size: 0.7rem; color: var(--text-tertiary); }
.session-group-items { display: flex; flex-direction: column; }
.session-card { padding: 10px 16px; display: flex; align-items: center; justify-content: space-between; gap: 12px; border-bottom: 1px solid var(--border-subtle); }
.session-card:last-child { border-bottom: none; }
.session-card-meta { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0; }
.session-id-label { font-family: var(--font-mono); font-size: 0.7rem; color: var(--text-muted); }
.session-status-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.65rem; font-weight: 700; text-transform: uppercase; flex-shrink: 0; }
.session-status-badge.active { background: var(--accent-emerald-dim); color: var(--accent-emerald); }
.session-time { font-size: 0.75rem; color: var(--text-tertiary); }
.session-chat-btn { background: var(--accent-violet-dim); color: var(--accent-violet); border: 1px solid transparent; padding: 6px 12px; font-size: 0.8rem; flex-shrink: 0; }
.session-chat-btn:hover { border-color: var(--accent-violet); }
.slide-over-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid var(--border-subtle); }
.slide-over-header h3 { margin: 0; font-size: 1rem; color: var(--text-primary); }
.slide-over-body { padding: 20px; flex: 1; overflow-y: auto; }
.slide-over-info { font-size: 0.85rem; color: var(--text-secondary); margin: 0 0 8px; }
.slide-over-info code { font-family: var(--font-mono); font-size: 0.8rem; background: var(--bg-tertiary); padding: 2px 6px; border-radius: 4px; }
.slide-over-hint { font-size: 0.85rem; color: var(--text-tertiary); margin-top: 16px; }
.slide-over-hint a { color: var(--accent-cyan); text-decoration: none; }
.slide-over-hint a:hover { text-decoration: underline; }
</style>
