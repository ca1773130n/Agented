<script setup lang="ts">
/**
 * Knowledge Graph explorer — an interactive, browsable view of Tesserae's
 * compiled graph. Lands on a connected overview subgraph (never empty),
 * renders it in a VueFlow canvas with a frontend-computed CONCENTRIC layout
 * (backend emits no coordinates), colours nodes by type and sizes them by
 * degree. Search or click a node to refocus on its neighbourhood and inspect
 * full detail (description, aliases, source, typed neighbours) in a side panel.
 */
import { ref, computed, onMounted, watch, nextTick } from 'vue';
import { useI18n } from 'vue-i18n';
import { VueFlow, useVueFlow } from '@vue-flow/core';
import type { Node as FlowNode, Edge as FlowEdge } from '@vue-flow/core';
import { Background } from '@vue-flow/background';
import { Controls } from '@vue-flow/controls';
import '@vue-flow/core/dist/style.css';
import '@vue-flow/core/dist/theme-default.css';
import '@vue-flow/controls/dist/style.css';

import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import ErrorState from '../components/base/ErrorState.vue';
import EmptyState from '../components/base/EmptyState.vue';
import { memorySystemApi } from '../services/api/memory-system';
import type {
  GraphNode,
  GraphEdge,
  NodeDetail,
} from '../services/api/memory-system';

const { t } = useI18n();

// --- Node-type → accent colour (deterministic) ---
const ACCENTS = ['cyan', 'emerald', 'amber', 'violet', 'crimson'] as const;
type Accent = (typeof ACCENTS)[number];
// A few explicit picks for common Tesserae node types; everything else hashes
// to a stable accent so the same type is always the same colour.
const TYPE_ACCENTS: Record<string, Accent> = {
  Decision: 'amber',
  Insight: 'emerald',
  Finding: 'emerald',
  Session: 'cyan',
  File: 'violet',
  Concept: 'cyan',
  Person: 'crimson',
  Gotcha: 'crimson',
  Runbook: 'emerald',
  Paper: 'violet',
  Requirement: 'amber',
};
function accentFor(type: string): Accent {
  const explicit = TYPE_ACCENTS[type];
  if (explicit) return explicit;
  let h = 0;
  for (let i = 0; i < type.length; i++) h = (h * 31 + type.charCodeAt(i)) >>> 0;
  return ACCENTS[h % ACCENTS.length];
}

// --- VueFlow canvas state ---
const { fitView } = useVueFlow({ id: 'kg-explorer' });
const flowNodes = ref<FlowNode[]>([]);
const flowEdges = ref<FlowEdge[]>([]);

const totalNodes = ref(0);
const totalEdges = ref(0);
const truncated = ref(false);
const selectedId = ref<string | null>(null);

// Distinct types present in the current canvas → legend.
const legend = computed(() => {
  const seen = new Map<string, Accent>();
  for (const n of flowNodes.value) {
    const type = (n.data as { type?: string }).type;
    if (type && !seen.has(type)) seen.set(type, accentFor(type));
  }
  return Array.from(seen.entries()).map(([type, accent]) => ({ type, accent }));
});

