<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import type { GeneratedTeamConfig, GeneratedAgentConfig, TopologyType, TopologyConfig, EntityType } from '../../services/api';
import { useToast } from '../../composables/useToast';

const props = defineProps<{
  config: GeneratedTeamConfig;
  warnings: string[];
}>();

const emit = defineEmits<{
  (e: 'save', config: GeneratedTeamConfig): void;
  (e: 'cancel'): void;
}>();

const showToast = useToast();

// Split warnings into creation notices vs actual errors
const creationWarnings = computed(() =>
  props.warnings.filter(w => w.includes('will be created'))
);
const errorWarnings = computed(() =>
  props.warnings.filter(w => !w.includes('will be created'))
);

// Local editable copies
const editName = ref('');
const editDescription = ref('');
const editColor = ref('#00d4ff');
const editTopology = ref<TopologyType | null>(null);
const editTopologyConfig = ref<TopologyConfig>({});
const editAgents = ref<GeneratedAgentConfig[]>([]);

onMounted(() => {
  editName.value = props.config.name || '';
  editDescription.value = props.config.description || '';
  editColor.value = props.config.color || '#00d4ff';
  editTopology.value = props.config.topology || null;
  editTopologyConfig.value = props.config.topology_config
    ? (typeof props.config.topology_config === 'string'
        ? JSON.parse(props.config.topology_config as unknown as string)
        : { ...props.config.topology_config })
    : {};
  editAgents.value = (props.config.agents || []).map(a => ({
    ...a,
    assignments: (a.assignments || []).map(asn => ({ ...asn })),
  }));
});

const topologyOptions: { value: TopologyType; label: string; desc: string }[] = [
  { value: 'sequential', label: 'Sequential Pipeline', desc: 'Agents execute in order' },
  { value: 'parallel', label: 'Parallel Fan-out', desc: 'All agents run simultaneously' },
  { value: 'coordinator', label: 'Coordinator', desc: 'Hub-spoke delegation' },
  { value: 'generator_critic', label: 'Generator / Critic', desc: 'Iterative improvement' },
];

function getTopologyLabel(t: TopologyType | null): string {
  if (!t) return 'None';
  const opt = topologyOptions.find(o => o.value === t);
  return opt ? opt.label : t;
}

function removeAgent(index: number) {
  editAgents.value.splice(index, 1);
}

function removeAssignment(agentIndex: number, assignmentIndex: number) {
  editAgents.value[agentIndex].assignments.splice(assignmentIndex, 1);
}

function getEntityTypeIcon(type: EntityType): string {
  const icons: Record<string, string> = {
    skill: 'S',
    command: 'C',
    hook: 'H',
    rule: 'R',
  };
  return icons[type] || '?';
}

function handleSave() {
  if (!editName.value.trim()) {
    showToast('Team name is required', 'error');
    return;
  }

  const finalConfig: GeneratedTeamConfig = {
    name: editName.value.trim(),
    description: editDescription.value.trim(),
    topology: editTopology.value as TopologyType,
    topology_config: editTopologyConfig.value,
    color: editColor.value,
    agents: editAgents.value,
  };

  emit('save', finalConfig);
}
</script>

