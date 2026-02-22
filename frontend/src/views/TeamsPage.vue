<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import type { Team, Agent, TopologyType, GeneratedTeamConfig } from '../services/api';
import { teamApi, agentApi, ApiError } from '../services/api';
import TopologyPicker from '../components/teams/TopologyPicker.vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import EmptyState from '../components/base/EmptyState.vue';
import ErrorState from '../components/base/ErrorState.vue';
import ListSearchSort from '../components/base/ListSearchSort.vue';
import PaginationBar from '../components/base/PaginationBar.vue';
import ConfirmModal from '../components/base/ConfirmModal.vue';
import TeamConfigReview from '../components/teams/TeamConfigReview.vue';
import AiStreamingLog from '../components/ai/AiStreamingLog.vue';
import { useStreamingGeneration } from '../composables/useStreamingGeneration';
import { useToast } from '../composables/useToast';
import { useListFilter } from '../composables/useListFilter';
import { useFocusTrap } from '../composables/useFocusTrap';
import { usePagination } from '../composables/usePagination';
import { useWebMcpPageTools } from '../webmcp/useWebMcpPageTools';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const router = useRouter();
const showToast = useToast();

const teams = ref<Team[]>([]);
const agents = ref<Agent[]>([]);
const isLoading = ref(true);
const loadError = ref<string | null>(null);
const showCreateModal = ref(false);
const showDeleteConfirm = ref(false);
const teamToDelete = ref<Team | null>(null);
const deletingId = ref<string | null>(null);
const { searchQuery, sortField, sortOrder, filteredAndSorted, hasActiveFilter, resultCount, totalCount } = useListFilter({
  items: teams,
  searchFields: ['name', 'description'] as (keyof Team)[],
  storageKey: 'teams-list-filter',
});

const pagination = usePagination({ defaultPageSize: 25, storageKey: 'teams-pagination' });

const sortOptions = [
  { value: 'name', label: 'Name' },
  { value: 'created_at', label: 'Date Created' },
];

// Form state
const newTeam = ref({ name: '', description: '', color: '#00d4ff', leader_id: '' });
const selectedTopology = ref<TopologyType | null>('coordinator');
const topologyConfig = ref('{}');

// AI Generation state
const showGenerateModal = ref(false);
const generateDescription = ref('');
const isGenerating = ref(false);
const showConfigReview = ref(false);
const generatedConfig = ref<GeneratedTeamConfig | null>(null);
const generatedWarnings = ref<string[]>([]);
const isSavingGenerated = ref(false);
const { log: generateLog, phase: generatePhase, startStream } = useStreamingGeneration();

// Modal overlay refs for Escape key handling
const configReviewOverlay = ref<HTMLElement | null>(null);
const createModalOverlay = ref<HTMLElement | null>(null);
const generateModalOverlay = ref<HTMLElement | null>(null);
useFocusTrap(configReviewOverlay, showConfigReview);
useFocusTrap(createModalOverlay, showCreateModal);
useFocusTrap(generateModalOverlay, showGenerateModal);

watch(showConfigReview, (val) => { if (val) nextTick(() => configReviewOverlay.value?.focus()); });
watch(showCreateModal, (val) => { if (val) nextTick(() => createModalOverlay.value?.focus()); });
watch(showGenerateModal, (val) => { if (val) nextTick(() => generateModalOverlay.value?.focus()); });

useWebMcpPageTools({
  page: 'TeamsPage',
  domain: 'teams',
  stateGetter: () => ({
    items: teams.value,
    itemCount: teams.value.length,
    isLoading: isLoading.value,
    error: loadError.value,
    searchQuery: searchQuery.value,
    sortField: sortField.value,
    sortOrder: sortOrder.value,
    currentPage: pagination.currentPage.value,
    pageSize: pagination.pageSize.value,
    totalCount: pagination.totalCount.value,
    selectedTopology: selectedTopology.value,
    topologyConfig: topologyConfig.value,
  }),
  modalGetter: () => ({
    showCreateModal: showCreateModal.value,
    showDeleteConfirm: showDeleteConfirm.value,
    formValues: newTeam.value,
  }),
  modalActions: {
    openCreate: () => { showCreateModal.value = true; },
    openDelete: (id: string) => {
      const team = teams.value.find((t: any) => t.id === id);
      if (team) { teamToDelete.value = team; showDeleteConfirm.value = true; }
    },
  },
  deps: [teams, searchQuery, sortField, sortOrder],
});

