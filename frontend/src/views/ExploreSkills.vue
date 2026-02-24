<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import type { MarketplaceSearchResult, Marketplace, SkillsShResult } from '../services/api';
import { marketplaceApi, skillsShApi, userSkillsApi, ApiError } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import EmptyState from '../components/base/EmptyState.vue';
import { useToast } from '../composables/useToast';
import { useFocusTrap } from '../composables/useFocusTrap';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const router = useRouter();

const showToast = useToast();

// Search state
const searchQuery = ref('');
const searchResults = ref<MarketplaceSearchResult[]>([]);
const isSearching = ref(false);
const isRefreshing = ref(false);

// Skills.sh state
const skillsShResults = ref<SkillsShResult[]>([]);
const isSearchingSkillsSh = ref(false);
const skillsShAvailable = ref(true);
const installingSkill = ref<string | null>(null);

// Marketplace management state
const registeredMarketplaces = ref<Marketplace[]>([]);
const showAddModal = ref(false);
const newMarketplace = ref({ name: '', url: '' });

const addModalRef = ref<HTMLElement | null>(null);
useFocusTrap(addModalRef, showAddModal);

useWebMcpTool({
  name: 'agented_explore_skills_get_state',
  description: 'Returns the current state of the Explore Skills page',
  page: 'ExploreSkills',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'ExploreSkills',
        searchQuery: searchQuery.value,
        searchResultsCount: searchResults.value.length,
        isSearching: isSearching.value,
        skillsShAvailable: skillsShAvailable.value,
      }),
    }],
  }),
  deps: [searchQuery, searchResults, isSearching, skillsShAvailable],
});

// Debounced search
let debounceTimer: ReturnType<typeof setTimeout>;

function debouncedSearch(query: string) {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    performSearch(query);
  }, 300);
}

async function performSearch(query: string) {
  isSearching.value = true;
  isSearchingSkillsSh.value = true;

  // Fetch marketplace and skills.sh results in parallel
  const [marketplacePromise, skillsShPromise] = [
    marketplaceApi.search(query, 'skill').catch(() => ({ results: [] as MarketplaceSearchResult[] })),
    skillsShApi.search(query).catch(() => ({ results: [] as SkillsShResult[], npx_available: true as boolean | undefined })),
  ];

  try {
    const marketplaceResponse = await marketplacePromise;
    searchResults.value = marketplaceResponse.results;
  } catch {
    searchResults.value = [];
  } finally {
    isSearching.value = false;
  }

  try {
    const skillsShResponse = await skillsShPromise;
    skillsShResults.value = skillsShResponse.results;
    if (skillsShResponse.npx_available !== undefined) {
      skillsShAvailable.value = skillsShResponse.npx_available !== false;
    }
  } catch {
    skillsShResults.value = [];
  } finally {
    isSearchingSkillsSh.value = false;
  }
}

function onSearchInput() {
  const q = searchQuery.value.trim();
  if (q.length >= 2 || q.length === 0) {
    debouncedSearch(q);
  }
}

async function refreshCache() {
  isRefreshing.value = true;
  try {
    await marketplaceApi.refreshCache();
    showToast('Marketplace cache refreshed', 'success');
    await performSearch(searchQuery.value.trim());
  } catch (e) {
    showToast('Failed to refresh cache', 'error');
  } finally {
    isRefreshing.value = false;
  }
}

async function loadMarketplaces() {
  try {
    const response = await marketplaceApi.list();
    registeredMarketplaces.value = response.marketplaces;
  } catch (e) {
    // Silently fail
  }
}

async function addMarketplace() {
  if (!newMarketplace.value.name.trim() || !newMarketplace.value.url.trim()) {
    showToast('Name and URL are required', 'error');
    return;
  }
  try {
    await marketplaceApi.create({
      name: newMarketplace.value.name,
      url: newMarketplace.value.url,
      type: 'git',
    });
    showToast('Marketplace added', 'success');
    showAddModal.value = false;
    newMarketplace.value = { name: '', url: '' };
    await loadMarketplaces();
    await performSearch(searchQuery.value.trim());
  } catch (e) {
    showToast('Failed to add marketplace', 'error');
  }
}

async function removeMarketplace(marketplaceId: string) {
  try {
    await marketplaceApi.delete(marketplaceId);
    showToast('Marketplace removed', 'success');
    await loadMarketplaces();
    await performSearch(searchQuery.value.trim());
  } catch (e) {
    showToast('Failed to remove marketplace', 'error');
  }
}

