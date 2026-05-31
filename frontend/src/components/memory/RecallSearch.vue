<script setup lang="ts">
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { agentMemoryApi, type MemoryMessage } from '../../services/api/agentMemory';

const props = defineProps<{ agentId: string }>();

const { t } = useI18n();

const query = ref('');
const topK = ref<number>(5);
const results = ref<MemoryMessage[]>([]);
const hasSearched = ref(false);
const loading = ref(false);
const error = ref<string | null>(null);

async function onSubmit() {
  const q = query.value.trim();
  if (!q) return;
  loading.value = true;
  error.value = null;
  hasSearched.value = true;
  try {
    const resp = await agentMemoryApi.recall(props.agentId, q, topK.value);
    results.value = resp.results;
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('recallSearch.recallFailed');
  } finally {
    loading.value = false;
  }
}

function truncate(s: string, n: number = 200): string {
  return s.length > n ? s.slice(0, n) + '…' : s;
}
</script>

<template>
  <div class="recall-search">
    <form @submit.prevent="onSubmit">
      <input
        v-model="query"
        type="search"
        :placeholder="t('recallSearch.placeholder')"
        data-testid="recall-input"
        class="recall-input"
      />
      <select v-model.number="topK" data-testid="recall-topk" class="recall-topk">
        <option :value="5">5</option>
        <option :value="10">10</option>
        <option :value="20">20</option>
      </select>
      <button type="submit" :disabled="!query.trim() || loading" class="recall-submit">
        {{ loading ? t('recallSearch.searching') : t('common.search') }}
      </button>
    </form>

    <div v-if="loading" class="state state-loading" data-testid="recall-loading">
      {{ t('recallSearch.searching') }}
    </div>
    <div v-else-if="error" class="state state-error" data-testid="recall-error">
      {{ error }}
    </div>
    <div v-else-if="!hasSearched" class="state state-empty" data-testid="recall-empty">
      {{ t('recallSearch.prompt') }}
    </div>
    <div v-else-if="results.length === 0" class="state state-empty" data-testid="recall-no-matches">
      {{ t('recallSearch.noMatches') }}
    </div>
    <ul v-else class="recall-results">
      <li
        v-for="msg in results"
        :key="msg.id"
        class="recall-result"
        data-testid="recall-result"
      >
        <div class="result-meta">
          <span class="result-role" :class="`role-${msg.role}`">{{ msg.role }}</span>
          <span class="result-time">{{ msg.created_at }}</span>
        </div>
        <div class="result-content">{{ truncate(msg.content) }}</div>
        <RouterLink
          :to="{ name: 'agent-memory-thread-detail', params: { id: agentId, thread_id: msg.thread_id } }"
          class="result-link"
          data-testid="recall-result-link"
        >
          {{ t('recallSearch.viewThread') }} →
        </RouterLink>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.recall-search { padding: 16px; background: var(--bg-secondary); border-radius: 8px; }
form { display: flex; gap: 8px; margin-bottom: 12px; }
.recall-input { flex: 1; padding: 6px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-subtle); color: var(--text-primary); border-radius: 4px; }
.recall-topk { padding: 6px 8px; background: var(--bg-tertiary); border: 1px solid var(--border-subtle); color: var(--text-primary); border-radius: 4px; }
.recall-submit { padding: 6px 16px; background: var(--accent-cyan, #60a5fa); color: var(--bg-primary, #0a0a0a); border: none; border-radius: 4px; cursor: pointer; }
.recall-submit:disabled { opacity: 0.5; cursor: not-allowed; }
.state { color: var(--text-tertiary); padding: 16px 0; text-align: center; font-style: italic; }
.state-error { color: var(--accent-red); }
.recall-results { list-style: none; padding: 0; margin: 0; }
.recall-result { padding: 12px 0; border-bottom: 1px solid var(--border-subtle); }
.recall-result:last-child { border-bottom: none; }
.result-meta { display: flex; gap: 8px; align-items: center; font-size: 11px; margin-bottom: 4px; }
.result-role { padding: 1px 6px; border-radius: 3px; font-weight: 600; }
.role-user { background: rgba(96, 165, 250, 0.15); color: var(--accent-cyan); }
.role-assistant { background: rgba(124, 58, 237, 0.15); color: var(--accent-violet); }
.role-system { background: rgba(113, 113, 122, 0.15); color: var(--text-tertiary); }
.role-tool { background: rgba(16, 185, 129, 0.15); color: var(--accent-green); }
.result-time { color: var(--text-tertiary); }
.result-content { font-size: 13px; line-height: 1.5; color: var(--text-primary); margin-bottom: 4px; }
.result-link { font-size: 11px; color: var(--accent-cyan); text-decoration: none; }
.result-link:hover { text-decoration: underline; }
</style>
