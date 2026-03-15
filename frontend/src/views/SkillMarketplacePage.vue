<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import PageHeader from '../components/base/PageHeader.vue';
import { useToast } from '../composables/useToast';
import { marketplaceApi, ApiError } from '../services/api';
import type { Marketplace, MarketplacePlugin } from '../services/api';

const router = useRouter();
const showToast = useToast();

const isLoading = ref(true);
const loadError = ref<string | null>(null);
const marketplaces = ref<Marketplace[]>([]);
const plugins = ref<MarketplacePlugin[]>([]);
const availablePlugins = ref<Array<{ name: string; description?: string; version?: string; source?: string; installed: boolean }>>([]);

const searchQuery = ref('');
const sortBy = ref<'name' | 'installed'>('name');
const isInstalling = ref<string | null>(null);
const selectedMarketplaceId = ref<string | null>(null);

onMounted(async () => {
  try {
    const resp = await marketplaceApi.list();
    marketplaces.value = resp.marketplaces;

    if (marketplaces.value.length > 0) {
      selectedMarketplaceId.value = marketplaces.value[0].id;
      await loadMarketplacePlugins(marketplaces.value[0].id);
    }
  } catch (err) {
    if (err instanceof ApiError) {
      loadError.value = `Failed to load marketplaces: ${err.message}`;
    } else {
      loadError.value = 'An unexpected error occurred while loading marketplaces.';
    }
  } finally {
    isLoading.value = false;
  }
});

async function loadMarketplacePlugins(marketplaceId: string) {
  selectedMarketplaceId.value = marketplaceId;
  try {
    const [pluginsResp, discoverResp] = await Promise.all([
      marketplaceApi.listPlugins(marketplaceId),
      marketplaceApi.discoverPlugins(marketplaceId).catch(() => ({ plugins: [], total: 0 })),
    ]);
    plugins.value = pluginsResp.plugins;
    availablePlugins.value = discoverResp.plugins;
  } catch (err) {
    if (err instanceof ApiError) {
      showToast(`Failed to load plugins: ${err.message}`, 'error');
    }
  }
}

// Merge installed and available into a unified list
interface DisplayPlugin {
  id: string;
  name: string;
  description: string;
  version: string;
  source: string;
  installed: boolean;
  pluginRef?: MarketplacePlugin;
}

const allPlugins = computed<DisplayPlugin[]>(() => {
  const installedNames = new Set(plugins.value.map((p) => p.remote_name || p.id));
  const result: DisplayPlugin[] = [];

  // Add installed plugins
  for (const p of plugins.value) {
    result.push({
      id: p.id,
      name: p.remote_name || p.id,
      description: '',
      version: p.version || 'latest',
      source: 'installed',
      installed: true,
      pluginRef: p,
    });
  }

  // Add available (not-yet-installed) plugins
  for (const p of availablePlugins.value) {
    if (!installedNames.has(p.name)) {
      result.push({
        id: p.name,
        name: p.name,
        description: p.description || '',
        version: p.version || 'latest',
        source: p.source || 'marketplace',
        installed: p.installed,
      });
    }
  }

  return result;
});

const filtered = computed(() => {
  let list = allPlugins.value;
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase();
    list = list.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.description.toLowerCase().includes(q)
    );
  }
  if (sortBy.value === 'installed') {
    list = [...list].sort((a, b) => (b.installed ? 1 : 0) - (a.installed ? 1 : 0));
  } else {
    list = [...list].sort((a, b) => a.name.localeCompare(b.name));
  }
  return list;
});

async function installPlugin(plugin: DisplayPlugin) {
  if (!selectedMarketplaceId.value) return;
  isInstalling.value = plugin.id;
  try {
    await marketplaceApi.installPlugin(selectedMarketplaceId.value, {
      remote_name: plugin.name,
      version: plugin.version,
    });
    plugin.installed = true;
    showToast(`"${plugin.name}" installed successfully.`, 'success');
    // Reload plugins
    await loadMarketplacePlugins(selectedMarketplaceId.value);
  } catch (err) {
    if (err instanceof ApiError) {
      showToast(`Failed to install: ${err.message}`, 'error');
    } else {
      showToast('Installation failed', 'error');
    }
  } finally {
    isInstalling.value = null;
  }
}

