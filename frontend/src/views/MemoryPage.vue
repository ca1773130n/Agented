<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { agentMemoryApi } from '../services/api/agentMemory';
import { useFocusRefresh } from '../composables/useFocusRefresh';
import WorkingMemoryView from '../components/memory/WorkingMemoryView.vue';
import RecallSearch from '../components/memory/RecallSearch.vue';
import ThreadList from '../components/memory/ThreadList.vue';

const route = useRoute();
const agentId = computed(() => route.params.id as string);

// Working memory state
const wmContent = ref<string | null>(null);
const wmLoading = ref(false);
const wmError = ref<string | null>(null);

// Threads list ref — exposes refresh()
const threadListRef = ref<{ refresh: () => Promise<void> } | null>(null);

async function loadWorkingMemory() {
  wmLoading.value = true;
  wmError.value = null;
  try {
    const wm = await agentMemoryApi.getWorkingMemory(agentId.value);
    wmContent.value = wm.content || null;
  } catch (e) {
    wmError.value = e instanceof Error ? e.message : 'Failed to load working memory';
  } finally {
    wmLoading.value = false;
  }
}

async function refreshAll() {
  await Promise.all([
    loadWorkingMemory(),
    threadListRef.value?.refresh() ?? Promise.resolve(),
  ]);
}

onMounted(() => {
  void loadWorkingMemory();
});

useFocusRefresh(refreshAll);
</script>

<template>
  <div class="memory-page">
    <header class="page-header">
      <h1>Agent Memory</h1>
      <div class="header-meta">
        <span class="agent-ref">agent:{{ agentId }}</span>
        <button
          type="button"
          class="refresh-btn"
          data-testid="refresh-btn"
          @click="refreshAll"
        >
          Refresh
        </button>
      </div>
    </header>

    <section class="region" data-testid="memory-region-working">
      <h2>Working Memory</h2>
      <WorkingMemoryView
        :content="wmContent"
        :loading="wmLoading"
        :error="wmError"
      />
    </section>

    <section class="region" data-testid="memory-region-recall">
      <h2>Recall</h2>
      <RecallSearch :agent-id="agentId" />
    </section>

    <section class="region" data-testid="memory-region-threads">
      <h2>Threads</h2>
      <ThreadList ref="threadListRef" :agent-id="agentId" />
    </section>
  </div>
</template>

<style scoped>
.memory-page { padding: 24px; max-width: 1100px; margin: 0 auto; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.page-header h1 { margin: 0; }
.header-meta { display: flex; gap: 16px; align-items: center; }
.agent-ref { font-family: var(--font-mono, monospace); font-size: 13px; color: var(--text-tertiary); }
.refresh-btn { padding: 6px 16px; background: var(--bg-tertiary); border: 1px solid var(--border-subtle); border-radius: 4px; color: var(--text-primary); cursor: pointer; }
.refresh-btn:hover { background: var(--bg-secondary); }
.region { margin-bottom: 24px; }
.region h2 { font-size: 16px; margin: 0 0 8px; color: var(--text-secondary); }
</style>
