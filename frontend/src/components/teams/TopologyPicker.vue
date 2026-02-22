<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import type { TopologyType, TopologyConfig, TeamMember } from '../../services/api';

const props = defineProps<{
  modelValue: TopologyType | null;
  teamMembers?: TeamMember[];
  initialConfig?: string;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: TopologyType | null): void;
  (e: 'update:config', value: string): void;
}>();

// Internal config state — load from initialConfig prop if provided
function parseInitialConfig(): TopologyConfig {
  if (props.initialConfig) {
    try {
      return JSON.parse(props.initialConfig);
    } catch { return {}; }
  }
  return {};
}
const config = ref<TopologyConfig>(parseInitialConfig());

const agentMembers = computed(() =>
  (props.teamMembers || []).filter(m => m.agent_id)
);

const topologies = [
  {
    type: 'sequential' as TopologyType,
    name: 'Sequential Pipeline',
    description: 'Agents execute in order, each receiving the previous agent\'s output.',
    icon: 'sequential',
  },
  {
    type: 'parallel' as TopologyType,
    name: 'Parallel Fan-out',
    description: 'All agents execute simultaneously with the same input.',
    icon: 'parallel',
  },
  {
    type: 'coordinator' as TopologyType,
    name: 'Coordinator / Dispatcher',
    description: 'A coordinator agent delegates work to worker agents.',
    icon: 'coordinator',
  },
  {
    type: 'generator_critic' as TopologyType,
    name: 'Generator / Critic',
    description: 'A generator creates output, a critic reviews it, repeating until approved.',
    icon: 'generator_critic',
  },
  {
    type: 'hierarchical' as TopologyType,
    name: 'Hierarchical',
    description: 'A lead agent manages tiers of sub-agents in a tree structure.',
    icon: 'hierarchical',
  },
  {
    type: 'human_in_loop' as TopologyType,
    name: 'Human-in-the-Loop',
    description: 'Agents execute with human approval gates at configured checkpoints.',
    icon: 'human_in_loop',
  },
  {
    type: 'composite' as TopologyType,
    name: 'Composite',
    description: 'Combines multiple sub-topologies into a single team workflow.',
    icon: 'composite',
  },
];

function selectTopology(type: TopologyType) {
  if (props.modelValue === type) {
    emit('update:modelValue', null);
    config.value = {};
    emit('update:config', '{}');
  } else {
    emit('update:modelValue', type);
    initConfig(type);
  }
}

function initConfig(type: TopologyType) {
  const savedPositions = config.value.positions;
  const agentIds = agentMembers.value.map(m => m.agent_id!);
  switch (type) {
    case 'sequential':
      config.value = { order: [...agentIds] };
      break;
    case 'parallel':
      config.value = { agents: [...agentIds] };
      break;
    case 'coordinator':
      config.value = {
        coordinator: agentIds[0] || '',
        workers: agentIds.slice(1),
      };
      break;
    case 'generator_critic':
      config.value = {
        generator: agentIds[0] || '',
        critic: agentIds[1] || '',
        max_iterations: 3,
      };
      break;
    case 'hierarchical':
      config.value = {
        lead: agentIds[0] || '',
        workers: agentIds.slice(1),
      };
      break;
    case 'human_in_loop':
      config.value = {
        order: [...agentIds],
        approval_nodes: [],
      };
      break;
    case 'composite':
      config.value = {
        sub_groups: [],
      };
      break;
  }
  if (savedPositions) {
    config.value.positions = savedPositions;
  }
  emitConfig();
}

function emitConfig() {
  emit('update:config', JSON.stringify(config.value));
}

// Sequential: move agent up/down
function moveAgent(index: number, direction: -1 | 1) {
  if (!config.value.order) return;
  const arr = [...config.value.order];
  const target = index + direction;
  if (target < 0 || target >= arr.length) return;
  [arr[index], arr[target]] = [arr[target], arr[index]];
  config.value.order = arr;
  emitConfig();
}

