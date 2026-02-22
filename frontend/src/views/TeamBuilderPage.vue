<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import type { Team, TeamMember, TeamAgentAssignment, Agent, TopologyType, TopologyConfig } from '../services/api';
import { teamApi, agentApi, superAgentApi, ApiError } from '../services/api';
import TeamCanvas from '../components/canvas/TeamCanvas.vue';
import TopologyPicker from '../components/teams/TopologyPicker.vue';
import AgentAssignmentEditor from '../components/teams/AgentAssignmentEditor.vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
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

// View mode
const viewMode = ref<'visual' | 'form'>('visual');

// Data state
const team = ref<Team | null>(null);
const members = ref<TeamMember[]>([]);
const assignments = ref<TeamAgentAssignment[]>([]);
const allAgents = ref<Agent[]>([]);
const allSuperAgents = ref<any[]>([]);
const canvasRef = ref<InstanceType<typeof TeamCanvas> | null>(null);

// Local topology state for form view
const localTopology = ref<TopologyType | null>(null);
const localTopologyConfig = ref<string>('{}');
const isFormSaving = ref(false);

// Available agents (not already team members)
const availableAgents = computed(() => {
  const memberAgentIds = new Set(members.value.filter(m => m.agent_id).map(m => m.agent_id));
  return allAgents.value.filter(a => !memberAgentIds.has(a.id));
});

// Available super agents (not already team members)
const availableSuperAgents = computed(() => {
  const memberSaIds = new Set(members.value.filter(m => m.super_agent_id).map(m => m.super_agent_id));
  return allSuperAgents.value.filter(sa => !memberSaIds.has(sa.id));
});

useWebMcpTool({
  name: 'hive_team_builder_get_state',
  description: 'Returns the current state of the TeamBuilderPage',
  page: 'TeamBuilderPage',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'TeamBuilderPage',
        teamId: team.value?.id ?? null,
        teamName: team.value?.name ?? null,
        viewMode: viewMode.value,
        memberCount: members.value.length,
        assignmentCount: assignments.value.length,
        availableAgentCount: availableAgents.value.length,
        localTopology: localTopology.value,
        isFormSaving: isFormSaving.value,
      }),
    }],
  }),
  deps: [team, viewMode, members, assignments, availableAgents, localTopology, isFormSaving],
});

// Load all data
async function loadData() {
  const [teamData, agentsData, saData] = await Promise.all([
    teamApi.get(teamId.value),
    agentApi.list(),
    superAgentApi.list().catch(() => ({ super_agents: [] })),
  ]);

  team.value = teamData;
  members.value = teamData.members || [];
  allAgents.value = agentsData.agents || [];
  allSuperAgents.value = saData.super_agents || [];

  // Load assignments
  try {
    const assignData = await teamApi.getAllAssignments(teamId.value);
    assignments.value = assignData.assignments || [];
  } catch {
    assignments.value = [];
  }

  // Sync local topology state
  localTopology.value = teamData.topology || null;
  localTopologyConfig.value = teamData.topology_config || '{}';
  return teamData;
}

// Handle topology update from TeamCanvas (includes dropdown changes)
async function onTopologyUpdate(payload: { topology: string | null; topology_config: any }) {
  if (!team.value) return;

  localTopologyConfig.value = typeof payload.topology_config === 'string'
    ? payload.topology_config
    : JSON.stringify(payload.topology_config);

  // Persist topology type change immediately if it differs from saved
  const newTopo = payload.topology as TopologyType | null;
  if (newTopo !== (team.value.topology || null)) {
    try {
      // Send ONLY topology (no config) to avoid config validation
      await teamApi.updateTopology(teamId.value, {
        topology: newTopo,
      });
      team.value.topology = newTopo || undefined;
    } catch {
      // Non-critical: will be saved with next explicit save
    }
  }
}

// Handle save from TeamCanvas
async function onSave(payload: { topology: string | null; topology_config: any; positions: any }) {
  try {
    // Parse existing config to preserve form-mode fields
    let existingConfig: TopologyConfig = {};
    try {
      const raw = team.value?.topology_config;
      existingConfig = raw
        ? (typeof raw === 'string' ? JSON.parse(raw) : raw)
        : {};
    } catch {
      existingConfig = {};
    }

    // Parse new config from canvas
    let newConfig: TopologyConfig = {};
    try {
      newConfig = typeof payload.topology_config === 'string'
        ? JSON.parse(payload.topology_config)
        : payload.topology_config || {};
    } catch {
      newConfig = {};
    }

    // Merge: new canvas config overrides existing, preserving fields not in new config
    const mergedConfig: TopologyConfig = { ...existingConfig, ...newConfig };
    // Ensure edges from canvas override stale DB edges
    if (newConfig.edges) {
      mergedConfig.edges = newConfig.edges;
    }
    mergedConfig.positions = payload.positions;

    // Send ONLY topology_config (no topology type) to avoid coupled validation.
    // Topology type changes are persisted immediately via onTopologyUpdate.
    await teamApi.updateTopology(teamId.value, {
      topology_config: JSON.stringify(mergedConfig),
    });
    showToast('Team topology saved', 'success');
    await loadData();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to save topology';
    showToast(message, 'error');
  }
}

