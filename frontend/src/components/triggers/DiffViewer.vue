<script setup lang="ts">
import { ref, computed } from 'vue';
import type { OutputDiff } from '../../services/api';

const props = defineProps<{
  diffData: OutputDiff;
}>();

const LINES_PER_PAGE = 200;
const visibleCount = ref(LINES_PER_PAGE);

const totalLines = computed(() => props.diffData.diff_lines.length);
const isLargeDiff = computed(() => totalLines.value > 500);
const visibleLines = computed(() => {
  if (!isLargeDiff.value) return props.diffData.diff_lines;
  return props.diffData.diff_lines.slice(0, visibleCount.value);
});
const hasMore = computed(() => visibleCount.value < totalLines.value);
const isEmpty = computed(() => totalLines.value === 0);

function showMore() {
  visibleCount.value = Math.min(visibleCount.value + LINES_PER_PAGE, totalLines.value);
}

function lineClass(type: string): string {
  if (type === 'added') return 'line-added';
  if (type === 'removed') return 'line-removed';
  return 'line-unchanged';
}
</script>

<template>
  <div class="diff-viewer">
    <!-- Change Summary Header -->
    <div class="diff-summary">
      <span class="summary-stat added">+{{ diffData.change_summary.added }}</span>
      <span class="summary-stat removed">-{{ diffData.change_summary.removed }}</span>
      <span class="summary-stat unchanged">~{{ diffData.change_summary.unchanged }}</span>
      <span class="summary-info">
        Original: {{ diffData.original_line_count }} lines |
        Replay: {{ diffData.replay_line_count }} lines
      </span>
    </div>

    <!-- Empty State -->
    <div v-if="isEmpty" class="diff-empty">
      <p>Outputs are identical</p>
      <p class="diff-empty-sub">No differences found between original and replay outputs.</p>
    </div>

    <!-- Diff Content -->
    <div v-else class="diff-content">
      <div class="diff-lines">
        <div
          v-for="line in visibleLines"
          :key="line.line_number"
          class="diff-line"
          :class="lineClass(line.type)"
        >
          <span class="line-gutter">{{ line.line_number }}</span>
          <span class="line-marker">
            <template v-if="line.type === 'added'">+</template>
            <template v-else-if="line.type === 'removed'">-</template>
            <template v-else>&nbsp;</template>
          </span>
          <span class="line-content">{{ line.content }}</span>
        </div>
      </div>

      <!-- Show More Button -->
      <div v-if="isLargeDiff && hasMore" class="show-more">
        <button class="show-more-btn" @click="showMore">
          Show more ({{ visibleCount }} / {{ totalLines }} lines)
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.diff-viewer {
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg-primary);
}

.diff-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-subtle);
  font-size: 0.8rem;
}

.summary-stat {
  font-family: var(--font-mono);
  font-weight: 600;
  font-size: 0.8rem;
  padding: 2px 8px;
  border-radius: 4px;
}

.summary-stat.added {
  color: var(--accent-emerald);
  background: rgba(16, 185, 129, 0.12);
}

.summary-stat.removed {
  color: var(--accent-crimson);
  background: rgba(239, 68, 68, 0.12);
}

.summary-stat.unchanged {
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
}

.summary-info {
  margin-left: auto;
  color: var(--text-muted);
  font-size: 0.75rem;
}

.diff-empty {
  padding: 40px 24px;
  text-align: center;
}

.diff-empty p {
  color: var(--text-secondary);
  font-size: 0.95rem;
  margin: 0;
}

.diff-empty-sub {
  color: var(--text-muted) !important;
  font-size: 0.8rem !important;
  margin-top: 6px !important;
}

.diff-content {
  overflow-x: auto;
}

.diff-lines {
  font-family: var(--font-mono);
  font-size: 0.8rem;
  line-height: 1.6;
}

.diff-line {
  display: flex;
  min-height: 24px;
  border-bottom: 1px solid transparent;
}

.diff-line.line-added {
  background: rgba(16, 185, 129, 0.08);
}

.diff-line.line-removed {
  background: rgba(239, 68, 68, 0.08);
}

.diff-line.line-unchanged {
  background: transparent;
}

.diff-line:hover {
  background: var(--bg-tertiary);
}

.line-gutter {
  flex-shrink: 0;
  width: 50px;
  text-align: right;
  padding: 0 8px;
  color: var(--text-muted);
  user-select: none;
  border-right: 1px solid var(--border-subtle);
}

.line-marker {
  flex-shrink: 0;
  width: 20px;
  text-align: center;
  color: var(--text-muted);
  user-select: none;
}

.line-added .line-marker {
  color: var(--accent-emerald);
  font-weight: 700;
}

.line-removed .line-marker {
  color: var(--accent-crimson);
  font-weight: 700;
}

.line-content {
  flex: 1;
  padding: 0 8px;
  white-space: pre;
  color: var(--text-secondary);
}

.line-added .line-content {
  color: var(--accent-emerald);
}

.line-removed .line-content {
  color: var(--accent-crimson);
}

.show-more {
  padding: 12px;
  text-align: center;
  border-top: 1px solid var(--border-subtle);
}

.show-more-btn {
  padding: 8px 20px;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.15s ease;
}

.show-more-btn:hover {
  background: var(--bg-tertiary);
  color: var(--accent-cyan);
  border-color: var(--accent-cyan);
}
</style>