async function installSkillsShSkill(skill: SkillsShResult) {
  if (!skill.install_cmd && !skill.source) {
    showToast('No install source available for this skill', 'error');
    return;
  }
  const source = skill.install_cmd
    ? skill.install_cmd.replace(/^npx\s+skills\s+add\s+/, '').replace(/\s+--.*$/, '')
    : skill.source || '';
  installingSkill.value = skill.name;
  try {
    await skillsShApi.install(source);
    showToast(`Installed "${skill.name}" from skills.sh`, 'success');
    skill.installed = true;
    // Refresh to update installed status
    await performSearch(searchQuery.value.trim());
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to install skill';
    showToast(message, 'error');
  } finally {
    installingSkill.value = null;
  }
}

// Marketplace skill install
const installingMarketplaceSkill = ref<string | null>(null);

async function installMarketplaceSkill(skill: MarketplaceSearchResult) {
  installingMarketplaceSkill.value = `${skill.marketplace_id}-${skill.name}`;
  try {
    await userSkillsApi.add({
      skill_name: skill.name,
      skill_path: skill.source || '',
      description: skill.description || '',
    });
    showToast(`Added "${skill.name}" to your library`, 'success');
    skill.installed = true;
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to add skill';
    showToast(message, 'error');
  } finally {
    installingMarketplaceSkill.value = null;
  }
}

function openSkillDetail(skill: SkillsShResult) {
  if (skill.detail_url) {
    window.open(skill.detail_url, '_blank');
  }
}