// Parallel: toggle agent
function toggleParallelAgent(agentId: string) {
  if (!config.value.agents) config.value.agents = [];
  const idx = config.value.agents.indexOf(agentId);
  if (idx >= 0) {
    config.value.agents.splice(idx, 1);
  } else {
    config.value.agents.push(agentId);
  }
  emitConfig();
}

// Coordinator: set coordinator
function setCoordinator(agentId: string) {
  config.value.coordinator = agentId;
  // Remove from workers if present
  if (config.value.workers) {
    config.value.workers = config.value.workers.filter(id => id !== agentId);
  }
  emitConfig();
}

// Coordinator/Hierarchical: toggle worker
function toggleWorker(agentId: string) {
  if (!config.value.workers) config.value.workers = [];
  if (agentId === config.value.coordinator || agentId === config.value.lead) return;
  const idx = config.value.workers.indexOf(agentId);
  if (idx >= 0) {
    config.value.workers.splice(idx, 1);
  } else {
    config.value.workers.push(agentId);
  }
  emitConfig();
}

// Generator/Critic setters
function setGenerator(agentId: string) {
  config.value.generator = agentId;
  if (config.value.critic === agentId) config.value.critic = '';
  emitConfig();
}

function setCritic(agentId: string) {
  config.value.critic = agentId;
  if (config.value.generator === agentId) config.value.generator = '';
  emitConfig();
}

function setMaxIterations(val: number) {
  config.value.max_iterations = Math.max(1, Math.min(20, val));
  emitConfig();
}

// Hierarchical: set lead
function setLead(agentId: string) {
  config.value.lead = agentId;
  if (config.value.workers) {
    config.value.workers = config.value.workers.filter(id => id !== agentId);
  }
  emitConfig();
}

// Human-in-loop: toggle approval node
function toggleApprovalNode(agentId: string) {
  if (!config.value.approval_nodes) config.value.approval_nodes = [];
  const idx = config.value.approval_nodes.indexOf(agentId);
  if (idx >= 0) {
    config.value.approval_nodes.splice(idx, 1);
  } else {
    config.value.approval_nodes.push(agentId);
  }
  emitConfig();
}

function getAgentName(agentId: string): string {
  const member = agentMembers.value.find(m => m.agent_id === agentId);
  return member?.name || agentId;
}

// Re-init config when members change, but only if config is empty
// (don't overwrite existing saved config loaded from initialConfig)
watch(() => props.teamMembers, () => {
  if (props.modelValue && Object.keys(config.value).length === 0) {
    initConfig(props.modelValue);
  }
}, { deep: true });
</script>

