<script setup lang="ts">
import { ref, computed } from 'vue';
import { teamApi, projectApi, ApiError } from '../../services/api';
import { useToast } from '../../composables/useToast';
import { useFocusTrap } from '../../composables/useFocusTrap';

const props = defineProps<{
  projectId: string;
  allTeams: Array<{ id: string; name: string; color: string; is_owner: boolean }>;
  totalTeamCount: number;
  teamRunMessages: Record<string, string>;
  teamRunning: Record<string, boolean>;
}>();

const emit = defineEmits<{
  (e: 'runTeam', teamId: string): void;
  (e: 'navigateToTeamDashboard', teamId: string): void;
  (e: 'update:teamRunMessages', value: Record<string, string>): void;
  (e: 'refresh'): void;
}>();

const showToast = useToast();

// Assign Team modal state
const showAssignModal = ref(false);
const assignModalRef = ref<HTMLElement | null>(null);
useFocusTrap(assignModalRef, showAssignModal);
const availableTeams = ref<Array<{ id: string; name: string; color: string }>>([]);
const selectedTeamId = ref('');
const isAssigning = ref(false);

// Filter out already-assigned teams
const unassignedTeams = computed(() => {
  const assignedIds = new Set(props.allTeams.map(t => t.id));
  return availableTeams.value.filter(t => !assignedIds.has(t.id));
});

async function openAssignModal() {
  showAssignModal.value = true;
  selectedTeamId.value = '';
  try {
    const data = await teamApi.list();
    availableTeams.value = (data.teams || []).map(t => ({
      id: t.id,
      name: t.name,
      color: t.color || '#666',
    }));
  } catch {
    showToast('Failed to load teams', 'error');
  }
}

async function assignTeam() {
  if (!selectedTeamId.value) return;
  isAssigning.value = true;
  try {
    await projectApi.assignTeam(props.projectId, selectedTeamId.value);
    showToast('Team assigned successfully', 'success');
    showAssignModal.value = false;
    emit('refresh');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to assign team';
    showToast(message, 'error');
  } finally {
    isAssigning.value = false;
  }
}

</script>

<template>
  <div class="card">
    <div class="card-header">
      <div class="header-left">
        <h3>Assigned Teams</h3>
        <span class="card-count">{{ totalTeamCount }} teams</span>
      </div>
      <button class="add-btn" @click="openAssignModal">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 5v14M5 12h14"/>
        </svg>
        Assign Team
      </button>
    </div>

    <div v-if="allTeams.length === 0" class="empty-state">
      <div class="empty-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
          <circle cx="9" cy="7" r="4"/>
          <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
          <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
        </svg>
      </div>
      <p>No teams assigned yet</p>
      <button class="btn-inline-assign" @click="openAssignModal">Assign Team</button>
    </div>

    <div v-else class="teams-run-list">
      <div v-for="team in allTeams" :key="team.id" class="team-run-card">
        <div class="team-run-header">
          <div class="team-color" :style="{ background: team.color }"></div>
          <span class="team-name entity-link" @click.stop="emit('navigateToTeamDashboard', team.id)">{{ team.name }}</span>
          <span v-if="team.is_owner" class="primary-badge">Primary</span>
        </div>
        <div class="team-run-body">
          <input
            :value="teamRunMessages[team.id]"
            type="text"
            class="team-run-input"
            placeholder="Optional message..."
            :disabled="teamRunning[team.id]"
            @input="($event: Event) => { const el = $event.target as HTMLInputElement; emit('update:teamRunMessages', { ...teamRunMessages, [team.id]: el.value }); }"
            @keyup.enter="emit('runTeam', team.id)"
          />
          <button
            class="team-run-btn"
            :disabled="teamRunning[team.id]"
            @click="emit('runTeam', team.id)"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polygon points="5 3 19 12 5 21 5 3"/>
            </svg>
            {{ teamRunning[team.id] ? 'Running...' : 'Run' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Assign Team Modal -->
    <Teleport to="body">
      <div v-if="showAssignModal" ref="assignModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-assign-team" tabindex="-1" @click.self="showAssignModal = false" @keydown.escape="showAssignModal = false">
        <div class="modal">
          <div class="modal-header">
            <h3 id="modal-title-assign-team">Assign Team</h3>
            <button class="modal-close" @click="showAssignModal = false">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M18 6L6 18M6 6l12 12"/>
              </svg>
            </button>
          </div>
          <div class="modal-body">
            <p class="modal-description">Select a team to assign to this project.</p>

            <div v-if="unassignedTeams.length === 0" class="empty-modal-state">
              <p>No available teams to assign.</p>
              <span>All teams are already assigned to this project.</span>
            </div>

            <div v-else class="team-select-wrapper">
              <select v-model="selectedTeamId" class="team-select">
                <option value="">Select a team...</option>
                <option v-for="team in unassignedTeams" :key="team.id" :value="team.id">
                  {{ team.name }}
                </option>
              </select>
              <svg class="select-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M6 9l6 6 6-6"/>
              </svg>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-cancel" @click="showAssignModal = false">Cancel</button>
            <button
              class="btn btn-assign"
              :disabled="!selectedTeamId || isAssigning"
              @click="assignTeam"
            >
              <span v-if="isAssigning">Assigning...</span>
              <span v-else>Assign Team</span>
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
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

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
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

.btn-inline-assign {
  display: inline-flex;
  align-items: center;
  padding: 6px 14px;
  margin-top: 8px;
  background: transparent;
  border: 1px solid var(--accent-cyan);
  border-radius: 6px;
  color: var(--accent-cyan);
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-inline-assign:hover {
  background: var(--accent-cyan);
  color: #000;
}

.team-color {
  width: 12px;
  height: 12px;
  border-radius: 3px;
  flex-shrink: 0;
}

.team-name {
  font-weight: 500;
  color: var(--text-primary);
  flex: 1;
}

.primary-badge {
  font-size: 0.65rem;
  font-weight: 600;
  text-transform: uppercase;
  padding: 2px 6px;
  border-radius: 3px;
  background: var(--accent-cyan);
  color: #000;
  letter-spacing: 0.03em;
}

.teams-run-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 20px;
}

.team-run-card {
  background: var(--bg-tertiary);
  border-radius: 8px;
  padding: 16px;
}

.team-run-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.team-run-body {
  display: flex;
  gap: 8px;
}

.team-run-input {
  flex: 1;
  padding: 8px 12px;
  background: var(--bg-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.85rem;
}

.team-run-input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.team-run-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: var(--accent-cyan);
  color: #000;
  border: none;
  border-radius: 6px;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: opacity 0.15s;
}

.team-run-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.team-run-btn svg {
  width: 14px;
  height: 14px;
}

/* Modal */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  width: 90%;
  max-width: 440px;
  animation: slideUp 0.3s ease;
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-subtle);
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

.modal-body {
  padding: 20px;
}

.modal-description {
  color: var(--text-secondary);
  font-size: 0.9rem;
  margin-bottom: 16px;
}

.empty-modal-state {
  text-align: center;
  padding: 20px;
  color: var(--text-tertiary);
}

.empty-modal-state p {
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.team-select-wrapper {
  position: relative;
}

.team-select {
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

.team-select:hover,
.team-select:focus {
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

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid var(--border-subtle);
}

.btn {
  padding: 10px 20px;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
}

.btn-cancel {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-subtle);
}

.btn-cancel:hover {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}

.btn-assign {
  background: var(--accent-cyan);
  color: #000;
}

.btn-assign:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 212, 255, 0.3);
}

.btn-assign:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
