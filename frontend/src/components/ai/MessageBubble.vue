<script setup lang="ts">
/**
 * MessageBubble renders an individual chat message with avatar,
 * header (role name + timestamp), and formatted content.
 * Supports a 350ms fade-in transition for new messages,
 * which can be skipped during mass render (historical messages).
 */
import { ref, onMounted, onUpdated } from 'vue';
import { renderMarkdown, attachCodeCopyHandlers } from '../../composables/useMarkdown';

const bubbleEl = ref<HTMLElement | null>(null);

function wireUpCopyButtons() {
  if (bubbleEl.value) {
    attachCodeCopyHandlers(bubbleEl.value);
  }
}

onMounted(wireUpCopyButtons);
onUpdated(wireUpCopyButtons);

withDefaults(
  defineProps<{
    role: string;
    content: string;
    timestamp: string;
    avatarPaths: string[];
    skipTransition: boolean;
    assistantName: string;
  }>(),
  {
    skipTransition: false,
    assistantName: 'AI',
  },
);
</script>

<template>
  <div ref="bubbleEl" :class="['message-bubble', role, { 'fade-in': !skipTransition }]">
    <div class="bubble-avatar">
      <svg v-if="role === 'user'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/>
        <circle cx="12" cy="7" r="4"/>
      </svg>
      <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path v-for="(d, i) in avatarPaths" :key="i" :d="d"/>
      </svg>
    </div>
    <div class="bubble-content">
      <div class="bubble-header">
        <span class="bubble-role">{{ role === 'user' ? 'You' : assistantName }}</span>
        <span class="bubble-time">{{ new Date(timestamp).toLocaleTimeString() }}</span>
      </div>
      <div class="bubble-text markdown-body markdown-rendered" v-html="renderMarkdown(content)"></div>
    </div>
  </div>
</template>

<style scoped>
.message-bubble {
  display: flex;
  gap: 12px;
  max-width: 85%;
}

.message-bubble.user {
  flex-direction: row-reverse;
  align-self: flex-end;
}

.message-bubble.assistant {
  align-self: flex-start;
}

/* Fade-in animation: 350ms opacity 0->1 + translateY(8px)->0 */
.message-bubble.fade-in {
  animation: bubbleFadeIn 350ms ease-out both;
}

@keyframes bubbleFadeIn {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Avatar */
.bubble-avatar {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.message-bubble.user .bubble-avatar {
  background: var(--accent-cyan-dim);
}

.message-bubble.user .bubble-avatar svg {
  color: var(--accent-cyan);
}

.message-bubble.assistant .bubble-avatar {
  background: var(--accent-violet-dim, rgba(136, 85, 255, 0.15));
}

.message-bubble.assistant .bubble-avatar svg {
  color: var(--accent-violet, #8855ff);
}

.bubble-avatar svg {
  width: 20px;
  height: 20px;
}

/* Content */
.bubble-content {
  background: var(--bg-tertiary);
  border-radius: 12px;
  padding: 12px 16px;
  min-width: 100px;
}

.message-bubble.user .bubble-content {
  background: var(--accent-cyan-dim);
}

.bubble-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.bubble-role {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.bubble-time {
  font-size: 11px;
  color: var(--text-tertiary);
}

/* Text content */
.bubble-text {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-secondary);
  word-wrap: break-word;
  overflow-wrap: break-word;
}

</style>
