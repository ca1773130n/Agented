<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import type { Team, TopologyType } from '../services/api';
import { teamApi, ApiError } from '../services/api';
import AgentAssignmentEditor from '../components/teams/AgentAssignmentEditor.vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import TeamTopologyCard from '../components/teams/TeamTopologyCard.vue';
import TeamTriggerCard from '../components/teams/TeamTriggerCard.vue';
import TeamMembersList from '../components/teams/TeamMembersList.vue';
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

// Run state
const isRunning = ref(false);
const runMessage = ref('');

// Agent members with agent_id
const agentMembers = computed(() =>
  (team.value?.members || []).filter(m => m.agent_id)
);

// Expanded assignment cards
const expandedAgents = ref<Set<string>>(new Set());

useWebMcpTool({
  name: 'hive_team_dashboard_get_state',
  description: 'Returns the current state of the TeamDashboard',
  page: 'TeamDashboard',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'TeamDashboard',
        teamId: team.value?.id ?? null,
        teamName: team.value?.name ?? null,
        isRunning: isRunning.value,
        memberCount: team.value?.members?.length ?? 0,
        agentMemberCount: agentMembers.value.length,
        topology: team.value?.topology ?? null,
        triggerSource: team.value?.trigger_source ?? null,
      }),
    }],
  }),
  deps: [team, isRunning, agentMembers],
});

function toggleAgentExpand(agentId: string) {
  if (expandedAgents.value.has(agentId)) {
    expandedAgents.value.delete(agentId);
  } else {
    expandedAgents.value.add(agentId);
  }
}

function getTopologyLabel(t?: TopologyType): string {
  if (!t) return 'None';
  const labels: Record<TopologyType, string> = {
    sequential: 'Sequential Pipeline',
    parallel: 'Parallel Fan-out',
    coordinator: 'Coordinator / Dispatcher',
    generator_critic: 'Generator / Critic',
    hierarchical: 'Hierarchical Delegation',
    human_in_loop: 'Human-in-the-Loop',
    composite: 'Composite Pattern',
  };
  return labels[t] || t;
}

function getTriggerLabel(t?: string): string {
  if (!t) return 'None';
  const labels: Record<string, string> = {
    webhook: 'Webhook',
    github: 'GitHub',
    manual: 'Manual',
    scheduled: 'Scheduled',
  };
  return labels[t] || t;
}

async function loadData() {
  const data = await teamApi.get(teamId.value);
  team.value = data;
  return data;
}

// Manual run
async function runTeam() {
  isRunning.value = true;
  try {
    const result = await teamApi.runTeam(teamId.value, { message: runMessage.value || undefined });
    showToast(result.message || 'Team run initiated', 'success');
    runMessage.value = '';
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to run team';
    showToast(message, 'error');
  } finally {
    isRunning.value = false;
  }
}


</script>

