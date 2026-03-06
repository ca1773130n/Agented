<script setup lang="ts">
import { ref, computed } from 'vue';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';

const showToast = useToast();

type PinStatus = 'pinned' | 'unpinned' | 'outdated';
type ComponentType = 'skill' | 'plugin';

interface VersionPin {
  id: string;
  componentType: ComponentType;
  componentId: string;
  componentName: string;
  pinnedVersion: string;
  latestVersion: string;
  botId: string;
  botName: string;
  status: PinStatus;
  pinnedAt: string;
  changelog?: string;
}

interface AvailableVersion {
  version: string;
  releasedAt: string;
  breaking: boolean;
  summary: string;
}

const pins = ref<VersionPin[]>([
  {
    id: 'pin-001',
    componentType: 'skill',
    componentId: 'skill-code-review',
    componentName: 'Code Review Skill',
    pinnedVersion: '2.3.1',
    latestVersion: '2.5.0',
    botId: 'bot-pr-review',
    botName: 'PR Review Bot',
    status: 'outdated',
    pinnedAt: '2026-01-15T00:00:00Z',
    changelog: 'v2.4.0 adds multi-language support. v2.5.0 improves Python AST parsing.',
  },
  {
    id: 'pin-002',
    componentType: 'plugin',
    componentId: 'plug-github',
    componentName: 'GitHub Plugin',
    pinnedVersion: '1.8.0',
    latestVersion: '1.8.0',
    botId: 'bot-pr-review',
    botName: 'PR Review Bot',
    status: 'pinned',
    pinnedAt: '2026-02-01T00:00:00Z',
  },
  {
    id: 'pin-003',
    componentType: 'skill',
    componentId: 'skill-security-scan',
    componentName: 'Security Scan Skill',
    pinnedVersion: '3.1.0',
    latestVersion: '3.2.1',
    botId: 'bot-security',
    botName: 'Security Audit Bot',
    status: 'outdated',
    pinnedAt: '2026-01-20T00:00:00Z',
    changelog: 'v3.2.0 adds OWASP Top 10 coverage. v3.2.1 fixes false positive in JWT checks.',
  },
  {
    id: 'pin-004',
    componentType: 'plugin',
    componentId: 'plug-slack',
    componentName: 'Slack Plugin',
    pinnedVersion: '2.0.0',
    latestVersion: '2.1.3',
    botId: 'bot-security',
    botName: 'Security Audit Bot',
    status: 'outdated',
    pinnedAt: '2025-12-01T00:00:00Z',
    changelog: 'v2.1.x adds thread reply support and improved rate limit handling.',
  },
  {
    id: 'pin-005',
    componentType: 'skill',
    componentId: 'skill-changelog-gen',
    componentName: 'Changelog Generator Skill',
    pinnedVersion: '1.2.3',
    latestVersion: '1.2.3',
    botId: 'bot-changelog',
    botName: 'Changelog Bot',
    status: 'pinned',
    pinnedAt: '2026-02-28T00:00:00Z',
  },
]);

const availableVersions: Record<string, AvailableVersion[]> = {
  'skill-code-review': [
    { version: '2.5.0', releasedAt: '2026-03-01T00:00:00Z', breaking: false, summary: 'Improved Python AST parsing, reduces false positives by 18%.' },
    { version: '2.4.0', releasedAt: '2026-02-10T00:00:00Z', breaking: false, summary: 'Multi-language support: added TypeScript and Go coverage.' },
    { version: '2.3.1', releasedAt: '2026-01-14T00:00:00Z', breaking: false, summary: 'Bug fix: handle empty file diffs gracefully.' },
    { version: '2.3.0', releasedAt: '2026-01-05T00:00:00Z', breaking: false, summary: 'New: configurable severity thresholds.' },
    { version: '2.0.0', releasedAt: '2025-11-01T00:00:00Z', breaking: true, summary: 'Breaking: removed legacy JSON output format.' },
  ],
  'skill-security-scan': [
    { version: '3.2.1', releasedAt: '2026-03-03T00:00:00Z', breaking: false, summary: 'Fix false positive in JWT secret detection.' },
    { version: '3.2.0', releasedAt: '2026-02-20T00:00:00Z', breaking: false, summary: 'Full OWASP Top 10 rule coverage added.' },
    { version: '3.1.0', releasedAt: '2026-01-18T00:00:00Z', breaking: false, summary: 'Added dependency audit checks.' },
  ],
};

const selectedPinId = ref<string | null>(null);
const upgradeTargets = ref<Record<string, string>>({});
const filterStatus = ref<PinStatus | 'all'>('all');
const filterBot = ref('all');

const filteredPins = computed(() => {
  let list = pins.value;
  if (filterStatus.value !== 'all') list = list.filter((p) => p.status === filterStatus.value);
  if (filterBot.value !== 'all') list = list.filter((p) => p.botId === filterBot.value);
  return list;
});

const bots = computed(() => {
  const ids = new Set(pins.value.map((p) => p.botId));
  return [...ids].map((id) => ({ id, name: pins.value.find((p) => p.botId === id)?.botName || id }));
});

