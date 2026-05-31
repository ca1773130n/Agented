<script setup lang="ts">
import { ref, watch, onMounted } from 'vue';
import type { RouteLocationRaw } from 'vue-router';
import type { SuperAgent, TeamMember, Agent } from '../../services/api';
import { superAgentApi, teamApi, agentApi } from '../../services/api';
import { useToast } from '../../composables/useToast';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();

const props = defineProps<{
  superAgentId: string;
  teamId: string | null;
}>();

/**
 * Resolve a team member to a router link target. Super-agent teammates
 * jump straight to their playground (the most useful destination from
 * here — that's where you'd start a chat with them). Bare-agent
 * members route to the agent detail page. The current SA's own card
 * (if it's listed as a team member) returns null so we don't render
 * a self-link. Manually-described members without an id return null
 * too; they stay as plain cards.
 */
function memberLinkTarget(member: TeamMember): RouteLocationRaw | null {
  if (member.super_agent_id && member.super_agent_id !== props.superAgentId) {
    return {
      name: 'super-agent-playground',
      params: { superAgentId: member.super_agent_id },
    };
  }
  if (member.agent_id) {
    return { name: 'agent-design', params: { agentId: member.agent_id } };
  }
  return null;
}

function childAgentLink(saId: string): RouteLocationRaw {
  return { name: 'super-agent-playground', params: { superAgentId: saId } };
}

const showToast = useToast();

const teamMembers = ref<TeamMember[]>([]);
const childAgents = ref<SuperAgent[]>([]);
const isLoading = ref(true);
const showAddMemberModal = ref(false);
const availableAgents = ref<Agent[]>([]);
const selectedAgentId = ref('');
const isAddingMember = ref(false);

async function loadComposition() {
  isLoading.value = true;

  try {
    // Load team members if this SuperAgent has a team
    if (props.teamId) {
      try {
        const teamResult = await teamApi.listMembers(props.teamId);
        teamMembers.value = teamResult.members || [];
      } catch {
        teamMembers.value = [];
      }
    } else {
      teamMembers.value = [];
    }

    // Load child SuperAgents (those with parent_super_agent_id === this agent)
    try {
      const saResult = await superAgentApi.list();
      childAgents.value = (saResult.super_agents || []).filter(
        (sa) => sa.parent_super_agent_id === props.superAgentId,
      );
    } catch {
      childAgents.value = [];
    }
  } finally {
    isLoading.value = false;
  }
}

async function openAddMemberModal() {
  showAddMemberModal.value = true;
  selectedAgentId.value = '';
  try {
    const data = await agentApi.list();
    availableAgents.value = data.agents || [];
  } catch {
    availableAgents.value = [];
  }
}

async function addMember() {
  if (!props.teamId || !selectedAgentId.value) return;
  isAddingMember.value = true;
  try {
    const agent = availableAgents.value.find(a => a.id === selectedAgentId.value);
    await teamApi.addMember(props.teamId, {
      name: agent?.name || selectedAgentId.value,
      agent_id: selectedAgentId.value,
      role: 'member',
    });
    showToast(t('subagentComposition.memberAdded'), 'success');
    showAddMemberModal.value = false;
    selectedAgentId.value = '';
    await loadComposition();
  } catch {
    showToast(t('subagentComposition.addError'), 'error');
  } finally {
    isAddingMember.value = false;
  }
}

async function removeMember(member: TeamMember) {
  if (!props.teamId) return;
  try {
    await teamApi.removeMember(props.teamId, member.id);
    showToast(t('subagentComposition.memberRemoved'), 'success');
    await loadComposition();
  } catch {
    showToast(t('subagentComposition.removeError'), 'error');
  }
}

watch(
  () => [props.superAgentId, props.teamId],
  () => loadComposition(),
);

onMounted(loadComposition);
</script>