<template>
  <div class="topology-picker">
    <div class="topology-grid">
      <div
        v-for="topo in topologies"
        :key="topo.type"
        class="topology-card"
        :class="{ selected: modelValue === topo.type }"
        @click="selectTopology(topo.type)"
      >
        <div class="topo-icon">
          <!-- Sequential: arrows in line -->
          <svg v-if="topo.icon === 'sequential'" viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="8" cy="20" r="4" />
            <line x1="12" y1="20" x2="18" y2="20" />
            <polygon points="18,17 24,20 18,23" fill="currentColor" stroke="none" />
            <circle cx="28" cy="20" r="4" />
            <line x1="32" y1="20" x2="38" y2="20" stroke-dasharray="2,2" />
          </svg>
          <!-- Parallel: branching arrows -->
          <svg v-else-if="topo.icon === 'parallel'" viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="8" cy="20" r="4" />
            <line x1="12" y1="20" x2="20" y2="10" />
            <line x1="12" y1="20" x2="20" y2="20" />
            <line x1="12" y1="20" x2="20" y2="30" />
            <circle cx="24" cy="10" r="4" />
            <circle cx="24" cy="20" r="4" />
            <circle cx="24" cy="30" r="4" />
          </svg>
          <!-- Coordinator: hub-and-spoke -->
          <svg v-else-if="topo.icon === 'coordinator'" viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="20" r="5" />
            <line x1="17" y1="17" x2="26" y2="10" />
            <line x1="17" y1="20" x2="26" y2="20" />
            <line x1="17" y1="23" x2="26" y2="30" />
            <circle cx="30" cy="10" r="3" />
            <circle cx="30" cy="20" r="3" />
            <circle cx="30" cy="30" r="3" />
          </svg>
          <!-- Generator/Critic: loop arrows -->
          <svg v-else-if="topo.icon === 'generator_critic'" viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="20" r="5" />
            <circle cx="28" cy="20" r="5" />
            <path d="M17 17 L23 17" />
            <polygon points="22,15 26,17 22,19" fill="currentColor" stroke="none" />
            <path d="M23 23 L17 23" />
            <polygon points="18,21 14,23 18,25" fill="currentColor" stroke="none" />
          </svg>
          <!-- Hierarchical: tree structure -->
          <svg v-else-if="topo.icon === 'hierarchical'" viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="20" cy="8" r="4" />
            <line x1="18" y1="12" x2="10" y2="22" />
            <line x1="22" y1="12" x2="30" y2="22" />
            <circle cx="10" cy="26" r="4" />
            <circle cx="30" cy="26" r="4" />
            <line x1="10" y1="30" x2="10" y2="36" stroke-dasharray="2,2" />
            <line x1="30" y1="30" x2="30" y2="36" stroke-dasharray="2,2" />
          </svg>
          <!-- Human-in-the-Loop: person with circular arrow -->
          <svg v-else-if="topo.icon === 'human_in_loop'" viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="14" cy="10" r="4" />
            <path d="M8 24 C8 18 14 16 14 16 C14 16 20 18 20 24" />
            <path d="M28 8 A8 8 0 1 1 28 24" />
            <polygon points="26,24 30,28 30,22" fill="currentColor" stroke="none" />
          </svg>
          <!-- Composite: overlapping rectangles -->
          <svg v-else-if="topo.icon === 'composite'" viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="4" y="6" width="18" height="14" rx="3" />
            <rect x="18" y="20" width="18" height="14" rx="3" />
            <rect x="14" y="13" width="12" height="14" rx="3" stroke-dasharray="3,2" />
          </svg>
        </div>
        <div class="topo-content">
          <h4>{{ topo.name }}</h4>
          <p>{{ topo.description }}</p>
        </div>
      </div>
    </div>

    <!-- Configuration Panel -->
    <div v-if="modelValue && agentMembers.length > 0" class="config-panel">
      <h4 class="config-title">Configuration</h4>

      <!-- Sequential Config: sortable agent list -->
      <div v-if="modelValue === 'sequential'" class="config-section">
        <p class="config-hint">Define the execution order by reordering agents.</p>
        <div v-if="config.order && config.order.length > 0" class="order-list">
          <div v-for="(agentId, idx) in config.order" :key="agentId" class="order-item">
            <span class="order-num">{{ idx + 1 }}</span>
            <span class="order-name">{{ getAgentName(agentId) }}</span>
            <div class="order-actions">
              <button class="order-btn" :disabled="idx === 0" @click="moveAgent(idx, -1)" title="Move up">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 15l-6-6-6 6"/></svg>
              </button>
              <button class="order-btn" :disabled="idx === (config.order?.length || 0) - 1" @click="moveAgent(idx, 1)" title="Move down">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
              </button>
            </div>
          </div>
        </div>
        <p v-else class="config-empty">No agent members to order.</p>
      </div>

      <!-- Parallel Config: checkboxes -->
      <div v-else-if="modelValue === 'parallel'" class="config-section">
        <p class="config-hint">Select which agents participate in parallel execution.</p>
        <div class="checkbox-list">
          <label v-for="member in agentMembers" :key="member.agent_id" class="checkbox-item">
            <input
              type="checkbox"
              :checked="config.agents?.includes(member.agent_id!)"
              @change="toggleParallelAgent(member.agent_id!)"
            />
            <span>{{ member.name }}</span>
          </label>
        </div>
      </div>

      <!-- Coordinator Config -->
      <div v-else-if="modelValue === 'coordinator'" class="config-section">
        <div class="config-field">
          <label>Coordinator</label>
          <select :value="config.coordinator" @change="setCoordinator(($event.target as HTMLSelectElement).value)" class="config-select">
            <option value="">-- Select coordinator --</option>
            <option v-for="member in agentMembers" :key="member.agent_id" :value="member.agent_id">
              {{ member.name }}
            </option>
          </select>
        </div>
        <div class="config-field">
          <label>Workers</label>
          <div class="checkbox-list">
            <label v-for="member in agentMembers" :key="member.agent_id" class="checkbox-item"
              :class="{ disabled: member.agent_id === config.coordinator }">
              <input
                type="checkbox"
                :checked="config.workers?.includes(member.agent_id!)"
                :disabled="member.agent_id === config.coordinator"
                @change="toggleWorker(member.agent_id!)"
              />
              <span>{{ member.name }}</span>
            </label>
          </div>
        </div>
      </div>

      <!-- Generator/Critic Config -->
      <div v-else-if="modelValue === 'generator_critic'" class="config-section">
        <div class="config-field">
          <label>Generator</label>
          <select :value="config.generator" @change="setGenerator(($event.target as HTMLSelectElement).value)" class="config-select">
            <option value="">-- Select generator --</option>
            <option v-for="member in agentMembers" :key="member.agent_id" :value="member.agent_id">
              {{ member.name }}
            </option>
          </select>
        </div>
        <div class="config-field">
          <label>Critic</label>
          <select :value="config.critic" @change="setCritic(($event.target as HTMLSelectElement).value)" class="config-select">
            <option value="">-- Select critic --</option>
            <option v-for="member in agentMembers" :key="member.agent_id" :value="member.agent_id">
              {{ member.name }}
            </option>
          </select>
        </div>
        <div class="config-field">
          <label>Max Iterations</label>
          <input
            type="number"
            :value="config.max_iterations"
            min="1"
            max="20"
            class="config-input"
            @input="setMaxIterations(Number(($event.target as HTMLInputElement).value))"
          />
        </div>
      </div>

      <!-- Hierarchical Config -->
      <div v-else-if="modelValue === 'hierarchical'" class="config-section">
        <div class="config-field">
          <label>Lead</label>
          <select :value="config.lead" @change="setLead(($event.target as HTMLSelectElement).value)" class="config-select">
            <option value="">-- Select lead --</option>
            <option v-for="member in agentMembers" :key="member.agent_id" :value="member.agent_id">
              {{ member.name }}
            </option>
          </select>
        </div>
        <div class="config-field">
          <label>Workers</label>
          <div class="checkbox-list">
            <label v-for="member in agentMembers" :key="member.agent_id" class="checkbox-item"
              :class="{ disabled: member.agent_id === config.lead }">
              <input
                type="checkbox"
                :checked="config.workers?.includes(member.agent_id!)"
                :disabled="member.agent_id === config.lead"
                @change="toggleWorker(member.agent_id!)"
              />
              <span>{{ member.name }}</span>
            </label>
          </div>
        </div>
      </div>

      <!-- Human-in-the-Loop Config -->
      <div v-else-if="modelValue === 'human_in_loop'" class="config-section">
        <p class="config-hint">Define the execution order and mark agents that require human approval before proceeding.</p>
        <div v-if="config.order && config.order.length > 0" class="order-list">
          <div v-for="(agentId, idx) in config.order" :key="agentId" class="order-item">
            <span class="order-num">{{ idx + 1 }}</span>
            <span class="order-name">{{ getAgentName(agentId) }}</span>
            <label class="approval-toggle" :title="'Toggle approval gate after this agent'">
              <input
                type="checkbox"
                :checked="config.approval_nodes?.includes(agentId)"
                @change="toggleApprovalNode(agentId)"
              />
              <span class="approval-label">Approval</span>
            </label>
            <div class="order-actions">
              <button class="order-btn" :disabled="idx === 0" @click="moveAgent(idx, -1)" title="Move up">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 15l-6-6-6 6"/></svg>
              </button>
              <button class="order-btn" :disabled="idx === (config.order?.length || 0) - 1" @click="moveAgent(idx, 1)" title="Move down">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
              </button>
            </div>
          </div>
        </div>
        <p v-else class="config-empty">No agent members to order.</p>
      </div>

      <!-- Composite Config -->
      <div v-else-if="modelValue === 'composite'" class="config-section">
        <p class="config-hint">Composite topology configuration is managed via the visual canvas editor.</p>
      </div>
    </div>

    <div v-else-if="modelValue && agentMembers.length === 0" class="config-panel">
      <p class="config-empty">Add agent members to the team to configure topology.</p>
    </div>
  </div>