const outdatedCount = computed(() => pins.value.filter((p) => p.status === 'outdated').length);

const selectedPin = computed(() => pins.value.find((p) => p.id === selectedPinId.value));

const versionsForSelected = computed(() => {
  if (!selectedPin.value) return [];
  return availableVersions[selectedPin.value.componentId] || [];
});

function statusColor(status: PinStatus): string {
  return status === 'pinned' ? 'var(--accent-green)' : status === 'outdated' ? 'var(--accent-amber)' : 'var(--text-secondary)';
}

function typeIcon(type: ComponentType): string {
  return type === 'skill' ? '⚡' : '🔌';
}

function applyPin(pin: VersionPin) {
  const target = upgradeTargets.value[pin.id] || pin.latestVersion;
  if (target === pin.pinnedVersion) {
    showToast('Already on that version', 'info');
    return;
  }
  pin.pinnedVersion = target;
  pin.status = pin.pinnedVersion === pin.latestVersion ? 'pinned' : 'outdated';
  pin.pinnedAt = new Date().toISOString();
  showToast(`${pin.componentName} pinned to v${target}`, 'success');
  selectedPinId.value = null;
}

function unpin(pin: VersionPin) {
  pin.status = 'unpinned';
  showToast(`${pin.componentName} unpinned — will follow latest`, 'info');
}

function upgradeAll() {
  const outdated = pins.value.filter((p) => p.status === 'outdated');
  outdated.forEach((p) => {
    p.pinnedVersion = p.latestVersion;
    p.status = 'pinned';
    p.pinnedAt = new Date().toISOString();
  });
  showToast(`Upgraded ${outdated.length} components to latest`, 'success');
}

</script>

<template>
  <div class="page-container">
    <AppBreadcrumb :items="[{ label: 'Settings' }, { label: 'Skill & Plugin Version Pinning' }]" />
    <PageHeader
      title="Skill & Plugin Version Pinning"
      subtitle="Pin bots to specific component versions and receive alerts when newer versions are available"
    />

    <!-- Summary -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-label">Total Pins</div>
        <div class="stat-value">{{ pins.length }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Up to Date</div>
        <div class="stat-value" style="color: var(--accent-green)">
          {{ pins.filter((p) => p.status === 'pinned').length }}
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Outdated</div>
        <div class="stat-value" :style="{ color: outdatedCount > 0 ? 'var(--accent-amber)' : 'var(--accent-green)' }">
          {{ outdatedCount }}
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Unpinned</div>
        <div class="stat-value" style="color: var(--text-secondary)">
          {{ pins.filter((p) => p.status === 'unpinned').length }}
        </div>
      </div>
    </div>

    <!-- Filters + bulk action -->
    <div class="controls-bar">
      <select v-model="filterStatus" class="filter-select">
        <option value="all">All statuses</option>
        <option value="pinned">Up to date</option>
        <option value="outdated">Outdated</option>
        <option value="unpinned">Unpinned</option>
      </select>
      <select v-model="filterBot" class="filter-select">
        <option value="all">All bots</option>
        <option v-for="bot in bots" :key="bot.id" :value="bot.id">{{ bot.name }}</option>
      </select>
      <button v-if="outdatedCount > 0" class="btn-warning" @click="upgradeAll">
        Upgrade All Outdated ({{ outdatedCount }})
      </button>
    </div>

    <div class="main-layout">
      <!-- Pin list -->
      <div class="pin-list">
        <div
          v-for="pin in filteredPins"
          :key="pin.id"
          class="pin-item"
          :class="{ selected: selectedPinId === pin.id }"
          @click="selectedPinId = selectedPinId === pin.id ? null : pin.id"
        >
          <div class="pin-header">
            <span class="type-icon">{{ typeIcon(pin.componentType) }}</span>
            <span class="component-name">{{ pin.componentName }}</span>
            <span class="status-badge" :style="{ background: statusColor(pin.status) + '22', color: statusColor(pin.status) }">
              {{ pin.status === 'pinned' ? 'up to date' : pin.status }}
            </span>
          </div>
          <div class="pin-bot">
            Bot: <strong>{{ pin.botName }}</strong>
          </div>
          <div class="pin-versions">
            <span class="pinned-ver">Pinned: <code>v{{ pin.pinnedVersion }}</code></span>
            <span v-if="pin.status === 'outdated'" class="latest-ver">
              Latest: <code>v{{ pin.latestVersion }}</code>
            </span>
          </div>
          <div v-if="pin.status === 'outdated' && pin.changelog" class="changelog-hint">
            {{ pin.changelog }}
          </div>
        </div>
        <div v-if="filteredPins.length === 0" class="empty-state">No pins match the current filter.</div>
      </div>

      <!-- Version picker panel -->
      <div v-if="selectedPin" class="version-panel">
        <div class="panel-header">
          <span class="type-icon">{{ typeIcon(selectedPin.componentType) }}</span>
          <h3>{{ selectedPin.componentName }}</h3>
        </div>
        <p class="panel-desc">Select the version to pin for <strong>{{ selectedPin.botName }}</strong>.</p>

        <div class="version-list">
          <label
            v-for="v in versionsForSelected"
            :key="v.version"
            class="version-row"
            :class="{
              current: v.version === selectedPin.pinnedVersion,
              latest: v.version === selectedPin.latestVersion,
              breaking: v.breaking,
            }"
          >
            <input
              v-model="upgradeTargets[selectedPin.id]"
              type="radio"
              :value="v.version"
            />
            <div class="version-info">
              <div class="version-header">
                <span class="version-num">v{{ v.version }}</span>
                <span v-if="v.version === selectedPin.pinnedVersion" class="ver-badge current-badge">current pin</span>
                <span v-else-if="v.version === selectedPin.latestVersion" class="ver-badge latest-badge">latest</span>
                <span v-if="v.breaking" class="ver-badge breaking-badge">breaking</span>
                <span class="ver-date">{{ new Date(v.releasedAt).toLocaleDateString() }}</span>
              </div>
              <div class="version-summary">{{ v.summary }}</div>
            </div>
          </label>
          <div v-if="versionsForSelected.length === 0" class="no-versions">
            Version history not available — pin will track <code>{{ selectedPin.latestVersion }}</code>.
          </div>
        </div>

        <div class="panel-actions">
          <button class="btn-primary" @click="applyPin(selectedPin)">Apply Pin</button>
          <button class="btn-ghost" @click="unpin(selectedPin)">Unpin (follow latest)</button>
          <button class="btn-ghost" @click="selectedPinId = null">Cancel</button>
        </div>
      </div>

      <div v-else class="panel-placeholder">
        <p>Select a pin to view version history and change the pinned version.</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-container {
  padding: 24px;
  max-width: 1100px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.stat-card {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 20px;
}

.stat-label {
  font-size: 12px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
}

.controls-bar {
  display: flex;
  gap: 12px;
  align-items: center;
}

.filter-select {
  background: var(--surface-2);
  border: 1px solid var(--border);
  color: var(--text-primary);
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}

.btn-warning {
  background: var(--accent-amber);
  color: #000;
  border: none;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  margin-left: auto;
}

.main-layout {
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: 20px;
  align-items: start;
}

.pin-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.pin-item {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  cursor: pointer;
  transition: border-color 0.15s;
}

.pin-item:hover {
  border-color: var(--accent-blue);
}

.pin-item.selected {
  border-color: var(--accent-blue);
  box-shadow: 0 0 0 2px rgba(var(--accent-blue-rgb, 66, 135, 245), 0.2);
}

.pin-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.type-icon {
  font-size: 16px;
}

.component-name {
  font-weight: 600;
  font-size: 14px;
  flex: 1;
}

.status-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
}

