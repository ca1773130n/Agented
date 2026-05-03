<script setup lang="ts">
import { ref, watch, onMounted } from 'vue';
import { agentMemoryApi, type MemoryThread } from '../../services/api/agentMemory';

const props = defineProps<{ agentId: string }>();

const threads = ref<MemoryThread[]>([]);
const total = ref(0);
const loading = ref(false);
const error = ref<string | null>(null);

const limit = 50;
const offset = ref(0);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const resp = await agentMemoryApi.listThreads(props.agentId, {
      limit,
      offset: offset.value,
    });
    threads.value = resp.threads;
    total.value = resp.total;
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to load threads';
  } finally {
    loading.value = false;
  }
}

async function refresh() {
  await load();
}

function nextPage() { offset.value += limit; void load(); }
function prevPage() { offset.value = Math.max(0, offset.value - limit); void load(); }

watch(() => props.agentId, () => { offset.value = 0; void load(); });
onMounted(() => { void load(); });

defineExpose({ refresh });
</script>

<template>
  <div class="thread-list">
    <div v-if="loading" class="state state-loading" data-testid="thread-list-loading">
      Loading threads…
    </div>
    <div v-else-if="error" class="state state-error" data-testid="thread-list-error">
      {{ error }}
      <button @click="load" class="retry-btn">Retry</button>
    </div>
    <div v-else-if="threads.length === 0" class="state state-empty" data-testid="thread-list-empty">
      No threads yet.
    </div>
    <ul v-else class="thread-rows">
      <li
        v-for="thread in threads"
        :key="thread.id"
        class="thread-row"
        data-testid="thread-row"
      >
        <RouterLink
          :to="{ name: 'agent-memory-thread-detail', params: { id: agentId, thread_id: thread.id } }"
          class="thread-link"
        >
          <span class="thread-title">{{ thread.title || '(untitled)' }}</span>
          <span class="thread-resource">{{ thread.resource_type }}:{{ thread.resource_id }}</span>
          <span class="thread-updated">{{ thread.updated_at }}</span>
        </RouterLink>
      </li>
    </ul>
    <footer v-if="!loading && total > limit" class="pagination">
      <button :disabled="offset === 0" @click="prevPage">Previous</button>
      <span>{{ offset + 1 }}–{{ Math.min(offset + limit, total) }} of {{ total }}</span>
      <button :disabled="offset + limit >= total" @click="nextPage">Next</button>
    </footer>
  </div>
</template>

<style scoped>
.thread-list { background: var(--bg-secondary); border-radius: 8px; overflow: hidden; }
.state { padding: 32px; text-align: center; color: var(--text-tertiary); font-style: italic; }
.state-error { color: var(--accent-red); }
.retry-btn { margin-left: 8px; padding: 4px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-subtle); border-radius: 4px; color: var(--text-primary); cursor: pointer; }
.thread-rows { list-style: none; padding: 0; margin: 0; }
.thread-row { border-bottom: 1px solid var(--border-subtle); }
.thread-row:last-child { border-bottom: none; }
.thread-link { display: flex; gap: 16px; padding: 12px 16px; text-decoration: none; color: inherit; }
.thread-link:hover { background: var(--bg-tertiary); }
.thread-title { flex: 1; font-weight: 600; }
.thread-resource { color: var(--text-tertiary); font-size: 12px; }
.thread-updated { color: var(--text-tertiary); font-size: 11px; }
.pagination { display: flex; justify-content: center; align-items: center; gap: 16px; padding: 16px; color: var(--text-tertiary); font-size: 13px; }
.pagination button { padding: 4px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-subtle); border-radius: 4px; color: var(--text-primary); cursor: pointer; }
.pagination button:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
