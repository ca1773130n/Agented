<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { tracingApi, type Trace, type TraceSpan } from '../services/api/tracing';
import { useTraceStream } from '../composables/useTraceStream';
import SpanTreeNode, { type SpanTreeChild } from '../components/tracing/SpanTreeNode.vue';

const route = useRoute();
const traceId = computed(() => route.params.id as string);

const trace = ref<Trace | null>(null);
const spans = ref<TraceSpan[]>([]);
const isLoading = ref(false);
const loadError = ref<string | null>(null);

const { events, start, stop } = useTraceStream(traceId);

async function load() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const result = await tracingApi.get(traceId.value);
    trace.value = result.trace;
    spans.value = result.spans;
    if (result.trace.status === 'running') {
      start();
    }
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : 'Failed to load trace';
  } finally {
    isLoading.value = false;
  }
}

// Patch the span tree as SSE events arrive.
watch(events, (next) => {
  for (const ev of next) {
    if (ev.kind === 'span_started') {
      // Append if not already present.
      if (!spans.value.find((s) => s.id === ev.span.id)) {
        spans.value = [...spans.value, ev.span];
      }
    } else if (ev.kind === 'span_ended') {
      spans.value = spans.value.map((s) => (s.id === ev.span.id ? ev.span : s));
    } else if (ev.kind === 'trace_ended') {
      if (trace.value && trace.value.id === ev.trace.id) {
        trace.value = ev.trace;
      }
    }
  }
}, { deep: true });

// Build the tree from parent_span_id.
const tree = computed<SpanTreeChild[]>(() => {
  const byParent = new Map<string | null, TraceSpan[]>();
  for (const s of spans.value) {
    const key = s.parent_span_id;
    if (!byParent.has(key)) byParent.set(key, []);
    byParent.get(key)!.push(s);
  }
  function build(parentId: string | null): SpanTreeChild[] {
    return (byParent.get(parentId) ?? []).map((span) => ({
      span,
      children: build(span.id),
    }));
  }
  return build(null);
});

onMounted(load);

watch(traceId, () => {
  stop();
  load();
});
</script>

<template>
  <div class="trace-detail-page">
    <div v-if="isLoading" data-testid="loading-state">Loading…</div>
    <div v-else-if="loadError" data-testid="error-state" class="error-state">
      {{ loadError }}
      <button @click="load">Retry</button>
    </div>
    <template v-else-if="trace">
      <header class="trace-header">
        <h1>{{ trace.name }}</h1>
        <div class="trace-meta">
          <span>{{ trace.entity_type }}:{{ trace.entity_id }}</span>
          <span class="status" :class="`status-${trace.status}`">{{ trace.status }}</span>
          <span>{{ trace.started_at }}</span>
          <span v-if="trace.duration_ms != null">{{ trace.duration_ms }}ms</span>
        </div>
        <pre v-if="trace.error_message" class="trace-error">{{ trace.error_message }}</pre>
        <pre v-if="trace.output">output: {{ JSON.stringify(trace.output, null, 2) }}</pre>
        <pre v-if="trace.attributes">attributes: {{ JSON.stringify(trace.attributes, null, 2) }}</pre>
      </header>
      <section class="span-tree">
        <SpanTreeNode
          v-for="root in tree"
          :key="root.span.id"
          :span="root.span"
          :children="root.children"
        />
        <div v-if="tree.length === 0" class="empty-tree">No spans yet.</div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.trace-detail-page { padding: 24px; }
.trace-header { margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border-subtle); }
.trace-header h1 { margin: 0 0 8px; }
.trace-meta { display: flex; gap: 16px; color: var(--text-tertiary); font-size: 13px; }
.status { padding: 2px 8px; border-radius: 4px; font-size: 11px; }
.status-running { background: rgba(96, 165, 250, 0.15); color: var(--accent-cyan); }
.status-completed { background: rgba(16, 185, 129, 0.15); color: var(--accent-green); }
.status-error { background: rgba(239, 68, 68, 0.15); color: var(--accent-red); }
.trace-error { color: var(--accent-red); background: var(--bg-tertiary); padding: 8px; border-radius: 4px; }
.trace-header pre { font-size: 11px; background: var(--bg-tertiary); padding: 8px; border-radius: 4px; }
.span-tree { padding: 16px; background: var(--bg-secondary); border-radius: 8px; }
.empty-tree { color: var(--text-tertiary); font-style: italic; padding: 16px; text-align: center; }
.error-state { padding: 48px; text-align: center; color: var(--accent-red); }
</style>
