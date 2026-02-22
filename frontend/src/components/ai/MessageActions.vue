<script setup lang="ts">
import { ref } from 'vue';
import type { ConversationMessage } from '../../services/api';

const props = defineProps<{
  content: string;
  allMessages?: ConversationMessage[];
}>();

const copyState = ref<'idle' | 'success' | 'error'>('idle');

async function copyToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      setCopyFeedback('success');
      return true;
    }
    // Textarea fallback for non-secure contexts
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    textarea.style.top = '-9999px';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(textarea);
    setCopyFeedback(ok ? 'success' : 'error');
    return ok;
  } catch {
    setCopyFeedback('error');
    return false;
  }
}

function setCopyFeedback(state: 'success' | 'error') {
  copyState.value = state;
  setTimeout(() => {
    copyState.value = 'idle';
  }, 1000);
}

function copyMessage() {
  copyToClipboard(props.content);
}

function formatConversation(msgs: ConversationMessage[]): string {
  return msgs
    .map(
      (msg) =>
        `[${msg.role}] ${new Date(msg.timestamp).toISOString()}\n${msg.content}`,
    )
    .join('\n\n---\n\n');
}

function copyAllConversation() {
  if (!props.allMessages || props.allMessages.length === 0) return;
  copyToClipboard(formatConversation(props.allMessages));
}

function exportConversation() {
  if (!props.allMessages || props.allMessages.length === 0) return;
  const text = formatConversation(props.allMessages);
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `conversation-${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.txt`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
</script>

<template>
  <div class="message-actions">
    <!-- Copy single message -->
    <button
      class="action-btn"
      :title="copyState === 'success' ? 'Copied!' : copyState === 'error' ? 'Copy failed' : 'Copy message'"
      @click.stop="copyMessage"
    >
      <!-- Checkmark icon (success) -->
      <svg v-if="copyState === 'success'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M20 6L9 17l-5-5"/>
      </svg>
      <!-- X icon (error) -->
      <svg v-else-if="copyState === 'error'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M18 6L6 18M6 6l12 12"/>
      </svg>
      <!-- Clipboard icon (idle) -->
      <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
        <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
      </svg>
    </button>

    <!-- Copy all conversation -->
    <button
      v-if="allMessages && allMessages.length > 0"
      class="action-btn"
      title="Copy conversation"
      @click.stop="copyAllConversation"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
        <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
        <line x1="14" y1="14" x2="18" y2="14"/>
        <line x1="14" y1="17" x2="18" y2="17"/>
      </svg>
    </button>

    <!-- Export conversation -->
    <button
      v-if="allMessages && allMessages.length > 0"
      class="action-btn"
      title="Export conversation"
      @click.stop="exportConversation"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
        <polyline points="7 10 12 15 17 10"/>
        <line x1="12" y1="15" x2="12" y2="3"/>
      </svg>
    </button>
  </div>
</template>

<style scoped>
.message-actions {
  position: absolute;
  top: -4px;
  right: 8px;
  display: flex;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.15s ease;
  pointer-events: none;
  z-index: 1;
}

.action-btn {
  width: 24px;
  height: 24px;
  padding: 4px;
  background: var(--bg-elevated, rgba(30, 30, 30, 0.95));
  border: 1px solid var(--border-default);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.15s;
  color: var(--text-secondary);
}

.action-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.action-btn svg {
  width: 14px;
  height: 14px;
}
</style>
