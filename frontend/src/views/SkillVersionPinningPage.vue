<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { versionPinsApi } from '../services/api/version-pins';
import type { VersionPin, ComponentVersionHistory, ComponentType, PinStatus } from '../services/api/version-pins';

const showToast = useToast();

// Local state
const pins = ref<VersionPin[]>([]);
const versionHistory = ref<Record<string, ComponentVersionHistory[]>>({});
const loading = ref(false);

const selectedPinId = ref<string | null>(null);
const upgradeTargets = ref<Record<string, string>>({});
const filterStatus = ref<PinStatus | 'all'>('all');
const filterBot = ref('all');

// ---- Data loading ----

async function loadPins() {
  loading.value = true;
  try {
    const res = await versionPinsApi.listPins();
    pins.value = res.pins;
  } catch (err) {
    showToast('Failed to load version pins', 'error');
  } finally {
    loading.value = false;
  }
}

async function loadVersionHistory(componentId: string) {
  if (versionHistory.value[componentId]) return;
  try {
    const res = await versionPinsApi.getVersionHistory(componentId);
    versionHistory.value = { ...versionHistory.value, [componentId]: res.history };
  } catch {
    // Non-fatal — panel will show "not available"
  }
}

onMounted(loadPins);

// ---- Computed ----

const filteredPins = computed(() => {
  let list = pins.value;
  if (filterStatus.value !== 'all') list = list.filter((p) => p.status === filterStatus.value);
  if (filterBot.value !== 'all') list = list.filter((p) => p.bot_id === filterBot.value);
  return list;
});

const bots = computed(() => {
  const ids = new Set(pins.value.map((p) => p.bot_id).filter(Boolean) as string[]);
  return [...ids].map((id) => ({
    id,
    name: pins.value.find((p) => p.bot_id === id)?.bot_name || id,
  }));
});

const outdatedCount = computed(() => pins.value.filter((p) => p.status === 'outdated').length);

const selectedPin = computed(() => pins.value.find((p) => p.id === selectedPinId.value));

const versionsForSelected = computed(() => {
  if (!selectedPin.value) return [];
  return versionHistory.value[selectedPin.value.component_id] || [];
});

// ---- Helpers ----

function statusColor(status: PinStatus): string {
  return status === 'pinned'
    ? 'var(--accent-green)'
    : status === 'outdated'
      ? 'var(--accent-amber)'
      : 'var(--text-secondary)';
}

function typeIcon(type: ComponentType): string {
  return type === 'skill' ? '⚡' : '🔌';
}

// ---- Actions ----

async function applyPin(pin: VersionPin) {
  const target = upgradeTargets.value[pin.id] || pin.latest_version;
  if (!target) {
    showToast('No target version selected', 'info');
    return;
  }
  if (target === pin.pinned_version) {
    showToast('Already on that version', 'info');
    return;
  }
  try {
    const updated = await versionPinsApi.updatePin(pin.id, {
      pinned_version: target,
      status: target === pin.latest_version ? 'pinned' : 'outdated',
    });
    const idx = pins.value.findIndex((p) => p.id === pin.id);
    if (idx !== -1) pins.value[idx] = updated;
    showToast(`${pin.component_name} pinned to v${target}`, 'success');
    selectedPinId.value = null;
  } catch {
    showToast('Failed to apply pin', 'error');
  }
}

async function unpin(pin: VersionPin) {
  try {
    const updated = await versionPinsApi.unpinPin(pin.id);
    const idx = pins.value.findIndex((p) => p.id === pin.id);
    if (idx !== -1) pins.value[idx] = updated;
    showToast(`${pin.component_name} unpinned — will follow latest`, 'info');
    selectedPinId.value = null;
  } catch {
    showToast('Failed to unpin', 'error');
  }
}

async function upgradeAll() {
  try {
    const res = await versionPinsApi.upgradeAll();
    showToast(`Upgraded ${res.upgraded} components to latest`, 'success');
    versionHistory.value = {};
    await loadPins();
  } catch {
    showToast('Failed to upgrade all', 'error');
  }
}

async function selectPin(pin: VersionPin) {
  selectedPinId.value = selectedPinId.value === pin.id ? null : pin.id;
  if (selectedPinId.value) {
    await loadVersionHistory(pin.component_id);
  }
}
</script>

<template>
  <div class="page-container">
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

    <div v-if="loading" class="loading-state">Loading version pins…</div>

    <div v-else class="main-layout">
      <!-- Pin list -->
      <div class="pin-list">
        <div
          v-for="pin in filteredPins"
          :key="pin.id"
          class="pin-item"
          :class="{ selected: selectedPinId === pin.id }"
          @click="selectPin(pin)"
        >
          <div class="pin-header">
            <span class="type-icon">{{ typeIcon(pin.component_type) }}</span>
            <span class="component-name">{{ pin.component_name }}</span>
            <span class="status-badge" :style="{ background: statusColor(pin.status) + '22', color: statusColor(pin.status) }">
              {{ pin.status === 'pinned' ? 'up to date' : pin.status }}
            </span>
          </div>
          <div class="pin-bot">
            Bot: <strong>{{ pin.bot_name || pin.bot_id || '—' }}</strong>
          </div>
          <div class="pin-versions">
            <span class="pinned-ver">Pinned: <code>{{ pin.pinned_version ? `v${pin.pinned_version}` : '—' }}</code></span>
            <span v-if="pin.status === 'outdated'" class="latest-ver">
              Latest: <code>v{{ pin.latest_version }}</code>
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
          <span class="type-icon">{{ typeIcon(selectedPin.component_type) }}</span>
          <h3>{{ selectedPin.component_name }}</h3>
        </div>
        <p class="panel-desc">Select the version to pin for <strong>{{ selectedPin.bot_name }}</strong>.</p>

        <div class="version-list">
          <label
            v-for="v in versionsForSelected"
            :key="v.version"
            class="version-row"
            :class="{
              current: v.version === selectedPin.pinned_version,
              latest: v.version === selectedPin.latest_version,
              breaking: !!v.breaking,
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
                <span v-if="v.version === selectedPin.pinned_version" class="ver-badge current-badge">current pin</span>
                <span v-else-if="v.version === selectedPin.latest_version" class="ver-badge latest-badge">latest</span>
                <span v-if="v.breaking" class="ver-badge breaking-badge">breaking</span>
                <span class="ver-date">{{ v.released_at ? new Date(v.released_at).toLocaleDateString() : '' }}</span>
              </div>
              <div class="version-summary">{{ v.summary }}</div>
            </div>
          </label>
          <div v-if="versionsForSelected.length === 0" class="no-versions">
            Version history not available — pin will track <code>{{ selectedPin.latest_version }}</code>.
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

.loading-state {
  text-align: center;
  padding: 48px;
  color: var(--text-secondary);
  font-size: 14px;
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
