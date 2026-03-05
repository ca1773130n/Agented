<script setup lang="ts">
import { ref, computed } from 'vue';
import type { InlineComment } from '../../services/api';

const props = defineProps<{
  comments: InlineComment[];
  lineNumber: number;
}>();

const emit = defineEmits<{
  (e: 'addComment', lineNumber: number, content: string): void;
}>();

const isAdding = ref(false);
const newCommentText = ref('');
const isHovered = ref(false);

const lineComments = computed(() =>
  props.comments.filter(c => c.line_number === props.lineNumber)
);

function formatRelativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return 'just now';
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  return `${Math.floor(diffHr / 24)}d ago`;
}

function handleSubmit() {
  const text = newCommentText.value.trim();
  if (!text) return;
  emit('addComment', props.lineNumber, text);
  newCommentText.value = '';
  isAdding.value = false;
}

function handleKeyDown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    handleSubmit();
  }
  if (e.key === 'Escape') {
    isAdding.value = false;
    newCommentText.value = '';
  }
}

function startAdding() {
  isAdding.value = true;
}
</script>

<template>
  <div
    class="inline-comment-container"
    @mouseenter="isHovered = true"
    @mouseleave="isHovered = false"
  >
    <!-- Add comment trigger -->
    <button
      v-if="(isHovered || lineComments.length > 0) && !isAdding"
      class="add-comment-btn"
      :class="{ 'has-comments': lineComments.length > 0 }"
      @click="startAdding"
      title="Add comment"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
        <path d="M12 5v14M5 12h14"/>
      </svg>
      <span v-if="lineComments.length > 0" class="comment-count">{{ lineComments.length }}</span>
    </button>

    <!-- Existing comments -->
    <div v-if="lineComments.length > 0" class="comments-list">
      <div v-for="comment in lineComments" :key="comment.id" class="comment-bubble">
        <span class="comment-author">{{ comment.viewer_name }}</span>
        <span class="comment-text">{{ comment.content }}</span>
        <span class="comment-time">{{ formatRelativeTime(comment.created_at) }}</span>
      </div>
    </div>

    <!-- New comment input -->
    <div v-if="isAdding" class="comment-input-wrapper">
      <input
        v-model="newCommentText"
        type="text"
        class="comment-input"
        placeholder="Add a comment..."
        autofocus
        @keydown="handleKeyDown"
      />
      <button class="comment-submit" @click="handleSubmit" :disabled="!newCommentText.trim()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
          <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
        </svg>
      </button>
    </div>
  </div>
</template>

<style scoped>
.inline-comment-container {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 20px;
  position: relative;
}

.add-comment-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px;
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 0.7rem;
  transition: all 0.15s ease;
  width: fit-content;
}

.add-comment-btn:hover {
  background: var(--bg-elevated);
  color: var(--accent-cyan);
  border-color: var(--accent-cyan);
}

.add-comment-btn.has-comments {
  color: var(--accent-cyan);
  border-color: rgba(0, 212, 255, 0.3);
}

.comment-count {
  font-weight: 600;
  font-size: 0.65rem;
}

.comments-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-left: 4px;
}

.comment-bubble {
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding: 4px 8px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  border-left: 2px solid var(--accent-cyan);
  font-size: 0.75rem;
  animation: commentFadeIn 0.2s ease;
}

@keyframes commentFadeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

.comment-author {
  font-weight: 600;
  color: var(--accent-cyan);
  white-space: nowrap;
  flex-shrink: 0;
}

.comment-text {
  color: var(--text-secondary);
  word-break: break-word;
}

.comment-time {
  font-size: 0.65rem;
  color: var(--text-muted);
  white-space: nowrap;
  flex-shrink: 0;
}

.comment-input-wrapper {
  display: flex;
  align-items: center;
  gap: 4px;
}

.comment-input {
  flex: 1;
  padding: 4px 8px;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  color: var(--text-primary);
  font-size: 0.75rem;
  font-family: inherit;
  outline: none;
  transition: border-color 0.15s ease;
}

.comment-input:focus {
  border-color: var(--accent-cyan);
}

.comment-input::placeholder {
  color: var(--text-muted);
}

.comment-submit {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: 4px;
  color: var(--accent-cyan);
  cursor: pointer;
  transition: all 0.15s ease;
}

.comment-submit:hover:not(:disabled) {
  background: var(--accent-cyan-dim);
  border-color: var(--accent-cyan);
}

.comment-submit:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