<template>
  <div class="subagent-composition">
    <div class="section-header">
      <h3 class="section-title">{{ t('subagentComposition.title') }}</h3>
      <button v-if="teamId" class="btn-add-member" @click="openAddMemberModal">
        + {{ t('subagentComposition.addMember') }}
      </button>
    </div>

    <div v-if="isLoading" class="composition-loading">
      <div class="loading-spinner"></div>
      <span>{{ t('subagentComposition.loading') }}</span>
    </div>

    <template v-else>
      <!-- Team Members -->
      <div v-if="teamMembers.length > 0" class="composition-section">
        <h4 class="subsection-title">{{ t('subagentComposition.teamMembers') }}</h4>
        <div class="member-list">
          <component
            :is="memberLinkTarget(member) ? 'router-link' : 'div'"
            v-for="member in teamMembers"
            :key="member.id"
            :to="memberLinkTarget(member) ?? undefined"
            class="member-card"
            :class="{ 'member-card--linkable': memberLinkTarget(member) }"
          >
            <div class="member-avatar">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/>
                <circle cx="12" cy="7" r="4"/>
              </svg>
            </div>
            <div class="member-info">
              <span class="member-name">{{ member.name }}</span>
              <span class="member-role">{{ member.role || t('subagentComposition.roleMember') }}</span>
            </div>
            <button
              class="remove-member-btn"
              :title="t('subagentComposition.removeFromTeam')"
              @click.stop.prevent="removeMember(member)"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </component>
        </div>
      </div>

      <!-- Child SuperAgents -->
      <div v-if="childAgents.length > 0" class="composition-section">
        <h4 class="subsection-title">{{ t('subagentComposition.childSuperAgents') }}</h4>
        <div class="member-list">
          <component
            :is="agent.id !== superAgentId ? 'router-link' : 'div'"
            v-for="agent in childAgents"
            :key="agent.id"
            :to="agent.id !== superAgentId ? childAgentLink(agent.id) : undefined"
            class="member-card"
            :class="{ 'member-card--linkable': agent.id !== superAgentId }"
          >
            <div class="member-avatar agent-avatar">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <circle cx="12" cy="8" r="4"/>
                <path d="M6 21v-2a4 4 0 014-4h4a4 4 0 014 4v2"/>
                <path d="M17 3l2 2-2 2M7 3l-2 2 2 2"/>
              </svg>
            </div>
            <div class="member-info">
              <span class="member-name">{{ agent.name }}</span>
              <div class="member-meta">
                <span :class="['backend-badge', `backend-${agent.backend_type}`]">
                  {{ agent.backend_type }}
                </span>
                <span :class="['status-indicator', agent.enabled ? 'active' : 'inactive']">
                  {{ agent.enabled ? t('subagentComposition.active') : t('subagentComposition.inactive') }}
                </span>
              </div>
            </div>
          </component>
        </div>
      </div>

      <!-- Empty state -->
      <div v-if="teamMembers.length === 0 && childAgents.length === 0" class="empty-state">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/>
          <circle cx="9" cy="7" r="4"/>
          <path d="M23 21v-2a4 4 0 00-3-3.87"/>
          <path d="M16 3.13a4 4 0 010 7.75"/>
        </svg>
        <p>{{ t('subagentComposition.empty') }}</p>
      </div>
    </template>

    <!-- Add Member Modal -->
    <Teleport to="body">
      <div v-if="showAddMemberModal" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-add-member" tabindex="-1" @click.self="showAddMemberModal = false" @keydown.escape="showAddMemberModal = false">
        <div class="modal modal-small">
          <div class="modal-header">
            <h2 id="modal-title-add-member">{{ t('subagentComposition.addModalTitle') }}</h2>
            <button class="modal-close" @click="showAddMemberModal = false">&times;</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label>{{ t('subagentComposition.selectAgent') }}</label>
              <select v-model="selectedAgentId">
                <option value="" disabled>{{ t('subagentComposition.chooseAgent') }}</option>
                <option v-for="agent in availableAgents" :key="agent.id" :value="agent.id">
                  {{ agent.name }}
                </option>
              </select>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn" @click="showAddMemberModal = false">{{ t('common.cancel') }}</button>
            <button class="btn btn-primary" :disabled="!selectedAgentId || isAddingMember" @click="addMember">
              {{ isAddingMember ? t('subagentComposition.adding') : t('subagentComposition.addMember') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.subagent-composition {
  padding: 8px 0;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.btn-add-member {
  padding: 4px 12px;
  background: transparent;
  border: 1px solid var(--accent-cyan, #00d4ff);
  border-radius: 6px;
  color: var(--accent-cyan, #00d4ff);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-add-member:hover {
  background: rgba(0, 212, 255, 0.1);
}

.composition-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px;
  color: var(--text-secondary);
  font-size: 14px;
}

.loading-spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border-default);
  border-top-color: var(--accent-violet);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.composition-section {
  margin-bottom: 20px;
}

.subsection-title {
  margin: 0 0 10px 0;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.member-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.member-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  transition: background 0.15s, border-color 0.15s;
  border: 1px solid transparent;
  text-decoration: none;
  color: inherit;
}

.member-card:hover {
  background: var(--bg-elevated, rgba(255, 255, 255, 0.05));
}

/* Linkable cards (clickable teammates) get a subtle pointer + accent
   ring on hover so the user can tell which cards jump to a playground
   vs. which are plain text (manual members, self). */
.member-card--linkable { cursor: pointer; }
.member-card--linkable:hover {
  border-color: var(--accent-cyan, rgba(0, 212, 255, 0.6));
}

.member-avatar {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  background: var(--accent-cyan-dim, rgba(0, 212, 255, 0.15));
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.member-avatar svg {
  width: 16px;
  height: 16px;
  color: var(--accent-cyan);
}

.member-avatar.agent-avatar {
  background: var(--accent-violet-dim, rgba(136, 85, 255, 0.15));
}

.member-avatar.agent-avatar svg {
  color: var(--accent-violet);
}

.member-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.member-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.member-role {
  font-size: 12px;
  color: var(--text-tertiary);
  text-transform: capitalize;
}

.member-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.backend-badge {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 3px;
  font-weight: 500;
  text-transform: uppercase;
}

.backend-claude {
  background: rgba(255, 136, 0, 0.15);
  color: #ff8800;
}

.backend-opencode {
  background: rgba(0, 136, 255, 0.15);
  color: #0088ff;
}

.backend-gemini {
  background: rgba(52, 168, 83, 0.15);
  color: #34a853;
}

.backend-codex {
  background: rgba(136, 85, 255, 0.15);
  color: #8855ff;
}

.status-indicator {
  font-size: 11px;
}

.status-indicator.active {
  color: var(--accent-emerald, #00ff88);
}

.status-indicator.inactive {
  color: var(--text-tertiary);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  text-align: center;
}

.empty-state svg {
  width: 40px;
  height: 40px;
  color: var(--text-tertiary);
  margin-bottom: 12px;
}

.empty-state p {
  margin: 0;
  color: var(--text-tertiary);
  font-size: 14px;
}

.remove-member-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: transparent;
  border: none;
  border-radius: 4px;
  color: var(--text-tertiary);
  cursor: pointer;
  opacity: 0;
  transition: all 0.15s;
  flex-shrink: 0;
  margin-left: auto;
}

.member-card:hover .remove-member-btn {
  opacity: 1;
}

.remove-member-btn:hover {
  background: var(--accent-crimson-dim, rgba(255, 51, 102, 0.15));
  color: var(--accent-crimson, #ff3366);
}

/* Modal styles */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  width: 90%;
  max-width: 480px;
}

.modal-small {
  max-width: 400px;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
}

.modal-header h2 {
  font-size: 1.1rem;
  font-weight: 600;
  margin: 0;
  color: var(--text-primary);
}

.modal-close {
  background: none;
  border: none;
  color: var(--text-tertiary);
  font-size: 1.5rem;
  cursor: pointer;
  line-height: 1;
}

.modal-body {
  padding: 20px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 16px 20px;
  border-top: 1px solid var(--border-default);
}
</style>
