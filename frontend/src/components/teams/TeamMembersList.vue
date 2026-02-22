<script setup lang="ts">
import { ref } from 'vue';
import type { Team, Agent } from '../../services/api';
import { teamApi, agentApi, ApiError } from '../../services/api';
import ConfirmModal from '../base/ConfirmModal.vue';
import { useToast } from '../../composables/useToast';
import { useFocusTrap } from '../../composables/useFocusTrap';

const props = defineProps<{
  team: Team;
  teamId: string;
}>();

const emit = defineEmits<{
  (e: 'member-added'): void;
  (e: 'member-removed'): void;
  (e: 'navigateToAgentDesign', agentId: string): void;
}>();

const showToast = useToast();

// Add Member modal state
const showAddMemberModal = ref(false);
const addMemberModalRef = ref<HTMLElement | null>(null);
useFocusTrap(addMemberModalRef, showAddMemberModal);
const agents = ref<Agent[]>([]);
const newMember = ref({
  name: '',
  email: '',
  role: 'member' as 'member' | 'senior' | 'lead',
  layer: 'backend' as 'frontend' | 'backend' | 'devops' | 'fullstack',
  agent_id: '',
});
const isAddingMember = ref(false);

// Confirm remove member state
const showRemoveMemberConfirm = ref(false);
const pendingRemoveMemberId = ref<number | null>(null);

function getLayerClass(layer: string): string {
  switch (layer) {
    case 'frontend': return 'layer-frontend';
    case 'backend': return 'layer-backend';
    case 'devops': return 'layer-devops';
    case 'fullstack': return 'layer-fullstack';
    default: return '';
  }
}

async function openAddMemberModal() {
  showAddMemberModal.value = true;
  newMember.value = { name: '', email: '', role: 'member', layer: 'backend', agent_id: '' };
  try {
    const data = await agentApi.list();
    agents.value = data.agents || [];
  } catch (err) {
    showToast('Failed to load agents', 'error');
  }
}

function onAgentSelect(agentId: string) {
  newMember.value.agent_id = agentId;
  const agent = agents.value.find(a => a.id === agentId);
  if (agent) {
    newMember.value.name = agent.name;
  }
}

async function addMember() {
  if (!newMember.value.name) {
    showToast('Member name is required', 'error');
    return;
  }
  isAddingMember.value = true;
  try {
    await teamApi.addMember(props.teamId, {
      name: newMember.value.name,
      email: newMember.value.email || undefined,
      role: newMember.value.role,
      layer: newMember.value.layer,
      agent_id: newMember.value.agent_id || undefined,
    });
    showToast('Member added successfully', 'success');
    showAddMemberModal.value = false;
    emit('member-added');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to add member';
    showToast(message, 'error');
  } finally {
    isAddingMember.value = false;
  }
}

function removeMember(memberId: number) {
  pendingRemoveMemberId.value = memberId;
  showRemoveMemberConfirm.value = true;
}

async function confirmRemoveMember() {
  const memberId = pendingRemoveMemberId.value;
  showRemoveMemberConfirm.value = false;
  pendingRemoveMemberId.value = null;
  if (memberId === null) return;
  try {
    await teamApi.removeMember(props.teamId, memberId);
    showToast('Member removed', 'success');
    emit('member-removed');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to remove member';
    showToast(message, 'error');
  }
}
</script>

