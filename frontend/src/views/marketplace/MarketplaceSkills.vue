<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import type { MarketplaceSearchResult, SkillsShResult } from '../../services/api';
import { marketplaceApi, skillsShApi, userSkillsApi, ApiError } from '../../services/api';
import LoadingState from '../../components/base/LoadingState.vue';
import EmptyState from '../../components/base/EmptyState.vue';
import { useToast } from '../../composables/useToast';
import { useWebMcpTool } from '../../composables/useWebMcpTool';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();
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

useWebMcpTool({
  name: 'agented_marketplace_skills_get_state',
  description: 'Returns the current state of the Marketplace Skills tab',
  page: 'MarketplaceSkills',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'MarketplaceSkills',
        searchQuery: searchQuery.value,
        searchResultsCount: searchResults.value.length,
        isSearching: isSearching.value,
        skillsShAvailable: skillsShAvailable.value,
      }),
    }],
  }),
  deps: [searchQuery, searchResults, isSearching, skillsShAvailable],
});

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
    showToast(t('marketplaceSkills.toast.cacheRefreshed'), 'success');
    await performSearch(searchQuery.value.trim());
  } catch (e) {
    showToast(t('marketplaceSkills.toast.cacheRefreshFailed'), 'error');
  } finally {
    isRefreshing.value = false;
  }
}

async function installSkillsShSkill(skill: SkillsShResult) {
  if (!skill.install_cmd && !skill.source) {
    showToast(t('marketplaceSkills.toast.noInstallSource'), 'error');
    return;
  }
  const source = skill.install_cmd
    ? skill.install_cmd.replace(/^npx\s+skills\s+add\s+/, '').replace(/\s+--.*$/, '')
    : skill.source || '';
  installingSkill.value = skill.name;
  try {
    await skillsShApi.install(source);
    showToast(t('marketplaceSkills.toast.installedFromSkillsSh', { name: skill.name }), 'success');
    skill.installed = true;
    await performSearch(searchQuery.value.trim());
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('marketplaceSkills.toast.installFailed');
    showToast(message, 'error');
  } finally {
    installingSkill.value = null;
  }
}

const installingMarketplaceSkill = ref<string | null>(null);

