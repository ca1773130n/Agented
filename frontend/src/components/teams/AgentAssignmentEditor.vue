<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import type { TeamAgentAssignment, EntityType, SkillInfo, Command, Hook, Rule } from '../../services/api';
import { teamApi, skillsApi, commandApi, hookApi, ruleApi } from '../../services/api';
import { useToast } from '../../composables/useToast';

const props = defineProps<{
  teamId: string;
  agentId: string;
  agentName: string;
}>();

const emit = defineEmits<{
  (e: 'updated'): void;
}>();

const showToast = useToast();

const assignments = ref<TeamAgentAssignment[]>([]);
const isLoading = ref(true);

// Available entities
const availableSkills = ref<SkillInfo[]>([]);
const availableCommands = ref<Command[]>([]);
const availableHooks = ref<Hook[]>([]);
const availableRules = ref<Rule[]>([]);

// Dropdown state
const openDropdown = ref<EntityType | null>(null);

// Group assignments by type
const skillAssignments = computed(() => assignments.value.filter(a => a.entity_type === 'skill'));
const commandAssignments = computed(() => assignments.value.filter(a => a.entity_type === 'command'));
const hookAssignments = computed(() => assignments.value.filter(a => a.entity_type === 'hook'));
const ruleAssignments = computed(() => assignments.value.filter(a => a.entity_type === 'rule'));

// Filter out already assigned
const filteredSkills = computed(() => {
  const assignedIds = new Set(skillAssignments.value.map(a => a.entity_id));
  return availableSkills.value.filter(s => !assignedIds.has(s.name));
});

const filteredCommands = computed(() => {
  const assignedIds = new Set(commandAssignments.value.map(a => a.entity_id));
  return availableCommands.value.filter(c => !assignedIds.has(String(c.id)));
});

const filteredHooks = computed(() => {
  const assignedIds = new Set(hookAssignments.value.map(a => a.entity_id));
  return availableHooks.value.filter(h => !assignedIds.has(String(h.id)));
});

const filteredRules = computed(() => {
  const assignedIds = new Set(ruleAssignments.value.map(a => a.entity_id));
  return availableRules.value.filter(r => !assignedIds.has(String(r.id)));
});

async function loadAssignments() {
  isLoading.value = true;
  try {
    const data = await teamApi.getAssignments(props.teamId, props.agentId);
    assignments.value = data.assignments || [];
  } catch {
    showToast('Failed to load assignments', 'error');
  } finally {
    isLoading.value = false;
  }
}

async function loadAvailableEntities() {
  try {
    const [skills, commands, hooks, rules] = await Promise.all([
      skillsApi.list().catch(() => ({ skills: [] as SkillInfo[] })),
      commandApi.list().catch(() => ({ commands: [] as Command[] })),
      hookApi.list().catch(() => ({ hooks: [] as Hook[] })),
      ruleApi.list().catch(() => ({ rules: [] as Rule[] })),
    ]);
    availableSkills.value = skills.skills || [];
    availableCommands.value = commands.commands || [];
    availableHooks.value = hooks.hooks || [];
    availableRules.value = rules.rules || [];
  } catch {
    // Silent fail - dropdowns will be empty
  }
}

function toggleDropdown(type: EntityType) {
  openDropdown.value = openDropdown.value === type ? null : type;
}

async function addAssignment(entityType: EntityType, entityId: string, entityName: string) {
  try {
    const result = await teamApi.addAssignment(props.teamId, props.agentId, {
      entity_type: entityType,
      entity_id: entityId,
      entity_name: entityName,
    });
    if (result.assignment) {
      assignments.value.push(result.assignment);
    } else {
      // Fallback: reload all
      await loadAssignments();
    }
    openDropdown.value = null;
    emit('updated');
    showToast(`Added ${entityType}: ${entityName}`, 'success');
  } catch {
    showToast(`Failed to add ${entityType}`, 'error');
  }
}