<template>
  <div class="config-review">
    <!-- Warnings Banner -->
    <div v-if="creationWarnings.length > 0 || errorWarnings.length > 0" class="warnings-banner" :class="{ 'warnings-info': errorWarnings.length === 0 }">
      <div class="warnings-header">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="warning-icon">
          <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
          <line x1="12" y1="9" x2="12" y2="13"/>
          <line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
        <span v-if="errorWarnings.length > 0">Some references could not be validated</span>
        <span v-else>New items will be auto-created on save</span>
      </div>
      <ul v-if="errorWarnings.length > 0" class="warnings-list">
        <li v-for="(w, i) in errorWarnings" :key="'e-' + i">{{ w }}</li>
      </ul>
      <ul v-if="creationWarnings.length > 0" class="warnings-list warnings-creation">
        <li v-for="(w, i) in creationWarnings" :key="'c-' + i">{{ w }}</li>
      </ul>
    </div>

    <!-- Team Info Section -->
    <div class="review-section">
      <h3 class="section-label">Team Information</h3>
      <div class="form-row">
        <div class="form-group flex-1">
          <label>Name</label>
          <input v-model="editName" type="text" placeholder="Team name" />
        </div>
        <div class="form-group color-group">
          <label>Color</label>
          <div class="color-input-wrap">
            <input v-model="editColor" type="color" class="color-swatch" />
            <span class="color-hex">{{ editColor }}</span>
          </div>
        </div>
      </div>
      <div class="form-group">
        <label>Description</label>
        <textarea v-model="editDescription" placeholder="Team description..." rows="3"></textarea>
      </div>
    </div>

    <!-- Topology Section -->
    <div class="review-section">
      <h3 class="section-label">Topology</h3>
      <div class="topology-selector">
        <button
          v-for="opt in topologyOptions"
          :key="opt.value"
          class="topo-option"
          :class="{ selected: editTopology === opt.value }"
          @click="editTopology = opt.value"
        >
          <span class="topo-label">{{ opt.label }}</span>
          <span class="topo-desc">{{ opt.desc }}</span>
        </button>
      </div>
      <div v-if="editTopology" class="topology-summary">
        <span class="topology-badge" :class="'topo-' + editTopology">
          {{ getTopologyLabel(editTopology) }}
        </span>
      </div>
    </div>

    <!-- Agents & Assignments Section -->
    <div class="review-section">
      <h3 class="section-label">Agents & Assignments ({{ editAgents.length }})</h3>

      <div v-if="editAgents.length === 0" class="empty-agents">
        No agents in configuration
      </div>

      <div v-for="(agent, aIdx) in editAgents" :key="aIdx" class="agent-card" :class="{ invalid: agent.valid === false }">
        <div class="agent-header">
          <div class="agent-meta">
            <div class="agent-name-row">
              <input
                v-model="agent.name"
                type="text"
                class="inline-edit agent-name-input"
                placeholder="Agent name"
              />
              <button class="btn-icon btn-remove" @click="removeAgent(aIdx)" title="Remove agent">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="18" y1="6" x2="6" y2="18"/>
                  <line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
            <input
              v-model="agent.role"
              type="text"
              class="inline-edit agent-role-input"
              placeholder="Agent role"
            />
          </div>

          <div class="agent-status">
            <span v-if="agent.agent_id === null" class="status-new">New agent -- will need to be created</span>
            <span v-else-if="agent.valid === false" class="status-invalid">Agent not found in system</span>
            <span v-else class="status-valid">Existing agent</span>
            <span v-if="agent.agent_id" class="agent-id-display">{{ agent.agent_id }}</span>
          </div>
        </div>

        <!-- Assignments -->
        <div v-if="agent.assignments.length > 0" class="assignments-section">
          <div class="assignments-label">Assignments</div>
          <div class="assignment-pills">
            <div
              v-for="(asn, asIdx) in agent.assignments"
              :key="asIdx"
              class="assignment-pill"
              :class="{ 'pill-invalid': asn.valid === false, 'pill-new': asn.needs_creation }"
            >
              <span class="pill-type-icon">{{ getEntityTypeIcon(asn.entity_type) }}</span>
              <span class="pill-name">{{ asn.entity_name || asn.entity_id }}</span>
              <span v-if="asn.needs_creation" class="pill-badge-new">NEW</span>
              <button class="pill-remove" @click="removeAssignment(aIdx, asIdx)" title="Remove assignment">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="18" y1="6" x2="6" y2="18"/>
                  <line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
          </div>
        </div>
        <div v-else class="no-assignments">No assignments</div>
      </div>
    </div>

    <!-- Action Buttons -->
    <div class="review-actions">
      <button class="btn btn-secondary" @click="emit('cancel')">Cancel</button>
      <button class="btn btn-primary" @click="handleSave">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/>
          <polyline points="17 21 17 13 7 13 7 21"/>
          <polyline points="7 3 7 8 15 8"/>
        </svg>
        Save & Create Team
      </button>
    </div>
  </div>
</template>

<style scoped>
.config-review {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

/* Warnings */
.warnings-banner {
  background: rgba(255, 170, 0, 0.1);
  border: 1px solid rgba(255, 170, 0, 0.3);
  border-radius: 10px;
  padding: 1rem 1.25rem;
}

.warnings-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  color: var(--accent-amber, #ffaa00);
  margin-bottom: 0.5rem;
}

.warning-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}

.warnings-list {
  margin: 0;
  padding-left: 1.5rem;
  font-size: 0.85rem;
  color: rgba(255, 170, 0, 0.8);
  line-height: 1.6;
}

.warnings-creation {
  color: rgba(0, 212, 255, 0.8);
  margin-top: 0.25rem;
}

.warnings-banner.warnings-info {
  background: rgba(0, 212, 255, 0.08);
  border-color: rgba(0, 212, 255, 0.25);
}