function formatInstalls(n: number): string {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

onMounted(async () => {
  await loadMarketplaces();
  await performSearch('');
});
</script>

<template>
  <div class="explore-page">
    <AppBreadcrumb :items="[{ label: 'Skills', action: () => router.push({ name: 'my-skills' }) }, { label: 'Explore' }]" />
    <PageHeader title="Explore Skills" subtitle="Search skills across marketplace registries and skills.sh">
      <template #actions>
        <button class="btn-back" @click="router.push({ name: 'my-skills' })">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
          Back to Skills
        </button>
      </template>
    </PageHeader>

    <!-- Search Bar -->
    <div class="search-bar">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="11" cy="11" r="8"/>
        <path d="M21 21l-4.35-4.35"/>
      </svg>
      <input
        v-model="searchQuery"
        type="text"
        placeholder="Search skills across marketplaces and skills.sh..."
        @input="onSearchInput"
      />
      <button class="refresh-btn" :disabled="isRefreshing" title="Refresh marketplace data" @click="refreshCache">
        <svg :class="{ spinning: isRefreshing }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M23 4v6h-6M1 20v-6h6"/>
          <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
        </svg>
      </button>
    </div>

    <!-- Search Results -->
    <div class="results-section">
      <div class="section-header">
        <h2>
          <template v-if="searchQuery.trim()">
            Results for "{{ searchQuery }}" ({{ searchResults.length }})
          </template>
          <template v-else>
            All Available Skills ({{ searchResults.length }})
          </template>
        </h2>
      </div>

      <LoadingState v-if="isSearching" message="Searching skills..." />

      <EmptyState
        v-else-if="searchResults.length === 0"
        title="No skills found"
        description="Try a different search term or add more marketplace registries."
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="11" cy="11" r="8"/>
            <path d="M21 21l-4.35-4.35"/>
          </svg>
        </template>
      </EmptyState>

      <!-- Results Grid -->
      <div v-else class="results-grid">
        <div
          v-for="skill in searchResults"
          :key="`${skill.marketplace_id}-${skill.name}`"
          class="skill-card"
        >
          <div class="skill-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M12 2L2 7l10 5 10-5-10-5z"/>
              <path d="M2 17l10 5 10-5"/>
              <path d="M2 12l10 5 10-5"/>
            </svg>
          </div>
          <div class="skill-info">
            <div class="skill-name-row">
              <h3>{{ skill.name }}</h3>
              <span v-if="skill.version" class="version-badge">v{{ skill.version }}</span>
              <span v-if="skill.installed" class="installed-badge">Installed</span>
            </div>
            <p class="skill-description">{{ skill.description || 'No description' }}</p>
            <span class="marketplace-badge">{{ skill.marketplace_name }}</span>
          </div>
          <div class="skill-actions">
            <button
              v-if="!skill.installed"
              class="install-btn"
              :disabled="installingMarketplaceSkill === `${skill.marketplace_id}-${skill.name}`"
              @click="installMarketplaceSkill(skill)"
            >
              {{ installingMarketplaceSkill === `${skill.marketplace_id}-${skill.name}` ? 'Adding...' : 'Add' }}
            </button>
            <span v-else class="installed-label">Added</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Skills.sh Results -->
    <div class="results-section skills-sh-section">
      <div class="section-header">
        <h2>
          <svg class="skills-sh-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
          </svg>
          <template v-if="searchQuery.trim()">
            skills.sh Results for "{{ searchQuery }}" ({{ skillsShResults.length }})
          </template>
          <template v-else>
            skills.sh Community Skills ({{ skillsShResults.length }})
          </template>
        </h2>
        <span v-if="!skillsShAvailable" class="unavailable-badge">npx not available</span>
      </div>

      <LoadingState v-if="isSearchingSkillsSh" message="Searching skills.sh..." />

      <EmptyState
        v-else-if="!skillsShAvailable"
        title="npx not available"
        description="skills.sh integration requires npx (Node.js). Install Node.js to browse community skills."
      />

      <EmptyState
        v-else-if="skillsShResults.length === 0"
        title="No skills.sh skills found"
        description="Try a different search term."
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
          </svg>
        </template>
      </EmptyState>

      <!-- Results Grid -->
      <div v-else class="results-grid">
        <div
          v-for="skill in skillsShResults"
          :key="`skills-sh-${skill.name}`"
          class="skill-card skills-sh-card clickable"
          @click="openSkillDetail(skill)"
        >
          <div class="skill-icon skills-sh-skill-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
            </svg>
          </div>
          <div class="skill-info">
            <div class="skill-name-row">
              <h3>{{ skill.name }}</h3>
              <span v-if="skill.installs" class="installs-badge">{{ formatInstalls(skill.installs) }}</span>
              <span v-if="skill.installed" class="installed-badge">Installed</span>
            </div>
            <div class="skill-meta-row">
              <span v-if="skill.source" class="marketplace-badge skills-sh-badge">{{ skill.source }}</span>
              <span class="marketplace-badge skills-sh-source-badge">skills.sh</span>
            </div>
          </div>
          <div class="skill-actions">
            <button
              v-if="!skill.installed"
              class="install-btn"
              :disabled="installingSkill === skill.name"
              @click.stop="installSkillsShSkill(skill)"
            >
              {{ installingSkill === skill.name ? 'Installing...' : 'Install' }}
            </button>
            <span v-else class="installed-label">Installed</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Manage Marketplace Registries -->
    <div class="registries-section">
      <div class="section-header">
        <h2>Manage Marketplace Registries ({{ registeredMarketplaces.length }})</h2>
        <button class="btn btn-primary" @click="showAddModal = true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="12" y1="5" x2="12" y2="19"/>
            <line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          Add Registry
        </button>
      </div>

      <EmptyState
        v-if="registeredMarketplaces.length === 0"
        title="No registries"
        description="No marketplace registries registered. Add a registry to start discovering skills."
      />

      <div v-else class="registries-list">
        <div
          v-for="marketplace in registeredMarketplaces"
          :key="marketplace.id"
          class="registry-row"
        >
          <div class="registry-icon">
            <svg viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
            </svg>
          </div>
          <div class="registry-info">
            <span class="registry-name">{{ marketplace.name }}</span>
            <span class="registry-url">{{ marketplace.url }}</span>
          </div>
          <button class="remove-btn" title="Remove registry" @click="removeMarketplace(marketplace.id)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- Add Marketplace Modal -->
    <Teleport to="body">
      <div v-if="showAddModal" ref="addModalRef" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-add-skill-marketplace" tabindex="-1" @click.self="showAddModal = false" @keydown.escape="showAddModal = false">
        <div class="modal">
          <h2 id="modal-title-add-skill-marketplace">Add Marketplace Registry</h2>
          <form @submit.prevent="addMarketplace">
            <div class="form-group">
              <label for="marketplace-name">Name *</label>
              <input
                id="marketplace-name"
                v-model="newMarketplace.name"
                type="text"
                placeholder="My Skill Repository"
                required
              />
            </div>
            <div class="form-group">
              <label for="marketplace-url">Git URL *</label>
              <input
                id="marketplace-url"
                v-model="newMarketplace.url"
                type="url"
                placeholder="https://github.com/user/repo or enterprise URL"
                required
              />
            </div>
            <div class="modal-actions">
              <button type="button" class="btn" @click="showAddModal = false">Cancel</button>
              <button type="submit" class="btn btn-primary">Add Registry</button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.explore-page {
}

.btn-back {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-back:hover {
  background: var(--bg-elevated);
  color: var(--text-primary);
}

.btn-back svg {
  width: 16px;
  height: 16px;
}

.search-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  margin-bottom: 24px;
}

.search-bar > svg {
  width: 20px;
  height: 20px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.search-bar input {
  flex: 1;
  background: transparent;
  border: none;
  font-size: 14px;
  color: var(--text-primary);
}

.search-bar input:focus {
  outline: none;
}

.search-bar input::placeholder {
  color: var(--text-tertiary);
}

.refresh-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}

.refresh-btn:hover {
  background: var(--bg-elevated);
  color: var(--text-primary);
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.refresh-btn svg {
  width: 16px;
  height: 16px;
}

.refresh-btn svg.spinning {
  animation: spin 1s linear infinite;
}

/* Results section */
.results-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 24px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.section-header h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.results-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.skill-card {
  display: flex;
  gap: 14px;
  padding: 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  transition: all 0.15s;
}

.skill-card.clickable {
  cursor: pointer;
}

.skill-card:hover {
  border-color: var(--accent-cyan);
  background: var(--bg-elevated);
}

.skill-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: var(--accent-cyan-dim, rgba(0, 212, 255, 0.1));
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--accent-cyan);
}

