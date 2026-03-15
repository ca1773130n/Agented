<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick, computed } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import type { RouteLocationRaw } from 'vue-router';
import { productApi, projectApi, teamApi, agentApi, pluginApi } from '../../services/api';

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ 'update:open': [value: boolean] }>();

const router = useRouter();
const route = useRoute();

// --- Types ---

type EntityType = 'Product' | 'Project' | 'Team' | 'Agent' | 'Plugin';

interface SearchResult {
  type: EntityType;
  name: string;
  id: string;
  route: RouteLocationRaw;
}

// --- State ---

const query = ref('');
const results = ref<SearchResult[]>([]);
const selectedIndex = ref(0);
const loading = ref(false);
const error = ref(false);
const inputRef = ref<HTMLInputElement | null>(null);
const resultsRef = ref<HTMLDivElement | null>(null);

// --- Cache ---

interface CachedData {
  products: { id: string; name: string }[];
  projects: { id: string; name: string }[];
  teams: { id: string; name: string }[];
  agents: { id: string; name: string }[];
  plugins: { id: string; name: string }[];
  timestamp: number;
}

let cachedData: CachedData | null = null;
const CACHE_TTL = 30_000; // 30 seconds

function isCacheValid(): boolean {
  return cachedData !== null && Date.now() - cachedData.timestamp < CACHE_TTL;
}

// --- Route mapping ---

function buildRoute(type: EntityType, id: string): RouteLocationRaw {
  switch (type) {
    case 'Product':
      return { name: 'product-dashboard', params: { productId: id } };
    case 'Project':
      return { name: 'project-dashboard', params: { projectId: id } };
    case 'Team':
      return { name: 'team-dashboard', params: { teamId: id } };
    case 'Agent':
      return { name: 'agent-design', params: { agentId: id } };
    case 'Plugin':
      return { name: 'plugin-detail', params: { pluginId: id } };
  }
}

// --- Data fetching ---

async function fetchAllEntities(): Promise<void> {
  if (isCacheValid()) return;

  loading.value = true;
  error.value = false;

  try {
    const [productsRes, projectsRes, teamsRes, agentsRes, pluginsRes] = await Promise.all([
      productApi.list(),
      projectApi.list(),
      teamApi.list(),
      agentApi.list(),
      pluginApi.list(),
    ]);

    cachedData = {
      products: productsRes.products.map((p) => ({ id: p.id, name: p.name })),
      projects: projectsRes.projects.map((p) => ({ id: p.id, name: p.name })),
      teams: teamsRes.teams.map((t) => ({ id: t.id, name: t.name })),
      agents: agentsRes.agents.map((a) => ({ id: a.id, name: a.name })),
      plugins: pluginsRes.plugins.map((p) => ({ id: p.id, name: p.name })),
      timestamp: Date.now(),
    };
  } catch {
    error.value = true;
  } finally {
    loading.value = false;
  }
}

function filterResults(q: string): SearchResult[] {
  if (!cachedData || !q.trim()) return [];

  const lower = q.toLowerCase();
  const matched: SearchResult[] = [];

  const entityGroups: { type: EntityType; items: { id: string; name: string }[] }[] = [
    { type: 'Product', items: cachedData.products },
    { type: 'Project', items: cachedData.projects },
    { type: 'Team', items: cachedData.teams },
    { type: 'Agent', items: cachedData.agents },
    { type: 'Plugin', items: cachedData.plugins },
  ];

  for (const group of entityGroups) {
    for (const item of group.items) {
      if (item.name.toLowerCase().includes(lower)) {
        matched.push({
          type: group.type,
          name: item.name,
          id: item.id,
          route: buildRoute(group.type, item.id),
        });
      }
    }
  }

  return matched;
}

// --- Grouped results ---

const groupedResults = computed(() => {
  const groups: { type: EntityType; items: SearchResult[] }[] = [];
  const typeOrder: EntityType[] = ['Product', 'Project', 'Team', 'Agent', 'Plugin'];

  for (const type of typeOrder) {
    const items = results.value.filter((r) => r.type === type);
    if (items.length > 0) {
      groups.push({ type, items });
    }
  }

  return groups;
});

// --- Debounced search ---

let debounceTimer: ReturnType<typeof setTimeout> | null = null;