useWebMcpTool({
  name: 'hive_teams_perform_search',
  description: 'Sets the search query on the teams list',
  page: 'TeamsPage',
  inputSchema: { type: 'object', properties: { query: { type: 'string', description: 'Search text' } }, required: ['query'] },
  execute: async (args: Record<string, unknown>) => {
    searchQuery.value = (args.query as string) || '';
    return { content: [{ type: 'text' as const, text: JSON.stringify({ success: true, searchQuery: searchQuery.value }) }] };
  },
});

function getTopologyLabel(t?: TopologyType): string {
  if (!t) return '';
  const labels: Record<TopologyType, string> = {
    sequential: 'Sequential',
    parallel: 'Parallel',
    coordinator: 'Coordinator',
    generator_critic: 'Gen/Critic',
    hierarchical: 'Hierarchical',
    human_in_loop: 'Human-in-Loop',
    composite: 'Composite',
  };
  return labels[t] || t;
}

function getTriggerLabel(t?: string): string {
  if (!t) return '';
  const labels: Record<string, string> = {
    webhook: 'Webhook',
    github: 'GitHub',
    manual: 'Manual',
    scheduled: 'Scheduled',
  };
  return labels[t] || t;
}

async function loadTeams() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const data = await teamApi.list({ limit: pagination.pageSize.value, offset: pagination.offset.value });
    teams.value = data.teams || [];
    if (data.total_count != null) pagination.totalCount.value = data.total_count;
  } catch (e) {
    loadError.value = e instanceof ApiError ? e.message : 'Failed to load teams';
    showToast(loadError.value, 'error');
  } finally {
    isLoading.value = false;
  }
}

watch([() => pagination.currentPage.value, () => pagination.pageSize.value], () => { loadTeams(); });
watch([searchQuery, sortField, sortOrder], () => { pagination.resetToFirstPage(); });

async function loadAgents() {
  try {
    const data = await agentApi.list();
    agents.value = data.agents || [];
  } catch {
    agents.value = [];
  }
}

async function createTeam() {
  if (!newTeam.value.name.trim()) {
    showToast('Team name is required', 'error');
    return;
  }
  if (!selectedTopology.value) {
    showToast('Topology is required', 'error');
    return;
  }
  try {
    const result = await teamApi.create({
      name: newTeam.value.name,
      description: newTeam.value.description || undefined,
      color: newTeam.value.color || undefined,
      leader_id: newTeam.value.leader_id || undefined,
    });
    // If topology was selected, update it after team creation
    if (selectedTopology.value && result.team?.id) {
      try {
        await teamApi.updateTopology(result.team.id, {
          topology: selectedTopology.value,
          topology_config: topologyConfig.value,
        });
      } catch {
        showToast('Team created but topology could not be saved', 'info');
      }
    }
    showToast('Team created successfully', 'success');
    showCreateModal.value = false;
    newTeam.value = { name: '', description: '', color: '#00d4ff', leader_id: '' };
    selectedTopology.value = 'coordinator';
    topologyConfig.value = '{}';
    await loadTeams();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to create team', 'error');
    }
  }
}

function confirmDelete(team: Team) {
  teamToDelete.value = team;
  showDeleteConfirm.value = true;
}

async function deleteTeam() {
  if (!teamToDelete.value) return;
  deletingId.value = teamToDelete.value.id;
  try {
    await teamApi.delete(teamToDelete.value.id);
    showToast(`Team "${teamToDelete.value.name}" deleted`, 'success');
    showDeleteConfirm.value = false;
    teamToDelete.value = null;
    await loadTeams();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to delete team', 'error');
    }
  } finally {
    deletingId.value = null;
  }
}

// AI Generation flow
function openGenerateModal() {
  generateDescription.value = '';
  showGenerateModal.value = true;
}

