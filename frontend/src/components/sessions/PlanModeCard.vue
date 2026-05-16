<script setup lang="ts">
/**
 * Render claude's ``ExitPlanMode`` proposal (v0.7.65).
 *
 * Claude in plan mode writes out a markdown plan and calls
 * ``ExitPlanMode`` to ask whether to start executing. The TUI shows
 * the plan with two actions: "Yes, proceed" or "Keep planning". This
 * card mirrors that.
 *
 * Plan content is markdown — rendered through the same
 * ``marked + DOMPurify`` pipeline ChatBubble uses, so headings,
 * lists, and tool chips inside the plan all render identically to
 * regular assistant prose.
 */
import { computed } from 'vue';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

const props = defineProps<{
  plan: string;
}>();

const emit = defineEmits<{
  (e: 'approve'): void;
  (e: 'keepPlanning'): void;
}>();

const planHtml = computed(() =>
  DOMPurify.sanitize(marked.parse(props.plan || '') as string),
);
</script>

<template>
  <div class="pm-card">
    <div class="pm-card-header">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M9 11l3 3L22 4" />
        <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
      </svg>
      <span>Claude has a plan</span>
    </div>

    <div class="pm-plan-body" v-html="planHtml" />

    <div class="pm-actions">
      <button
        type="button"
        class="pm-btn pm-btn-secondary"
        @click="emit('keepPlanning')"
      >
        Keep planning
      </button>
      <button
        type="button"
        class="pm-btn pm-btn-primary"
        @click="emit('approve')"
      >
        Approve & execute
      </button>
    </div>
  </div>
</template>

<style scoped>
.pm-card {
  margin: 12px 0;
  border: 1px solid var(--accent-green, #4caf50);
  border-radius: 10px;
  background: linear-gradient(
    to bottom,
    rgba(76, 175, 80, 0.06),
    var(--bg-secondary)
  );
  overflow: hidden;
}

.pm-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: rgba(76, 175, 80, 0.1);
  border-bottom: 1px solid rgba(76, 175, 80, 0.2);
  font-size: 12px;
  font-weight: 600;
  color: var(--accent-green, #4caf50);
  letter-spacing: 0.02em;
}
.pm-card-header svg {
  width: 14px;
  height: 14px;
}

.pm-plan-body {
  padding: 14px 18px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-primary);
  background: var(--bg-primary);
  max-height: 480px;
  overflow-y: auto;
}

/* Apply the same chat-bubble heading scale to the plan markdown. */
:deep(.pm-plan-body h1),
.pm-plan-body :deep(h1) {
  font-size: 1.5em;
  margin: 12px 0 6px;
  font-weight: 600;
  border-bottom: 1px solid var(--border-default);
  padding-bottom: 0.15em;
}
.pm-plan-body :deep(h2) {
  font-size: 1.25em;
  margin: 10px 0 5px;
  font-weight: 600;
}
.pm-plan-body :deep(h3) {
  font-size: 1.1em;
  margin: 8px 0 4px;
  font-weight: 600;
}
.pm-plan-body :deep(ul),
.pm-plan-body :deep(ol) {
  margin: 6px 0;
  padding-left: 22px;
}
.pm-plan-body :deep(li) {
  margin: 3px 0;
}
.pm-plan-body :deep(code) {
  font-family: 'Geist Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.86em;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--bg-tertiary);
  color: var(--accent-purple, #b388ff);
  border: 1px solid rgba(179, 136, 255, 0.18);
}
.pm-plan-body :deep(pre) {
  margin: 10px 0;
  padding: 12px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  overflow-x: auto;
}
.pm-plan-body :deep(pre code) {
  background: transparent;
  border: 0;
  padding: 0;
  color: var(--text-primary);
}

.pm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--border-default);
  background: var(--bg-primary);
}
.pm-btn {
  padding: 7px 16px;
  border-radius: 6px;
  border: 1px solid var(--border-default);
  background: var(--bg-tertiary);
  color: var(--text-primary);
  font-family: inherit;
  font-size: 13px;
  cursor: pointer;
  transition: filter 0.12s, background 0.12s;
}
.pm-btn-primary {
  background: var(--accent-green, #4caf50);
  color: #001a08;
  border-color: var(--accent-green, #4caf50);
  font-weight: 600;
}
.pm-btn-primary:hover {
  filter: brightness(1.08);
}
.pm-btn-secondary:hover {
  background: var(--bg-secondary);
}
</style>
