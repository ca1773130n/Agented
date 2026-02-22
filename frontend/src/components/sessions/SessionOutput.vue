<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue';
import { useStreamingParser } from '../../composables/useStreamingParser';

const outputContainer = ref<HTMLElement | null>(null);
const isNearBottom = ref(true);
const SCROLL_THRESHOLD = 48;

let parser: ReturnType<typeof useStreamingParser> | null = null;

function initParser() {
  if (!outputContainer.value) return;
  parser = useStreamingParser({
    onFlush: () => {
      if (isNearBottom.value && outputContainer.value) {
        outputContainer.value.scrollTop = outputContainer.value.scrollHeight;
      }
    },
  });
  parser.init(outputContainer.value);
}

// Initialize parser when container appears
watch(outputContainer, (el) => {
  if (el) {
    initParser();
  }
});

function onScroll() {
  if (!outputContainer.value) return;
  const el = outputContainer.value;
  const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
  isNearBottom.value = distanceFromBottom <= SCROLL_THRESHOLD;
}

function scrollToBottom() {
  isNearBottom.value = true;
  if (outputContainer.value) {
    outputContainer.value.scrollTop = outputContainer.value.scrollHeight;
  }
}

// Exposed methods for parent component
function write(text: string) {
  parser?.write(text);
}

function finalize() {
  parser?.finalize();
}

function reset() {
  if (parser) {
    parser.destroy();
    parser = null;
  }
  initParser();
}

defineExpose({ write, finalize, reset });

onBeforeUnmount(() => {
  if (parser) {
    parser.destroy();
    parser = null;
  }
});
</script>

<template>
  <div class="session-output-wrapper">
    <div
      class="session-output"
      ref="outputContainer"
      @scroll="onScroll"
    ></div>
    <button
      v-if="!isNearBottom"
      class="scroll-bottom-btn"
      title="Scroll to bottom"
      @click="scrollToBottom"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="6 9 12 15 18 9" />
      </svg>
    </button>
  </div>
</template>

<style scoped>
.session-output-wrapper {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.session-output {
  flex: 1;
  background: var(--bg-primary);
  font-family: 'Geist Mono', monospace;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
  padding: 16px;
  overflow-y: auto;
  max-height: 60vh;
  word-wrap: break-word;
  overflow-wrap: break-word;
}

/* smd.js output styling for dark theme */
.session-output :deep(p) {
  margin: 4px 0;
}

.session-output :deep(p:first-child) {
  margin-top: 0;
}

.session-output :deep(strong) {
  color: var(--text-primary);
  font-weight: 600;
}

.session-output :deep(em) {
  font-style: italic;
}

.session-output :deep(a) {
  color: var(--accent-cyan);
  text-decoration: none;
}

.session-output :deep(a:hover) {
  text-decoration: underline;
}

.session-output :deep(code) {
  background: var(--bg-tertiary);
  padding: 2px 5px;
  border-radius: 3px;
  font-family: 'Geist Mono', monospace;
  font-size: 0.9em;
  color: var(--accent-cyan);
  border: 1px solid var(--border-default);
}

.session-output :deep(pre) {
  background: #0d1117;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  padding: 10px 12px;
  overflow-x: auto;
  margin: 8px 0;
}

.session-output :deep(pre code) {
  background: none;
  padding: 0;
  border: none;
  font-family: 'Geist Mono', monospace;
  font-size: 12.5px;
  line-height: 1.5;
  color: #e6edf3;
  tab-size: 2;
}

.session-output :deep(h1),
.session-output :deep(h2),
.session-output :deep(h3) {
  color: var(--text-primary);
  font-weight: 600;
  margin: 12px 0 4px 0;
  line-height: 1.3;
}

.session-output :deep(h1) { font-size: 1.2em; }
.session-output :deep(h2) { font-size: 1.1em; }
.session-output :deep(h3) { font-size: 1.05em; }

.session-output :deep(ul),
.session-output :deep(ol) {
  margin: 4px 0;
  padding-left: 1.5em;
}

.session-output :deep(li) {
  margin: 2px 0;
  line-height: 1.6;
}

.session-output :deep(blockquote) {
  border-left: 3px solid var(--accent-cyan);
  padding: 4px 12px;
  margin: 6px 0;
  color: var(--text-secondary);
  background: rgba(0, 212, 255, 0.04);
  border-radius: 0 4px 4px 0;
}

.session-output :deep(hr) {
  border: 0;
  border-top: 1px solid var(--border-default);
  margin: 8px 0;
}

.session-output :deep(table) {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.92em;
  margin: 8px 0;
  border: 1px solid var(--border-default);
  border-radius: 4px;
  overflow: hidden;
}

.session-output :deep(th) {
  padding: 6px 10px;
  text-align: left;
  font-weight: 600;
  color: var(--text-primary);
  background: rgba(255, 255, 255, 0.04);
  border-bottom: 1px solid var(--border-default);
}

.session-output :deep(td) {
  padding: 4px 10px;
  border-bottom: 1px solid var(--border-default);
}

/* Scroll to bottom floating button */
.scroll-bottom-btn {
  position: absolute;
  bottom: 12px;
  right: 16px;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  z-index: 10;
}

.scroll-bottom-btn:hover {
  background: var(--bg-tertiary);
  border-color: var(--accent-cyan);
}

.scroll-bottom-btn svg {
  width: 16px;
  height: 16px;
  color: var(--text-secondary);
}
</style>