<template>
  <!-- Team Members Card -->
  <div class="card">
    <div class="card-header">
      <div class="header-left">
        <h3>Team Members</h3>
        <span class="card-count">{{ team.members?.length || 0 }} members</span>
      </div>
      <button class="add-btn" @click="openAddMemberModal">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 5v14M5 12h14"/>
        </svg>
        Add Member
      </button>
    </div>

    <div v-if="!team.members || team.members.length === 0" class="empty-state">
      <div class="empty-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
          <circle cx="9" cy="7" r="4"/>
          <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
          <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
        </svg>
      </div>
      <p>No members yet</p>
      <span>Add members to this team from the Teams page</span>
    </div>

    <div v-else class="members-list">
      <div v-for="member in team.members" :key="member.id" class="member-row">
        <div class="member-avatar" :class="{ 'is-agent': member.agent_id }">
          <svg v-if="member.agent_id" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="8" r="4"/>
            <path d="M20 21a8 8 0 1 0-16 0"/>
          </svg>
          <span v-else>{{ member.name.charAt(0).toUpperCase() }}</span>
        </div>
        <div class="member-info">
          <span
            v-if="member.agent_id"
            class="member-name entity-link"
            @click="emit('navigateToAgentDesign', member.agent_id!)"
          >{{ member.name }}</span>
          <span v-else class="member-name">{{ member.name }}</span>
          <span v-if="member.agent_id" class="member-agent-id">{{ member.agent_id }}</span>
          <span v-else-if="member.email" class="member-email">{{ member.email }}</span>
          <span v-if="member.role" class="member-description">{{ member.role }}</span>
        </div>
        <div class="member-badges">
          <span v-if="member.agent_id" class="badge agent-badge">Agent</span>
          <span v-if="member.layer" class="badge" :class="getLayerClass(member.layer)">{{ member.layer }}</span>
        </div>
        <button class="remove-btn" @click="removeMember(member.id)" title="Remove member">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 6L6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>
    </div>
  </div>

  <!-- Add Member Modal -->
  <div v-if="showAddMemberModal" ref="addMemberModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-add-member" tabindex="-1" @click.self="showAddMemberModal = false" @keydown.escape="showAddMemberModal = false">
    <div class="modal">
      <div class="modal-header">
        <h3 id="modal-title-add-member">Add Team Member</h3>
        <button class="modal-close" @click="showAddMemberModal = false">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 6L6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>
      <div class="modal-body">
        <!-- Agent Selection -->
        <div class="form-group">
          <label for="member-agent">Select Agent (optional)</label>
          <select id="member-agent" v-model="newMember.agent_id" class="form-select" @change="onAgentSelect(newMember.agent_id)">
            <option value="">-- No agent (manual entry) --</option>
            <option v-for="agent in agents" :key="agent.id" :value="agent.id">
              {{ agent.name }}
            </option>
          </select>
          <span class="form-hint">Select an agent to auto-fill name, or leave empty for manual entry</span>
        </div>

        <!-- Name -->
        <div class="form-group">
          <label for="member-name">Name *</label>
          <input id="member-name" v-model="newMember.name" type="text" class="form-input" placeholder="Member name" :disabled="!!newMember.agent_id">
        </div>

        <!-- Email -->
        <div class="form-group">
          <label for="member-email">Email</label>
          <input id="member-email" v-model="newMember.email" type="email" class="form-input" placeholder="member@example.com">
        </div>

        <!-- Role -->
        <div class="form-group">
          <label for="member-role">Role</label>
          <select id="member-role" v-model="newMember.role" class="form-select">
            <option value="member">Member</option>
            <option value="senior">Senior</option>
            <option value="lead">Lead</option>
          </select>
        </div>

        <!-- Layer -->
        <div class="form-group">
          <label for="member-layer">Layer</label>
          <select id="member-layer" v-model="newMember.layer" class="form-select">
            <option value="frontend">Frontend</option>
            <option value="backend">Backend</option>
            <option value="devops">DevOps</option>
            <option value="fullstack">Fullstack</option>
          </select>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-secondary" @click="showAddMemberModal = false">Cancel</button>
        <button class="btn btn-primary" :disabled="!newMember.name || isAddingMember" @click="addMember">
          <span v-if="isAddingMember">Adding...</span>
          <span v-else>Add Member</span>
        </button>
      </div>
    </div>
  </div>

  <ConfirmModal
    :open="showRemoveMemberConfirm"
    title="Remove Member"
    message="Are you sure you want to remove this member?"
    confirm-label="Remove"
    variant="danger"
    @confirm="confirmRemoveMember"
    @cancel="showRemoveMemberConfirm = false"
  />
</template>

<style scoped>
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

/* Header with button */
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.add-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.add-btn svg {
  width: 14px;
  height: 14px;
}

.add-btn:hover {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}

/* Members List */
.members-list {
  display: flex;
  flex-direction: column;
}

.member-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.member-row:last-child {
  border-bottom: none;
}

.member-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--accent-violet, #8855ff), var(--accent-cyan, #00d4ff));
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.member-avatar span {
  font-size: 1rem;
  font-weight: 600;
  color: white;
}

.member-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.member-name {
  font-weight: 500;
  color: var(--text-primary);
}

.member-email {
  font-size: 0.8rem;
  color: var(--text-tertiary);
}

.member-agent-id {
  font-size: 0.75rem;
  font-family: var(--font-mono);
  color: var(--text-tertiary);
}

.member-description {
  font-size: 0.8rem;
  color: var(--text-secondary);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.member-avatar.is-agent {
  background: linear-gradient(135deg, var(--accent-cyan, #00d4ff), var(--accent-emerald, #00ff88));
}

.member-avatar.is-agent svg {
  width: 18px;
  height: 18px;
  color: var(--bg-primary);
}

.agent-badge {
  background: rgba(0, 212, 255, 0.15) !important;
  color: var(--accent-cyan, #00d4ff) !important;
}

.member-badges {
  display: flex;
  gap: 8px;
}

.badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: capitalize;
  flex-shrink: 0;
  white-space: nowrap;
}

.layer-frontend {
  background: rgba(0, 212, 255, 0.15);
  color: #00d4ff;
}

.layer-backend {
  background: rgba(0, 255, 136, 0.15);
  color: #00ff88;
}

.layer-devops {
  background: rgba(255, 136, 0, 0.15);
  color: #ff8800;
}

.layer-fullstack {
  background: rgba(136, 85, 255, 0.15);
  color: #8855ff;
}

/* Empty State */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
}

.empty-icon {
  width: 48px;
  height: 48px;
  color: var(--text-muted);
  margin-bottom: 12px;
}

.empty-icon svg {
  width: 100%;
  height: 100%;
}

.empty-state span {
  font-size: 0.85rem;
  color: var(--text-tertiary);
}

/* Remove button */
.remove-btn {
  width: 28px;
  height: 28px;
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  flex-shrink: 0;
}

.remove-btn:hover {
  background: rgba(255, 85, 85, 0.15);
  color: #ff5555;
}

.remove-btn svg {
  width: 16px;
  height: 16px;
}

/* Modal */
.modal {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  width: 90%;
  max-width: 480px;
  animation: slideUp 0.3s ease;
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.modal-header h3 {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.modal-close {
  width: 32px;
  height: 32px;
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.modal-close:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.modal-close svg {
  width: 18px;
  height: 18px;
}

/* Form Elements */
.form-input,
.form-select {
  width: 100%;
  padding: 10px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.9rem;
  transition: border-color 0.2s;
}

.form-input:focus,
.form-select:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.form-input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.form-select option {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.form-hint {
  font-size: 0.8rem;
  color: var(--text-tertiary);
  margin-top: 0.35rem;
  display: block;
}

/* Buttons */
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
</style>
