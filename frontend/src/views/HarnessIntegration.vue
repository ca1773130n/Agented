<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue';
import type {
  Project,
  Team,
  Agent,
  Command,
  Hook,
  UserSkill,
  PluginComponent,
  HarnessConfig,
} from '../services/api';
import {
  projectApi,
  teamApi,
  agentApi,
  commandApi,
  hookApi,
  harnessApi,
  pluginApi,
  ApiError
} from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import HarnessConnectionPanel from '../components/harness/HarnessConnectionPanel.vue';
import HarnessProjectScanner from '../components/harness/HarnessProjectScanner.vue';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';
import { useRouter } from 'vue-router';

const router = useRouter();

const props = defineProps<{
  projectId?: string;
}>();

const showToast = useToast();

// State
const isLoading = ref(true);
const project = ref<Project | null>(null);
const teams = ref<Team[]>([]);
const agents = ref<Agent[]>([]);
const commands = ref<Command[]>([]);
const hooks = ref<Hook[]>([]);
const skills = ref<UserSkill[]>([]);
const scripts = ref<PluginComponent[]>([]);
const harnessConfig = ref<HarnessConfig | null>(null);

// Connection management state
const isLoadingHarness = ref(false);
const isDeployingHarness = ref(false);

useWebMcpTool({
  name: 'agented_harness_integration_get_state',
  description: 'Returns the current state of the Harness Integration page',
  page: 'HarnessIntegration',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'HarnessIntegration',
        projectId: props.projectId ?? null,
        projectName: project.value?.name ?? null,
        teamsCount: teams.value.length,
        agentsCount: agents.value.length,
        commandsCount: commands.value.length,
        hooksCount: hooks.value.length,
        skillsCount: skills.value.length,
        isLoading: isLoading.value,
      }),
    }],
  }),
  deps: [project, teams, agents, commands, hooks, skills, isLoading],
});

// Computed
const hasProject = computed(() => !!props.projectId && !!project.value);
const hasGitHubRepo = computed(() => !!project.value?.github_repo);

// Filter teams: only show UI-created teams in the included section
const includedTeams = computed(() =>
  teams.value.filter(t => t.source === 'ui_created' || !t.source)
);

// GitHub-synced teams are shown separately
const syncedTeams = computed(() =>
  teams.value.filter(t => t.source === 'github_sync')
);

// Load all data
async function loadData() {
  isLoading.value = true;
  try {
    // If project-scoped, load project data
    if (props.projectId) {
      const [projectData, teamsData, commandsData, hooksData] = await Promise.all([
        projectApi.get(props.projectId),
        projectApi.listTeams(props.projectId),
        commandApi.list(props.projectId),
        hookApi.list(props.projectId)
      ]);
      project.value = projectData;
      teams.value = teamsData.teams.map(t => ({ ...t, member_count: 0 })) as Team[];
      commands.value = commandsData.commands;
      hooks.value = hooksData.hooks;

      // Load agents from assigned teams
      const allAgents: Agent[] = [];
      const agentsResponse = await agentApi.list();
      // Filter agents that belong to team members
      for (const team of teams.value) {
        const teamData = await teamApi.get(team.id);
        if (teamData.members) {
          for (const member of teamData.members) {
            if (member.agent_id) {
              const agent = agentsResponse.agents.find(a => a.id === member.agent_id);
              if (agent && !allAgents.find(a => a.id === agent.id)) {
                allAgents.push(agent);
              }
            }
          }
        }
      }
      agents.value = allAgents;
    } else {
      // Global view - load all
      const [teamsData, agentsData, commandsData, hooksData] = await Promise.all([
        teamApi.list(),
        agentApi.list(),
        commandApi.list(),
        hookApi.list()
      ]);
      teams.value = teamsData.teams;
      agents.value = agentsData.agents;
      commands.value = commandsData.commands;
      hooks.value = hooksData.hooks;
    }

    // Load skills and scripts (global)
    const [skillsData, pluginsData] = await Promise.all([
      harnessApi.getSkills(),
      pluginApi.list()
    ]);
    skills.value = skillsData.skills || [];

    // Extract scripts from plugins
    const allScripts: PluginComponent[] = [];
    for (const plugin of pluginsData.plugins) {
      if (plugin.components) {
        for (const comp of plugin.components) {
          if (comp.type === 'script') {
            allScripts.push(comp);
          }
        }
      }
    }
    scripts.value = allScripts;

    // Load harness config
    await refreshConfig();
  } catch {
    showToast('Failed to load harness data', 'error');
  } finally {
    isLoading.value = false;
  }
}

async function refreshConfig() {
  try {
    const configData = await harnessApi.getConfig();
    harnessConfig.value = configData;
  } catch {
    // Silent — config preview is secondary
  }
}