// --- Concentric layout: center at (0,0), 1-hop on r≈220, 2-hop+ on r≈420 ---
function buildFlow(nodes: GraphNode[], edges: GraphEdge[]) {
  const ids = new Set(nodes.map((n) => n.id));
  const safeEdges = edges.filter((e) => ids.has(e.source) && ids.has(e.target));

  // Undirected adjacency for BFS hop distance from the center.
  const adj = new Map<string, string[]>();
  for (const e of safeEdges) {
    (adj.get(e.source) ?? adj.set(e.source, []).get(e.source)!).push(e.target);
    (adj.get(e.target) ?? adj.set(e.target, []).get(e.target)!).push(e.source);
  }
  const center = nodes.find((n) => n.center) ?? nodes[0];
  const hop = new Map<string, number>();
  if (center) {
    hop.set(center.id, 0);
    const queue = [center.id];
    while (queue.length) {
      const cur = queue.shift() as string;
      const d = hop.get(cur) as number;
      for (const nb of adj.get(cur) ?? []) {
        if (!hop.has(nb)) {
          hop.set(nb, d + 1);
          queue.push(nb);
        }
      }
    }
  }

  // Bucket into rings (unreachable → outer ring 2).
  const rings = new Map<number, GraphNode[]>();
  for (const n of nodes) {
    const h = hop.has(n.id) ? Math.min(hop.get(n.id) as number, 2) : 2;
    (rings.get(h) ?? rings.set(h, []).get(h)!).push(n);
  }
  // Ring radius SCALES with how many nodes sit on it (each node reserves ~RING_SLOT
  // px of arc), so a busy ring spreads out instead of overlapping — long labels are
  // also clamped (full name lives in the detail panel), keeping nodes compact.
  const RING_SLOT = 180;
  const baseRadii: Record<number, number> = { 0: 0, 1: 240, 2: 480 };
  const ringRadius = (h: number, count: number) =>
    h === 0 ? 0 : Math.max(baseRadii[h] ?? 520, (count * RING_SLOT) / (Math.PI * 2));

  const degs = nodes.map((n) => n.degree);
  const minD = degs.length ? Math.min(...degs) : 0;
  const maxD = degs.length ? Math.max(...degs) : 1;
  const range = Math.max(1, maxD - minD);
  const clampLabel = (s: string) => (s.length > 40 ? s.slice(0, 39).trimEnd() + '…' : s);

  const built: FlowNode[] = [];
  for (const [h, group] of rings) {
    const r = ringRadius(h, group.length);
    group.forEach((n, i) => {
      // stagger alternate rings by half a slot so outer nodes don't line up
      // radially behind inner ones.
      const angle = ((i + (h % 2) * 0.5) / Math.max(1, group.length)) * Math.PI * 2;
      const x = h === 0 ? 0 : Math.cos(angle) * r;
      const y = h === 0 ? 0 : Math.sin(angle) * r;
      const accent = accentFor(n.type);
      const size = 96 + Math.round(((n.degree - minD) / range) * 64);
      built.push({
        id: n.id,
        position: { x, y },
        data: { label: clampLabel(n.name), type: n.type, degree: n.degree },
        class: n.center ? 'kg-node kg-node--center' : 'kg-node',
        style: {
          background: `var(--accent-${accent}-dim)`,
          border: `1.5px solid var(--accent-${accent})`,
          color: 'var(--text-primary)',
          width: `${size}px`,
          borderRadius: '12px',
          fontSize: '11px',
          fontWeight: '600',
          textAlign: 'center',
          padding: '8px 10px',
        },
      });
    });
  }

  flowNodes.value = built;
  flowEdges.value = safeEdges.map((e, i) => ({
    id: `${e.source}__${e.target}__${i}`,
    source: e.source,
    target: e.target,
    label: e.type,
    style: { stroke: 'var(--border-default)', strokeWidth: 1.2 },
    labelStyle: { fill: 'var(--text-secondary)', fontSize: '9px', fontWeight: 500 },
    labelBgStyle: { fill: 'var(--bg-secondary)', fillOpacity: 0.85 },
    labelBgPadding: [4, 2] as [number, number],
    labelBgBorderRadius: 4,
  }));

  nextTick(() => fitView({ padding: 0.2, duration: 300 }));
}

// --- Overview (landing) ---
const loading = ref(true);
const loadError = ref<string | null>(null);

async function loadOverview() {
  loading.value = true;
  loadError.value = null;
  try {
    const res = await memorySystemApi.graphOverview(null, 30);
    totalNodes.value = res.total_nodes;
    totalEdges.value = res.total_edges;
    truncated.value = false;
    buildFlow(res.nodes, res.edges);
    // Auto-open the seed node's detail so the panel isn't empty on landing.
    const seed = res.nodes.find((n) => n.center) ?? res.nodes[0];
    if (seed) void focusNode(seed.id, { skipSubgraph: true });
  } catch (e) {
    loadError.value = (e as Error).message || t('knowledgeGraph.overviewFailed');
  } finally {
    loading.value = false;
  }
}

// --- Focus a node: refocus canvas on its subgraph + load detail panel ---
const detail = ref<NodeDetail | null>(null);
const detailLoading = ref(false);
const detailError = ref<string | null>(null);

async function focusNode(nodeId: string, opts: { skipSubgraph?: boolean } = {}) {
  selectedId.value = nodeId;
  if (!opts.skipSubgraph) {
    try {
      const sg = await memorySystemApi.graphSubgraph(nodeId, null, 1, 40);
      truncated.value = sg.truncated;
      buildFlow(sg.nodes, sg.edges);
    } catch (e) {
      loadError.value = (e as Error).message || t('knowledgeGraph.subgraphFailed');
    }
  }
  detailLoading.value = true;
  detailError.value = null;
  try {
    detail.value = await memorySystemApi.graphNodeDetail(nodeId);
  } catch (e) {
    detail.value = null;
    detailError.value = (e as Error).message || t('knowledgeGraph.detailFailed');
  } finally {
    detailLoading.value = false;
  }
}

