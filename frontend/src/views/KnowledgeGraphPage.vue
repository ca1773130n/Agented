<script setup lang="ts">
/**
 * Knowledge Graph explorer — makes Tesserae's graph BROWSABLE (previously
 * Agented only surfaced digests ABOUT it). An overview header (`tesserae status`:
 * node/edge/session counts + last compile) + a raw-retrieval search
 * (`tesserae query --json`: BM25/semantic, NO LLM) returning ranked hits with
 * kind/score/excerpt/node_id. Sibling of MemoryDoctorPage / ActivitySummaryPage.
 */
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import PageHeader from '../components/base/PageHeader.vue';
import { memorySystemApi } from '../services/api/memory-system';
import type { GraphStatus, GraphHit } from '../services/api/memory-system';

const { t } = useI18n();

const status = ref<GraphStatus | null>(null);
const statusError = ref<string | null>(null);

const q = ref('');
const topK = ref(8);
const hits = ref<GraphHit[]>([]);
const searching = ref(false);
const searchError = ref<string | null>(null);
const searched = ref(false);

async function loadStatus() {
  try {
    const res = await memorySystemApi.graphStatus();
    status.value = res.status;
    if (!res.ok) statusError.value = res.reason || t('knowledgeGraph.statusFailed');
  } catch (e) {
    statusError.value = (e as Error).message || t('knowledgeGraph.statusFailed');
  }
}

async function search() {
  const question = q.value.trim();
  if (!question) return;
  searching.value = true;
  searchError.value = null;
  searched.value = true;
  try {
    const res = await memorySystemApi.graphQuery(question, topK.value);
    hits.value = res.hits;
    if (!res.ok) searchError.value = res.reason || t('knowledgeGraph.searchFailed');
  } catch (e) {
    searchError.value = (e as Error).message || t('knowledgeGraph.searchFailed');
    hits.value = [];
  } finally {
    searching.value = false;
  }
}

function scorePct(score: number): number {
  // Retrieval scores are already ~0..1; clamp for the bar width.
  return Math.max(0, Math.min(100, Math.round(score * 100)));
}

onMounted(loadStatus);
</script>