.skill-icon svg {
  width: 22px;
  height: 22px;
}

.skill-info {
  flex: 1;
  min-width: 0;
}

.skill-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}

.skill-name-row h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.version-badge {
  font-size: 11px;
  padding: 2px 6px;
  background: var(--bg-elevated);
  color: var(--text-tertiary);
  border-radius: 4px;
}

.installed-badge {
  font-size: 11px;
  padding: 2px 6px;
  background: var(--accent-emerald-dim, rgba(0, 255, 136, 0.1));
  color: var(--accent-emerald);
  border-radius: 4px;
  font-weight: 500;
}

.installs-badge {
  font-size: 11px;
  padding: 2px 6px;
  background: var(--accent-amber-dim, rgba(255, 180, 0, 0.1));
  color: var(--accent-amber, #ffb400);
  border-radius: 4px;
  font-weight: 500;
}

.skill-description {
  margin: 0 0 8px 0;
  font-size: 13px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.marketplace-badge {
  font-size: 11px;
  padding: 2px 8px;
  background: var(--accent-blue-dim, rgba(56, 139, 253, 0.1));
  color: var(--accent-blue, #388bfd);
  border-radius: 4px;
  font-weight: 500;
}

/* Registries section */
.registries-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 20px;
}

.registries-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.registry-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.registry-icon {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  background: var(--accent-violet-dim, rgba(136, 85, 255, 0.1));
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--accent-violet);
}

.registry-icon svg {
  width: 16px;
  height: 16px;
}

.registry-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.registry-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.registry-url {
  font-size: 12px;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.remove-btn {
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

.remove-btn:hover {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

.remove-btn svg {
  width: 14px;
  height: 14px;
}

/* Modal styles */
.modal {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 24px;
  max-width: 450px;
  width: 90%;
}

.form-group input {
  width: 100%;
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 14px;
}

/* Skills.sh section */
.skills-sh-section {
  border-color: var(--accent-amber-dim, rgba(255, 180, 0, 0.2));
}

.skills-sh-icon {
  width: 18px;
  height: 18px;
  margin-right: 6px;
  vertical-align: middle;
  color: var(--accent-amber, #ffb400);
}

.skills-sh-skill-icon {
  background: var(--accent-amber-dim, rgba(255, 180, 0, 0.1));
  color: var(--accent-amber, #ffb400);
}

.skills-sh-card {
  display: flex;
  align-items: flex-start;
}

.skill-meta-row {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.skills-sh-badge {
  background: var(--bg-elevated);
  color: var(--text-tertiary);
}

.skills-sh-source-badge {
  background: var(--accent-amber-dim, rgba(255, 180, 0, 0.1));
  color: var(--accent-amber, #ffb400);
}

.unavailable-badge {
  font-size: 11px;
  padding: 2px 8px;
  background: var(--accent-crimson-dim, rgba(255, 69, 58, 0.1));
  color: var(--accent-crimson, #ff453a);
  border-radius: 4px;
  font-weight: 500;
}

.skill-actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.install-btn {
  padding: 6px 14px;
  background: var(--accent-cyan);
  color: #000;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.install-btn:hover {
  background: #00c4ee;
}

.install-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.installed-label {
  font-size: 12px;
  color: var(--accent-emerald);
  font-weight: 500;
  white-space: nowrap;
}
</style>