async function generateTeamConfig() {
  if (!generateDescription.value.trim() || generateDescription.value.trim().length < 10) {
    showToast('Please provide a description of at least 10 characters', 'error');
    return;
  }

  isGenerating.value = true;

  try {
    const result = await startStream<{ config: GeneratedTeamConfig; warnings: string[] }>(
      '/admin/teams/generate/stream',
      { description: generateDescription.value.trim() },
    );

    if (result) {
      generatedConfig.value = result.config;
      generatedWarnings.value = result.warnings || [];
      showGenerateModal.value = false;
      showConfigReview.value = true;
    }
  } catch (e) {
    showToast('Failed to generate team configuration', 'error');
  } finally {
    isGenerating.value = false;
  }
}

async function saveGeneratedConfig(config: GeneratedTeamConfig) {
  isSavingGenerated.value = true;
  try {
    // 1. Create the team
    const result = await teamApi.create({
      name: config.name,
      description: config.description || undefined,
      color: config.color || undefined,
    });

    const teamId = result.team?.id;
    if (!teamId) {
      showToast('Team creation failed', 'error');
      return;
    }

    // 2. Set topology if provided
    if (config.topology) {
      try {
        await teamApi.updateTopology(teamId, {
          topology: config.topology,
          topology_config: JSON.stringify(config.topology_config || {}),
        });
      } catch {
        showToast('Team created but topology could not be saved', 'info');
      }
    }

    // 3. Process each agent — create new agents if needed, then add as members
    for (const agentCfg of config.agents) {
      let agentId = agentCfg.agent_id;

      // Auto-create agent if agent_id is null (AI suggested a new agent)
      if (!agentId) {
        try {
          const agentResult = await agentApi.create({
            name: agentCfg.name,
            role: agentCfg.role || 'member',
            description: `Auto-created for team "${config.name}"`,
          });
          agentId = agentResult.agent_id;
        } catch {
          showToast(`Could not create agent "${agentCfg.name}" — skipping`, 'info');
          continue;
        }
      }

      // Add agent as team member
      try {
        await teamApi.addMember(teamId, {
          name: agentCfg.name,
          role: agentCfg.role || 'member',
          agent_id: agentId,
        });
      } catch {
        // Member may already exist — skip
      }

      // Auto-create skills that need creation, then create all assignments
      for (const assignment of agentCfg.assignments) {
        if (assignment.valid === false) continue;

        // Auto-create skills that don't exist yet
        if (assignment.needs_creation && assignment.entity_type === 'skill') {
          try {
            const resp = await fetch('/api/skills/user', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                skill_name: assignment.entity_id,
                skill_path: `generated/${assignment.entity_id}`,
                description: assignment.entity_name || assignment.entity_id,
              }),
            });
            if (!resp.ok) {
              // Skill creation failed — still try assignment in case it already exists
            }
          } catch {
            // Skill creation failed — still try assignment in case it already exists
          }
        }

        try {
          await teamApi.addAssignment(teamId, agentId, {
            entity_type: assignment.entity_type,
            entity_id: assignment.entity_id,
            entity_name: assignment.entity_name || undefined,
          });
        } catch {
          // Assignment may be duplicate — skip
        }
      }
    }

    showToast('Team created from generated configuration', 'success');
    showConfigReview.value = false;
    generatedConfig.value = null;
    generatedWarnings.value = [];
    await loadTeams();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to save generated team', 'error');
    }
    // Don't close review on error - let user retry
  } finally {
    isSavingGenerated.value = false;
  }
}

function cancelConfigReview() {
  showConfigReview.value = false;
  generatedConfig.value = null;
  generatedWarnings.value = [];
}

onMounted(() => {
  loadTeams();
  loadAgents();
});
</script>