<template>
  <div class="kg-page">
    <PageHeader :title="t('knowledgeGraph.title')" :subtitle="t('knowledgeGraph.subtitle')" />

    <!-- Overview: what does Tesserae know -->
    <div v-if="statusError" class="kg-state kg-state--error">{{ statusError }}</div>
    <div v-else-if="status" class="kg-overview">
      <div class="kg-stat">
        <span class="kg-stat__val">{{ status.nodes.toLocaleString() }}</span>
        <span class="kg-stat__label">{{ t('knowledgeGraph.nodes') }}</span>
      </div>
      <div class="kg-stat">
        <span class="kg-stat__val">{{ status.edges.toLocaleString() }}</span>
        <span class="kg-stat__label">{{ t('knowledgeGraph.edges') }}</span>
      </div>
      <div class="kg-stat">
        <span class="kg-stat__val">{{ status.sessions.toLocaleString() }}</span>
        <span class="kg-stat__label">{{ t('knowledgeGraph.sessions') }}</span>
      </div>
      <div class="kg-stat kg-stat--wide">
        <span class="kg-stat__val kg-stat__val--sm">{{ status.last_compile || '—' }}</span>
        <span class="kg-stat__label">{{ t('knowledgeGraph.lastCompile') }}</span>
      </div>
      <span v-if="status.graph_corrupt" class="kg-corrupt">{{ t('knowledgeGraph.corrupt') }}</span>
    </div>

    <!-- Search the graph -->
    <form class="kg-search" @submit.prevent="search">
      <input
        v-model="q"
        class="kg-search__input"
        type="search"
        :placeholder="t('knowledgeGraph.searchPlaceholder')"
      />
      <input v-model.number="topK" class="kg-search__topk" type="number" min="1" max="50" />
      <button class="kg-search__btn" type="submit" :disabled="searching || !q.trim()">
        {{ searching ? t('knowledgeGraph.searching') : t('knowledgeGraph.search') }}
      </button>
    </form>

    <div v-if="searchError" class="kg-state kg-state--error">{{ searchError }}</div>
    <template v-else-if="searched && !searching">
      <div v-if="hits.length === 0" class="kg-state">{{ t('knowledgeGraph.noHits') }}</div>
      <ul v-else class="kg-hits">
        <li v-for="(h, i) in hits" :key="`${h.node_id}-${i}`" class="kg-hit">
          <div class="kg-hit__head">
            <span class="kg-hit__title">{{ h.title }}</span>
            <span class="kg-hit__kind">{{ h.kind }}</span>
            <span class="kg-hit__score">{{ h.score.toFixed(2) }}</span>
          </div>
          <div class="kg-hit__bar"><span :style="{ width: scorePct(h.score) + '%' }" /></div>
          <div v-if="h.excerpt" class="kg-hit__excerpt">{{ h.excerpt }}</div>
          <div class="kg-hit__meta">
            <span v-if="h.node_id" class="kg-hit__node">{{ h.node_id }}</span>
            <a
              v-if="h.arxiv_id"
              class="kg-hit__arxiv"
              :href="`https://arxiv.org/abs/${h.arxiv_id}`"
              target="_blank"
              rel="noopener noreferrer"
            >arXiv:{{ h.arxiv_id }}</a>
          </div>
        </li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.kg-page {
  padding: 24px;
  max-width: 920px;
}
.kg-state {
  padding: 32px;
  text-align: center;
  color: var(--text-secondary, #a1a1aa);
}
.kg-state--error {
  color: #ef4444;
}
.kg-overview {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin: 16px 0 24px;
}
.kg-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 12px 18px;
  background: var(--bg-tertiary, #1a1a24);
  border-radius: 10px;
  min-width: 96px;
}
.kg-stat--wide {
  min-width: 180px;
}
.kg-stat__val {
  font-size: 22px;
  font-weight: 600;
  color: var(--text-primary, #e4e4e7);
  font-family: var(--font-mono, monospace);
}
.kg-stat__val--sm {
  font-size: 14px;
}
.kg-stat__label {
  font-size: 11px;
  color: var(--text-secondary, #71717a);
  text-transform: uppercase;
  letter-spacing: 0.4px;
}
.kg-corrupt {
  font-size: 12px;
  font-weight: 600;
  color: #f87171;
  padding: 4px 10px;
  border-radius: 100px;
  background: rgba(239, 68, 68, 0.15);
}
.kg-search {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
}
.kg-search__input {
  flex: 1;
  padding: 9px 14px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 8px;
  background: var(--bg-secondary, #12121a);
  color: var(--text-primary, #e4e4e7);
  font-size: 14px;
}
.kg-search__topk {
  width: 64px;
  padding: 9px 10px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 8px;
  background: var(--bg-secondary, #12121a);
  color: var(--text-primary, #e4e4e7);
  font-size: 14px;
}
.kg-search__btn {
  padding: 9px 18px;
  border: 1px solid rgba(79, 70, 229, 0.5);
  border-radius: 8px;
  background: rgba(79, 70, 229, 0.15);
  color: #a5b4fc;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}
.kg-search__btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.kg-hits {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.kg-hit {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  padding: 12px 14px;
}
.kg-hit__head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.kg-hit__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #e4e4e7);
  flex: 1;
}
.kg-hit__kind {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 100px;
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-secondary, #a1a1aa);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.kg-hit__score {
  font-size: 12px;
  color: var(--text-secondary, #71717a);
  font-family: var(--font-mono, monospace);
}
.kg-hit__bar {
  height: 3px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 2px;
  margin: 8px 0;
  overflow: hidden;
}
.kg-hit__bar span {
  display: block;
  height: 100%;
  background: #6366f1;
}
.kg-hit__excerpt {
  font-size: 13px;
  color: var(--text-secondary, #a1a1aa);
  margin-top: 4px;
}
.kg-hit__meta {
  display: flex;
  gap: 12px;
  margin-top: 6px;
}
.kg-hit__node {
  font-size: 11px;
  color: var(--text-secondary, #71717a);
  font-family: var(--font-mono, monospace);
}
.kg-hit__arxiv {
  font-size: 11px;
  color: #a5b4fc;
  text-decoration: none;
}
</style>
