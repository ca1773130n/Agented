<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { renderMarkdown } from '../../../composables/useMarkdown';

const props = defineProps<{
  finding?: string | null;
}>();

const { t } = useI18n();

const hasContent = computed(() => !!props.finding && props.finding.trim().length > 0);
const rendered = computed(() => (hasContent.value ? renderMarkdown(props.finding as string) : ''));
</script>

<template>
  <section class="report-viewer">
    <h3 class="rv-title">{{ t('surface.research.report.title') }}</h3>
    <p v-if="!hasContent" class="rv-empty">{{ t('surface.research.report.empty') }}</p>
    <!-- FINDING.md via renderMarkdown — the DOMPurify-sanitized GREEN renderer (useMarkdown.ts). NOT MarkdownContent. -->
    <div v-else class="rv-body markdown-body" v-html="rendered" />
  </section>
</template>

<style scoped>
.report-viewer {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.rv-title {
  font-size: 0.95rem;
  margin: 0;
}
.rv-empty {
  font-size: 0.85rem;
  color: var(--text-secondary);
}
.rv-body {
  font-size: 0.9rem;
  line-height: 1.55;
  overflow-x: auto;
}
</style>