async function removeAssignment(assignment: TeamAgentAssignment) {
  try {
    await teamApi.deleteAssignment(props.teamId, assignment.id);
    assignments.value = assignments.value.filter(a => a.id !== assignment.id);
    emit('updated');
    showToast(`Removed ${assignment.entity_type}: ${assignment.entity_name || assignment.entity_id}`, 'info');
  } catch {
    showToast(`Failed to remove ${assignment.entity_type}`, 'error');
  }
}

onMounted(() => {
  loadAssignments();
  loadAvailableEntities();
});
</script>

<template>
  <div class="assignment-editor">
    <div v-if="isLoading" class="loading-assignments">
      <span>Loading assignments...</span>
    </div>
    <template v-else>
      <!-- Skills Section -->
      <div class="assignment-section">
        <div class="section-header">
          <span class="section-label">Skills</span>
          <span class="section-count">{{ skillAssignments.length }}</span>
          <button class="add-pill-btn" @click="toggleDropdown('skill')" title="Add skill">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
          </button>
        </div>
        <div v-if="openDropdown === 'skill'" class="dropdown-panel">
          <div v-if="filteredSkills.length === 0" class="dropdown-empty">No more skills available</div>
          <div
            v-for="skill in filteredSkills"
            :key="skill.name"
            class="dropdown-item"
            @click="addAssignment('skill', skill.name, skill.name)"
          >
            {{ skill.name }}
          </div>
        </div>
        <div class="pills">
          <span v-for="a in skillAssignments" :key="a.id" class="pill pill-skill">
            {{ a.entity_name || a.entity_id }}
            <button class="pill-remove" @click="removeAssignment(a)" title="Remove">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
            </button>
          </span>
          <span v-if="skillAssignments.length === 0" class="empty-text">No skills assigned</span>
        </div>
      </div>

      <!-- Commands Section -->
      <div class="assignment-section">
        <div class="section-header">
          <span class="section-label">Commands</span>
          <span class="section-count">{{ commandAssignments.length }}</span>
          <button class="add-pill-btn" @click="toggleDropdown('command')" title="Add command">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
          </button>
        </div>
        <div v-if="openDropdown === 'command'" class="dropdown-panel">
          <div v-if="filteredCommands.length === 0" class="dropdown-empty">No more commands available</div>
          <div
            v-for="cmd in filteredCommands"
            :key="cmd.id"
            class="dropdown-item"
            @click="addAssignment('command', String(cmd.id), cmd.name)"
          >
            {{ cmd.name }}
          </div>
        </div>
        <div class="pills">
          <span v-for="a in commandAssignments" :key="a.id" class="pill pill-command">
            {{ a.entity_name || a.entity_id }}
            <button class="pill-remove" @click="removeAssignment(a)" title="Remove">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
            </button>
          </span>
          <span v-if="commandAssignments.length === 0" class="empty-text">No commands assigned</span>
        </div>
      </div>

      <!-- Hooks Section -->
      <div class="assignment-section">
        <div class="section-header">
          <span class="section-label">Hooks</span>
          <span class="section-count">{{ hookAssignments.length }}</span>
          <button class="add-pill-btn" @click="toggleDropdown('hook')" title="Add hook">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
          </button>
        </div>
        <div v-if="openDropdown === 'hook'" class="dropdown-panel">
          <div v-if="filteredHooks.length === 0" class="dropdown-empty">No more hooks available</div>
          <div
            v-for="hook in filteredHooks"
            :key="hook.id"
            class="dropdown-item"
            @click="addAssignment('hook', String(hook.id), hook.name)"
          >
            {{ hook.name }}
          </div>
        </div>
        <div class="pills">
          <span v-for="a in hookAssignments" :key="a.id" class="pill pill-hook">
            {{ a.entity_name || a.entity_id }}
            <button class="pill-remove" @click="removeAssignment(a)" title="Remove">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
            </button>
          </span>
          <span v-if="hookAssignments.length === 0" class="empty-text">No hooks assigned</span>
        </div>
      </div>

      <!-- Rules Section -->
      <div class="assignment-section">
        <div class="section-header">
          <span class="section-label">Rules</span>
          <span class="section-count">{{ ruleAssignments.length }}</span>
          <button class="add-pill-btn" @click="toggleDropdown('rule')" title="Add rule">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
          </button>
        </div>
        <div v-if="openDropdown === 'rule'" class="dropdown-panel">
          <div v-if="filteredRules.length === 0" class="dropdown-empty">No more rules available</div>
          <div
            v-for="rule in filteredRules"
            :key="rule.id"
            class="dropdown-item"
            @click="addAssignment('rule', String(rule.id), rule.name)"
          >
            {{ rule.name }}
          </div>
        </div>
        <div class="pills">
          <span v-for="a in ruleAssignments" :key="a.id" class="pill pill-rule">
            {{ a.entity_name || a.entity_id }}
            <button class="pill-remove" @click="removeAssignment(a)" title="Remove">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
            </button>
          </span>
          <span v-if="ruleAssignments.length === 0" class="empty-text">No rules assigned</span>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.assignment-editor {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.loading-assignments {
  padding: 16px;
  text-align: center;
  color: var(--text-tertiary, #606070);
  font-size: 0.8rem;
}

.assignment-section {
  position: relative;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.section-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-secondary, #a0a0b0);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.section-count {
  font-size: 0.65rem;
  font-weight: 600;
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-tertiary, #606070);
  padding: 2px 6px;
  border-radius: 4px;
}

.add-pill-btn {
  margin-left: auto;
  width: 22px;
  height: 22px;
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

.add-pill-btn:hover {
  border-color: var(--accent-cyan, #00d4ff);
  color: var(--accent-cyan, #00d4ff);
}

.add-pill-btn svg {
  width: 12px;
  height: 12px;
}

/* Dropdown */
.dropdown-panel {
  position: absolute;
  top: 28px;
  right: 0;
  z-index: 10;
  background: var(--bg-elevated, #22222e);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: 8px;
  box-shadow: var(--shadow-lg, 0 8px 32px rgba(0, 0, 0, 0.5));
  max-height: 200px;
  overflow-y: auto;
  min-width: 200px;
}

.dropdown-item {
  padding: 8px 14px;
  font-size: 0.8rem;
  color: var(--text-secondary, #a0a0b0);
  cursor: pointer;
  transition: all 0.15s;
}

.dropdown-item:hover {
  background: var(--accent-cyan-dim, rgba(0, 212, 255, 0.15));
  color: var(--accent-cyan, #00d4ff);
}

.dropdown-empty {
  padding: 12px 14px;
  font-size: 0.75rem;
  color: var(--text-tertiary, #606070);
  text-align: center;
}

/* Pills */
.pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 28px;
  align-items: center;
}

.pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 16px;
  font-size: 0.75rem;
  font-weight: 500;
}

.pill-skill {
  background: rgba(0, 212, 255, 0.15);
  color: var(--accent-cyan, #00d4ff);
}

.pill-command {
  background: rgba(0, 255, 136, 0.15);
  color: var(--accent-emerald, #00ff88);
}

.pill-hook {
  background: rgba(136, 85, 255, 0.15);
  color: var(--accent-violet, #8855ff);
}

.pill-rule {
  background: rgba(255, 170, 0, 0.15);
  color: var(--accent-amber, #ffaa00);
}

.pill-remove {
  width: 14px;
  height: 14px;
  background: transparent;
  border: none;
  color: inherit;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0.6;
  transition: opacity 0.15s;
}

.pill-remove:hover {
  opacity: 1;
}

.pill-remove svg {
  width: 10px;
  height: 10px;
}

.empty-text {
  font-size: 0.75rem;
  color: var(--text-muted, #404050);
  font-style: italic;
}
</style>
