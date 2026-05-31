<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { renderMarkdown } from '../../composables/useMarkdown';

const props = withDefaults(
  defineProps<{
    content: string | null;
    loading?: boolean;
    error?: string | null;
  }>(),
  {
    loading: false,
    error: null,
  },
);

const { t } = useI18n();

const renderedHtml = computed(() => {
  if (!props.content) return '';
  return renderMarkdown(props.content);
});
</script>

<template>
  <div class="working-memory-view">
    <div v-if="loading" class="state state-loading" data-testid="working-memory-loading">
      {{ t('workingMemory.loading') }}
    </div>
    <div v-else-if="error" class="state state-error" data-testid="working-memory-error">
      {{ error }}
    </div>
    <div v-else-if="!content" class="state state-empty" data-testid="working-memory-empty">
      {{ t('workingMemory.empty') }}
    </div>
    <div
      v-else
      class="working-memory-body markdown-body"
      data-testid="working-memory-body"
      v-html="renderedHtml"
    />
  </div>
</template>

<style scoped>
.working-memory-view { padding: 16px; background: var(--bg-secondary); border-radius: 8px; }
.state { color: var(--text-tertiary); font-style: italic; padding: 16px 0; text-align: center; }
.state-error { color: var(--accent-red); }
.working-memory-body { font-size: 14px; line-height: 1.6; color: var(--text-primary); }
.working-memory-body :deep(h1), .working-memory-body :deep(h2), .working-memory-body :deep(h3) { margin: 12px 0 6px; }
.working-memory-body :deep(ul) { margin: 4px 0; padding-left: 24px; }
.working-memory-body :deep(code) { background: var(--bg-tertiary); padding: 1px 4px; border-radius: 3px; }
.working-memory-body :deep(pre) { background: var(--bg-tertiary); padding: 8px; border-radius: 4px; overflow-x: auto; }
</style>