async function uninstallPlugin(plugin: DisplayPlugin) {
  if (!selectedMarketplaceId.value || !plugin.pluginRef) return;
  try {
    await marketplaceApi.uninstallPlugin(selectedMarketplaceId.value, plugin.pluginRef.id || plugin.id);
    plugin.installed = false;
    showToast(`"${plugin.name}" uninstalled.`, 'success');
    // Reload plugins
    await loadMarketplacePlugins(selectedMarketplaceId.value);
  } catch (err) {
    if (err instanceof ApiError) {
      showToast(`Failed to uninstall: ${err.message}`, 'error');
    }
  }
}

async function handleSearch() {
  if (!searchQuery.value.trim()) return;
  try {
    const resp = await marketplaceApi.search(searchQuery.value, 'plugin');
    if (resp.results && resp.results.length > 0) {
      showToast(`Found ${resp.results.length} result(s)`, 'success');
    }
  } catch {
    // Search is supplementary, don't block on failure
  }
}
</script>

<template>
  <div class="skill-marketplace">

    <PageHeader
      title="Skill Marketplace"
      subtitle="Browse and install plugins from connected marketplaces."
    />

    <!-- Loading state -->
    <div v-if="isLoading" class="card" style="padding: 48px; text-align: center;">
      <span style="color: var(--text-tertiary); font-size: 0.85rem;">Loading marketplaces...</span>
    </div>

    <!-- Error state -->
    <div v-else-if="loadError" class="card" style="padding: 48px; text-align: center;">
      <span style="color: #ef4444; font-size: 0.85rem;">{{ loadError }}</span>
    </div>

    <!-- Empty state -->
    <div v-else-if="marketplaces.length === 0" class="card" style="padding: 48px; text-align: center;">
      <span style="color: var(--text-tertiary); font-size: 0.85rem;">No marketplaces configured. Add a marketplace to browse plugins.</span>
    </div>

    <template v-else>
      <!-- Search + sort bar -->
      <div class="search-bar card">
        <div class="search-input-wrap">
          <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            v-model="searchQuery"
            class="search-input"
            placeholder="Search plugins by name or description..."
            @keyup.enter="handleSearch"
          />
        </div>
        <div class="sort-row">
          <span class="sort-label">Sort:</span>
          <select v-model="sortBy" class="select select-sm">
            <option value="name">By Name</option>
            <option value="installed">Installed First</option>
          </select>
        </div>
      </div>

      <div class="marketplace-layout">
        <!-- Marketplace sidebar -->
        <aside class="category-sidebar card">
          <div class="sidebar-title">Marketplaces</div>
          <button
            v-for="mp in marketplaces"
            :key="mp.id"
            class="cat-btn"
            :class="{ active: selectedMarketplaceId === mp.id }"
            @click="loadMarketplacePlugins(mp.id)"
          >
            {{ mp.name }}
          </button>
        </aside>

        <!-- Plugin grid -->
        <div class="skill-grid">
          <div v-if="filtered.length === 0" class="empty-state">
            <div class="empty-icon" style="font-size: 2.5rem; margin-bottom: 12px; opacity: 0.5;">?</div>
            <p>No plugins match your search. Try a different keyword.</p>
          </div>

          <div v-for="plugin in filtered" :key="plugin.id" class="skill-card card">
            <div class="skill-header">
              <div class="skill-name-row">
                <span class="skill-name">{{ plugin.name }}</span>
              </div>
              <div class="skill-author">{{ plugin.source }}</div>
            </div>

            <div class="skill-desc">{{ plugin.description || 'No description available' }}</div>

            <div class="skill-meta">
              <span class="version">v{{ plugin.version }}</span>
            </div>

            <div class="skill-footer">
              <span class="updated">Source: {{ plugin.source }}</span>
              <div class="footer-actions">
                <button
                  v-if="!plugin.installed"
                  class="btn btn-primary btn-sm"
                  :disabled="isInstalling === plugin.id"
                  @click="installPlugin(plugin)"
                >
                  {{ isInstalling === plugin.id ? 'Installing...' : 'Install' }}
                </button>
                <button v-else class="btn btn-installed btn-sm" @click="uninstallPlugin(plugin)">
                  Installed
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.skill-marketplace { display: flex; flex-direction: column; gap: 20px; animation: fadeIn 0.3s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

.card { background: var(--bg-secondary); border: 1px solid var(--border-default); border-radius: 10px; }

/* Search */
.search-bar { padding: 12px 16px; display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.search-input-wrap { flex: 1; position: relative; display: flex; align-items: center; }
.search-icon { position: absolute; left: 10px; color: var(--text-tertiary); pointer-events: none; }
.search-input { width: 100%; padding: 8px 12px 8px 34px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.875rem; }
.search-input:focus { outline: none; border-color: var(--accent-cyan); }
.sort-row { display: flex; align-items: center; gap: 8px; }
.sort-label { font-size: 0.78rem; color: var(--text-tertiary); }
.select { padding: 7px 10px; background: var(--bg-tertiary); border: 1px solid var(--border-default); border-radius: 7px; color: var(--text-primary); font-size: 0.82rem; }
.select-sm { font-size: 0.78rem; padding: 5px 8px; }

/* Layout */
.marketplace-layout { display: grid; grid-template-columns: 180px 1fr; gap: 16px; align-items: start; }

/* Category sidebar */
.category-sidebar { padding: 12px; }
.sidebar-title { font-size: 0.72rem; font-weight: 600; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.05em; padding: 4px 8px 8px; }
.cat-btn { width: 100%; display: flex; align-items: center; justify-content: space-between; padding: 7px 10px; border-radius: 7px; border: none; background: transparent; color: var(--text-secondary); font-size: 0.82rem; cursor: pointer; transition: all 0.1s; }
.cat-btn:hover { background: var(--bg-tertiary); color: var(--text-primary); }
.cat-btn.active { background: rgba(6,182,212,0.1); color: var(--accent-cyan); font-weight: 500; }
.cat-count { font-size: 0.7rem; background: var(--bg-tertiary); padding: 1px 6px; border-radius: 10px; color: var(--text-tertiary); }

/* Skill grid */
.skill-grid { display: flex; flex-direction: column; gap: 12px; }

.skill-card { padding: 16px; display: flex; flex-direction: column; gap: 10px; }
.skill-header { display: flex; flex-direction: column; gap: 2px; }
.skill-name-row { display: flex; align-items: center; gap: 8px; }
.skill-name { font-size: 0.9rem; font-weight: 600; color: var(--text-primary); }
.official-badge { font-size: 0.65rem; font-weight: 700; background: rgba(99,102,241,0.15); color: #818cf8; border: 1px solid rgba(99,102,241,0.25); padding: 1px 6px; border-radius: 4px; }
.skill-author { font-size: 0.75rem; color: var(--text-tertiary); }
.skill-desc { font-size: 0.82rem; color: var(--text-secondary); line-height: 1.5; }

.skill-tags { display: flex; flex-wrap: wrap; gap: 5px; }
.skill-tag { font-size: 0.72rem; background: var(--bg-tertiary); border: 1px solid var(--border-default); padding: 2px 8px; border-radius: 5px; color: var(--text-tertiary); }

.skill-meta { display: flex; align-items: center; gap: 5px; font-size: 0.78rem; flex-wrap: wrap; }
.stars { color: #fbbf24; letter-spacing: -1px; }
.rating-val { font-weight: 600; color: var(--text-primary); }
.rating-count { color: var(--text-tertiary); }
.meta-sep { color: var(--border-default); }
.usage-count, .version { color: var(--text-tertiary); }

.skill-footer { display: flex; align-items: center; justify-content: space-between; padding-top: 8px; border-top: 1px solid var(--border-default); }
.updated { font-size: 0.75rem; color: var(--text-tertiary); }
.footer-actions { }

.btn { padding: 7px 14px; border-radius: 7px; font-size: 0.82rem; font-weight: 500; cursor: pointer; border: none; transition: all 0.15s; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: var(--accent-cyan); color: #000; }
.btn-primary:hover:not(:disabled) { opacity: 0.9; }
.btn-installed { background: rgba(52,211,153,0.12); border: 1px solid rgba(52,211,153,0.25); color: #34d399; }
.btn-installed:hover { background: rgba(248,113,113,0.1); border-color: rgba(248,113,113,0.25); color: #f87171; }
.btn-sm { padding: 5px 12px; font-size: 0.78rem; }

.empty-state { text-align: center; padding: 48px 20px; color: var(--text-secondary); }
.empty-icon { font-size: 2.5rem; margin-bottom: 12px; }
</style>