function onNodeClick({ node }: { node: FlowNode }) {
  void focusNode(node.id);
}

function closePanel() {
  detail.value = null;
  selectedId.value = null;
}

// --- Search (debounced ~250ms) ---
const q = ref('');
const results = ref<GraphNode[]>([]);
const searching = ref(false);
const searched = ref(false);
let searchTimer: ReturnType<typeof setTimeout> | undefined;

watch(q, (val) => {
  clearTimeout(searchTimer);
  const query = val.trim();
  if (!query) {
    results.value = [];
    searched.value = false;
    return;
  }
  searchTimer = setTimeout(async () => {
    searching.value = true;
    try {
      const res = await memorySystemApi.graphSearchNodes(query);
      results.value = res.nodes;
      searched.value = true;
    } catch {
      results.value = [];
      searched.value = true;
    } finally {
      searching.value = false;
    }
  }, 250);
});

function pickResult(node: GraphNode) {
  q.value = '';
  results.value = [];
  searched.value = false;
  void focusNode(node.id);
}

onMounted(loadOverview);
</script>

<template>
  <div class="kg-page">
    <PageHeader :title="t('knowledgeGraph.title')" :subtitle="t('knowledgeGraph.subtitle')">
      <template v-if="!loading && !loadError" #actions>
        <div class="kg-counts">
          <span><strong>{{ totalNodes.toLocaleString() }}</strong> {{ t('knowledgeGraph.nodes') }}</span>
          <span class="kg-counts__sep">·</span>
          <span><strong>{{ totalEdges.toLocaleString() }}</strong> {{ t('knowledgeGraph.edges') }}</span>
        </div>
      </template>
    </PageHeader>

    <!-- Search -->
    <div class="kg-search">
      <input
        v-model="q"
        class="kg-search__input"
        type="search"
        :placeholder="t('knowledgeGraph.searchPlaceholder')"
        :aria-label="t('knowledgeGraph.searchPlaceholder')"
      />
      <span v-if="searching" class="kg-search__status">{{ t('knowledgeGraph.searching') }}</span>
      <ul v-if="results.length" class="kg-results" role="listbox">
        <li
          v-for="r in results"
          :key="r.id"
          class="kg-result"
          role="option"
          tabindex="0"
          @click="pickResult(r)"
          @keydown.enter="pickResult(r)"
        >
          <span class="kg-result__name">{{ r.name }}</span>
          <span
            class="kg-result__chip"
            :style="{
              color: `var(--accent-${accentFor(r.type)})`,
              background: `var(--accent-${accentFor(r.type)}-dim)`,
            }"
          >{{ r.type }}</span>
          <span class="kg-result__deg">{{ t('knowledgeGraph.degree', { n: r.degree }) }}</span>
        </li>
      </ul>
      <div v-else-if="searched && !searching" class="kg-results kg-results--empty">
        {{ t('knowledgeGraph.searchNoResults') }}
      </div>
    </div>

    <LoadingState v-if="loading" :message="t('knowledgeGraph.loading')" />
    <ErrorState
      v-else-if="loadError"
      :title="t('knowledgeGraph.overviewFailed')"
      :message="loadError"
      @retry="loadOverview"
    />
    <EmptyState
      v-else-if="!flowNodes.length"
      :title="t('knowledgeGraph.graphEmptyTitle')"
      :description="t('knowledgeGraph.graphEmptyBody')"
    />

    <div v-else class="kg-layout">
      <div class="kg-canvas-wrap">
        <p v-if="truncated" class="kg-truncated">{{ t('knowledgeGraph.truncated') }}</p>
        <VueFlow
          v-model:nodes="flowNodes"
          v-model:edges="flowEdges"
          class="kg-flow"
          :min-zoom="0.15"
          :max-zoom="2"
          fit-view-on-init
          @node-click="onNodeClick"
        >
          <Background :gap="22" />
          <Controls :show-interactive="false" />
        </VueFlow>

        <div v-if="legend.length" class="kg-legend">
          <span class="kg-legend__title">{{ t('knowledgeGraph.legendTitle') }}</span>
          <span
            v-for="l in legend"
            :key="l.type"
            class="kg-legend__item"
          >
            <span class="kg-legend__dot" :style="{ background: `var(--accent-${l.accent})` }" />
            {{ l.type }}
          </span>
        </div>
      </div>

      <!-- Detail side panel -->
      <aside v-if="selectedId" class="kg-panel">
        <button class="kg-panel__close" :aria-label="t('knowledgeGraph.panelClose')" @click="closePanel">×</button>

        <div v-if="detailLoading" class="kg-panel__loading">{{ t('common.loading') }}</div>
        <div v-else-if="detailError" class="kg-panel__error">{{ detailError }}</div>
        <template v-else-if="detail">
          <span
            class="kg-panel__type"
            :style="{
              color: `var(--accent-${accentFor(detail.type)})`,
              background: `var(--accent-${accentFor(detail.type)}-dim)`,
            }"
          >{{ detail.type }}</span>
          <h2 class="kg-panel__name">{{ detail.name }}</h2>
          <div class="kg-panel__meta">{{ t('knowledgeGraph.degree', { n: detail.degree }) }}</div>

          <p v-if="detail.description" class="kg-panel__desc">{{ detail.description }}</p>
          <p v-else class="kg-panel__desc kg-panel__desc--muted">{{ t('knowledgeGraph.panelNoDescription') }}</p>

          <div v-if="detail.aliases.length" class="kg-panel__section">
            <span class="kg-panel__label">{{ t('knowledgeGraph.panelAliases') }}</span>
            <div class="kg-panel__aliases">
              <span v-for="a in detail.aliases" :key="a" class="kg-panel__alias">{{ a }}</span>
            </div>
          </div>

          <div v-if="detail.source_path" class="kg-panel__section">
            <span class="kg-panel__label">{{ t('knowledgeGraph.panelSource') }}</span>
            <code class="kg-panel__source">{{ detail.source_path }}</code>
          </div>

          <div v-if="detail.neighbors.length" class="kg-panel__section">
            <span class="kg-panel__label">
              {{ t('knowledgeGraph.panelNeighbors') }} ({{ detail.neighbors.length }})
            </span>
            <ul class="kg-neighbors">
              <li
                v-for="n in detail.neighbors"
                :key="n.id + n.edge_type"
                class="kg-neighbor"
                tabindex="0"
                @click="focusNode(n.id)"
                @keydown.enter="focusNode(n.id)"
              >
                <span
                  class="kg-neighbor__dot"
                  :style="{ background: `var(--accent-${accentFor(n.type)})` }"
                />
                <span class="kg-neighbor__name">{{ n.name }}</span>
                <span class="kg-neighbor__edge">
                  {{ n.direction === 'in' ? '←' : '→' }} {{ n.edge_type }}
                </span>
              </li>
            </ul>
          </div>
        </template>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.kg-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.kg-counts {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-secondary);
}
.kg-counts strong {
  color: var(--text-primary);
  font-family: var(--font-mono, monospace);
}
.kg-counts__sep {
  opacity: 0.5;
}

