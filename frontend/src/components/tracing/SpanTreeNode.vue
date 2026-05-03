<script setup lang="ts">
import { ref } from 'vue';
import type { TraceSpan } from '../../services/api/tracing';

export interface SpanTreeChild {
  span: TraceSpan;
  children: SpanTreeChild[];
}

defineOptions({ name: 'SpanTreeNode' });

defineProps<{ span: TraceSpan; children: SpanTreeChild[] }>();

const expanded = ref(false);
function toggle() { expanded.value = !expanded.value; }
</script>

<template>
  <div class="span-tree-node">
    <div class="span-row">
      <button
        type="button"
        class="span-toggle"
        data-testid="span-toggle"
        @click="toggle"
      >{{ expanded ? '▼' : '▶' }}</button>
      <span class="span-name">{{ span.name }}</span>
      <span class="span-type" data-testid="span-type">{{ span.span_type }}</span>
      <span class="span-status" :class="`status-${span.status}`" data-testid="span-status">{{ span.status }}</span>
      <span v-if="span.duration_ms != null" class="span-duration">{{ span.duration_ms }}ms</span>
    </div>
    <div v-if="expanded" class="span-body" data-testid="span-body">
      <pre v-if="span.input">input: {{ JSON.stringify(span.input, null, 2) }}</pre>
      <pre v-if="span.output">output: {{ JSON.stringify(span.output, null, 2) }}</pre>
      <pre v-if="span.attributes">attributes: {{ JSON.stringify(span.attributes, null, 2) }}</pre>
      <pre v-if="span.error_message" class="span-error">error: {{ span.error_message }}</pre>
    </div>
    <div v-if="children.length > 0" class="span-children">
      <SpanTreeNode
        v-for="child in children"
        :key="child.span.id"
        :span="child.span"
        :children="child.children"
      />
    </div>
  </div>
</template>

<style scoped>
.span-tree-node { font-family: var(--font-mono, monospace); font-size: 13px; }
.span-row { display: flex; gap: 8px; align-items: center; padding: 4px 8px; }
.span-toggle { background: none; border: none; cursor: pointer; color: var(--text-tertiary); padding: 0 4px; }
.span-name { font-weight: 600; color: var(--text-primary); }
.span-type { font-size: 11px; padding: 1px 6px; border-radius: 4px; background: var(--bg-tertiary); color: var(--text-tertiary); }
.span-status { font-size: 11px; padding: 1px 6px; border-radius: 4px; }
.status-running { background: rgba(96, 165, 250, 0.15); color: var(--accent-cyan, #60a5fa); }
.status-completed { background: rgba(16, 185, 129, 0.15); color: var(--accent-green, #10b981); }
.status-error { background: rgba(239, 68, 68, 0.15); color: var(--accent-red, #ef4444); }
.span-duration { color: var(--text-tertiary); font-size: 11px; margin-left: auto; }
.span-body { padding: 4px 24px; }
.span-body pre { font-size: 11px; background: var(--bg-tertiary); padding: 8px; border-radius: 4px; white-space: pre-wrap; word-wrap: break-word; }
.span-body .span-error { color: var(--accent-red, #ef4444); }
.span-children { padding-left: 20px; border-left: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.08)); margin-left: 12px; }
</style>
