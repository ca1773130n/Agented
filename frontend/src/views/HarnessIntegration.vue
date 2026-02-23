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
  MarketplaceSearchResult
} from '../services/api';
import {
  projectApi,
  teamApi,
  agentApi,
  commandApi,
  hookApi,
  harnessApi,
  pluginApi,
  marketplaceApi,
  ApiError
} from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
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

// UI State
const copied = ref(false);
const isLoadingHarness = ref(false);
const isDeployingHarness = ref(false);
const expandedSections = ref<Record<string, boolean>>({
  teams: true,
  agents: true,
  commands: true,
  hooks: true,
  skills: true,
  plugins: true,
  scripts: false
});

// Plugin search state
const pluginSearchQuery = ref('');
const pluginSearchResults = ref<MarketplaceSearchResult[]>([]);
const isSearchingPlugins = ref(false);
const selectedPlugins = ref<MarketplaceSearchResult[]>([]);
const showPluginDropdown = ref(false);
let pluginDebounceTimer: ReturnType<typeof setTimeout>;

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
        expandedSections: expandedSections.value,
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
  } catch (e) {
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

// Toggle section
function toggleSection(section: string) {
  expandedSections.value[section] = !expandedSections.value[section];
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

// Plugin search
function onPluginSearchInput() {
  const q = pluginSearchQuery.value.trim();
  clearTimeout(pluginDebounceTimer);
  pluginDebounceTimer = setTimeout(async () => {
    if (q.length >= 2 || q.length === 0) {
      isSearchingPlugins.value = true;
      try {
        const response = await marketplaceApi.search(q, 'plugin');
        // Filter out already selected plugins
        const selectedNames = new Set(selectedPlugins.value.map(p => `${p.marketplace_id}-${p.name}`));
        pluginSearchResults.value = response.results.filter(
          r => !selectedNames.has(`${r.marketplace_id}-${r.name}`)
        );
        showPluginDropdown.value = true;
      } catch (e) {
        pluginSearchResults.value = [];
      } finally {
        isSearchingPlugins.value = false;
      }
    }
  }, 300);
}

function selectPlugin(plugin: MarketplaceSearchResult) {
  selectedPlugins.value.push(plugin);
  pluginSearchQuery.value = '';
  pluginSearchResults.value = [];
  showPluginDropdown.value = false;
}

function removeSelectedPlugin(index: number) {
  selectedPlugins.value.splice(index, 1);
}

function closePluginDropdown() {
  // Delay to allow click on dropdown items
  setTimeout(() => {
    showPluginDropdown.value = false;
  }, 200);
}

// Copy config to clipboard
async function copyConfig() {
  if (!harnessConfig.value) return;
  try {
    await navigator.clipboard.writeText(harnessConfig.value.config_json);
    copied.value = true;
    showToast('Configuration copied to clipboard', 'success');
    setTimeout(() => { copied.value = false; }, 2000);
  } catch (e) {
    showToast('Failed to copy to clipboard', 'error');
  }
}

// Download config
function downloadConfig() {
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

// Watch for project changes
watch(() => props.projectId, () => {
  loadData();
});

// Reactive config preview: refresh when selected plugins change
watch(selectedPlugins, () => {
  refreshConfig();
}, { deep: true });

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

    <!-- Workflow Steps -->
    <div v-if="hasProject && hasGitHubRepo" class="workflow-steps">
      <div class="step" :class="{ active: true, completed: includedTeams.length > 0 }">
        <div class="step-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/>
            <path d="M21 21l-4.35-4.35"/>
          </svg>
        </div>
        <div class="step-info">
          <span class="step-label">Discover</span>
          <span class="step-desc">Load components from GitHub</span>
        </div>
      </div>
      <div class="step-connector"></div>
      <div class="step" :class="{ active: includedTeams.length > 0, completed: includedTeams.length > 0 }">
        <div class="step-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/>
          </svg>
        </div>
        <div class="step-info">
          <span class="step-label">Import</span>
          <span class="step-desc">Select components to include</span>
        </div>
      </div>
      <div class="step-connector"></div>
      <div class="step" :class="{ active: includedTeams.length > 0 }">
        <div class="step-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 20h9M16.5 3.5a2.121 2.121 0 113 3L7 19l-4 1 1-4L16.5 3.5z"/>
          </svg>
        </div>
        <div class="step-info">
          <span class="step-label">Configure</span>
          <span class="step-desc">Customize settings</span>
        </div>
      </div>
      <div class="step-connector"></div>
      <div class="step">
        <div class="step-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M9 11l3 3L22 4"/>
            <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>
          </svg>
        </div>
        <div class="step-info">
          <span class="step-label">Validate</span>
          <span class="step-desc">Check configuration</span>
        </div>
      </div>
      <div class="step-connector"></div>
      <div class="step">
        <div class="step-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
          </svg>
        </div>
        <div class="step-info">
          <span class="step-label">Deploy</span>
          <span class="step-desc">Push to GitHub</span>
        </div>
      </div>
    </div>

    <LoadingState v-if="isLoading" message="Loading harness configuration..." />

    <!-- Main Content -->
    <div v-else class="harness-content">
      <!-- Teams Section -->
      <div class="section">
        <div class="section-header" @click="toggleSection('teams')">
          <div class="section-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/>
              <circle cx="9" cy="7" r="4"/>
              <path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/>
            </svg>
            <h2>Included Teams ({{ includedTeams.length }})</h2>
          </div>
          <svg class="chevron" :class="{ expanded: expandedSections.teams }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </div>
        <div v-if="expandedSections.teams" class="section-content">
          <div v-if="includedTeams.length === 0" class="empty-section">
            <span>No teams assigned</span>
          </div>
          <div v-else class="items-grid">
            <div v-for="team in includedTeams" :key="team.id" class="item-card team-card">
              <div class="item-color" :style="{ backgroundColor: team.color }"></div>
              <div class="item-info">
                <span class="item-name">{{ team.name }}</span>
                <span class="item-meta">{{ team.member_count }} members</span>
              </div>
            </div>
          </div>

          <!-- GitHub Synced Teams (read-only) -->
          <div v-if="syncedTeams.length > 0" class="synced-teams-section">
            <div class="synced-header">
              <svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16">
                <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
              </svg>
              <span>Teams from GitHub ({{ syncedTeams.length }})</span>
            </div>
            <div class="items-grid">
              <div v-for="team in syncedTeams" :key="team.id" class="item-card team-card synced">
                <div class="item-color" :style="{ backgroundColor: team.color }"></div>
                <div class="item-info">
                  <span class="item-name">{{ team.name }}</span>
                  <span class="item-meta">{{ team.member_count }} members</span>
                </div>
                <span class="source-badge github">GitHub</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Agents Section -->
      <div class="section">
        <div class="section-header" @click="toggleSection('agents')">
          <div class="section-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
              <path d="M7 11V7a5 5 0 0110 0v4"/>
            </svg>
            <h2>Included Agents ({{ agents.length }})</h2>
          </div>
          <svg class="chevron" :class="{ expanded: expandedSections.agents }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </div>
        <div v-if="expandedSections.agents" class="section-content">
          <div v-if="agents.length === 0" class="empty-section">
            <span>No agents included</span>
          </div>
          <div v-else class="items-grid">
            <div v-for="agent in agents" :key="agent.id" class="item-card agent-card">
              <div class="item-icon agent-icon" :style="{ backgroundColor: agent.color || 'var(--accent-violet-dim)' }">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                  <path d="M7 11V7a5 5 0 0110 0v4"/>
                </svg>
              </div>
              <div class="item-info">
                <span class="item-name">{{ agent.name }}</span>
                <span class="item-meta">{{ agent.role || agent.description || 'No role defined' }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Commands Section -->
      <div class="section">
        <div class="section-header" @click="toggleSection('commands')">
          <div class="section-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="4 17 10 11 4 5"/>
              <line x1="12" y1="19" x2="20" y2="19"/>
            </svg>
            <h2>Included Commands ({{ commands.length }})</h2>
          </div>
          <svg class="chevron" :class="{ expanded: expandedSections.commands }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </div>
        <div v-if="expandedSections.commands" class="section-content">
          <div v-if="commands.length === 0" class="empty-section">
            <span>No commands configured</span>
          </div>
          <div v-else class="items-list">
            <div v-for="cmd in commands" :key="cmd.id" class="item-row">
              <div class="item-icon command-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="4 17 10 11 4 5"/>
                  <line x1="12" y1="19" x2="20" y2="19"/>
                </svg>
              </div>
              <div class="item-info">
                <span class="item-name">/{{ cmd.name }}</span>
                <span class="item-meta">{{ cmd.description || 'No description' }}</span>
              </div>
              <span class="item-badge" :class="cmd.enabled ? 'enabled' : 'disabled'">
                {{ cmd.enabled ? 'Enabled' : 'Disabled' }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Hooks Section -->
      <div class="section">
        <div class="section-header" @click="toggleSection('hooks')">
          <div class="section-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/>
              <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/>
            </svg>
            <h2>Included Hooks ({{ hooks.length }})</h2>
          </div>
          <svg class="chevron" :class="{ expanded: expandedSections.hooks }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </div>
        <div v-if="expandedSections.hooks" class="section-content">
          <div v-if="hooks.length === 0" class="empty-section">
            <span>No hooks configured</span>
          </div>
          <div v-else class="items-list">
            <div v-for="hook in hooks" :key="hook.id" class="item-row">
              <div class="item-icon hook-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/>
                  <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/>
                </svg>
              </div>
              <div class="item-info">
                <span class="item-name">{{ hook.name }}</span>
                <span class="item-meta">{{ hook.event }} - {{ hook.description || 'No description' }}</span>
              </div>
              <span class="item-badge event-badge">{{ hook.event }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Skills Section -->
      <div class="section">
        <div class="section-header" @click="toggleSection('skills')">
          <div class="section-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 2L2 7l10 5 10-5-10-5z"/>
              <path d="M2 17l10 5 10-5"/>
              <path d="M2 12l10 5 10-5"/>
            </svg>
            <h2>Included Skills ({{ skills.length }})</h2>
          </div>
          <svg class="chevron" :class="{ expanded: expandedSections.skills }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </div>
        <div v-if="expandedSections.skills" class="section-content">
          <div v-if="skills.length === 0" class="empty-section">
            <span>No skills selected for harness</span>
          </div>
          <div v-else class="items-list">
            <div v-for="skill in skills" :key="skill.id" class="item-row">
              <div class="item-icon skill-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                  <path d="M2 17l10 5 10-5"/>
                  <path d="M2 12l10 5 10-5"/>
                </svg>
              </div>
              <div class="item-info">
                <span class="item-name">{{ skill.skill_name }}</span>
                <span class="item-meta">{{ skill.skill_path }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Marketplace Plugins Section -->
      <div class="section">
        <div class="section-header" @click="toggleSection('plugins')">
          <div class="section-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
              <path d="M3 9h18M9 21V9"/>
            </svg>
            <h2>Marketplace Plugins ({{ selectedPlugins.length }})</h2>
          </div>
          <svg class="chevron" :class="{ expanded: expandedSections.plugins }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </div>
        <div v-if="expandedSections.plugins" class="section-content">
          <!-- Plugin Search Input -->
          <div class="plugin-search-container">
            <div class="plugin-search-input">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="11" cy="11" r="8"/>
                <path d="M21 21l-4.35-4.35"/>
              </svg>
              <input
                v-model="pluginSearchQuery"
                type="text"
                placeholder="Search plugins from marketplaces..."
                @input="onPluginSearchInput"
                @focus="onPluginSearchInput"
                @blur="closePluginDropdown"
              />
              <div v-if="isSearchingPlugins" class="search-spinner"></div>
            </div>

            <!-- Dropdown Results -->
            <div v-if="showPluginDropdown && pluginSearchResults.length > 0" class="plugin-dropdown">
              <div
                v-for="plugin in pluginSearchResults"
                :key="`${plugin.marketplace_id}-${plugin.name}`"
                class="plugin-dropdown-item"
                @mousedown.prevent="selectPlugin(plugin)"
              >
                <div class="dropdown-item-info">
                  <span class="dropdown-item-name">{{ plugin.name }}</span>
                  <span class="dropdown-item-desc">{{ plugin.description || 'No description' }}</span>
                </div>
                <span class="dropdown-marketplace-badge">{{ plugin.marketplace_name }}</span>
              </div>
            </div>

            <div v-if="showPluginDropdown && pluginSearchResults.length === 0 && !isSearchingPlugins && pluginSearchQuery.trim().length >= 2" class="plugin-dropdown">
              <div class="plugin-dropdown-empty">No plugins found</div>
            </div>
          </div>

          <!-- Selected Plugins -->
          <div v-if="selectedPlugins.length === 0" class="empty-section">
            <span>No marketplace plugins selected. Search above to add plugins.</span>
          </div>
          <div v-else class="selected-plugins">
            <div v-for="(plugin, index) in selectedPlugins" :key="`selected-${plugin.marketplace_id}-${plugin.name}`" class="selected-plugin-chip">
              <span class="chip-name">{{ plugin.name }}</span>
              <span class="chip-marketplace">{{ plugin.marketplace_name }}</span>
              <button class="chip-remove" @click="removeSelectedPlugin(index)" title="Remove plugin">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="18" y1="6" x2="6" y2="18"/>
                  <line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Scripts Section -->
      <div class="section">
        <div class="section-header" @click="toggleSection('scripts')">
          <div class="section-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
              <polyline points="10 9 9 9 8 9"/>
            </svg>
            <h2>Included Scripts ({{ scripts.length }})</h2>
          </div>
          <svg class="chevron" :class="{ expanded: expandedSections.scripts }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </div>
        <div v-if="expandedSections.scripts" class="section-content">
          <div v-if="scripts.length === 0" class="empty-section">
            <span>No scripts configured</span>
          </div>
          <div v-else class="items-list">
            <div v-for="script in scripts" :key="script.id" class="item-row">
              <div class="item-icon script-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                  <polyline points="14 2 14 8 20 8"/>
                </svg>
              </div>
              <div class="item-info">
                <span class="item-name">{{ script.name }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Config Preview Section -->
      <div class="section config-section">
        <div class="section-header">
          <div class="section-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
            </svg>
            <h2>Config Preview</h2>
          </div>
          <div class="preview-actions">
            <button class="btn btn-sm" @click="copyConfig" :disabled="!harnessConfig">
              <svg v-if="!copied" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M20 6L9 17l-5-5"/>
              </svg>
              {{ copied ? 'Copied!' : 'Copy' }}
            </button>
            <button class="btn btn-sm" @click="downloadConfig" :disabled="!harnessConfig">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/>
              </svg>
              Download
            </button>
          </div>
        </div>
        <div class="config-preview">
          <pre><code>{{ harnessConfig?.config_json || '{}' }}</code></pre>
        </div>
      </div>
    </div>
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

/* Sections */
.harness-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  cursor: pointer;
  transition: background 0.15s;
}

.section-header:hover {
  background: var(--bg-tertiary);
}

.section-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-title svg {
  width: 20px;
  height: 20px;
  color: var(--accent-cyan);
}

.section-title h2 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.chevron {
  width: 20px;
  height: 20px;
  color: var(--text-tertiary);
  transition: transform 0.2s;
}

.chevron.expanded {
  transform: rotate(180deg);
}

.section-content {
  padding: 0 20px 20px;
}

.empty-section {
  padding: 24px;
  text-align: center;
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
  border-radius: 8px;
}

/* Items Grid (for Teams, Agents) */
.items-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.item-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.item-color {
  width: 8px;
  height: 40px;
  border-radius: 4px;
  flex-shrink: 0;
}

.item-icon {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.item-icon svg {
  width: 18px;
  height: 18px;
}

.agent-icon {
  background: var(--accent-violet-dim);
  color: var(--accent-violet);
}

.command-icon {
  background: var(--accent-green-dim, rgba(0, 200, 83, 0.15));
  color: var(--accent-green, #00c853);
}

.hook-icon {
  background: var(--accent-orange-dim, rgba(255, 152, 0, 0.15));
  color: var(--accent-orange, #ff9800);
}

.skill-icon {
  background: var(--accent-violet-dim, rgba(136, 85, 255, 0.15));
  color: var(--accent-violet, #8855ff);
}

.script-icon {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.item-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.item-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-meta {
  font-size: 12px;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Items List (for Commands, Hooks, Skills, Scripts) */
.items-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.item-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.item-badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  flex-shrink: 0;
}

.item-badge.enabled {
  background: var(--accent-green-dim, rgba(0, 200, 83, 0.15));
  color: var(--accent-green, #00c853);
}

.item-badge.disabled {
  background: var(--bg-elevated);
  color: var(--text-tertiary);
}

.item-badge.event-badge {
  background: var(--accent-orange-dim, rgba(255, 152, 0, 0.15));
  color: var(--accent-orange, #ff9800);
}

/* Config Section */
.config-section .section-header {
  cursor: default;
}

.config-section .section-header:hover {
  background: transparent;
}

.preview-actions {
  display: flex;
  gap: 8px;
}

.config-preview {
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 16px;
  max-height: 300px;
  overflow: auto;
  margin: 0 20px 20px;
}

.config-preview pre {
  margin: 0;
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--text-secondary);
  white-space: pre-wrap;
}

/* Buttons */

/* Button spinner */
.spinner-btn {
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

/* Plugin Search */
.plugin-search-container {
  position: relative;
  margin-bottom: 12px;
}

.plugin-search-input {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  transition: border-color 0.15s;
}

.plugin-search-input:focus-within {
  border-color: var(--accent-cyan);
}

.plugin-search-input svg {
  width: 16px;
  height: 16px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.plugin-search-input input {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: 14px;
}

.plugin-search-input input:focus {
  outline: none;
}

.plugin-search-input input::placeholder {
  color: var(--text-tertiary);
}

.search-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--border-default);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}

.plugin-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  margin-top: 4px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  max-height: 240px;
  overflow-y: auto;
  z-index: 10;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}

.plugin-dropdown-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  cursor: pointer;
  transition: background 0.1s;
}

.plugin-dropdown-item:hover {
  background: var(--bg-tertiary);
}

.dropdown-item-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.dropdown-item-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.dropdown-item-desc {
  font-size: 12px;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dropdown-marketplace-badge {
  font-size: 10px;
  padding: 2px 6px;
  background: var(--accent-blue-dim, rgba(56, 139, 253, 0.1));
  color: var(--accent-blue, #388bfd);
  border-radius: 3px;
  font-weight: 500;
  flex-shrink: 0;
  white-space: nowrap;
}

.plugin-dropdown-empty {
  padding: 16px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 13px;
}

.selected-plugins {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.selected-plugin-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
}

.chip-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.chip-marketplace {
  font-size: 10px;
  padding: 1px 5px;
  background: var(--accent-blue-dim, rgba(56, 139, 253, 0.1));
  color: var(--accent-blue, #388bfd);
  border-radius: 3px;
}

.chip-remove {
  width: 18px;
  height: 18px;
  background: transparent;
  border: none;
  border-radius: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-tertiary);
  transition: all 0.1s;
}

.chip-remove:hover {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.chip-remove svg {
  width: 12px;
  height: 12px;
}

/* Synced Teams Section */
.synced-teams-section {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border-subtle);
}

.synced-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--text-tertiary);
}

.synced-header svg {
  color: var(--text-tertiary);
}

.team-card.synced {
  background: var(--bg-tertiary);
  opacity: 0.75;
  border: 1px dashed var(--border-default);
}

.source-badge {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  padding: 2px 6px;
  border-radius: 3px;
}

.source-badge.github {
  background: rgba(110, 84, 148, 0.2);
  color: #9d8ac7;
}

/* Workflow Steps */
.workflow-steps {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 20px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  margin-bottom: 24px;
  overflow-x: auto;
}

.step {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  border: 1px solid transparent;
  opacity: 0.5;
  transition: all 0.2s;
}

.step.active {
  opacity: 1;
}

.step.completed {
  border-color: var(--accent-emerald);
  background: rgba(0, 255, 136, 0.08);
}

.step-icon {
  width: 32px;
  height: 32px;
  background: var(--bg-elevated);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
}

.step.active .step-icon {
  color: var(--accent-cyan);
}

.step.completed .step-icon {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.step-icon svg {
  width: 16px;
  height: 16px;
}

.step-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.step-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.step-desc {
  font-size: 11px;
  color: var(--text-tertiary);
}

.step-connector {
  width: 24px;
  height: 2px;
  background: var(--border-default);
  flex-shrink: 0;
}
</style>
