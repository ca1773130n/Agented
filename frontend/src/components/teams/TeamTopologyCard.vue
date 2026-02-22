<script setup lang="ts">
import { ref } from 'vue';
import type { Team, TopologyType } from '../../services/api';
import { teamApi, ApiError } from '../../services/api';
import TopologyPicker from './TopologyPicker.vue';
import { useToast } from '../../composables/useToast';

const props = defineProps<{
  team: Team;
}>();

const emit = defineEmits<{
  (e: 'updated'): void;
}>();

const showToast = useToast();

const editingTopology = ref(false);
const editTopology = ref<TopologyType | null>(null);
const editTopologyConfig = ref('{}');
const isSavingTopology = ref(false);

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

function startEditTopology() {
  editTopology.value = props.team.topology || null;
  editTopologyConfig.value = props.team.topology_config || '{}';
  editingTopology.value = true;
}

async function saveTopology() {
  isSavingTopology.value = true;
  try {
    await teamApi.updateTopology(props.team.id, {
      topology: editTopology.value,
      topology_config: editTopologyConfig.value,
    });
    showToast('Topology updated', 'success');
    editingTopology.value = false;
    emit('updated');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to update topology';
    showToast(message, 'error');
  } finally {
    isSavingTopology.value = false;
  }
}
</script>

<template>
  <div class="card">
    <div class="card-header">
      <div class="header-left">
        <h3>Topology</h3>
        <span v-if="team.topology" class="card-count">{{ getTopologyLabel(team.topology) }}</span>
        <span v-else class="card-count">Not configured</span>
      </div>
      <button class="add-btn" @click="editingTopology ? (editingTopology = false) : startEditTopology()">
        {{ editingTopology ? 'Cancel' : 'Edit' }}
      </button>
    </div>
    <div v-if="editingTopology" class="card-body">
      <TopologyPicker
        v-model="editTopology"
        :team-members="team.members"
        :initial-config="editTopologyConfig"
        @update:config="editTopologyConfig = $event"
      />
      <div class="card-actions">
        <button class="action-btn primary compact" :disabled="isSavingTopology" @click="saveTopology">
          {{ isSavingTopology ? 'Saving...' : 'Save Topology' }}
        </button>
      </div>
    </div>
    <div v-else-if="!team.topology" class="empty-state">
      <p>No topology configured</p>
      <span>Set a topology to define how agents collaborate</span>
    </div>
  </div>
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

.card-body {
  padding: 20px;
}

.card-actions {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
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

.add-btn:hover {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}

/* Action Buttons */
.action-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 20px;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}

.action-btn.primary {
  background: linear-gradient(135deg, var(--accent-cyan, #00d4ff) 0%, var(--accent-emerald, #00ff88) 100%);
  color: var(--bg-primary);
}

.action-btn.primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 212, 255, 0.3);
}

.action-btn.primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.action-btn.compact {
  padding: 8px 16px;
  font-size: 0.85rem;
}

/* Empty State */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
}

.empty-state span {
  font-size: 0.85rem;
  color: var(--text-tertiary);
}
</style>
