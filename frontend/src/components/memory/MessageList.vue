<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { ChatBubble } from '@ai-accounts/vue-styled';
import type { MemoryMessage } from '../../services/api/agentMemory';

defineProps<{ messages: MemoryMessage[] }>();

const { t } = useI18n();
</script>

<template>
  <div class="message-list">
    <div v-if="messages.length === 0" class="state state-empty" data-testid="message-list-empty">
      {{ t('messageList.empty') }}
    </div>
    <div v-else class="message-rows">
      <div
        v-for="msg in messages"
        :key="msg.id"
        class="message-row"
        data-testid="message-row"
      >
        <ChatBubble
          :role="(msg.role as 'user' | 'assistant' | 'system' | 'tool')"
          :content="msg.content"
          :timestamp="msg.created_at"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.message-list { padding: 16px; }
.state { padding: 32px; text-align: center; color: var(--text-tertiary); font-style: italic; }
.message-rows { display: flex; flex-direction: column; gap: 8px; }
.message-row { /* ChatBubble brings its own styles */ }
</style>
