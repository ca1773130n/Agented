<script setup lang="ts">
/**
 * Render trusted markdown content with dark-theme styles.
 *
 * Use this component anywhere a message body, conversation log entry,
 * or AI response needs to render markdown — replaces ad-hoc
 * ``<div>{{ content }}</div>`` blocks that leak literal ``## Summary``
 * to the user. Mirrors the visual rules in vue-styled's ChatBubble
 * so live chat and historical viewers look consistent.
 *
 * Security: the parsed output is DOMPurify-sanitized before it reaches
 * ``v-html``. Callers pass agent/session/trigger-authored content that is
 * NOT trusted (autonomous agents, remote triggers), so sanitization is
 * mandatory here — ``marked`` passes raw inline HTML through by default.
 */
import { computed } from 'vue';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

const props = withDefaults(
  defineProps<{
    /** Markdown source. Empty / null renders empty. */
    content: string | null | undefined;
    /**
     * When ``true``, allow line breaks inside paragraphs without an
     * intervening blank line. Useful for chat where users type
     * single-line messages and expect Enter to break the line.
     */
    breaks?: boolean;
  }>(),
  { breaks: false },
);

const html = computed(() => {
  const src = props.content || '';
  const raw = (props.breaks
    ? marked.parse(src, { breaks: true })
    : marked.parse(src)) as string;
  // DOMPurify with defaults: keeps all markdown-generated tags, drops
  // scripts/event-handlers/javascript: URLs. ADD_ATTR keeps link target/rel.
  return DOMPurify.sanitize(raw, { ADD_ATTR: ['target', 'rel'] });
});
</script>

<template>
  <div class="md-content" v-html="html" />
</template>

<style scoped>
.md-content {
  font-size: 13px;
  line-height: 1.55;
  color: var(--text-primary);
  word-break: break-word;
}
.md-content :deep(p) { margin: 0.25rem 0; }
.md-content :deep(ul),
.md-content :deep(ol) { padding-inline-start: 1.5rem; margin: 0.25rem 0; }
.md-content :deep(li) { margin: 0.125rem 0; }
.md-content :deep(li > ul),
.md-content :deep(li > ol) { margin: 0.125rem 0; }
.md-content :deep(pre) {
  background: var(--bg-tertiary, #0a0a0a);
  border-radius: 6px;
  padding: 0.6rem 0.75rem;
  overflow-x: auto;
  margin: 0.5rem 0;
  font-size: 12px;
}
.md-content :deep(code) {
  font-family: var(--font-mono, ui-monospace, monospace);
}
.md-content :deep(:not(pre) > code) {
  background: var(--bg-tertiary, #0a0a0a);
  padding: 0.05rem 0.3rem;
  border-radius: 4px;
}
.md-content :deep(h1),
.md-content :deep(h2),
.md-content :deep(h3),
.md-content :deep(h4),
.md-content :deep(h5),
.md-content :deep(h6) {
  font-weight: 700;
  line-height: 1.25;
  margin: 0.75rem 0 0.35rem;
  color: var(--text-primary);
}
.md-content :deep(h1):first-child,
.md-content :deep(h2):first-child,
.md-content :deep(h3):first-child { margin-top: 0; }
.md-content :deep(h1) { font-size: 1.3rem; }
.md-content :deep(h2) { font-size: 1.1rem; }
.md-content :deep(h3) { font-size: 1.0rem; }
.md-content :deep(h4) {
  font-size: 0.9rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-secondary);
}
.md-content :deep(h5),
.md-content :deep(h6) { font-size: 0.85rem; color: var(--text-secondary); }
.md-content :deep(blockquote) {
  border-left: 3px solid var(--border-strong, #3f3f46);
  padding: 0.15rem 0.6rem;
  margin: 0.4rem 0;
  color: var(--text-secondary);
}
.md-content :deep(table) {
  border-collapse: collapse;
  margin: 0.5rem 0;
  font-size: 0.85rem;
}
.md-content :deep(th),
.md-content :deep(td) {
  border: 1px solid var(--border-default);
  padding: 0.3rem 0.55rem;
  text-align: left;
}
.md-content :deep(th) {
  background: var(--bg-tertiary);
  font-weight: 600;
}
.md-content :deep(hr) {
  border: 0;
  border-top: 1px solid var(--border-default);
  margin: 0.6rem 0;
}
.md-content :deep(a) {
  color: var(--accent-cyan, #60a5fa);
  text-decoration: underline;
}
.md-content :deep(a:hover) { text-decoration: none; }
.md-content :deep(strong) { color: var(--text-primary); }
.md-content :deep(em) { font-style: italic; }
</style>