</template>

<style scoped>
.topology-picker {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.topology-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.topology-card {
  display: flex;
  gap: 12px;
  padding: 14px;
  background: var(--bg-tertiary, #1a1a24);
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
  min-height: 100px;
}

.topology-card:hover {
  border-color: var(--text-tertiary, #606070);
  background: var(--bg-elevated, #22222e);
}

.topology-card.selected {
  border-color: var(--accent-cyan, #00d4ff);
  background: var(--accent-cyan-dim, rgba(0, 212, 255, 0.15));
}

.topo-icon {
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  color: var(--text-tertiary, #606070);
}

.topology-card.selected .topo-icon {
  color: var(--accent-cyan, #00d4ff);
}

.topo-icon svg {
  width: 40px;
  height: 40px;
}

.topo-content {
  flex: 1;
  min-width: 0;
}

.topo-content h4 {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-primary, #f0f0f5);
  margin-bottom: 4px;
}

.topo-content p {
  font-size: 0.75rem;
  color: var(--text-tertiary, #606070);
  line-height: 1.4;
}

.topology-card.selected .topo-content p {
  color: var(--text-secondary, #a0a0b0);
}

/* Config Panel */
.config-panel {
  background: var(--bg-tertiary, #1a1a24);
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  border-radius: 10px;
  padding: 16px;
}

.config-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-secondary, #a0a0b0);
  margin-bottom: 12px;
}

.config-hint {
  font-size: 0.75rem;
  color: var(--text-tertiary, #606070);
  margin-bottom: 12px;
}

.config-empty {
  font-size: 0.8rem;
  color: var(--text-tertiary, #606070);
  text-align: center;
  padding: 16px;
}

.config-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.config-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.config-field label {
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--text-secondary, #a0a0b0);
}

.config-select {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  border-radius: 6px;
  color: var(--text-primary, #f0f0f5);
  font-size: 0.85rem;
}

.config-select option {
  background: var(--bg-secondary, #12121a);
  color: var(--text-primary, #f0f0f5);
}

.config-input {
  width: 80px;
  padding: 8px 12px;
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  border-radius: 6px;
  color: var(--text-primary, #f0f0f5);
  font-size: 0.85rem;
}

/* Order list for sequential */
.order-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.order-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: var(--bg-secondary, #12121a);
  border-radius: 6px;
}

.order-num {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.7rem;
  font-weight: 600;
  background: var(--accent-cyan-dim, rgba(0, 212, 255, 0.15));
  color: var(--accent-cyan, #00d4ff);
  border-radius: 50%;
  flex-shrink: 0;
}

.order-name {
  flex: 1;
  font-size: 0.85rem;
  color: var(--text-primary, #f0f0f5);
}

.order-actions {
  display: flex;
  gap: 4px;
}

.order-btn {
  width: 24px;
  height: 24px;
  background: transparent;
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  border-radius: 4px;
  color: var(--text-tertiary, #606070);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.order-btn:hover:not(:disabled) {
  border-color: var(--accent-cyan, #00d4ff);
  color: var(--accent-cyan, #00d4ff);
}

.order-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.order-btn svg {
  width: 14px;
  height: 14px;
}

/* Checkbox list */
.checkbox-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.checkbox-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: var(--bg-secondary, #12121a);
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
  color: var(--text-primary, #f0f0f5);
}

.checkbox-item.disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.checkbox-item input[type="checkbox"] {
  accent-color: var(--accent-cyan, #00d4ff);
}

/* Approval toggle for human-in-loop */
.approval-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  font-size: 0.75rem;
  margin-left: auto;
}

.approval-toggle input[type="checkbox"] {
  accent-color: var(--accent-amber, #ffaa00);
}

.approval-label {
  color: var(--text-tertiary, #606070);
  font-size: 0.7rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
</style>