// Load harness from GitHub
async function loadHarness() {
  if (!props.projectId) return;
  isLoadingHarness.value = true;
  try {
    const result = await projectApi.loadHarness(props.projectId);
    if (result.error) {
      showToast(result.error, 'error');
    } else {
      showToast(result.message || 'Harness loaded successfully', 'success');
      await loadData();
    }
  } catch (e) {
    const message = e instanceof ApiError ? e.message : 'Failed to load harness';
    showToast(message, 'error');
  } finally {
    isLoadingHarness.value = false;
  }
}

// Deploy harness to GitHub
async function deployHarness() {
  if (!props.projectId) return;
  isDeployingHarness.value = true;
  try {
    const result = await projectApi.deployHarness(props.projectId);
    if (result.error) {
      showToast(result.error, 'error');
    } else {
      showToast(result.message || 'Harness deployed successfully', 'success');
      if (result.pr_url) {
        showToast(`PR created: ${result.pr_url}`, 'info');
      }
    }
  } catch (e) {
    const message = e instanceof ApiError ? e.message : 'Failed to deploy harness';
    showToast(message, 'error');
  } finally {
    isDeployingHarness.value = false;
  }
}

// Copy config toast notification (clipboard write handled by scanner component)
function onCopyConfig(success: boolean) {
  if (success) {
    showToast('Configuration copied to clipboard', 'success');
  } else {
    showToast('Failed to copy to clipboard', 'error');
  }
}

// Download config (triggered by scanner component)
function onDownloadConfig() {
  if (!harnessConfig.value) return;
  const blob = new Blob([harnessConfig.value.config_json], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = project.value ? `${project.value.name}-harness-config.json` : 'harness-config.json';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast('Configuration downloaded', 'success');
}

// Refresh config when plugins selection changes in the scanner
function onPluginsChanged() {
  refreshConfig();
}

// Watch for project changes
watch(() => props.projectId, () => {
  loadData();
});

// Refresh config when key data sections change
watch(
  [() => teams.value.length, () => agents.value.length, () => commands.value.length, () => hooks.value.length, () => skills.value.length],
  () => {
    refreshConfig();
  }
);

onMounted(() => {
  loadData();
});
</script>

<template>
  <div class="harness-page">
    <AppBreadcrumb :items="[{ label: 'Plugins', action: () => router.push({ name: 'plugins' }) }, { label: 'Harness Integration' }]" />
    <PageHeader
      title="Harness Integration"
      :subtitle="project ? `Configure harness settings for ${project.name}` : 'Build your unified harness configuration for Claude Code'"
    >
      <template v-if="hasProject && hasGitHubRepo" #actions>
        <button
          class="btn"
          @click="loadHarness"
          :disabled="isLoadingHarness"
        >
          <template v-if="isLoadingHarness">
            <div class="spinner-btn"></div>
            Loading...
          </template>
          <template v-else>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
            </svg>
            Load from GitHub
          </template>
        </button>
        <button
          class="btn btn-primary"
          @click="deployHarness"
          :disabled="isDeployingHarness"
        >
          <template v-if="isDeployingHarness">
            <div class="spinner-btn"></div>
            Deploying...
          </template>
          <template v-else>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
              <path d="M14 2v6h6M10 9l-2 2m0 0l2 2m-2-2h8"/>
            </svg>
            Deploy to GitHub
          </template>
        </button>
      </template>
    </PageHeader>

    <!-- Info Banner -->
    <div class="info-banner" v-if="!hasProject">
      <div class="banner-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/>
          <path d="M12 16v-4M12 8h.01"/>
        </svg>
      </div>
      <div class="banner-content">
        <p>
          Select a project to configure its harness settings, or view the global configuration below.
        </p>
      </div>
    </div>

    <!-- GitHub workflow steps (connection management) -->
    <HarnessConnectionPanel
      v-if="hasProject && hasGitHubRepo"
      :included-teams-count="includedTeams.length"
    />

    <LoadingState v-if="isLoading" message="Loading harness configuration..." />

    <!-- Project data sections (teams, agents, commands, hooks, skills, plugins, scripts, config) -->
    <HarnessProjectScanner
      v-else
      :included-teams="includedTeams"
      :synced-teams="syncedTeams"
      :agents="agents"
      :commands="commands"
      :hooks="hooks"
      :skills="skills"
      :scripts="scripts"
      :harness-config="harnessConfig"
      @plugins-changed="onPluginsChanged"
      @copy-config="(success) => onCopyConfig(success)"
      @download-config="onDownloadConfig"
    />
  </div>
</template>

<style scoped>
.harness-page {
}

.info-banner {
  display: flex;
  gap: 16px;
  padding: 16px 20px;
  background: var(--accent-cyan-dim);
  border: 1px solid rgba(0, 212, 255, 0.3);
  border-radius: 10px;
  margin-bottom: 24px;
}

.banner-icon {
  flex-shrink: 0;
  color: var(--accent-cyan);
}

.banner-icon svg {
  width: 24px;
  height: 24px;
}

.banner-content p {
  margin: 0;
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.5;
}

/* Button spinner */
.spinner-btn {
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
