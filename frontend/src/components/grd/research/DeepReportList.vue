<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { researchApi } from '../../../services/api';
import type { DeepReportSummary } from '../../../services/api/research';
import { renderMarkdown } from '../../../composables/useMarkdown';

const props = defineProps<{
  projectId: string;
}>();

const { t } = useI18n();

const reports = ref<DeepReportSummary[]>([]);
const selectedName = ref<string | null>(null);
const selectedMarkdown = ref<string | null>(null);

const hasReports = computed(() => reports.value.length > 0);
const rendered = computed(() =>
  selectedMarkdown.value && selectedMarkdown.value.trim().length > 0
    ? renderMarkdown(selectedMarkdown.value)
    : '',
);

function relativeTime(modified: number): string {
  // ``modified`` is a POSIX mtime in seconds.
  const date = new Date(modified * 1000);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString();
}

async function refresh() {
  try {
    const res = await researchApi.listDeepReports(props.projectId);
    reports.value = res.reports || [];
  } catch {
    reports.value = [];
  }
}

async function selectReport(name: string) {
  selectedName.value = name;
  try {
    const res = await researchApi.getDeepReport(props.projectId, name);
    selectedMarkdown.value = res.markdown;
  } catch {
    selectedMarkdown.value = null;
  }
}

onMounted(refresh);

defineExpose({ refresh });
</script>

<template>
  <section class="deep-report-list">
    <h3 class="drl-title">{{ t('surface.research.deepReports.title') }}</h3>
    <p v-if="!hasReports" class="drl-empty">{{ t('surface.research.deepReports.empty') }}</p>
    <ul v-else class="drl-rows">
      <li
        v-for="report in reports"
        :key="report.path"
        class="drl-row"
        :class="{ active: report.name === selectedName }"
        @click="selectReport(report.name)"
      >
        <span class="drl-name">{{ report.name }}</span>
        <span class="drl-meta">
          {{ t('surface.research.deepReports.milestone') }}: {{ report.milestone }}
          <span class="drl-dot">·</span>
          {{ relativeTime(report.modified) }}
        </span>
      </li>
    </ul>
    <div v-if="rendered" class="drl-body markdown-body" v-html="rendered" />
  </section>
</template>

<style scoped>
.deep-report-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 16px;
}
.drl-title {
  font-size: 0.95rem;
  margin: 0;
}
.drl-empty {
  font-size: 0.85rem;
  color: var(--text-secondary);
}
.drl-rows {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.drl-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  cursor: pointer;
}
.drl-row.active {
  border-color: var(--accent-cyan);
}
.drl-name {
  font-size: 0.85rem;
  color: var(--text-primary);
}
.drl-meta {
  font-size: 0.72rem;
  color: var(--text-secondary);
}
.drl-dot {
  margin: 0 4px;
}
.drl-body {
  margin-top: 8px;
  font-size: 0.9rem;
  line-height: 1.55;
  overflow-x: auto;
}
</style>