// Handle form view topology config update
function onFormTopologyConfigUpdate(configStr: string) {
  localTopologyConfig.value = configStr;
}

// Handle form view save
async function onFormSave() {
  if (!localTopology.value) {
    showToast('Please select a topology before saving', 'error');
    return;
  }
  isFormSaving.value = true;
  try {
    await teamApi.updateTopology(teamId.value, {
      topology: localTopology.value,
      topology_config: localTopologyConfig.value,
    });
    showToast('Team topology saved', 'success');
    await loadData();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to save topology';
    showToast(message, 'error');
  } finally {
    isFormSaving.value = false;
  }
}

// Reload assignments after form view changes
async function reloadAssignments() {
  try {
    const assignData = await teamApi.getAllAssignments(teamId.value);
    assignments.value = assignData.assignments || [];
  } catch {
    // Non-critical — ignore reload failure
  }
}

watch(viewMode, (newMode) => {
  if (newMode === 'visual') {
    nextTick(() => {
      canvasRef.value?.resyncFromTeam();
      setTimeout(() => canvasRef.value?.fitView(), 50);
    });
  }
});
</script>

<template>
  <EntityLayout :load-entity="loadData" entity-label="team builder">
    <template #default="{ reload: _reload }">
  <div class="team-builder-page">
    <!-- Header bar -->
    <div class="builder-header">
      <AppBreadcrumb :items="[
        { label: 'Teams', action: () => router.push({ name: 'teams' }) },
        { label: team?.name || 'Team', action: () => router.push({ name: 'team-dashboard', params: { teamId: teamId } }) },
        { label: 'Builder' },
      ]" />
      <h2 class="builder-title">{{ team?.name || 'Team Builder' }}</h2>
      <div class="view-toggle">
        <button
          :class="{ active: viewMode === 'visual' }"
          @click="viewMode = 'visual'"
        >Visual</button>
        <button
          :class="{ active: viewMode === 'form' }"
          @click="viewMode = 'form'"
        >Form</button>
      </div>
    </div>

    <!-- Visual mode: full canvas -->
    <div v-if="viewMode === 'visual'" class="builder-canvas">
      <TeamCanvas
        ref="canvasRef"
        :team="team"
        :members="members"
        :assignments="assignments"
        :available-agents="availableAgents"
        :available-super-agents="availableSuperAgents"
        @update:topology="onTopologyUpdate"
        @save="onSave"
        @members-changed="loadData"
        @navigate-to-agent="(agentId: any) => router.push({ name: 'agent-design', params: { agentId } })"
        @navigate-to-assignment="(_payload: any) => { /* Assignment navigation handled by entity type */ }"
      />
    </div>

    <!-- Form mode: existing topology picker + assignment editors -->
    <div v-else class="builder-form">
      <div class="form-section">
        <h3>Topology</h3>
        <TopologyPicker
          v-model="localTopology"
          :team-members="members"
          :initial-config="localTopologyConfig"
          @update:config="onFormTopologyConfigUpdate"
        />
      </div>
      <div class="form-section">
        <h3>Agent Assignments</h3>
        <div v-if="members.filter(m => m.agent_id).length === 0" class="empty-assignments">
          <p>No agent members to configure</p>
        </div>
        <div v-for="member in members.filter(m => m.agent_id)" :key="member.agent_id" class="member-assignments">
          <AgentAssignmentEditor
            :team-id="teamId"
            :agent-id="member.agent_id!"
            :agent-name="member.name"
            @updated="reloadAssignments"
          />
        </div>
      </div>
      <div class="form-actions">
        <button class="save-btn" :disabled="isFormSaving" @click="onFormSave">
          <span v-if="isFormSaving" class="btn-spinner"></span>
          {{ isFormSaving ? 'Saving...' : 'Save Changes' }}
        </button>
      </div>
    </div>
  </div>
    </template>
  </EntityLayout>
</template>

<style scoped>
.team-builder-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-height: 100vh;
  overflow: hidden;
  background: var(--bg-primary);
}

.builder-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 20px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-subtle);
  flex-shrink: 0;
}

.builder-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  flex: 1;
}

.view-toggle {
  display: flex;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  overflow: hidden;
}

.view-toggle button {
  padding: 6px 16px;
  font-size: 12px;
  font-weight: 500;
  border: none;
  cursor: pointer;
  transition: all 0.15s;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.view-toggle button.active {
  background: var(--accent-cyan, #00d4ff);
  color: #000;
}

.view-toggle button:not(.active):hover {
  background: var(--bg-elevated);
  color: var(--text-primary);
}

.builder-canvas {
  flex: 1;
  overflow: hidden;
}

.builder-form {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  max-width: 800px;
}

.form-section {
  margin-bottom: 24px;
}

.form-section h3 {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 12px;
}

.member-assignments {
  margin-bottom: 16px;
  padding: 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
}

.empty-assignments {
  padding: 24px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 0.9rem;
}

.save-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 24px;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  border: none;
  background: linear-gradient(135deg, var(--accent-cyan, #00d4ff) 0%, var(--accent-emerald, #00ff88) 100%);
  color: var(--bg-primary);
  transition: all 0.2s;
}

.save-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 212, 255, 0.3);
}

.save-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
}

.btn-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(0, 0, 0, 0.3);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
</style>
