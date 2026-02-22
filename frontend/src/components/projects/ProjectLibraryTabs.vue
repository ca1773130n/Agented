<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import type { Agent, ProjectSkill, Hook, Command, Rule, ProjectInstallation } from '../../services/api';
import { useToast } from '../../composables/useToast';

type LibraryTab = 'agents' | 'skills' | 'hooks' | 'commands' | 'rules';

const props = defineProps<{
  projectId: string;
  allAgents: Agent[];
  projectSkills: ProjectSkill[];
  allHooks: Hook[];
  allCommands: Command[];
  allRules: Rule[];
  installations: ProjectInstallation[];
  isInstallingComponent: Record<string, boolean>;
}>();

const emit = defineEmits<{
  (e: 'install', componentType: string, componentId: string, componentName: string): void;
  (e: 'uninstall', componentType: string, componentId: string, componentName: string): void;
  (e: 'addSkill'): void;
  (e: 'removeSkill', skill: ProjectSkill): void;
  (e: 'toggleHook', hook: Hook): void;
  (e: 'toggleCommand', command: Command): void;
  (e: 'toggleRule', rule: Rule): void;
  (e: 'refresh'): void;
}>();

const showToast = useToast();

const activeLibraryTab = ref<LibraryTab>('agents');

// Bulk selection state
const selectedItems = ref<Set<string>>(new Set());
const selectAll = ref(false);
const isBulkInstalling = ref(false);
const bulkProgress = ref('');

// Collapsible sections state (collapsed by default)
const collapsedSections = ref<Record<string, boolean>>({
  agents: true,
  skills: true,
  hooks_project: true,
  hooks_global: true,
  commands_project: true,
  commands_global: true,
  rules_project: true,
  rules_global: true,
});

function toggleSection(key: string) {
  collapsedSections.value[key] = !collapsedSections.value[key];
}

// Clear selection when tab changes
watch(activeLibraryTab, () => {
  selectedItems.value = new Set();
  selectAll.value = false;
});

const projectHooks = computed(() =>
  props.allHooks.filter(h => h.project_id === props.projectId)
);

const globalHooks = computed(() =>
  props.allHooks.filter(h => !h.project_id)
);

const projectCommands = computed(() =>
  props.allCommands.filter(c => c.project_id === props.projectId)
);

const globalCommands = computed(() =>
  props.allCommands.filter(c => !c.project_id)
);

const projectRules = computed(() =>
  props.allRules.filter(r => r.project_id === props.projectId)
);

const globalRules = computed(() =>
  props.allRules.filter(r => !r.project_id)
);

function isInstalled(componentType: string, componentId: string): boolean {
  return props.installations.some(
    i => i.component_type === componentType && i.component_id === componentId
  );
}

// Get all selectable items for the current tab
interface SelectableItem { key: string; type: string; id: string; name: string; }

const currentTabItems = computed<SelectableItem[]>(() => {
  switch (activeLibraryTab.value) {
    case 'agents':
      return props.allAgents.map(a => ({ key: `agent-${a.id}`, type: 'agent', id: a.id, name: a.name }));
    case 'skills':
      return props.projectSkills.map(s => ({ key: `skill-${s.skill_name}`, type: 'skill', id: s.skill_name, name: s.skill_name }));
    case 'hooks':
      return projectHooks.value.map(h => ({ key: `hook-${h.id}`, type: 'hook', id: String(h.id), name: h.name }));
    case 'commands':
      return projectCommands.value.map(c => ({ key: `command-${c.id}`, type: 'command', id: String(c.id), name: c.name }));
    case 'rules':
      return projectRules.value.map(r => ({ key: `rule-${r.id}`, type: 'rule', id: String(r.id), name: r.name }));
    default:
      return [];
  }
});

function toggleItem(key: string) {
  const next = new Set(selectedItems.value);
  if (next.has(key)) {
    next.delete(key);
  } else {
    next.add(key);
  }
  selectedItems.value = next;
  selectAll.value = next.size === currentTabItems.value.length && next.size > 0;
}

function toggleSelectAll() {
  if (selectAll.value) {
    selectedItems.value = new Set();
    selectAll.value = false;
  } else {
    selectedItems.value = new Set(currentTabItems.value.map(i => i.key));
    selectAll.value = true;
  }
}

