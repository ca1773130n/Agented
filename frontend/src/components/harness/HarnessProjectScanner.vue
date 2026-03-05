<script setup lang="ts">
import { ref } from 'vue';
import type { Team, Agent, Command, Hook, UserSkill, PluginComponent, HarnessConfig, MarketplaceSearchResult } from '../../services/api';
import { marketplaceApi } from '../../services/api';

const props = defineProps<{
  includedTeams: Team[];
  syncedTeams: Team[];
  agents: Agent[];
  commands: Command[];
  hooks: Hook[];
  skills: UserSkill[];
  scripts: PluginComponent[];
  harnessConfig: HarnessConfig | null;
}>();

const emit = defineEmits<{
  pluginsChanged: [plugins: MarketplaceSearchResult[]];
  copyConfig: [success: boolean];
  downloadConfig: [];
}>();

const expandedSections = ref<Record<string, boolean>>({
  teams: true,
  agents: true,
  commands: true,
  hooks: true,
  skills: true,
  plugins: true,
  scripts: false,
});

const copied = ref(false);

// Plugin search state
const pluginSearchQuery = ref('');
const pluginSearchResults = ref<MarketplaceSearchResult[]>([]);
const isSearchingPlugins = ref(false);
const selectedPlugins = ref<MarketplaceSearchResult[]>([]);
const showPluginDropdown = ref(false);
let pluginDebounceTimer: ReturnType<typeof setTimeout>;

function toggleSection(section: string) {
  expandedSections.value[section] = !expandedSections.value[section];
}

function onPluginSearchInput() {
  const q = pluginSearchQuery.value.trim();
  clearTimeout(pluginDebounceTimer);
  pluginDebounceTimer = setTimeout(async () => {
    if (q.length >= 2 || q.length === 0) {
      isSearchingPlugins.value = true;
      try {
        const response = await marketplaceApi.search(q, 'plugin');
        const selectedNames = new Set(selectedPlugins.value.map(p => `${p.marketplace_id}-${p.name}`));
        pluginSearchResults.value = response.results.filter(
          r => !selectedNames.has(`${r.marketplace_id}-${r.name}`)
        );
        showPluginDropdown.value = true;
      } catch {
        pluginSearchResults.value = [];
      } finally {
        isSearchingPlugins.value = false;
      }
    }
  }, 300);
}

function selectPlugin(plugin: MarketplaceSearchResult) {
  selectedPlugins.value.push(plugin);
  pluginSearchQuery.value = '';
  pluginSearchResults.value = [];
  showPluginDropdown.value = false;
  emit('pluginsChanged', selectedPlugins.value);
}

function removeSelectedPlugin(index: number) {
  selectedPlugins.value.splice(index, 1);
  emit('pluginsChanged', selectedPlugins.value);
}

function closePluginDropdown() {
  setTimeout(() => {
    showPluginDropdown.value = false;
  }, 200);
}

async function copyConfig() {
  if (!props.harnessConfig) return;
  try {
    await navigator.clipboard.writeText(props.harnessConfig.config_json);
    copied.value = true;
    emit('copyConfig', true);
    setTimeout(() => { copied.value = false; }, 2000);
  } catch {
    emit('copyConfig', false);
  }
}

function downloadConfig() {
  emit('downloadConfig');
}
</script>

