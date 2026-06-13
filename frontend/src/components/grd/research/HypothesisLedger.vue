<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { renderMarkdown } from '../../../composables/useMarkdown';

const props = defineProps<{
  hypotheses?: string | null;
}>();

const { t } = useI18n();

const hasContent = computed(() => !!props.hypotheses && props.hypotheses.trim().length > 0);
const rendered = computed(() => (hasContent.value ? renderMarkdown(props.hypotheses as string) : ''));
</script>

<template>
  <section class="hypothesis-ledger">
    <h3 class="hl-title">{{ t('surface.research.ledger.title') }}</h3>
    <p v-if="!hasContent" class="hl-empty">{{ t('surface.research.ledger.empty') }}</p>
    <!-- renderMarkdown output is DOMPurify-sanitized (useMarkdown.ts) — the GREEN renderer, NOT MarkdownContent. -->
    <div v-else class="hl-body markdown-body" v-html="rendered" />
  </section>
</template>

<style scoped>
.hypothesis-ledger {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.hl-title {
  font-size: 0.95rem;
  margin: 0;
}
.hl-empty {
  font-size: 0.85rem;
  color: var(--text-secondary);
}
.hl-body {
  font-size: 0.85rem;
  overflow-x: auto;
}
</style>