async function bulkInstall() {
  const items = currentTabItems.value.filter(i => selectedItems.value.has(i.key) && !isInstalled(i.type, i.id));
  if (items.length === 0) {
    showToast('All selected items are already installed', 'info');
    return;
  }
  isBulkInstalling.value = true;
  let completed = 0;
  bulkProgress.value = `Installing 0/${items.length}...`;

  const results = await Promise.allSettled(
    items.map(async (item) => {
      emit('install', item.type, item.id, item.name);
      completed++;
      bulkProgress.value = `Installing ${completed}/${items.length}...`;
    })
  );

  const succeeded = results.filter(r => r.status === 'fulfilled').length;
  isBulkInstalling.value = false;
  bulkProgress.value = '';
  selectedItems.value = new Set();
  selectAll.value = false;
  showToast(`Installed ${succeeded} components`, 'success');
  emit('refresh');
}

async function bulkUninstall() {
  const items = currentTabItems.value.filter(i => selectedItems.value.has(i.key) && isInstalled(i.type, i.id));
  if (items.length === 0) {
    showToast('No selected items are installed', 'info');
    return;
  }
  isBulkInstalling.value = true;
  let completed = 0;
  bulkProgress.value = `Uninstalling 0/${items.length}...`;

  const results = await Promise.allSettled(
    items.map(async (item) => {
      emit('uninstall', item.type, item.id, item.name);
      completed++;
      bulkProgress.value = `Uninstalling ${completed}/${items.length}...`;
    })
  );

  const succeeded = results.filter(r => r.status === 'fulfilled').length;
  isBulkInstalling.value = false;
  bulkProgress.value = '';
  selectedItems.value = new Set();
  selectAll.value = false;
  showToast(`Uninstalled ${succeeded} components`, 'success');
  emit('refresh');
}
</script>