.warnings-banner.warnings-info .warnings-header {
  color: var(--accent-cyan, #00d4ff);
}

/* Sections */
.review-section {
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 1.25rem;
}

.section-label {
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-secondary, #888);
  margin-bottom: 1rem;
  font-weight: 600;
}

/* Form */
.form-row {
  display: flex;
  gap: 1rem;
  margin-bottom: 1rem;
}

.flex-1 {
  flex: 1;
}

.form-group input[type="text"] {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
}

.color-group {
  width: 140px;
}

.color-input-wrap {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.color-swatch {
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  padding: 0;
}

.color-hex {
  font-size: 0.8rem;
  color: var(--text-secondary, #888);
  font-family: monospace;
}

/* Topology */
.topology-selector {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.topo-option {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: 0.75rem;
  background: var(--bg-tertiary, #1a1a24);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
  text-align: left;
  color: var(--text-primary, #fff);
}

.topo-option:hover {
  border-color: var(--accent-cyan, #00d4ff);
}

.topo-option.selected {
  border-color: var(--accent-cyan, #00d4ff);
  background: rgba(0, 212, 255, 0.08);
}

.topo-label {
  font-weight: 600;
  font-size: 0.85rem;
  margin-bottom: 0.25rem;
}

.topo-desc {
  font-size: 0.75rem;
  color: var(--text-secondary, #888);
}

.topology-summary {
  margin-top: 0.5rem;
}

.topology-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.topo-sequential { background: rgba(0, 212, 255, 0.15); color: var(--accent-cyan, #00d4ff); }
.topo-parallel { background: rgba(0, 255, 136, 0.15); color: var(--accent-emerald, #00ff88); }
.topo-coordinator { background: rgba(136, 85, 255, 0.15); color: var(--accent-violet, #8855ff); }
.topo-generator_critic { background: rgba(255, 170, 0, 0.15); color: var(--accent-amber, #ffaa00); }

/* Agent Cards */
.empty-agents {
  text-align: center;
  color: var(--text-secondary, #888);
  padding: 2rem;
}

.agent-card {
  background: var(--bg-tertiary, #1a1a24);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  padding: 1rem;
  margin-bottom: 0.75rem;
  transition: border-color 0.2s;
}

.agent-card.invalid {
  border-color: rgba(255, 77, 77, 0.5);
  background: rgba(255, 77, 77, 0.04);
}

.agent-header {
  margin-bottom: 0.75rem;
}

.agent-meta {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.agent-name-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.inline-edit {
  background: transparent;
  border: 1px solid transparent;
  border-radius: 4px;
  padding: 0.25rem 0.4rem;
  color: var(--text-primary, #fff);
  font-family: inherit;
  transition: border-color 0.15s;
}

.inline-edit:hover,
.inline-edit:focus {
  border-color: var(--border-default);
  background: var(--bg-secondary, #12121a);
  outline: none;
}

.agent-name-input {
  font-weight: 600;
  font-size: 1rem;
  flex: 1;
}

.agent-role-input {
  font-size: 0.85rem;
  color: var(--text-secondary, #888);
}

.btn-icon {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0.25rem;
  color: var(--text-secondary, #888);
  transition: color 0.15s;
}

.btn-icon:hover {
  color: #ff4d4d;
}

.btn-icon svg {
  width: 16px;
  height: 16px;
}

.btn-remove svg {
  width: 18px;
  height: 18px;
}

.agent-status {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-top: 0.5rem;
  flex-wrap: wrap;
}

.status-new {
  font-size: 0.8rem;
  color: var(--accent-amber, #ffaa00);
  font-style: italic;
}

.status-invalid {
  font-size: 0.8rem;
  color: #ff4d4d;
  font-weight: 500;
}

.status-valid {
  font-size: 0.8rem;
  color: var(--accent-emerald, #00ff88);
}

.agent-id-display {
  font-size: 0.75rem;
  color: var(--text-secondary, #888);
  font-family: monospace;
  background: var(--bg-secondary, #12121a);
  padding: 2px 6px;
  border-radius: 3px;
}

/* Assignments */
.assignments-section {
  border-top: 1px solid var(--border-default);
  padding-top: 0.75rem;
}

.assignments-label {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-secondary, #888);
  margin-bottom: 0.5rem;
}

.assignment-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.assignment-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.3rem 0.6rem;
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  font-size: 0.8rem;
  transition: all 0.15s;
}

.assignment-pill.pill-invalid {
  border-color: rgba(255, 77, 77, 0.5);
  background: rgba(255, 77, 77, 0.08);
}

.assignment-pill.pill-new {
  border-color: rgba(0, 212, 255, 0.4);
  background: rgba(0, 212, 255, 0.08);
}

.pill-badge-new {
  font-size: 0.55rem;
  font-weight: 800;
  letter-spacing: 0.06em;
  padding: 1px 4px;
  border-radius: 3px;
  background: rgba(0, 212, 255, 0.2);
  color: var(--accent-cyan, #00d4ff);
}

.pill-type-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 3px;
  background: rgba(0, 212, 255, 0.15);
  color: var(--accent-cyan, #00d4ff);
  font-size: 0.65rem;
  font-weight: 700;
}

.pill-name {
  color: var(--text-primary, #fff);
}

.pill-remove {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  color: var(--text-secondary, #888);
  display: inline-flex;
  transition: color 0.15s;
}

.pill-remove:hover {
  color: #ff4d4d;
}

.pill-remove svg {
  width: 12px;
  height: 12px;
}

.no-assignments {
  font-size: 0.8rem;
  color: var(--text-muted, #404050);
  padding-top: 0.5rem;
  border-top: 1px solid var(--border-default);
}

/* Actions */
.review-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding-top: 0.5rem;
}

.btn-secondary {
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-primary, #fff);
  border: 1px solid var(--border-default);
}

.btn-secondary:hover {
  border-color: var(--text-secondary, #888);
}
</style>