/* Search */
.kg-search {
  position: relative;
}
.kg-search__input {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--border-default);
  border-radius: 10px;
  background: var(--bg-secondary, #12121a);
  color: var(--text-primary, #e4e4e7);
  font-size: 14px;
  font-family: inherit;
  transition: border-color var(--transition-fast);
}
.kg-search__input:focus {
  outline: none;
  border-color: var(--accent-cyan);
}
.kg-search__status {
  position: absolute;
  right: 14px;
  top: 12px;
  font-size: 12px;
  color: var(--text-secondary);
}
.kg-results {
  list-style: none;
  margin: 6px 0 0;
  padding: 4px;
  position: absolute;
  z-index: 20;
  width: 100%;
  max-height: 320px;
  overflow-y: auto;
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-default);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}
.kg-results--empty {
  padding: 12px 14px;
  font-size: 13px;
  color: var(--text-secondary);
}
.kg-result {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background var(--transition-fast);
}
.kg-result:hover,
.kg-result:focus-visible {
  background: var(--bg-tertiary, #1a1a24);
  outline: none;
}
.kg-result__name {
  flex: 1;
  font-size: 13px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kg-result__chip {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 100px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  white-space: nowrap;
}
.kg-result__deg {
  font-size: 11px;
  color: var(--text-secondary);
  font-family: var(--font-mono, monospace);
}

/* Layout: canvas + panel */
.kg-layout {
  display: flex;
  gap: 16px;
  align-items: stretch;
  min-height: 560px;
}
.kg-canvas-wrap {
  position: relative;
  flex: 1;
  min-width: 0;
  border: 1px solid var(--border-subtle);
  border-radius: 14px;
  overflow: hidden;
  background: var(--bg-secondary, #12121a);
}
.kg-flow {
  width: 100%;
  height: 100%;
  min-height: 560px;
}
.kg-flow :deep(.vue-flow__background) {
  background: var(--bg-primary, #0a0a10);
}
.kg-flow :deep(.vue-flow__node.kg-node) {
  cursor: pointer;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
  transition: box-shadow var(--transition-fast), transform var(--transition-fast);
  line-height: 1.3;
  /* Keep labels to 3 lines so a node never grows tall enough to overlap its ring. */
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.kg-flow :deep(.vue-flow__node.kg-node:hover) {
  transform: translateY(-1px);
}
.kg-flow :deep(.vue-flow__node.kg-node--center) {
  box-shadow: 0 0 0 3px var(--bg-primary), 0 0 0 4px var(--accent-cyan), 0 4px 16px rgba(0, 0, 0, 0.5);
}
.kg-flow :deep(.vue-flow__controls) {
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.4);
}

.kg-truncated {
  position: absolute;
  top: 10px;
  left: 12px;
  z-index: 10;
  margin: 0;
  padding: 4px 10px;
  font-size: 11px;
  color: var(--accent-amber);
  background: var(--accent-amber-dim);
  border-radius: 100px;
}

.kg-legend {
  position: absolute;
  bottom: 12px;
  left: 12px;
  z-index: 10;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 10px;
  max-width: 70%;
  padding: 8px 12px;
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
}
.kg-legend__title {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  color: var(--text-secondary);
}
.kg-legend__item {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--text-secondary);
}
.kg-legend__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

/* Detail panel */
.kg-panel {
  position: relative;
  width: 320px;
  flex-shrink: 0;
  padding: 20px;
  border: 1px solid var(--border-subtle);
  border-radius: 14px;
  background: var(--bg-secondary, #12121a);
  overflow-y: auto;
  max-height: 640px;
}
.kg-panel__close {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 26px;
  height: 26px;
  border: none;
  border-radius: 8px;
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-secondary);
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  transition: color var(--transition-fast), background var(--transition-fast);
}
.kg-panel__close:hover {
  color: var(--text-primary);
  background: var(--bg-elevated, #222230);
}
.kg-panel__loading,
.kg-panel__error {
  padding: 20px 0;
  font-size: 13px;
  color: var(--text-secondary);
}
.kg-panel__error {
  color: var(--danger);
}
.kg-panel__type {
  display: inline-block;
  font-size: 10px;
  padding: 3px 9px;
  border-radius: 100px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.kg-panel__name {
  margin: 10px 0 4px;
  font-size: 17px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.3;
  word-break: break-word;
}
.kg-panel__meta {
  font-size: 11px;
  color: var(--text-secondary);
  font-family: var(--font-mono, monospace);
}
.kg-panel__desc {
  margin: 14px 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--text-secondary);
  word-break: break-word;
}
.kg-panel__desc--muted {
  opacity: 0.6;
  font-style: italic;
}
.kg-panel__section {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--border-subtle);
}
.kg-panel__label {
  display: block;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}
.kg-panel__aliases {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.kg-panel__alias {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 6px;
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-secondary);
}
.kg-panel__source {
  display: block;
  font-size: 11px;
  color: var(--text-secondary);
  font-family: var(--font-mono, monospace);
  word-break: break-all;
  opacity: 0.8;
}
.kg-neighbors {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.kg-neighbor {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  border-radius: 8px;
  cursor: pointer;
  transition: background var(--transition-fast);
}
.kg-neighbor:hover,
.kg-neighbor:focus-visible {
  background: var(--bg-tertiary, #1a1a24);
  outline: none;
}
.kg-neighbor__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.kg-neighbor__name {
  flex: 1;
  font-size: 12px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kg-neighbor__edge {
  font-size: 10px;
  color: var(--text-secondary);
  font-family: var(--font-mono, monospace);
  white-space: nowrap;
}

@media (max-width: 900px) {
  .kg-layout {
    flex-direction: column;
  }
  .kg-panel {
    width: auto;
  }
}
</style>
