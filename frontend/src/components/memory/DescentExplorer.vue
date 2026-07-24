<script setup lang="ts">
/**
 * Descent explorer — Tesserae 0.25 `graph_map` structural navigation.
 *
 * Renders the compiled graph's community hierarchy as budgeted CARDS instead of
 * loading the whole (multi-million-token) graph: start at the root map, click a
 * card to DESCEND by its scope_id, use the breadcrumb to ASCEND, and page an
 * oversized level with "load more" (cursor). Cost is depth × budget, not graph
 * size. Self-contained: mount it anywhere (the KG Explorer page hosts it).
 */
import { ref, computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { memorySystemApi } from '../../services/api/memory-system';
import type { GraphMapCard, GraphMapHeader } from '../../services/api/memory-system';

const { t } = useI18n();

interface Crumb {
  id: string | null;
  title: string;
}

const trail = ref<Crumb[]>([{ id: null, title: '' }]);
const header = ref<GraphMapHeader | null>(null);
const cards = ref<GraphMapCard[]>([]);
const loading = ref(true);
const loadingMore = ref(false);
const error = ref<string | null>(null);

const currentScope = computed<string | null>(() => trail.value[trail.value.length - 1].id);
const hasMore = computed(
  () => (header.value?.total_cards ?? 0) > cards.value.length,
);
// A descendable card has a hierarchy below it; leaf 'node' cards do not.
function canDescend(c: GraphMapCard): boolean {
  return c.kind === 'community' && (c.children_count ?? 0) > 0;
}

// Monotonic request id: rapid drill/ascend can leave a SLOWER earlier request in
// flight, and without this guard its late response would overwrite the newer scope's
// cards. Only the most recent request may write state.
let reqSeq = 0;

async function loadScope(scope: string | null) {
  const myReq = ++reqSeq;
  loading.value = true;
  error.value = null;
  try {
    const res = await memorySystemApi.graphMap(scope);
    if (myReq !== reqSeq) return; // superseded — discard
    if (!res.ok || !res.map) {
      error.value = res.reason || t('descent.failed');
      header.value = null;
      cards.value = [];
      return;
    }
    header.value = res.map.header;
    cards.value = res.map.cards;
  } catch (e) {
    if (myReq !== reqSeq) return;
    error.value = (e as Error).message || t('descent.failed');
  } finally {
    if (myReq === reqSeq) loading.value = false;
  }
}

async function loadMore() {
  if (loadingMore.value || !hasMore.value) return;
  const myReq = reqSeq; // page belongs to THIS scope; a navigation invalidates it
  loadingMore.value = true;
  try {
    const res = await memorySystemApi.graphMap(currentScope.value, cards.value.length);
    if (myReq !== reqSeq) return; // navigated away — do not append to the new scope
    if (res.ok && res.map) {
      // Append only genuinely new scope_ids (defensive against cursor overlap).
      const seen = new Set(cards.value.map((c) => c.scope_id));
      cards.value.push(...res.map.cards.filter((c) => !seen.has(c.scope_id)));
    } else {
      // Don't fail silently — the user needs to know the page didn't arrive.
      error.value = res.reason || t('descent.failed');
    }
  } catch (e) {
    if (myReq === reqSeq) error.value = (e as Error).message || t('descent.failed');
  } finally {
    if (myReq === reqSeq) loadingMore.value = false;
  }
}

function descend(c: GraphMapCard) {
  if (!canDescend(c)) return;
  trail.value.push({ id: c.scope_id, title: c.title });
  void loadScope(c.scope_id);
}

function goToCrumb(idx: number) {
  if (idx === trail.value.length - 1) return;
  trail.value = trail.value.slice(0, idx + 1);
  void loadScope(trail.value[idx].id);
}

onMounted(() => {
  trail.value = [{ id: null, title: t('descent.root') }];
  void loadScope(null);
});
</script>

<template>
  <section class="descent" aria-label="Descent explorer">
    <header class="descent__head">
      <div class="descent__title">
        <h3>{{ t('descent.title') }}</h3>
        <p>{{ t('descent.subtitle') }}</p>
      </div>
      <div v-if="header" class="descent__stats">
        <span v-if="header.node_count != null"><strong>{{ header.node_count.toLocaleString() }}</strong> {{ t('knowledgeGraph.nodes') }}</span>
        <span v-if="header.community_count != null"><strong>{{ header.community_count }}</strong> {{ t('descent.communities') }}</span>
        <span v-if="header.levels != null"><strong>{{ header.levels }}</strong> {{ t('descent.levels') }}</span>
      </div>
    </header>

    <!-- Breadcrumb / ascend -->
    <nav class="descent__crumbs" :aria-label="t('descent.breadcrumb')">
      <template v-for="(c, i) in trail" :key="i">
        <button
          class="descent__crumb"
          :class="{ 'descent__crumb--current': i === trail.length - 1 }"
          :disabled="i === trail.length - 1"
          @click="goToCrumb(i)"
        >{{ c.title || t('descent.root') }}</button>
        <span v-if="i < trail.length - 1" class="descent__crumb-sep">/</span>
      </template>
    </nav>

    <div v-if="loading" class="descent__msg">{{ t('descent.loading') }}</div>
    <div v-else-if="error" class="descent__msg descent__msg--error">
      {{ error }}
      <button class="descent__retry" @click="loadScope(currentScope)">{{ t('descent.retry') }}</button>
    </div>
    <div v-else-if="!cards.length" class="descent__msg">{{ t('descent.empty') }}</div>

    <ul v-else class="descent__cards">
      <li
        v-for="c in cards"
        :key="c.scope_id"
        class="descent__card"
        :class="{ 'descent__card--drillable': canDescend(c) }"
        :tabindex="canDescend(c) ? 0 : -1"
        :role="canDescend(c) ? 'button' : undefined"
        @click="descend(c)"
        @keydown.enter="descend(c)"
      >
        <div class="descent__card-top">
          <span class="descent__card-title">{{ c.title }}</span>
          <span
            class="descent__badge"
            :class="c.quality === 'llm' ? 'descent__badge--llm' : 'descent__badge--struct'"
          >{{ c.quality === 'llm' ? t('descent.qualityLlm') : t('descent.qualityStructural') }}</span>
        </div>
        <p v-if="c.summary" class="descent__card-summary">{{ c.summary }}</p>
        <div class="descent__card-meta">
          <span v-if="c.size != null">{{ t('descent.members', { n: c.size.toLocaleString() }) }}</span>
          <span v-if="canDescend(c)" class="descent__card-drill">{{ t('descent.children', { n: c.children_count }) }} ›</span>
          <span v-if="c.stale" class="descent__stale">{{ t('descent.stale') }}</span>
        </div>
        <div v-if="c.tags && c.tags.length" class="descent__tags">
          <span v-for="tag in c.tags.slice(0, 6)" :key="tag" class="descent__tag">{{ tag }}</span>
        </div>
      </li>
    </ul>

    <button
      v-if="!loading && !error && hasMore"
      class="descent__more"
      :disabled="loadingMore"
      @click="loadMore"
    >{{ loadingMore ? t('descent.loading') : t('descent.loadMore', { n: (header?.total_cards ?? 0) - cards.length }) }}</button>
  </section>
</template>

<style scoped>
.descent {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface-1, var(--bg-elevated));
  padding: 1rem 1.15rem 1.25rem;
}
.descent__head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  flex-wrap: wrap;
}
.descent__title h3 {
  margin: 0;
  font-size: 1rem;
}
.descent__title p {
  margin: 0.15rem 0 0;
  font-size: 0.8rem;
  color: var(--text-muted);
}
.descent__stats {
  display: flex;
  gap: 0.9rem;
  font-size: 0.8rem;
  color: var(--text-muted);
  white-space: nowrap;
}
.descent__stats strong {
  color: var(--text);
}
.descent__crumbs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.3rem;
  margin: 0.85rem 0 0.75rem;
}
.descent__crumb {
  background: none;
  border: none;
  color: var(--accent-blue, #6ea8fe);
  cursor: pointer;
  font-size: 0.82rem;
  padding: 0.1rem 0.2rem;
  border-radius: 4px;
}
.descent__crumb--current {
  color: var(--text);
  font-weight: 600;
  cursor: default;
}
.descent__crumb-sep {
  color: var(--text-muted);
  font-size: 0.8rem;
}
.descent__msg {
  padding: 1.5rem 0.5rem;
  text-align: center;
  color: var(--text-muted);
  font-size: 0.85rem;
}
.descent__msg--error {
  color: var(--accent-red, #e5484d);
}
.descent__retry {
  margin-left: 0.6rem;
  font-size: 0.78rem;
  padding: 0.15rem 0.55rem;
  border-radius: 5px;
  border: 1px solid var(--border);
  background: var(--bg-elevated);
  color: var(--text);
  cursor: pointer;
}
.descent__cards {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 0.7rem;
}
.descent__card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.7rem 0.8rem;
  background: var(--bg-elevated);
  outline: none;
}
.descent__card--drillable {
  cursor: pointer;
  transition: border-color 0.12s, transform 0.12s;
}
.descent__card--drillable:hover,
.descent__card--drillable:focus-visible {
  border-color: var(--accent-blue, #6ea8fe);
  transform: translateY(-1px);
}
.descent__card-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.5rem;
}
.descent__card-title {
  font-size: 0.86rem;
  font-weight: 600;
  color: var(--text);
  line-height: 1.25;
}
.descent__badge {
  font-size: 0.64rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  padding: 0.1rem 0.35rem;
  border-radius: 4px;
  white-space: nowrap;
  flex-shrink: 0;
}
.descent__badge--llm {
  color: var(--accent-green, #30a46c);
  background: color-mix(in srgb, var(--accent-green, #30a46c) 16%, transparent);
}
.descent__badge--struct {
  color: var(--text-muted);
  background: color-mix(in srgb, var(--text-muted) 14%, transparent);
}
.descent__card-summary {
  margin: 0.4rem 0 0;
  font-size: 0.78rem;
  color: var(--text-muted);
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.descent__card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  margin-top: 0.5rem;
  font-size: 0.74rem;
  color: var(--text-muted);
}
.descent__card-drill {
  color: var(--accent-blue, #6ea8fe);
  font-weight: 600;
}
.descent__stale {
  color: var(--accent-amber, #f5a623);
}
.descent__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  margin-top: 0.55rem;
}
.descent__tag {
  font-size: 0.68rem;
  color: var(--text-muted);
  background: color-mix(in srgb, var(--text-muted) 12%, transparent);
  padding: 0.08rem 0.4rem;
  border-radius: 4px;
}
.descent__more {
  display: block;
  margin: 0.9rem auto 0;
  font-size: 0.8rem;
  padding: 0.4rem 1rem;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg-elevated);
  color: var(--text);
  cursor: pointer;
}
.descent__more:disabled {
  opacity: 0.6;
  cursor: default;
}
</style>