.pin-bot {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.pin-versions {
  display: flex;
  gap: 16px;
  font-size: 12px;
}

.pinned-ver code, .latest-ver code {
  font-family: monospace;
  font-size: 12px;
  background: var(--surface-3);
  padding: 1px 6px;
  border-radius: 4px;
}

.latest-ver {
  color: var(--accent-amber);
}

.changelog-hint {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
  font-style: italic;
}

.version-panel {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 20px;
  position: sticky;
  top: 20px;
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.panel-header h3 {
  font-size: 15px;
  font-weight: 600;
  margin: 0;
}

.panel-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 16px;
}

.version-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 20px;
}

.version-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid var(--border);
  cursor: pointer;
  transition: background 0.1s;
}

.version-row:hover {
  background: var(--surface-3);
}

.version-row.current {
  border-color: var(--accent-blue);
}

.version-row.breaking {
  border-color: var(--accent-red);
}

.version-row input[type="radio"] {
  margin-top: 3px;
}

.version-info {
  flex: 1;
}

.version-header {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}

.version-num {
  font-weight: 700;
  font-family: monospace;
  font-size: 13px;
}

.ver-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 8px;
}

.current-badge {
  background: rgba(66, 135, 245, 0.15);
  color: var(--accent-blue);
}

.latest-badge {
  background: rgba(80, 200, 120, 0.15);
  color: var(--accent-green);
}

.breaking-badge {
  background: rgba(255, 80, 80, 0.15);
  color: var(--accent-red);
}

.ver-date {
  font-size: 11px;
  color: var(--text-secondary);
  margin-left: auto;
}

.version-summary {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.no-versions {
  font-size: 13px;
  color: var(--text-secondary);
  padding: 12px;
  text-align: center;
  background: var(--surface-3);
  border-radius: 6px;
}

.panel-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.btn-primary {
  background: var(--accent-blue);
  color: #fff;
  border: none;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.btn-ghost {
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border);
  padding: 8px 14px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}

.panel-placeholder {
  background: var(--surface-2);
  border: 1px dashed var(--border);
  border-radius: 8px;
  padding: 48px 24px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}

.empty-state {
  text-align: center;
  padding: 32px;
  color: var(--text-secondary);
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 8px;
}
</style>