watch(query, (val) => {
  if (debounceTimer) clearTimeout(debounceTimer);

  debounceTimer = setTimeout(() => {
    results.value = filterResults(val);
    selectedIndex.value = 0;
  }, 200);
});

// --- State computations ---

const showInitial = computed(
  () => !loading.value && !error.value && !query.value.trim() && results.value.length === 0,
);

const showEmpty = computed(
  () =>
    !loading.value && !error.value && query.value.trim().length > 0 && results.value.length === 0,
);

// --- Navigation ---

function selectResult(result: SearchResult): void {
  router.push(result.route);
  close();
}

function selectCurrent(): void {
  if (results.value.length > 0 && selectedIndex.value < results.value.length) {
    selectResult(results.value[selectedIndex.value]);
  }
}

function close(): void {
  emit('update:open', false);
  query.value = '';
  results.value = [];
  selectedIndex.value = 0;
}

// --- Keyboard navigation ---

function onKeydown(e: KeyboardEvent): void {
  switch (e.key) {
    case 'ArrowDown':
      e.preventDefault();
      if (results.value.length > 0) {
        selectedIndex.value = (selectedIndex.value + 1) % results.value.length;
        scrollSelectedIntoView();
      }
      break;
    case 'ArrowUp':
      e.preventDefault();
      if (results.value.length > 0) {
        selectedIndex.value =
          (selectedIndex.value - 1 + results.value.length) % results.value.length;
        scrollSelectedIntoView();
      }
      break;
    case 'Enter':
      e.preventDefault();
      selectCurrent();
      break;
    case 'Escape':
      e.preventDefault();
      close();
      break;
  }
}

function scrollSelectedIntoView(): void {
  nextTick(() => {
    const container = resultsRef.value;
    if (!container) return;
    const selected = container.querySelector('.palette-result.selected') as HTMLElement | null;
    if (selected) {
      selected.scrollIntoView({ block: 'nearest' });
    }
  });
}

// --- Focus management ---

function onBackdropClick(e: MouseEvent): void {
  if ((e.target as HTMLElement).classList.contains('command-palette-backdrop')) {
    close();
  }
}

function onFocusTrap(e: KeyboardEvent): void {
  if (e.key !== 'Tab') return;

  const modal = (e.currentTarget as HTMLElement).querySelector('.command-palette') as HTMLElement;
  if (!modal) return;

  const focusable = modal.querySelectorAll<HTMLElement>(
    'input, button, [tabindex]:not([tabindex="-1"])',
  );
  if (focusable.length === 0) return;

  const first = focusable[0];
  const last = focusable[focusable.length - 1];

  if (e.shiftKey) {
    if (document.activeElement === first) {
      e.preventDefault();
      last.focus();
    }
  } else {
    if (document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }
}

// --- Global keyboard shortcut (Cmd+K / Ctrl+K) ---

function onGlobalKeydown(e: KeyboardEvent): void {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault();
    emit('update:open', !props.open);
  }
}

onMounted(() => {
  document.addEventListener('keydown', onGlobalKeydown);
});

onUnmounted(() => {
  document.removeEventListener('keydown', onGlobalKeydown);
  if (debounceTimer) clearTimeout(debounceTimer);
});

// --- Watch open prop ---

watch(
  () => props.open,
  async (isOpen) => {
    if (isOpen) {
      await fetchAllEntities();
      await nextTick();
      inputRef.value?.focus();
    } else {
      query.value = '';
      results.value = [];
      selectedIndex.value = 0;
    }
  },
);

// --- Close on route change ---

watch(
  () => route.fullPath,
  () => {
    if (props.open) {
      close();
    }
  },
);

// --- Retry ---

function retry(): void {
  cachedData = null;
  fetchAllEntities();
}

// --- Flat index helper ---