<template>
  <div class="card library-card">
    <div class="card-header">
      <h3>Project Library</h3>
      <span class="card-count">
        {{ allAgents.length }} agents, {{ projectSkills.length }} skills, {{ projectHooks.length }} hooks, {{ projectCommands.length }} commands, {{ projectRules.length }} rules
        <template v-if="installations.length > 0"> &middot; {{ installations.length }} installed to .claude/</template>
      </span>
    </div>

    <!-- Library Tabs -->
    <div class="library-tabs">
      <button
        class="tab-btn"
        :class="{ active: activeLibraryTab === 'agents' }"
        @click="activeLibraryTab = 'agents'"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
          <circle cx="12" cy="7" r="4"/>
        </svg>
        Agents ({{ allAgents.length }})
      </button>
      <button
        class="tab-btn"
        :class="{ active: activeLibraryTab === 'skills' }"
        @click="activeLibraryTab = 'skills'"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M12 2L2 7l10 5 10-5-10-5z"/>
          <path d="M2 17l10 5 10-5"/>
          <path d="M2 12l10 5 10-5"/>
        </svg>
        Skills ({{ projectSkills.length }})
      </button>
      <button
        class="tab-btn"
        :class="{ active: activeLibraryTab === 'hooks' }"
        @click="activeLibraryTab = 'hooks'"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
        </svg>
        Hooks ({{ projectHooks.length }})
      </button>
      <button
        class="tab-btn"
        :class="{ active: activeLibraryTab === 'commands' }"
        @click="activeLibraryTab = 'commands'"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <polyline points="4 17 10 11 4 5"/>
          <line x1="12" y1="19" x2="20" y2="19"/>
        </svg>
        Commands ({{ projectCommands.length }})
      </button>
      <button
        class="tab-btn"
        :class="{ active: activeLibraryTab === 'rules' }"
        @click="activeLibraryTab = 'rules'"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M9 11l3 3L22 4"/>
          <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>
        </svg>
        Rules ({{ projectRules.length }})
      </button>
    </div>

    <!-- Agents Tab Content -->
    <div v-if="activeLibraryTab === 'agents'" class="tab-content">
      <div class="tab-header">
        <label class="select-all-label">
          <input type="checkbox" :checked="selectAll" @change="toggleSelectAll" class="bulk-checkbox" />
          <span class="section-title">Agents</span>
        </label>
        <div class="tab-header-actions">
          <button
            v-if="selectedItems.size > 0"
            class="header-bulk-btn install"
            :disabled="isBulkInstalling"
            @click="bulkInstall"
          >Install Selected ({{ selectedItems.size }})</button>
          <button
            v-if="selectedItems.size > 0"
            class="header-bulk-btn uninstall"
            :disabled="isBulkInstalling"
            @click="bulkUninstall"
          >Uninstall Selected</button>
        </div>
      </div>

      <div v-if="allAgents.length === 0" class="empty-state small">
        <p>No agents available</p>
      </div>

      <div v-else class="library-section">
        <button class="section-collapse-btn" @click="toggleSection('agents')">
          <svg :class="{ rotated: !collapsedSections.agents }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
          <span>{{ allAgents.length }} agent{{ allAgents.length !== 1 ? 's' : '' }}</span>
        </button>
        <div v-if="!collapsedSections.agents" class="library-items">
          <div v-for="agent in allAgents" :key="agent.id" class="library-item">
            <input
              type="checkbox"
              :checked="selectedItems.has(`agent-${agent.id}`)"
              @change="toggleItem(`agent-${agent.id}`)"
              class="bulk-checkbox"
            />
            <div class="item-icon agent">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                <circle cx="12" cy="7" r="4"/>
              </svg>
            </div>
            <div class="item-info">
              <span class="item-name">{{ agent.name }}</span>
              <span v-if="agent.role" class="item-meta">{{ agent.role }}</span>
            </div>
            <div class="install-actions">
              <span v-if="isInstalled('agent', agent.id)" class="installed-badge">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                  <path d="M20 6L9 17l-5-5"/>
                </svg>
                .claude/
              </span>
              <button
                v-if="isInstalled('agent', agent.id)"
                class="install-btn uninstall"
                :disabled="isInstallingComponent[`agent-${agent.id}`]"
                @click.stop="emit('uninstall', 'agent', agent.id, agent.name)"
                title="Remove from .claude/ directory"
              >
                Uninstall
              </button>
              <button
                v-else
                class="install-btn"
                :disabled="isInstallingComponent[`agent-${agent.id}`]"
                @click.stop="emit('install', 'agent', agent.id, agent.name)"
                title="Install to .claude/ directory"
              >
                Install
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Skills Tab Content -->
    <div v-if="activeLibraryTab === 'skills'" class="tab-content">
      <div class="tab-header">
        <label class="select-all-label">
          <input type="checkbox" :checked="selectAll" @change="toggleSelectAll" class="bulk-checkbox" />
          <span class="section-title">Project Skills</span>
        </label>
        <div class="tab-header-actions">
          <button
            v-if="selectedItems.size > 0"
            class="header-bulk-btn install"
            :disabled="isBulkInstalling"
            @click="bulkInstall"
          >Install Selected ({{ selectedItems.size }})</button>
          <button
            v-if="selectedItems.size > 0"
            class="header-bulk-btn uninstall"
            :disabled="isBulkInstalling"
            @click="bulkUninstall"
          >Uninstall Selected</button>
          <button class="btn-add-skill" @click="emit('addSkill')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            Add Skill
          </button>
        </div>
      </div>

      <div v-if="projectSkills.length === 0" class="empty-state small">
        <p>No skills assigned to this project</p>
      </div>

      <div v-else class="skills-list">
        <button class="section-collapse-btn" @click="toggleSection('skills')">
          <svg :class="{ rotated: !collapsedSections.skills }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
          <span>{{ projectSkills.length }} skill{{ projectSkills.length !== 1 ? 's' : '' }}</span>
        </button>
        <template v-if="!collapsedSections.skills">
        <div v-for="skill in projectSkills" :key="skill.id" class="skill-item">
          <input
            type="checkbox"
            :checked="selectedItems.has(`skill-${skill.skill_name}`)"
            @change="toggleItem(`skill-${skill.skill_name}`)"
            class="bulk-checkbox"
          />
          <div class="skill-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M12 2L2 7l10 5 10-5-10-5z"/>
              <path d="M2 17l10 5 10-5"/>
              <path d="M2 12l10 5 10-5"/>
            </svg>
          </div>
          <div class="skill-info">
            <span class="skill-name">{{ skill.skill_name }}</span>
            <span v-if="skill.skill_path" class="skill-path">{{ skill.skill_path }}</span>
          </div>
          <span class="skill-source" :class="skill.source">{{ skill.source }}</span>
          <div class="install-actions">
            <span v-if="isInstalled('skill', skill.skill_name)" class="installed-badge">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                <path d="M20 6L9 17l-5-5"/>
              </svg>
              .claude/
            </span>
            <button
              v-if="isInstalled('skill', skill.skill_name)"
              class="install-btn uninstall"
              :disabled="isInstallingComponent[`skill-${skill.skill_name}`]"
              @click.stop="emit('uninstall', 'skill', skill.skill_name, skill.skill_name)"
              title="Remove from .claude/ directory"
            >
              Uninstall
            </button>
            <button
              v-else
              class="install-btn"
              :disabled="isInstallingComponent[`skill-${skill.skill_name}`]"
              @click.stop="emit('install', 'skill', skill.skill_name, skill.skill_name)"
              title="Install to .claude/ directory"
            >
              Install
            </button>
          </div>
          <button
            v-if="skill.source === 'manual'"
            class="btn-remove-skill"
            @click="emit('removeSkill', skill)"
            title="Remove skill"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
        </template>
      </div>
    </div>

    <!-- Hooks Tab Content -->
    <div v-if="activeLibraryTab === 'hooks'" class="tab-content">
      <div class="tab-header">
        <label class="select-all-label">
          <input type="checkbox" :checked="selectAll" @change="toggleSelectAll" class="bulk-checkbox" />
          <span class="section-title">Project Hooks</span>
        </label>
        <div class="tab-header-actions">
          <button
            v-if="selectedItems.size > 0"
            class="header-bulk-btn install"
            :disabled="isBulkInstalling"
            @click="bulkInstall"
          >Install Selected ({{ selectedItems.size }})</button>
          <button
            v-if="selectedItems.size > 0"
            class="header-bulk-btn uninstall"
            :disabled="isBulkInstalling"
            @click="bulkUninstall"
          >Uninstall Selected</button>
        </div>
      </div>

      <div v-if="projectHooks.length === 0 && globalHooks.length === 0" class="empty-state small">
        <p>No hooks available</p>
      </div>

      <template v-else>
        <div v-if="projectHooks.length > 0" class="library-section">
          <button class="section-collapse-btn" @click="toggleSection('hooks_project')">
            <svg :class="{ rotated: !collapsedSections.hooks_project }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
            <span>Included in Project ({{ projectHooks.length }})</span>
          </button>
          <div v-if="!collapsedSections.hooks_project" class="library-items">
            <div v-for="hook in projectHooks" :key="hook.id" class="library-item included">
              <input
                type="checkbox"
                :checked="selectedItems.has(`hook-${hook.id}`)"
                @change="toggleItem(`hook-${hook.id}`)"
                class="bulk-checkbox"
              />
              <div class="item-icon hook">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
                  <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
                </svg>
              </div>
              <div class="item-info">
                <span class="item-name">{{ hook.name }}</span>
                <span class="item-meta">{{ hook.event }}</span>
              </div>
              <div class="install-actions">
                <span v-if="isInstalled('hook', String(hook.id))" class="installed-badge">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                    <path d="M20 6L9 17l-5-5"/>
                  </svg>
                  .claude/
                </span>
                <button
                  v-if="isInstalled('hook', String(hook.id))"
                  class="install-btn uninstall"
                  :disabled="isInstallingComponent[`hook-${hook.id}`]"
                  @click.stop="emit('uninstall', 'hook', String(hook.id), hook.name)"
                  title="Remove from .claude/ directory"
                >
                  Uninstall
                </button>
                <button
                  v-else
                  class="install-btn"
                  :disabled="isInstallingComponent[`hook-${hook.id}`]"
                  @click.stop="emit('install', 'hook', String(hook.id), hook.name)"
                  title="Install to .claude/ directory"
                >
                  Install
                </button>
              </div>
              <button class="toggle-btn included" @click="emit('toggleHook', hook)" title="Remove from project">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M20 6L9 17l-5-5"/>
                </svg>
              </button>
            </div>
          </div>
        </div>

        <div v-if="globalHooks.length > 0" class="library-section">
          <button class="section-collapse-btn" @click="toggleSection('hooks_global')">
            <svg :class="{ rotated: !collapsedSections.hooks_global }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
            <span>Available Global ({{ globalHooks.length }})</span>
          </button>
          <div v-if="!collapsedSections.hooks_global" class="library-items">
            <div v-for="hook in globalHooks" :key="hook.id" class="library-item">
              <div class="item-icon hook">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
                  <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
                </svg>
              </div>
              <div class="item-info">
                <span class="item-name">{{ hook.name }}</span>
                <span class="item-meta">{{ hook.event }}</span>
              </div>
              <div class="install-actions">
                <span v-if="isInstalled('hook', String(hook.id))" class="installed-badge">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                    <path d="M20 6L9 17l-5-5"/>
                  </svg>
                  .claude/
                </span>
                <button
                  v-if="isInstalled('hook', String(hook.id))"
                  class="install-btn uninstall"
                  :disabled="isInstallingComponent[`hook-${hook.id}`]"
                  @click.stop="emit('uninstall', 'hook', String(hook.id), hook.name)"
                  title="Remove from .claude/ directory"
                >
                  Uninstall
                </button>
                <button
                  v-else
                  class="install-btn"
                  :disabled="isInstallingComponent[`hook-${hook.id}`]"
                  @click.stop="emit('install', 'hook', String(hook.id), hook.name)"
                  title="Install to .claude/ directory"
                >
                  Install
                </button>
              </div>
              <button class="toggle-btn" @click="emit('toggleHook', hook)" title="Include to Project">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="12" y1="5" x2="12" y2="19"/>
                  <line x1="5" y1="12" x2="19" y2="12"/>
                </svg>
              </button>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- Commands Tab Content -->
    <div v-if="activeLibraryTab === 'commands'" class="tab-content">
      <div class="tab-header">
        <label class="select-all-label">
          <input type="checkbox" :checked="selectAll" @change="toggleSelectAll" class="bulk-checkbox" />
          <span class="section-title">Project Commands</span>
        </label>
        <div class="tab-header-actions">
          <button
            v-if="selectedItems.size > 0"
            class="header-bulk-btn install"
            :disabled="isBulkInstalling"
            @click="bulkInstall"
          >Install Selected ({{ selectedItems.size }})</button>
          <button
            v-if="selectedItems.size > 0"
            class="header-bulk-btn uninstall"
            :disabled="isBulkInstalling"
            @click="bulkUninstall"
          >Uninstall Selected</button>
        </div>
      </div>

      <div v-if="projectCommands.length === 0 && globalCommands.length === 0" class="empty-state small">
        <p>No commands available</p>
      </div>

      <template v-else>
        <div v-if="projectCommands.length > 0" class="library-section">
          <button class="section-collapse-btn" @click="toggleSection('commands_project')">
            <svg :class="{ rotated: !collapsedSections.commands_project }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
            <span>Included in Project ({{ projectCommands.length }})</span>
          </button>
          <div v-if="!collapsedSections.commands_project" class="library-items">
            <div v-for="command in projectCommands" :key="command.id" class="library-item included">
              <input
                type="checkbox"
                :checked="selectedItems.has(`command-${command.id}`)"
                @change="toggleItem(`command-${command.id}`)"
                class="bulk-checkbox"
              />
              <div class="item-icon command">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <polyline points="4 17 10 11 4 5"/>
                  <line x1="12" y1="19" x2="20" y2="19"/>
                </svg>
              </div>
              <div class="item-info">
                <span class="item-name">/{{ command.name }}</span>
                <span v-if="command.description" class="item-meta">{{ command.description }}</span>
              </div>
              <div class="install-actions">
                <span v-if="isInstalled('command', String(command.id))" class="installed-badge">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                    <path d="M20 6L9 17l-5-5"/>
                  </svg>
                  .claude/
                </span>
                <button
                  v-if="isInstalled('command', String(command.id))"
                  class="install-btn uninstall"
                  :disabled="isInstallingComponent[`command-${command.id}`]"
                  @click.stop="emit('uninstall', 'command', String(command.id), command.name)"
                  title="Remove from .claude/ directory"
                >
                  Uninstall
                </button>
                <button
                  v-else
                  class="install-btn"
                  :disabled="isInstallingComponent[`command-${command.id}`]"
                  @click.stop="emit('install', 'command', String(command.id), command.name)"
                  title="Install to .claude/ directory"
                >
                  Install
                </button>
              </div>
              <button class="toggle-btn included" @click="emit('toggleCommand', command)" title="Remove from project">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M20 6L9 17l-5-5"/>
                </svg>
              </button>
            </div>
          </div>
        </div>

        <div v-if="globalCommands.length > 0" class="library-section">
          <button class="section-collapse-btn" @click="toggleSection('commands_global')">
            <svg :class="{ rotated: !collapsedSections.commands_global }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
            <span>Available Global ({{ globalCommands.length }})</span>
          </button>
          <div v-if="!collapsedSections.commands_global" class="library-items">
            <div v-for="command in globalCommands" :key="command.id" class="library-item">
              <div class="item-icon command">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <polyline points="4 17 10 11 4 5"/>
                  <line x1="12" y1="19" x2="20" y2="19"/>
                </svg>
              </div>
              <div class="item-info">
                <span class="item-name">/{{ command.name }}</span>
                <span v-if="command.description" class="item-meta">{{ command.description }}</span>
              </div>
              <div class="install-actions">
                <span v-if="isInstalled('command', String(command.id))" class="installed-badge">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                    <path d="M20 6L9 17l-5-5"/>
                  </svg>
                  .claude/
                </span>
                <button
                  v-if="isInstalled('command', String(command.id))"
                  class="install-btn uninstall"
                  :disabled="isInstallingComponent[`command-${command.id}`]"
                  @click.stop="emit('uninstall', 'command', String(command.id), command.name)"
                  title="Remove from .claude/ directory"
                >
                  Uninstall
                </button>
                <button
                  v-else
                  class="install-btn"
                  :disabled="isInstallingComponent[`command-${command.id}`]"
                  @click.stop="emit('install', 'command', String(command.id), command.name)"
                  title="Install to .claude/ directory"
                >
                  Install
                </button>
              </div>
              <button class="toggle-btn" @click="emit('toggleCommand', command)" title="Include to Project">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="12" y1="5" x2="12" y2="19"/>
                  <line x1="5" y1="12" x2="19" y2="12"/>
                </svg>
              </button>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- Rules Tab Content -->
    <div v-if="activeLibraryTab === 'rules'" class="tab-content">
      <div class="tab-header">
        <label class="select-all-label">
          <input type="checkbox" :checked="selectAll" @change="toggleSelectAll" class="bulk-checkbox" />
          <span class="section-title">Project Rules</span>
        </label>
        <div class="tab-header-actions">
          <button
            v-if="selectedItems.size > 0"
            class="header-bulk-btn install"
            :disabled="isBulkInstalling"
            @click="bulkInstall"
          >Install Selected ({{ selectedItems.size }})</button>
          <button
            v-if="selectedItems.size > 0"
            class="header-bulk-btn uninstall"
            :disabled="isBulkInstalling"
            @click="bulkUninstall"
          >Uninstall Selected</button>
        </div>
      </div>

      <div v-if="projectRules.length === 0 && globalRules.length === 0" class="empty-state small">
        <p>No rules available</p>
      </div>

      <template v-else>
        <div v-if="projectRules.length > 0" class="library-section">
          <button class="section-collapse-btn" @click="toggleSection('rules_project')">
            <svg :class="{ rotated: !collapsedSections.rules_project }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
            <span>Included in Project ({{ projectRules.length }})</span>
          </button>
          <div v-if="!collapsedSections.rules_project" class="library-items">
            <div v-for="rule in projectRules" :key="rule.id" class="library-item included">
              <input
                type="checkbox"
                :checked="selectedItems.has(`rule-${rule.id}`)"
                @change="toggleItem(`rule-${rule.id}`)"
                class="bulk-checkbox"
              />
              <div class="item-icon rule">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M9 11l3 3L22 4"/>
                  <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>
                </svg>
              </div>
              <div class="item-info">
                <span class="item-name">{{ rule.name }}</span>
                <span class="item-meta">{{ rule.rule_type }}</span>
              </div>
              <div class="install-actions">
                <span v-if="isInstalled('rule', String(rule.id))" class="installed-badge">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                    <path d="M20 6L9 17l-5-5"/>
                  </svg>
                  .claude/
                </span>
                <button
                  v-if="isInstalled('rule', String(rule.id))"
                  class="install-btn uninstall"
                  :disabled="isInstallingComponent[`rule-${rule.id}`]"
                  @click.stop="emit('uninstall', 'rule', String(rule.id), rule.name)"
                  title="Remove from .claude/ directory"
                >
                  Uninstall
                </button>
                <button
                  v-else
                  class="install-btn"
                  :disabled="isInstallingComponent[`rule-${rule.id}`]"
                  @click.stop="emit('install', 'rule', String(rule.id), rule.name)"
                  title="Install to .claude/ directory"
                >
                  Install
                </button>
              </div>
              <button class="toggle-btn included" @click="emit('toggleRule', rule)" title="Remove from project">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M20 6L9 17l-5-5"/>
                </svg>
              </button>
            </div>
          </div>
        </div>

        <div v-if="globalRules.length > 0" class="library-section">
          <button class="section-collapse-btn" @click="toggleSection('rules_global')">
            <svg :class="{ rotated: !collapsedSections.rules_global }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="9 18 15 12 9 6"/>
            </svg>
            <span>Available Global ({{ globalRules.length }})</span>
          </button>
          <div v-if="!collapsedSections.rules_global" class="library-items">
            <div v-for="rule in globalRules" :key="rule.id" class="library-item">
              <div class="item-icon rule">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M9 11l3 3L22 4"/>
                  <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>
                </svg>
              </div>
              <div class="item-info">
                <span class="item-name">{{ rule.name }}</span>
                <span class="item-meta">{{ rule.rule_type }}</span>
              </div>
              <div class="install-actions">
                <span v-if="isInstalled('rule', String(rule.id))" class="installed-badge">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                    <path d="M20 6L9 17l-5-5"/>
                  </svg>
                  .claude/
                </span>
                <button
                  v-if="isInstalled('rule', String(rule.id))"
                  class="install-btn uninstall"
                  :disabled="isInstallingComponent[`rule-${rule.id}`]"
                  @click.stop="emit('uninstall', 'rule', String(rule.id), rule.name)"
                  title="Remove from .claude/ directory"
                >
                  Uninstall
                </button>
                <button
                  v-else
                  class="install-btn"
                  :disabled="isInstallingComponent[`rule-${rule.id}`]"
                  @click.stop="emit('install', 'rule', String(rule.id), rule.name)"
                  title="Install to .claude/ directory"
                >
                  Install
                </button>
              </div>
              <button class="toggle-btn" @click="emit('toggleRule', rule)" title="Include to Project">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="12" y1="5" x2="12" y2="19"/>
                  <line x1="5" y1="12" x2="19" y2="12"/>
                </svg>
              </button>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- Floating Bulk Action Bar -->
    <div v-if="selectedItems.size > 0" class="bulk-action-bar">
      <span class="bulk-count">{{ selectedItems.size }} selected</span>
      <span v-if="bulkProgress" class="bulk-progress">{{ bulkProgress }}</span>
      <div class="bulk-buttons">
        <button
          class="bulk-btn install"
          :disabled="isBulkInstalling"
          @click="bulkInstall"
        >
          Install Selected
        </button>
        <button
          class="bulk-btn uninstall"
          :disabled="isBulkInstalling"
          @click="bulkUninstall"
        >
          Uninstall Selected
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.card {
  overflow: hidden;
  position: relative;
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

.library-card {
  overflow: visible;
}

.library-tabs {
  display: flex;
  gap: 4px;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-tertiary);
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: var(--text-tertiary);
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.tab-btn:hover {
  background: var(--bg-elevated);
  color: var(--text-secondary);
}

.tab-btn.active {
  background: var(--bg-secondary);
  color: var(--accent-cyan);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.tab-btn svg {
  width: 16px;
  height: 16px;
}

.tab-content {
  padding: 0;
}

.tab-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.select-all-label {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}

.section-title {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
}

.empty-state.small {
  padding: 32px 20px;
}

.empty-state.small p {
  font-size: 0.85rem;
  margin-bottom: 0;
}

.library-section {
  padding: 16px 20px;
}

.library-section:not(:last-child) {
  border-bottom: 1px solid var(--border-subtle);
}

.section-label {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-tertiary);
  margin-bottom: 12px;
}

.library-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.library-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  border: 1px solid transparent;
  transition: all 0.15s;
}

