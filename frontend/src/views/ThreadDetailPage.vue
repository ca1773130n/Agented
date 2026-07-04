<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute } from 'vue-router';
import {
  agentMemoryApi,
  type MemoryThread,
  type MemoryMessage,
} from '../services/api/agentMemory';
import { useFocusRefresh } from '../composables/useFocusRefresh';
import MessageList from '../components/memory/MessageList.vue';

const { t } = useI18n();
const route = useRoute();
const agentId = computed(() => route.params.id as string);
const threadId = computed(() => route.params.thread_id as string);

const thread = ref<MemoryThread | null>(null);
const messages = ref<MemoryMessage[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const [threadData, m] = await Promise.all([
      agentMemoryApi.getThread(agentId.value, threadId.value),
      agentMemoryApi.getMessages(agentId.value, threadId.value),
    ]);
    thread.value = threadData;
    messages.value = m.messages;
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('threadDetail.loadFailed');
  } finally {
    loading.value = false;
  }
}

async function refreshMessages() {
  if (!threadId.value) return;
  try {
    const m = await agentMemoryApi.getMessages(agentId.value, threadId.value);
    messages.value = m.messages;
  } catch {
    // silent — keep existing messages on transient refresh failure
  }
}

onMounted(() => { void load(); });
watch([agentId, threadId], () => { void load(); });

useFocusRefresh(refreshMessages);
</script>

<template>
  <div class="thread-detail-page">
    <RouterLink
      :to="{ name: 'agent-memory', params: { id: agentId } }"
      class="back-link"
    >
      {{ t('threadDetail.backToMemory') }}
    </RouterLink>

    <div v-if="loading" class="state state-loading" data-testid="thread-detail-loading">
      {{ t('threadDetail.loading') }}
    </div>
    <div
      v-else-if="error"
      class="state state-error"
      data-testid="thread-detail-error"
    >
      {{ error }}
      <button @click="load" class="retry-btn">{{ t('common.retry') }}</button>
    </div>
    <template v-else-if="thread">
      <header class="thread-header">
        <h1>{{ thread.title || t('threadDetail.untitled') }}</h1>
        <div class="thread-meta">
          <span>{{ thread.resource_type }}:{{ thread.resource_id }}</span>
          <span>{{ t('threadDetail.created', { date: thread.created_at }) }}</span>
          <span>{{ t('threadDetail.messagesCount', { count: messages.length }) }}</span>
        </div>
      </header>
      <MessageList :messages="messages" />
    </template>
  </div>
</template>

<style scoped>
.thread-detail-page { }
.back-link { display: inline-block; margin-bottom: 16px; color: var(--accent-cyan); text-decoration: none; font-size: 13px; }
.back-link:hover { text-decoration: underline; }
.thread-header { margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border-subtle); }
.thread-header h1 { margin: 0 0 8px; }
.thread-meta { display: flex; gap: 16px; color: var(--text-tertiary); font-size: 13px; }
.state { padding: 48px; text-align: center; color: var(--text-tertiary); font-style: italic; }
.state-error { color: var(--accent-red); }
.retry-btn { margin-left: 8px; padding: 4px 12px; background: var(--bg-tertiary); border: 1px solid var(--border-subtle); border-radius: 4px; color: var(--text-primary); cursor: pointer; }
</style>