function getFlatIndex(groupType: EntityType, itemIndex: number): number {
  let flat = 0;
  for (const group of groupedResults.value) {
    if (group.type === groupType) {
      return flat + itemIndex;
    }
    flat += group.items.length;
  }
  return flat;
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="command-palette-backdrop"
      @click="onBackdropClick"
      @keydown="onFocusTrap"
    >
      <div class="command-palette" @keydown="onKeydown">
        <div class="palette-input-wrapper">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.35-4.35" />
          </svg>
          <input
            ref="inputRef"
            v-model="query"
            class="palette-input"
            type="text"
            placeholder="Search products, projects, teams, agents, plugins..."
            autocomplete="off"
            spellcheck="false"
          />
        </div>

        <div ref="resultsRef" class="palette-results">
          <!-- Loading -->
          <div v-if="loading" class="palette-state">
            <div class="spinner" />
            <div>Searching...</div>
          </div>

          <!-- Error -->
          <div v-else-if="error" class="palette-state">
            <div>Search failed</div>
            <button class="retry-btn" @click="retry">Retry</button>
          </div>

          <!-- Initial state -->
          <div v-else-if="showInitial" class="palette-state">
            Type to search across products, projects, teams, agents, and plugins
          </div>

          <!-- Empty results -->
          <div v-else-if="showEmpty" class="palette-state">No results found</div>

          <!-- Results grouped by type -->
          <template v-else>
            <template v-for="group in groupedResults" :key="group.type">
              <div class="palette-group-label">{{ group.type }}s</div>
              <div
                v-for="(result, itemIdx) in group.items"
                :key="result.id"
                class="palette-result"
                :class="{ selected: selectedIndex === getFlatIndex(group.type, itemIdx) }"
                @click="selectResult(result)"
                @mouseenter="selectedIndex = getFlatIndex(group.type, itemIdx)"
              >
                <span class="palette-result-name">{{ result.name }}</span>
                <span class="palette-type-badge" :class="result.type.toLowerCase()">{{
                  result.type
                }}</span>
              </div>
            </template>
          </template>
        </div>

        <div class="palette-hint">
          <span><kbd>&uarr;</kbd> <kbd>&darr;</kbd> navigate</span>
          <span><kbd>Enter</kbd> select</span>
          <span><kbd>Esc</kbd> close</span>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.command-palette-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 2000;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 120px;
}

.command-palette {
  width: 90%;
  max-width: 560px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  overflow: hidden;
}

.palette-input-wrapper {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-subtle);
}

.palette-input-wrapper svg {
  width: 18px;
  height: 18px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.palette-input {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: 1rem;
  font-family: inherit;
  outline: none;
}

.palette-input::placeholder {
  color: var(--text-muted);
}

.palette-results {
  max-height: 400px;
  overflow-y: auto;
  padding: 8px;
}

.palette-group-label {
  padding: 8px 8px 4px;
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.palette-result {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: background var(--transition-fast);
}

.palette-result:hover,
.palette-result.selected {
  background: var(--bg-tertiary);
}

.palette-result-name {
  flex: 1;
  color: var(--text-primary);
  font-size: 0.9rem;
}

.palette-type-badge {
  font-size: 0.7rem;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 500;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

/* Type-specific badge colors */
.palette-type-badge.product {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}
.palette-type-badge.project {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}
.palette-type-badge.team {
  background: var(--accent-violet-dim);
  color: var(--accent-violet);
}
.palette-type-badge.agent {
  background: var(--accent-amber-dim);
  color: var(--accent-amber);
}
.palette-type-badge.plugin {
  background: var(--accent-crimson-dim);
  color: var(--accent-crimson);
}

/* States */
.palette-state {
  padding: 32px 16px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 0.9rem;
}

.palette-state .spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--border-default);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: palette-spin 1s linear infinite;
  margin: 0 auto 12px;
}

@keyframes palette-spin {
  to {
    transform: rotate(360deg);
  }
}

.palette-state .retry-btn {
  margin-top: 8px;
  padding: 6px 16px;
  background: transparent;
  border: 1px solid var(--accent-cyan);
  border-radius: 6px;
  color: var(--accent-cyan);
  cursor: pointer;
  font-size: 0.85rem;
  transition: background var(--transition-fast);
}

.palette-state .retry-btn:hover {
  background: rgba(0, 212, 255, 0.1);
}

.palette-hint {
  padding: 8px 16px;
  border-top: 1px solid var(--border-subtle);
  font-size: 0.75rem;
  color: var(--text-muted);
  display: flex;
  gap: 12px;
}

.palette-hint kbd {
  background: var(--bg-tertiary);
  padding: 1px 5px;
  border-radius: 3px;
  font-family: var(--font-mono);
  font-size: 0.7rem;
}
</style>