async function installMarketplaceSkill(skill: MarketplaceSearchResult) {
  installingMarketplaceSkill.value = `${skill.marketplace_id}-${skill.name}`;
  try {
    await userSkillsApi.add({
      skill_name: skill.name,
      skill_path: skill.source || '',
      description: skill.description || '',
    });
    showToast(t('marketplaceSkills.toast.addedToLibrary', { name: skill.name }), 'success');
    skill.installed = true;
  } catch (err) {
    const message = err instanceof ApiError ? err.message : t('marketplaceSkills.toast.addFailed');
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

function goToRegistrySettings() {
  // SettingsPage reads the active tab from window.location.hash, not
  // from route.query — use a hash fragment so we actually land on
  // the marketplaces tab instead of falling back to the default.
  router.push({ name: 'settings', hash: '#marketplaces' });
}

onMounted(async () => {
  await performSearch('');
});
</script>

<template>
  <div class="marketplace-pane">
    <!-- Search Bar -->
    <div class="search-bar">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="11" cy="11" r="8"/>
        <path d="M21 21l-4.35-4.35"/>
      </svg>
      <input
        v-model="searchQuery"
        type="text"
        :placeholder="t('marketplaceSkills.searchPlaceholder')"
        @input="onSearchInput"
      />
      <button class="refresh-btn" :disabled="isRefreshing" :title="t('marketplaceSkills.refreshTitle')" @click="refreshCache">
        <svg :class="{ spinning: isRefreshing }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M23 4v6h-6M1 20v-6h6"/>
          <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
        </svg>
      </button>
    </div>

    <!-- Marketplace lane -->
    <div class="results-section">
      <div class="section-header">
        <h2>
          <template v-if="searchQuery.trim()">
            {{ t('marketplaceSkills.fromMarketplaceQuery', { query: searchQuery, count: searchResults.length }) }}
          </template>
          <template v-else>
            {{ t('marketplaceSkills.fromMarketplace', { count: searchResults.length }) }}
          </template>
        </h2>
      </div>

      <LoadingState v-if="isSearching" :message="t('marketplaceSkills.searching')" />

      <EmptyState
        v-else-if="searchResults.length === 0"
        :title="t('marketplaceSkills.emptyMarketplaceTitle')"
        :description="t('marketplaceSkills.emptyMarketplaceDescription')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="11" cy="11" r="8"/>
            <path d="M21 21l-4.35-4.35"/>
          </svg>
        </template>
      </EmptyState>

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
              <span v-if="skill.installed" class="installed-badge">{{ t('marketplaceSkills.installedBadge') }}</span>
            </div>
            <p class="skill-description">{{ skill.description || t('marketplaceSkills.noDescription') }}</p>
            <span class="marketplace-badge">{{ skill.marketplace_name }}</span>
          </div>
          <div class="skill-actions">
            <button
              v-if="!skill.installed"
              class="install-btn"
              :disabled="installingMarketplaceSkill === `${skill.marketplace_id}-${skill.name}`"
              @click="installMarketplaceSkill(skill)"
            >
              {{ installingMarketplaceSkill === `${skill.marketplace_id}-${skill.name}` ? t('marketplaceSkills.adding') : t('common.add') }}
            </button>
            <span v-else class="installed-label">{{ t('marketplaceSkills.added') }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Skills.sh lane -->
    <div class="results-section skills-sh-section">
      <div class="section-header">
        <h2>
          <svg class="skills-sh-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
          </svg>
          <template v-if="searchQuery.trim()">
            {{ t('marketplaceSkills.fromSkillsShQuery', { query: searchQuery, count: skillsShResults.length }) }}
          </template>
          <template v-else>
            {{ t('marketplaceSkills.fromSkillsSh', { count: skillsShResults.length }) }}
          </template>
        </h2>
        <span v-if="!skillsShAvailable" class="unavailable-badge">{{ t('marketplaceSkills.npxUnavailable') }}</span>
      </div>

      <LoadingState v-if="isSearchingSkillsSh" :message="t('marketplaceSkills.searchingSkillsSh')" />

      <EmptyState
        v-else-if="!skillsShAvailable"
        :title="t('marketplaceSkills.npxUnavailable')"
        :description="t('marketplaceSkills.npxUnavailableDescription')"
      />

      <EmptyState
        v-else-if="skillsShResults.length === 0"
        :title="t('marketplaceSkills.emptySkillsShTitle')"
        :description="t('marketplaceSkills.emptySkillsShDescription')"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
          </svg>
        </template>
      </EmptyState>

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
              <span v-if="skill.installed" class="installed-badge">{{ t('marketplaceSkills.installedBadge') }}</span>
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
              {{ installingSkill === skill.name ? t('marketplaceSkills.installing') : t('marketplaceSkills.install') }}
            </button>
            <span v-else class="installed-label">{{ t('marketplaceSkills.installedBadge') }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Registry admin pointer (replaces the deleted inline panel) -->
    <div class="registry-pointer">
      <span>{{ t('marketplaceSkills.registryPointer') }}</span>
      <button type="button" class="link-btn" @click="goToRegistrySettings">
        {{ t('marketplaceSkills.registryLink') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.marketplace-pane {
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

.registry-pointer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 14px 16px;
  background: var(--bg-secondary);
  border: 1px dashed var(--border-default);
  border-radius: 10px;
  font-size: 13px;
  color: var(--text-tertiary);
}

.link-btn {
  background: none;
  border: none;
  color: var(--accent-cyan);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  padding: 0;
}

.link-btn:hover {
  text-decoration: underline;
}
</style>