<template>
  <div class="harness-content">
    <!-- Teams Section -->
    <div class="section">
      <div class="section-header" @click="toggleSection('teams')">
        <div class="section-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/>
            <circle cx="9" cy="7" r="4"/>
            <path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/>
          </svg>
          <h2>Included Teams ({{ includedTeams.length }})</h2>
        </div>
        <svg class="chevron" :class="{ expanded: expandedSections.teams }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>
      <div v-if="expandedSections.teams" class="section-content">
        <div v-if="includedTeams.length === 0" class="empty-section">
          <span>No teams assigned</span>
        </div>
        <div v-else class="items-grid">
          <div v-for="team in includedTeams" :key="team.id" class="item-card team-card">
            <div class="item-color" :style="{ backgroundColor: team.color }"></div>
            <div class="item-info">
              <span class="item-name">{{ team.name }}</span>
              <span class="item-meta">{{ team.member_count }} members</span>
            </div>
          </div>
        </div>

        <!-- GitHub Synced Teams (read-only) -->
        <div v-if="syncedTeams.length > 0" class="synced-teams-section">
          <div class="synced-header">
            <svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16">
              <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
            </svg>
            <span>Teams from GitHub ({{ syncedTeams.length }})</span>
          </div>
          <div class="items-grid">
            <div v-for="team in syncedTeams" :key="team.id" class="item-card team-card synced">
              <div class="item-color" :style="{ backgroundColor: team.color }"></div>
              <div class="item-info">
                <span class="item-name">{{ team.name }}</span>
                <span class="item-meta">{{ team.member_count }} members</span>
              </div>
              <span class="source-badge github">GitHub</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Agents Section -->
    <div class="section">
      <div class="section-header" @click="toggleSection('agents')">
        <div class="section-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
            <path d="M7 11V7a5 5 0 0110 0v4"/>
          </svg>
          <h2>Included Agents ({{ agents.length }})</h2>
        </div>
        <svg class="chevron" :class="{ expanded: expandedSections.agents }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>
      <div v-if="expandedSections.agents" class="section-content">
        <div v-if="agents.length === 0" class="empty-section">
          <span>No agents included</span>
        </div>
        <div v-else class="items-grid">
          <div v-for="agent in agents" :key="agent.id" class="item-card agent-card">
            <div class="item-icon agent-icon" :style="{ backgroundColor: agent.color || 'var(--accent-violet-dim)' }">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                <path d="M7 11V7a5 5 0 0110 0v4"/>
              </svg>
            </div>
            <div class="item-info">
              <span class="item-name">{{ agent.name }}</span>
              <span class="item-meta">{{ agent.role || agent.description || 'No role defined' }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Commands Section -->
    <div class="section">
      <div class="section-header" @click="toggleSection('commands')">
        <div class="section-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="4 17 10 11 4 5"/>
            <line x1="12" y1="19" x2="20" y2="19"/>
          </svg>
          <h2>Included Commands ({{ commands.length }})</h2>
        </div>
        <svg class="chevron" :class="{ expanded: expandedSections.commands }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>
      <div v-if="expandedSections.commands" class="section-content">
        <div v-if="commands.length === 0" class="empty-section">
          <span>No commands configured</span>
        </div>
        <div v-else class="items-list">
          <div v-for="cmd in commands" :key="cmd.id" class="item-row">
            <div class="item-icon command-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="4 17 10 11 4 5"/>
                <line x1="12" y1="19" x2="20" y2="19"/>
              </svg>
            </div>
            <div class="item-info">
              <span class="item-name">/{{ cmd.name }}</span>
              <span class="item-meta">{{ cmd.description || 'No description' }}</span>
            </div>
            <span class="item-badge" :class="cmd.enabled ? 'enabled' : 'disabled'">
              {{ cmd.enabled ? 'Enabled' : 'Disabled' }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Hooks Section -->
    <div class="section">
      <div class="section-header" @click="toggleSection('hooks')">
        <div class="section-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/>
            <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/>
          </svg>
          <h2>Included Hooks ({{ hooks.length }})</h2>
        </div>
        <svg class="chevron" :class="{ expanded: expandedSections.hooks }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>
      <div v-if="expandedSections.hooks" class="section-content">
        <div v-if="hooks.length === 0" class="empty-section">
          <span>No hooks configured</span>
        </div>
        <div v-else class="items-list">
          <div v-for="hook in hooks" :key="hook.id" class="item-row">
            <div class="item-icon hook-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/>
                <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/>
              </svg>
            </div>
            <div class="item-info">
              <span class="item-name">{{ hook.name }}</span>
              <span class="item-meta">{{ hook.event }} - {{ hook.description || 'No description' }}</span>
            </div>
            <span class="item-badge event-badge">{{ hook.event }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Skills Section -->
    <div class="section">
      <div class="section-header" @click="toggleSection('skills')">
        <div class="section-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
            <path d="M2 12l10 5 10-5"/>
          </svg>
          <h2>Included Skills ({{ skills.length }})</h2>
        </div>
        <svg class="chevron" :class="{ expanded: expandedSections.skills }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>
      <div v-if="expandedSections.skills" class="section-content">
        <div v-if="skills.length === 0" class="empty-section">
          <span>No skills selected for harness</span>
        </div>
        <div v-else class="items-list">
          <div v-for="skill in skills" :key="skill.id" class="item-row">
            <div class="item-icon skill-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                <path d="M2 17l10 5 10-5"/>
                <path d="M2 12l10 5 10-5"/>
              </svg>
            </div>
            <div class="item-info">
              <span class="item-name">{{ skill.skill_name }}</span>
              <span class="item-meta">{{ skill.skill_path }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Marketplace Plugins Section -->
    <div class="section">
      <div class="section-header" @click="toggleSection('plugins')">
        <div class="section-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
            <path d="M3 9h18M9 21V9"/>
          </svg>
          <h2>Marketplace Plugins ({{ selectedPlugins.length }})</h2>
        </div>
        <svg class="chevron" :class="{ expanded: expandedSections.plugins }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>
      <div v-if="expandedSections.plugins" class="section-content">
        <!-- Plugin Search Input -->
        <div class="plugin-search-container">
          <div class="plugin-search-input">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="8"/>
              <path d="M21 21l-4.35-4.35"/>
            </svg>
            <input
              v-model="pluginSearchQuery"
              type="text"
              placeholder="Search plugins from marketplaces..."
              @input="onPluginSearchInput"
              @focus="onPluginSearchInput"
              @blur="closePluginDropdown"
            />
            <div v-if="isSearchingPlugins" class="search-spinner"></div>
          </div>

          <!-- Dropdown Results -->
          <div v-if="showPluginDropdown && pluginSearchResults.length > 0" class="plugin-dropdown">
            <div
              v-for="plugin in pluginSearchResults"
              :key="`${plugin.marketplace_id}-${plugin.name}`"
              class="plugin-dropdown-item"
              @mousedown.prevent="selectPlugin(plugin)"
            >
              <div class="dropdown-item-info">
                <span class="dropdown-item-name">{{ plugin.name }}</span>
                <span class="dropdown-item-desc">{{ plugin.description || 'No description' }}</span>
              </div>
              <span class="dropdown-marketplace-badge">{{ plugin.marketplace_name }}</span>
            </div>
          </div>

          <div v-if="showPluginDropdown && pluginSearchResults.length === 0 && !isSearchingPlugins && pluginSearchQuery.trim().length >= 2" class="plugin-dropdown">
            <div class="plugin-dropdown-empty">No plugins found</div>
          </div>
        </div>

        <!-- Selected Plugins -->
        <div v-if="selectedPlugins.length === 0" class="empty-section">
          <span>No marketplace plugins selected. Search above to add plugins.</span>
        </div>
        <div v-else class="selected-plugins">
          <div v-for="(plugin, index) in selectedPlugins" :key="`selected-${plugin.marketplace_id}-${plugin.name}`" class="selected-plugin-chip">
            <span class="chip-name">{{ plugin.name }}</span>
            <span class="chip-marketplace">{{ plugin.marketplace_name }}</span>
            <button class="chip-remove" @click="removeSelectedPlugin(index)" title="Remove plugin">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Scripts Section -->
    <div class="section">
      <div class="section-header" @click="toggleSection('scripts')">
        <div class="section-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
            <polyline points="10 9 9 9 8 9"/>
          </svg>
          <h2>Included Scripts ({{ scripts.length }})</h2>
        </div>
        <svg class="chevron" :class="{ expanded: expandedSections.scripts }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>
      <div v-if="expandedSections.scripts" class="section-content">
        <div v-if="scripts.length === 0" class="empty-section">
          <span>No scripts configured</span>
        </div>
        <div v-else class="items-list">
          <div v-for="script in scripts" :key="script.id" class="item-row">
            <div class="item-icon script-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
            </div>
            <div class="item-info">
              <span class="item-name">{{ script.name }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Config Preview Section -->
    <div class="section config-section">
      <div class="section-header">
        <div class="section-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
          </svg>
          <h2>Config Preview</h2>
        </div>
        <div class="preview-actions">
          <button class="btn btn-sm" @click="copyConfig" :disabled="!harnessConfig">
            <svg v-if="!copied" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
              <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
            </svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M20 6L9 17l-5-5"/>
            </svg>
            {{ copied ? 'Copied!' : 'Copy' }}
          </button>
          <button class="btn btn-sm" @click="downloadConfig" :disabled="!harnessConfig">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/>
            </svg>
            Download
          </button>
        </div>
      </div>
      <div class="config-preview">
        <pre><code>{{ harnessConfig?.config_json || '{}' }}</code></pre>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Sections */
.harness-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  overflow: hidden;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  cursor: pointer;
  transition: background 0.15s;
}

.section-header:hover {
  background: var(--bg-tertiary);
}

.section-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-title svg {
  width: 20px;
  height: 20px;
  color: var(--accent-cyan);
}

.section-title h2 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.chevron {
  width: 20px;
  height: 20px;
  color: var(--text-tertiary);
  transition: transform 0.2s;
}

.chevron.expanded {
  transform: rotate(180deg);
}

.section-content {
  padding: 0 20px 20px;
}

.empty-section {
  padding: 24px;
  text-align: center;
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
  border-radius: 8px;
}

/* Items Grid (for Teams, Agents) */
.items-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.item-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.item-color {
  width: 8px;
  height: 40px;
  border-radius: 4px;
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

.agent-icon {
  background: var(--accent-violet-dim);
  color: var(--accent-violet);
}

.command-icon {
  background: var(--accent-green-dim, rgba(0, 200, 83, 0.15));
  color: var(--accent-green, #00c853);
}

.hook-icon {
  background: var(--accent-orange-dim, rgba(255, 152, 0, 0.15));
  color: var(--accent-orange, #ff9800);
}

.skill-icon {
  background: var(--accent-violet-dim, rgba(136, 85, 255, 0.15));
  color: var(--accent-violet, #8855ff);
}

.script-icon {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}

.item-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.item-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-meta {
  font-size: 12px;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Items List (for Commands, Hooks, Skills, Scripts) */
.items-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.item-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.item-badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  flex-shrink: 0;
}

.item-badge.enabled {
  background: var(--accent-green-dim, rgba(0, 200, 83, 0.15));
  color: var(--accent-green, #00c853);
}

.item-badge.disabled {
  background: var(--bg-elevated);
  color: var(--text-tertiary);
}

.item-badge.event-badge {
  background: var(--accent-orange-dim, rgba(255, 152, 0, 0.15));
  color: var(--accent-orange, #ff9800);
}

/* Config Section */
.config-section .section-header {
  cursor: default;
}

.config-section .section-header:hover {
  background: transparent;
}

.preview-actions {
  display: flex;
  gap: 8px;
}

.config-preview {
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 16px;
  max-height: 300px;
  overflow: auto;
  margin: 0 20px 20px;
}

.config-preview pre {
  margin: 0;
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--text-secondary);
  white-space: pre-wrap;
}

/* Plugin Search */
.plugin-search-container {
  position: relative;
  margin-bottom: 12px;
}

.plugin-search-input {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  transition: border-color 0.15s;
}

.plugin-search-input:focus-within {
  border-color: var(--accent-cyan);
}

.plugin-search-input svg {
  width: 16px;
  height: 16px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.plugin-search-input input {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: 14px;
}

.plugin-search-input input:focus {
  outline: none;
}

.plugin-search-input input::placeholder {
  color: var(--text-tertiary);
}

.search-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--border-default);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}

.plugin-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  margin-top: 4px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  max-height: 240px;
  overflow-y: auto;
  z-index: 10;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}

.plugin-dropdown-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  cursor: pointer;
  transition: background 0.1s;
}

.plugin-dropdown-item:hover {
  background: var(--bg-tertiary);
}

.dropdown-item-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.dropdown-item-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.dropdown-item-desc {
  font-size: 12px;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dropdown-marketplace-badge {
  font-size: 10px;
  padding: 2px 6px;
  background: var(--accent-blue-dim, rgba(56, 139, 253, 0.1));
  color: var(--accent-blue, #388bfd);
  border-radius: 3px;
  font-weight: 500;
  flex-shrink: 0;
  white-space: nowrap;
}

.plugin-dropdown-empty {
  padding: 16px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 13px;
}

.selected-plugins {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.selected-plugin-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
}

.chip-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.chip-marketplace {
  font-size: 10px;
  padding: 1px 5px;
  background: var(--accent-blue-dim, rgba(56, 139, 253, 0.1));
  color: var(--accent-blue, #388bfd);
  border-radius: 3px;
}

.chip-remove {
  width: 18px;
  height: 18px;
  background: transparent;
  border: none;
  border-radius: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-tertiary);
  transition: all 0.1s;
}

.chip-remove:hover {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.chip-remove svg {
  width: 12px;
  height: 12px;
}

/* Synced Teams Section */
.synced-teams-section {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border-subtle);
}

.synced-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--text-tertiary);
}

.synced-header svg {
  color: var(--text-tertiary);
}

.team-card.synced {
  background: var(--bg-tertiary);
  opacity: 0.75;
  border: 1px dashed var(--border-default);
}

.source-badge {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  padding: 2px 6px;
  border-radius: 3px;
}

.source-badge.github {
  background: rgba(110, 84, 148, 0.2);
  color: #9d8ac7;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