<template>
  <div class="teams-page">
    <!-- Config Review Overlay -->
    <Teleport to="body">
      <div v-if="showConfigReview && generatedConfig" ref="configReviewOverlay" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-config-review" tabindex="-1" @click.self="cancelConfigReview" @keydown.escape="cancelConfigReview">
        <div class="modal modal-xlarge">
          <div class="modal-header">
            <h2 id="modal-title-config-review">Review Generated Team Configuration</h2>
            <button class="modal-close" @click="cancelConfigReview">&times;</button>
          </div>
          <div class="modal-body">
            <TeamConfigReview
              :config="generatedConfig"
              :warnings="generatedWarnings"
              @save="saveGeneratedConfig"
              @cancel="cancelConfigReview"
            />
          </div>
        </div>
      </div>
    </Teleport>

    <AppBreadcrumb :items="[{ label: 'Teams' }]" />
    <PageHeader title="Teams" subtitle="Manage your organization's teams and their members">
      <template #actions>
        <button class="btn btn-ai" @click="openGenerateModal">
          <span class="ai-badge">AI</span>
          Generate Team
        </button>
        <button class="btn btn-primary" @click="showCreateModal = true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          Create Team
        </button>
      </template>
    </PageHeader>

    <ListSearchSort
      v-if="!isLoading && !loadError && teams.length > 0"
      v-model:searchQuery="searchQuery"
      v-model:sortField="sortField"
      v-model:sortOrder="sortOrder"
      :sort-options="sortOptions"
      :result-count="resultCount"
      :total-count="totalCount"
      placeholder="Search teams..."
    />

    <LoadingState v-if="isLoading" message="Loading teams..." />

    <ErrorState v-else-if="loadError" title="Failed to load teams" :message="loadError" @retry="loadTeams" />

    <EmptyState v-else-if="teams.length === 0" title="No teams yet" description="Create your first team to organize your people">
      <template #actions>
        <button class="btn btn-ai" @click="openGenerateModal">
          <span class="ai-badge">AI</span>
          Generate Team
        </button>
        <button class="btn btn-primary" @click="showCreateModal = true">Create Your First Team</button>
      </template>
    </EmptyState>

    <EmptyState v-else-if="filteredAndSorted.length === 0 && hasActiveFilter" title="No matching teams" description="Try a different search term" />

    <div v-else class="teams-grid">
      <div
        v-for="team in filteredAndSorted"
        :key="team.id"
        class="team-card clickable"
        :style="{ '--team-color': team.color }"
        @click="router.push({ name: 'team-dashboard', params: { teamId: team.id } })"
      >
        <div class="team-header">
          <div class="team-icon" :style="{ background: team.color }">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
              <circle cx="9" cy="7" r="4"/>
              <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
              <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
            </svg>
          </div>
          <div class="team-info">
            <h3>{{ team.name }}</h3>
            <span class="team-id">{{ team.id }}</span>
          </div>
          <div class="member-badge">
            {{ team.member_count }} {{ team.member_count === 1 ? 'member' : 'members' }}
          </div>
        </div>

        <p v-if="team.description" class="team-description">{{ team.description }}</p>

        <div class="team-badges">
          <span v-if="team.topology" class="topology-badge" :class="'topo-' + team.topology">
            {{ getTopologyLabel(team.topology) }}
          </span>
          <span v-else class="topology-badge topo-none">No topology</span>
          <span v-if="team.trigger_source" class="trigger-badge" :class="'trigger-' + team.trigger_source">
            {{ getTriggerLabel(team.trigger_source) }}
          </span>
          <span v-else class="trigger-badge trigger-none">No trigger</span>
          <span v-if="team.enabled !== undefined" class="enabled-dot" :class="{ active: team.enabled === 1 }" :title="team.enabled === 1 ? 'Enabled' : 'Disabled'"></span>
        </div>

        <div v-if="team.leader_name" class="team-leader">
          <span class="leader-label">Leader:</span>
          <span class="leader-name">{{ team.leader_name }}</span>
        </div>

        <div class="team-actions">
          <button class="btn btn-small btn-danger" @click.stop="confirmDelete(team)" :disabled="deletingId === team.id">
            <span v-if="deletingId === team.id" class="btn-spinner"></span>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
            </svg>
            {{ deletingId === team.id ? 'Deleting...' : 'Delete' }}
          </button>
        </div>
      </div>
    </div>

    <PaginationBar
      v-if="!isLoading && !loadError && teams.length > 0"
      v-model:currentPage="pagination.currentPage.value"
      v-model:pageSize="pagination.pageSize.value"
      :total-pages="pagination.totalPages.value"
      :page-size-options="pagination.pageSizeOptions"
      :range-start="pagination.rangeStart.value"
      :range-end="pagination.rangeEnd.value"
      :total-count="pagination.totalCount.value"
      :is-first-page="pagination.isFirstPage.value"
      :is-last-page="pagination.isLastPage.value"
    />

    <!-- Create Modal -->
    <Teleport to="body">
      <div v-if="showCreateModal" ref="createModalOverlay" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-create-team" tabindex="-1" @click.self="showCreateModal = false" @keydown.escape="showCreateModal = false">
        <div class="modal modal-create">
          <div class="modal-header">
            <h2 id="modal-title-create-team">Create Team</h2>
            <button class="modal-close" @click="showCreateModal = false">&times;</button>
          </div>
          <div class="modal-body">
            <div class="create-form">
              <div class="form-row">
                <div class="form-group form-group-grow">
                  <label>Team Name <span class="required">*</span></label>
                  <input v-model="newTeam.name" type="text" placeholder="e.g., Platform Team" class="form-input" />
                </div>
                <div class="form-group form-group-color">
                  <label>Color</label>
                  <div class="color-picker">
                    <input v-model="newTeam.color" type="color" />
                    <span class="color-hex">{{ newTeam.color }}</span>
                  </div>
                </div>
              </div>

              <div class="form-group">
                <label>Description</label>
                <textarea v-model="newTeam.description" placeholder="Describe the team's purpose..." class="form-textarea" rows="2"></textarea>
              </div>

              <div class="form-group">
                <label>Leader (Agent) <span class="required">*</span></label>
                <select v-model="newTeam.leader_id" class="form-select">
                  <option value="">Select a leader agent...</option>
                  <option v-for="agent in agents" :key="agent.id" :value="agent.id">
                    {{ agent.name }}
                  </option>
                </select>
              </div>

              <div class="form-group">
                <label>Topology <span class="required">*</span></label>
                <TopologyPicker
                  v-model="selectedTopology"
                  :team-members="[]"
                  @update:config="topologyConfig = $event"
                />
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showCreateModal = false">Cancel</button>
            <button class="btn btn-primary" :disabled="!newTeam.name.trim() || !selectedTopology" @click="createTeam">Create Team</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Generate Team Modal -->
    <Teleport to="body">
      <div v-if="showGenerateModal" ref="generateModalOverlay" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-generate-team" tabindex="-1" @click.self="!isGenerating && (showGenerateModal = false)" @keydown.escape="!isGenerating && (showGenerateModal = false)">
        <div class="modal modal-large">
          <div class="modal-header">
            <h2 id="modal-title-generate-team">
              <span class="ai-badge ai-badge-header">AI</span>
              Generate Team Configuration
            </h2>
            <button v-if="!isGenerating" class="modal-close" @click="showGenerateModal = false">&times;</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label>Describe the team you want to create</label>
              <textarea
                v-model="generateDescription"
                :disabled="isGenerating"
                placeholder="Describe the team you want to create, e.g., 'A code review team with a senior reviewer that checks code quality and a security specialist that scans for vulnerabilities, running in a sequential pipeline'"
                rows="5"
                class="generate-textarea"
              ></textarea>
            </div>
            <AiStreamingLog
              v-if="isGenerating"
              :log="generateLog"
              :is-streaming="isGenerating"
              :phase="generatePhase || 'Generating team configuration...'"
              hint="Streaming Claude CLI verbose output"
            />
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" :disabled="isGenerating" @click="showGenerateModal = false">Cancel</button>
            <button
              class="btn btn-ai"
              :disabled="isGenerating || generateDescription.trim().length < 10"
              @click="generateTeamConfig"
            >
              <span v-if="isGenerating" class="btn-loading"></span>
              <span class="ai-badge">AI</span>
              {{ isGenerating ? 'Generating...' : 'Generate' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <ConfirmModal
      :open="showDeleteConfirm"
      title="Delete Team"
      :message="`Are you sure you want to delete \u201C${teamToDelete?.name}\u201D? This action cannot be undone.`"
      confirm-label="Delete"
      cancel-label="Cancel"
      variant="danger"
      @confirm="deleteTeam"
      @cancel="showDeleteConfirm = false"
    />

  </div>
</template>

<style scoped>
.teams-page {
}

.btn-ai:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(136, 85, 255, 0.4);
}

.btn-ai:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

.ai-badge-header {
  background: linear-gradient(135deg, var(--accent-violet, #8855ff) 0%, var(--accent-cyan, #00d4ff) 100%);
  color: #fff;
  font-size: 0.7rem;
  padding: 2px 8px;
  border-radius: 4px;
  margin-right: 0.25rem;
}

.btn-secondary {
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-primary, #fff);
  border: 1px solid var(--border-default);
}

.btn-danger {
  background: rgba(255, 77, 77, 0.2);
  color: #ff4d4d;
  border: 1px solid rgba(255, 77, 77, 0.3);
}

.btn-small {
  padding: 0.5rem 0.75rem;
  font-size: 0.85rem;
}

.btn-small svg {
  width: 14px;
  height: 14px;
}

.btn-loading,
.btn-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.teams-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 1.5rem;
}

.team-card.clickable {
  cursor: pointer;
}

.team-card {
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 1.5rem;
  transition: all 0.2s;
}

.team-card:hover {
  border-color: var(--team-color, var(--accent-cyan, #00d4ff));
  box-shadow: 0 0 20px rgba(0, 212, 255, 0.1);
}

.team-header {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 1rem;
}

.team-icon {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.team-icon svg {
  width: 24px;
  height: 24px;
  color: #000;
}

.team-info {
  flex: 1;
  min-width: 0;
}

.team-info h3 {
  font-size: 1.1rem;
  font-weight: 600;
  margin-bottom: 0.25rem;
}

.team-id {
  font-size: 0.75rem;
  color: var(--text-secondary, #888);
  font-family: monospace;
}

.member-badge {
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-secondary, #888);
  padding: 0.25rem 0.75rem;
  border-radius: 20px;
  font-size: 0.8rem;
}

.team-description {
  color: var(--text-secondary, #888);
  font-size: 0.9rem;
  margin-bottom: 1rem;
  line-height: 1.5;
}

.team-leader {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 1rem;
  font-size: 0.85rem;
}

.leader-label {
  color: var(--text-secondary, #888);
}

.leader-name {
  color: var(--accent-cyan, #00d4ff);
  font-weight: 500;
}

.team-actions {
  display: flex;
  gap: 0.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-default);
}

/* Modal styles */

.modal-create {
  max-width: 560px;
  max-height: 85vh;
  padding: 0 !important;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-create .modal-body {
  overflow-y: auto;
  flex: 1 1 0;
  min-height: 0;
  padding: 1.5rem;
  margin-bottom: 0;
}

.modal-create .modal-header,
.modal-create .modal-footer {
  padding: 1rem 1.5rem;
  flex-shrink: 0;
}

.modal-create .modal-header {
  border-bottom: 1px solid var(--border-default);
}

.modal-create .modal-footer {
  border-top: 1px solid var(--border-default);
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}

.modal-large {
  max-width: 700px;
  max-height: 90vh;
  padding: 0 !important;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-large .modal-body {
  overflow-y: auto;
  flex: 1 1 0;
  min-height: 0;
  padding: 1.5rem;
  margin-bottom: 0;
}

.modal-xlarge {
  max-width: 900px;
  max-height: 90vh;
  padding: 0 !important;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-xlarge .modal-body {
  overflow-y: auto;
  flex: 1 1 0;
  min-height: 0;
  padding: 1.5rem;
  margin-bottom: 0;
}

.modal-small {
  max-width: 400px;
}

.modal-large .modal-header,
.modal-xlarge .modal-header {
  padding: 1.25rem 1.5rem;
  margin-bottom: 0;
  border-bottom: 1px solid var(--border-default);
  flex-shrink: 0;
}

.modal-large .modal-footer,
.modal-xlarge .modal-footer {
  padding: 1rem 1.5rem;
  border-top: 1px solid var(--border-default);
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  flex-shrink: 0;
}

.modal-header h2 {
  font-size: 1.25rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.modal-close {
  background: none;
  border: none;
  font-size: 1.5rem;
  color: var(--text-secondary, #888);
  cursor: pointer;
}

/* Create form styles */

.create-form {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.form-row {
  display: flex;
  gap: 1rem;
  align-items: flex-end;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-group-grow {
  flex: 1;
}

.form-group-color {
  flex-shrink: 0;
  width: 140px;
}

.form-group label {
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--text-secondary, #888);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.required {
  color: var(--accent-red, #ff4d4d);
}

.form-input,
.form-textarea,
.form-select {
  width: 100%;
  padding: 0.625rem 0.75rem;
  background: var(--bg-tertiary, #1a1a24);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  color: var(--text-primary, #fff);
  font-size: 0.9rem;
  font-family: inherit;
  transition: border-color 0.15s;
}

.form-input:focus,
.form-textarea:focus,
.form-select:focus {
  outline: none;
  border-color: var(--accent-cyan, #00d4ff);
}

.form-input::placeholder,
.form-textarea::placeholder {
  color: var(--text-tertiary, #555);
}

.form-textarea {
  resize: vertical;
  min-height: 60px;
  line-height: 1.5;
}

.form-select {
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23888' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 0.75rem center;
  padding-right: 2rem;
}

.form-select option {
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-primary, #fff);
}

.color-picker {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0.75rem;
  background: var(--bg-tertiary, #1a1a24);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  height: 42px;
}

.color-picker input[type="color"] {
  width: 32px;
  height: 32px;
  min-width: 32px;
  min-height: 32px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  padding: 0;
  flex-shrink: 0;
  -webkit-appearance: none;
  appearance: none;
}

.color-picker input[type="color"]::-webkit-color-swatch-wrapper {
  padding: 2px;
}

.color-picker input[type="color"]::-webkit-color-swatch {
  border: none;
  border-radius: 4px;
}

.color-hex {
  font-family: 'Geist Mono', monospace;
  font-size: 0.85rem;
  color: var(--text-secondary, #888);
}

.modal-footer .btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.generate-textarea {
  min-height: 140px;
  line-height: 1.5;
}

.generate-textarea:disabled {
  opacity: 0.6;
}

.warning-text {
  color: #ff4d4d;
  font-size: 0.9rem;
  margin-top: 0.5rem;
}

/* Team badges */
.team-badges {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 0.75rem;
  flex-wrap: wrap;
}

.topology-badge, .trigger-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.topo-sequential {
  background: rgba(0, 212, 255, 0.15);
  color: var(--accent-cyan, #00d4ff);
}

.topo-parallel {
  background: rgba(0, 255, 136, 0.15);
  color: var(--accent-emerald, #00ff88);
}

.topo-coordinator {
  background: rgba(136, 85, 255, 0.15);
  color: var(--accent-violet, #8855ff);
}

.topo-generator_critic {
  background: rgba(255, 170, 0, 0.15);
  color: var(--accent-amber, #ffaa00);
}

.topo-none {
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-muted, #404050);
}

.trigger-webhook {
  background: rgba(0, 212, 255, 0.15);
  color: var(--accent-cyan, #00d4ff);
}

.trigger-github {
  background: rgba(136, 85, 255, 0.15);
  color: var(--accent-violet, #8855ff);
}

.trigger-manual {
  background: rgba(0, 255, 136, 0.15);
  color: var(--accent-emerald, #00ff88);
}

.trigger-scheduled {
  background: rgba(255, 170, 0, 0.15);
  color: var(--accent-amber, #ffaa00);
}

.trigger-none {
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-muted, #404050);
}

.enabled-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-muted, #404050);
  margin-left: 4px;
}

.enabled-dot.active {
  background: var(--accent-emerald, #00ff88);
  box-shadow: 0 0 6px rgba(0, 255, 136, 0.4);
}
</style>