<template>
  <EntityLayout :load-entity="loadData" entity-label="team">
    <template #default="{ reload: _reload }">
  <div class="team-dashboard">
    <AppBreadcrumb :items="[{ label: 'Teams', action: () => router.push({ name: 'teams' }) }, { label: team?.name || 'Team' }]" />

    <template v-if="team">
      <!-- Team Status Card -->
      <div class="status-card">
        <div class="status-card-header">
          <div class="team-icon-lg" :style="{ background: `linear-gradient(135deg, ${team.color}, var(--accent-cyan, #00d4ff))` }">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
              <circle cx="9" cy="7" r="4"/>
              <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
              <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
            </svg>
          </div>
          <div class="status-info">
            <h2>{{ team.name }}</h2>
            <div class="status-meta">
              <span class="meta-pill members">
                {{ team.member_count }} members
              </span>
              <span v-if="team.topology" class="meta-pill topology">{{ getTopologyLabel(team.topology) }}</span>
              <span v-if="team.trigger_source" class="meta-pill trigger">{{ getTriggerLabel(team.trigger_source) }}</span>
              <span v-if="team.enabled !== undefined" class="enabled-dot" :class="{ active: team.enabled === 1 }" :title="team.enabled === 1 ? 'Enabled' : 'Disabled'"></span>
              <span class="color-indicator" :style="{ background: team.color }"></span>
            </div>
          </div>
        </div>
        <p v-if="team.description" class="team-description">{{ team.description }}</p>

        <!-- Leader Section -->
        <div v-if="team.leader_name" class="leader-section">
          <div class="leader-label">Team Leader</div>
          <div class="leader-info">
            <div class="leader-avatar">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="8" r="4"/>
                <path d="M20 21a8 8 0 1 0-16 0"/>
              </svg>
            </div>
            <div class="leader-details">
              <span class="leader-name">{{ team.leader_name }}</span>
              <span v-if="team.leader_id" class="leader-id">{{ team.leader_id }}</span>
            </div>
            <span class="leader-badge">Agent</span>
          </div>
        </div>
      </div>

      <!-- Quick Actions -->
      <div class="actions-row">
        <button class="action-btn secondary" @click="router.push({ name: 'teams' })">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
          All Teams
        </button>
        <button class="action-btn secondary" @click="router.push({ name: 'team-settings', params: { teamId: teamId } })">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
          </svg>
          Edit Team
        </button>
        <button
          class="visual-builder-btn"
          :disabled="!team.members || team.members.filter(m => m.agent_id).length === 0"
          :title="(!team.members || team.members.filter(m => m.agent_id).length === 0) ? 'Add agents to use Visual Builder' : 'Open Visual Builder'"
          @click="router.push({ name: 'team-builder', params: { teamId: teamId } })"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="3" y="3" width="7" height="7" rx="1"/>
            <rect x="14" y="3" width="7" height="7" rx="1"/>
            <rect x="3" y="14" width="7" height="7" rx="1"/>
            <rect x="14" y="14" width="7" height="7" rx="1"/>
            <path d="M10 6.5h4M6.5 10v4M17.5 10v4M10 17.5h4"/>
          </svg>
          Visual Builder
        </button>
      </div>

      <!-- Test Run section -->
      <div v-if="team.topology" class="card run-card">
        <div class="card-header">
          <h3>Test Run</h3>
          <span class="test-run-badge">Runs on server codebase</span>
        </div>
        <div class="test-run-info">
          Test mode runs on the Hive server's local directory, not a project working directory. For project-scoped runs, use the Project dashboard.
        </div>
        <div class="run-body">
          <input
            v-model="runMessage"
            type="text"
            class="form-input"
            placeholder="Optional message for the test run..."
            @keyup.enter="runTeam"
          />
          <button class="action-btn primary compact" :disabled="isRunning" @click="runTeam">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polygon points="5 3 19 12 5 21 5 3"/>
            </svg>
            {{ isRunning ? 'Running...' : 'Test Run' }}
          </button>
        </div>
      </div>

      <!-- Team Configuration: Topology -->
      <TeamTopologyCard :team="team" @updated="loadData" />

      <!-- Trigger Configuration -->
      <TeamTriggerCard :team="team" @updated="loadData" />

      <!-- Agent Assignments -->
      <div class="card">
        <div class="card-header">
          <div class="header-left">
            <h3>Agent Assignments</h3>
            <span class="card-count">{{ agentMembers.length }} agents</span>
          </div>
        </div>

        <div v-if="agentMembers.length === 0" class="empty-state">
          <p>No agent members</p>
          <span>Add agent members to assign skills, commands, hooks, and rules</span>
        </div>

        <div v-else class="agent-assignments-list">
          <div v-for="member in agentMembers" :key="member.agent_id" class="agent-assignment-card">
            <div class="agent-assignment-header" @click="toggleAgentExpand(member.agent_id!)">
              <div class="agent-avatar is-agent">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="8" r="4"/>
                  <path d="M20 21a8 8 0 1 0-16 0"/>
                </svg>
              </div>
              <div class="agent-assignment-info">
                <span
                  class="agent-assignment-name entity-link"
                  @click.stop="router.push({ name: 'agent-design', params: { agentId: member.agent_id! } })"
                >{{ member.name }}</span>
                <span class="agent-assignment-id">{{ member.agent_id }}</span>
              </div>
              <svg class="expand-chevron" :class="{ expanded: expandedAgents.has(member.agent_id!) }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </div>
            <div v-if="expandedAgents.has(member.agent_id!)" class="agent-assignment-body">
              <AgentAssignmentEditor
                :team-id="teamId"
                :agent-id="member.agent_id!"
                :agent-name="member.name"
                @updated="loadData"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- Team Members -->
      <TeamMembersList
        :team="team"
        :team-id="teamId"
        @member-added="loadData"
        @member-removed="loadData"
        @navigate-to-agent-design="(agentId: string) => router.push({ name: 'agent-design', params: { agentId } })"
      />

      <!-- Team Info -->
      <div class="card">
        <div class="card-header">
          <h3>Team Info</h3>
        </div>
        <div class="info-grid">
          <div class="info-item">
            <span class="info-label">Team ID</span>
            <span class="info-value mono">{{ team.id }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Members</span>
            <span class="info-value">{{ team.member_count }} total</span>
          </div>
          <div v-if="team.leader_id" class="info-item">
            <span class="info-label">Leader</span>
            <span class="info-value">{{ team.leader_name || team.leader_id }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Color</span>
            <div class="color-preview">
              <span class="color-swatch" :style="{ background: team.color }"></span>
              <span class="info-value mono">{{ team.color }}</span>
            </div>
          </div>
          <div v-if="team.created_at" class="info-item">
            <span class="info-label">Created</span>
            <span class="info-value">{{ new Date(team.created_at).toLocaleDateString() }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
    </template>
  </EntityLayout>
</template>

<style scoped>
.team-dashboard { display: flex; flex-direction: column; gap: 24px; width: 100%; animation: fadeIn 0.4s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }

/* Status Card */
.status-card { background: var(--bg-secondary); border: 1px solid var(--border-subtle); border-radius: 12px; padding: 28px; }
.status-card-header { display: flex; align-items: center; gap: 20px; }
.team-icon-lg { width: 56px; height: 56px; border-radius: 14px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.team-icon-lg svg { width: 28px; height: 28px; color: var(--bg-primary); }
.status-info h2 { font-family: var(--font-mono); font-size: 1.25rem; font-weight: 600; color: var(--text-primary); letter-spacing: -0.02em; margin-bottom: 8px; }
.status-meta { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.meta-pill { display: inline-flex; align-items: center; padding: 4px 10px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em; }
.meta-pill.members { background: var(--accent-cyan-dim, rgba(0, 212, 255, 0.15)); color: var(--accent-cyan, #00d4ff); }
.meta-pill.topology { background: var(--accent-violet-dim, rgba(136, 85, 255, 0.15)); color: var(--accent-violet, #8855ff); }
.meta-pill.trigger { background: var(--accent-emerald-dim, rgba(0, 255, 136, 0.15)); color: var(--accent-emerald, #00ff88); }
.enabled-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-muted, #404050); }
.enabled-dot.active { background: var(--accent-emerald, #00ff88); box-shadow: 0 0 6px rgba(0, 255, 136, 0.4); }
.color-indicator { width: 16px; height: 16px; border-radius: 4px; border: 2px solid var(--border-subtle); }
.team-description { margin-top: 16px; color: var(--text-secondary); line-height: 1.6; }

/* Leader */
.leader-section { margin-top: 20px; padding-top: 20px; border-top: 1px solid var(--border-subtle); }
.leader-label { font-size: 0.75rem; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px; }
.leader-info { display: flex; align-items: center; gap: 12px; }
.leader-avatar { width: 44px; height: 44px; border-radius: 50%; background: linear-gradient(135deg, var(--accent-cyan, #00d4ff), var(--accent-emerald, #00ff88)); display: flex; align-items: center; justify-content: center; }
.leader-avatar svg { width: 22px; height: 22px; color: var(--bg-primary); }
.leader-details { flex: 1; display: flex; flex-direction: column; gap: 2px; }
.leader-name { font-weight: 600; color: var(--text-primary); }
.leader-id { font-size: 0.75rem; font-family: var(--font-mono); color: var(--text-tertiary); }
.leader-badge { padding: 4px 10px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; text-transform: uppercase; background: rgba(0, 212, 255, 0.15); color: var(--accent-cyan, #00d4ff); }

/* Actions */
.actions-row { display: flex; gap: 12px; flex-wrap: wrap; }
.action-btn { display: flex; align-items: center; gap: 8px; padding: 12px 20px; border-radius: 8px; font-size: 0.9rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.2s; }
.action-btn svg { width: 18px; height: 18px; }
.action-btn.secondary { background: var(--bg-tertiary); color: var(--text-primary); border: 1px solid var(--border-subtle); }
.action-btn.secondary:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); }
.action-btn.primary { background: linear-gradient(135deg, var(--accent-cyan, #00d4ff) 0%, var(--accent-emerald, #00ff88) 100%); color: var(--bg-primary); }
.action-btn.primary:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0, 212, 255, 0.3); }
.action-btn.primary:disabled { opacity: 0.6; cursor: not-allowed; }
.action-btn.compact { padding: 8px 16px; font-size: 0.85rem; }

/* Run card */
.run-card .card-header { border-bottom: none; padding-bottom: 0; }
.test-run-badge { font-size: 0.7rem; font-weight: 600; text-transform: uppercase; padding: 3px 8px; border-radius: 4px; background: rgba(245, 158, 11, 0.15); color: #f59e0b; letter-spacing: 0.03em; }
.test-run-info { padding: 8px 20px; font-size: 0.82rem; color: var(--text-secondary, #888); line-height: 1.4; }
.run-body { display: flex; gap: 12px; padding: 12px 20px 16px; align-items: center; }
.run-body .form-input { flex: 1; }

/* Cards */
.card { overflow: hidden; }
.card-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border-subtle); }
.card-header h3 { font-size: 0.95rem; font-weight: 600; color: var(--text-primary); }
.card-count { font-size: 0.75rem; color: var(--text-tertiary); background: var(--bg-tertiary); padding: 4px 8px; border-radius: 4px; }

/* Agent Assignments */
.agent-assignments-list { display: flex; flex-direction: column; }
.agent-assignment-card { border-bottom: 1px solid var(--border-subtle); }
.agent-assignment-card:last-child { border-bottom: none; }
.agent-assignment-header { display: flex; align-items: center; gap: 12px; padding: 14px 20px; cursor: pointer; transition: background 0.15s; }
.agent-assignment-header:hover { background: var(--bg-tertiary); }
.agent-avatar.is-agent { width: 36px; height: 36px; border-radius: 50%; background: linear-gradient(135deg, var(--accent-cyan, #00d4ff), var(--accent-emerald, #00ff88)); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.agent-avatar.is-agent svg { width: 16px; height: 16px; color: var(--bg-primary); }
.agent-assignment-info { flex: 1; display: flex; flex-direction: column; gap: 2px; }
.agent-assignment-name { font-weight: 500; color: var(--text-primary); font-size: 0.9rem; }
.agent-assignment-id { font-size: 0.7rem; font-family: var(--font-mono); color: var(--text-tertiary); }
.expand-chevron { width: 16px; height: 16px; color: var(--text-tertiary); transition: transform 0.2s; flex-shrink: 0; }
.expand-chevron.expanded { transform: rotate(180deg); }
.agent-assignment-body { padding: 8px 20px 16px 68px; }

/* Shared layout */
.header-left { display: flex; align-items: center; gap: 12px; }
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 2rem; }
.empty-state span { font-size: 0.85rem; color: var(--text-tertiary); }

/* Info Grid */
.info-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; padding: 20px; }
.info-item { display: flex; flex-direction: column; gap: 4px; }
.info-label { font-size: 0.75rem; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.05em; }
.info-value { font-size: 0.9rem; color: var(--text-primary); }
.info-value.mono { font-family: var(--font-mono); font-size: 0.8rem; }
.color-preview { display: flex; align-items: center; gap: 8px; }
.color-swatch { width: 20px; height: 20px; border-radius: 4px; border: 1px solid var(--border-subtle); }

/* Form & Visual Builder */
.form-input { width: 100%; padding: 10px 14px; background: var(--bg-tertiary); border: 1px solid var(--border-subtle); border-radius: 6px; color: var(--text-primary); font-size: 0.9rem; transition: border-color 0.2s; }
.form-input:focus { outline: none; border-color: var(--accent-cyan); }
.visual-builder-btn { display: flex; align-items: center; gap: 8px; padding: 12px 20px; border-radius: 8px; background: linear-gradient(135deg, rgba(0, 212, 255, 0.15), rgba(168, 85, 247, 0.15)); color: var(--accent-cyan); border: 1px solid rgba(0, 212, 255, 0.3); font-size: 0.9rem; font-weight: 500; cursor: pointer; transition: all 0.2s; }
.visual-builder-btn svg { width: 18px; height: 18px; }
.visual-builder-btn:hover:not(:disabled) { background: linear-gradient(135deg, rgba(0, 212, 255, 0.25), rgba(168, 85, 247, 0.25)); border-color: var(--accent-cyan); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0, 212, 255, 0.2); }
.visual-builder-btn:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