.library-item.included {
  background: rgba(0, 212, 255, 0.08);
  border-color: var(--accent-cyan);
}

/* Checkbox styling */
.bulk-checkbox {
  width: 16px;
  height: 16px;
  accent-color: var(--accent-cyan);
  cursor: pointer;
  flex-shrink: 0;
}

.item-icon {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.item-icon svg {
  width: 18px;
  height: 18px;
}

.item-icon.agent {
  background: var(--accent-cyan-dim, rgba(0, 212, 255, 0.15));
  color: var(--accent-cyan, #00d4ff);
}

.item-icon.hook {
  background: var(--accent-violet-dim, rgba(136, 85, 255, 0.15));
  color: var(--accent-violet, #8855ff);
}

.item-icon.command {
  background: var(--accent-amber-dim, rgba(255, 170, 0, 0.15));
  color: var(--accent-amber, #ffaa00);
}

.item-icon.rule {
  background: var(--accent-emerald-dim, rgba(0, 255, 136, 0.15));
  color: var(--accent-emerald, #00ff88);
}

.item-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.item-name {
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-meta {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.toggle-btn {
  width: 32px;
  height: 32px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-tertiary);
  transition: all 0.15s;
  flex-shrink: 0;
}

.toggle-btn:hover {
  background: var(--bg-elevated);
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}

.toggle-btn.included {
  background: var(--accent-cyan);
  border-color: var(--accent-cyan);
  color: #000;
}

.toggle-btn.included:hover {
  background: var(--accent-crimson);
  border-color: var(--accent-crimson);
  color: #fff;
}

.toggle-btn svg {
  width: 16px;
  height: 16px;
}

/* Install Actions */
.install-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  flex-shrink: 0;
}

.installed-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--accent-emerald, #00ff88);
  background: var(--accent-emerald-dim, rgba(0, 255, 136, 0.15));
  padding: 2px 8px;
  border-radius: 4px;
}

.install-btn {
  padding: 4px 10px;
  font-size: 0.75rem;
  font-weight: 500;
  border-radius: 4px;
  border: 1px solid var(--accent-cyan);
  background: transparent;
  color: var(--accent-cyan);
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;
}

.install-btn:hover:not(:disabled) {
  background: var(--accent-cyan);
  color: #000;
}

.install-btn.uninstall {
  border-color: var(--accent-crimson, #ff4081);
  color: var(--accent-crimson, #ff4081);
}

.install-btn.uninstall:hover:not(:disabled) {
  background: var(--accent-crimson, #ff4081);
  color: #fff;
}

.install-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Skills */
.btn-add-skill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--accent-violet);
  border: none;
  border-radius: 6px;
  color: #fff;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-add-skill:hover {
  background: #9966ff;
}

.btn-add-skill svg {
  width: 14px;
  height: 14px;
}

.skills-list {
  display: flex;
  flex-direction: column;
  padding: 12px 20px 20px;
}

.skill-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  margin-bottom: 8px;
}

.skill-item:last-child {
  margin-bottom: 0;
}

.skill-icon {
  width: 36px;
  height: 36px;
  background: var(--accent-violet-dim, rgba(136, 85, 255, 0.15));
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.skill-icon svg {
  width: 18px;
  height: 18px;
  color: var(--accent-violet, #8855ff);
}

.skill-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.skill-name {
  font-weight: 500;
  color: var(--text-primary);
}

.skill-path {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.skill-source {
  font-size: 0.7rem;
  font-weight: 500;
  text-transform: uppercase;
  padding: 2px 6px;
  border-radius: 3px;
  background: var(--bg-elevated);
  color: var(--text-tertiary);
}

.skill-source.manual {
  background: var(--accent-violet-dim, rgba(136, 85, 255, 0.15));
  color: var(--accent-violet, #8855ff);
}

.skill-source.team_sync {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.skill-source.agent_sync {
  background: var(--accent-green-dim, rgba(0, 200, 83, 0.15));
  color: var(--accent-green, #00c853);
}

.btn-remove-skill {
  width: 28px;
  height: 28px;
  background: transparent;
  border: none;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-tertiary);
  transition: all 0.15s;
}

.btn-remove-skill:hover {
  background: var(--accent-crimson-dim, rgba(255, 64, 129, 0.15));
  color: var(--accent-crimson, #ff4081);
}

.btn-remove-skill svg {
  width: 14px;
  height: 14px;
}

/* Floating Bulk Action Bar */
.bulk-action-bar {
  position: sticky;
  bottom: 0;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 20px;
  background: var(--bg-secondary);
  border-top: 1px solid var(--accent-cyan);
  box-shadow: 0 -4px 12px rgba(0, 0, 0, 0.2);
  z-index: 10;
}

.bulk-count {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--accent-cyan);
}

.bulk-progress {
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.bulk-buttons {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.bulk-btn {
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  border: none;
}

.bulk-btn.install {
  background: var(--accent-cyan);
  color: #000;
}

.bulk-btn.install:hover:not(:disabled) {
  box-shadow: 0 2px 8px rgba(0, 212, 255, 0.3);
}

.bulk-btn.uninstall {
  background: transparent;
  border: 1px solid var(--accent-crimson, #ff4081);
  color: var(--accent-crimson, #ff4081);
}

.bulk-btn.uninstall:hover:not(:disabled) {
  background: var(--accent-crimson, #ff4081);
  color: #fff;
}

.bulk-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Section collapse toggle */
.section-collapse-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 0;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: color 0.15s;
  font-family: inherit;
  margin-bottom: 8px;
}

.section-collapse-btn:hover {
  color: var(--text-primary);
}

.section-collapse-btn svg {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  transition: transform 0.2s;
}

.section-collapse-btn svg.rotated {
  transform: rotate(90deg);
}

/* Header bulk actions */
.tab-header-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.header-bulk-btn {
  padding: 5px 12px;
  border-radius: 5px;
  font-size: 0.75rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  border: none;
  white-space: nowrap;
}

.header-bulk-btn.install {
  background: var(--accent-cyan);
  color: #000;
}

.header-bulk-btn.install:hover:not(:disabled) {
  box-shadow: 0 2px 8px rgba(0, 212, 255, 0.3);
}

.header-bulk-btn.uninstall {
  background: transparent;
  border: 1px solid var(--accent-crimson, #ff4081);
  color: var(--accent-crimson, #ff4081);
}

.header-bulk-btn.uninstall:hover:not(:disabled) {
  background: var(--accent-crimson, #ff4081);
  color: #fff;
}

.header-bulk-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
