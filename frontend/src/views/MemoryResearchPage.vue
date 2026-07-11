<script setup lang="ts">
/**
 * Memory Research — wires Tesserae's agentic `research` loop (plan → search →
 * reflect → synthesize) as an "investigate a question across the knowledge graph"
 * surface. Kicks off an async job and polls until the synthesized markdown report
 * is ready. SLOW + LLM-backed (minutes). Sibling of KnowledgeGraphPage.
 * (Distinct from ResearchPage.vue, which is the project competitive-autoresearch.)
 */
import { ref, onUnmounted } from 'vue';
import { useI18n } from 'vue-i18n';
import PageHeader from '../components/base/PageHeader.vue';
import MarkdownContent from '../components/base/MarkdownContent.vue';
import { memorySystemApi } from '../services/api/memory-system';

const { t } = useI18n();

const query = ref('');
const running = ref(false);
const error = ref<string | null>(null);
const report = ref('');
const elapsed = ref(0);

let pollTimer: ReturnType<typeof setInterval> | null = null;
let clockTimer: ReturnType<typeof setInterval> | null = null;
let alive = true; // guards against setting a timer after unmount (in-flight await)

function stopTimers() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  if (clockTimer) { clearInterval(clockTimer); clockTimer = null; }
}

async function investigate() {
  const q = query.value.trim();
  if (!q || running.value) return;
  running.value = true;
  error.value = null;
  report.value = '';
  elapsed.value = 0;
  clockTimer = setInterval(() => (elapsed.value += 1), 1000);
  try {
    const { job_id } = await memorySystemApi.startResearch(q);
    // If the component unmounted during the await, don't start an orphaned poller.
    if (!alive) { stopTimers(); return; }
    pollTimer = setInterval(() => poll(job_id), 3000);
  } catch (e) {
    error.value = (e as Error).message || t('memoryResearch.failed');
    running.value = false;
    stopTimers();
  }
}

async function poll(jobId: string) {
  try {
    const job = await memorySystemApi.researchJob(jobId);
    if (job.status === 'running') return;
    // terminal
    running.value = false;
    stopTimers();
    if (job.status === 'completed' && job.result?.ok) {
      report.value = job.result.report_md || '';
    } else {
      error.value = job.result?.reason || t('memoryResearch.failed');
    }
  } catch (e) {
    running.value = false;
    stopTimers();
    error.value = (e as Error).message || t('memoryResearch.failed');
  }
}

onUnmounted(() => { alive = false; stopTimers(); });
</script>

<template>
  <div class="research-page">
    <PageHeader :title="t('memoryResearch.title')" :subtitle="t('memoryResearch.subtitle')" />

    <form class="research-bar" @submit.prevent="investigate">
      <input
        v-model="query"
        class="research-input"
        type="text"
        :placeholder="t('memoryResearch.placeholder')"
        :disabled="running"
      />
      <button class="research-btn" type="submit" :disabled="running || !query.trim()">
        {{ running ? t('memoryResearch.running') : t('memoryResearch.investigate') }}
      </button>
    </form>

    <div v-if="running" class="research-state">
      <span class="research-spinner" />
      {{ t('memoryResearch.workingFor', { s: elapsed }) }}
    </div>
    <div v-else-if="error" class="research-state research-state--error">{{ error }}</div>

    <div v-if="report" class="research-report">
      <MarkdownContent :content="report" />
    </div>
  </div>
</template>

<style scoped>
.research-page {
  padding: 24px;
  max-width: 920px;
}
.research-bar {
  display: flex;
  gap: 8px;
  margin: 16px 0 20px;
}
.research-input {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 8px;
  background: var(--bg-secondary, #12121a);
  color: var(--text-primary, #e4e4e7);
  font-size: 14px;
}
.research-input:disabled {
  opacity: 0.6;
}
.research-btn {
  padding: 10px 20px;
  border: 1px solid rgba(79, 70, 229, 0.5);
  border-radius: 8px;
  background: rgba(79, 70, 229, 0.18);
  color: #a5b4fc;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
.research-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.research-state {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px;
  color: var(--text-secondary, #a1a1aa);
  font-size: 14px;
}
.research-state--error {
  color: #ef4444;
}
.research-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(165, 180, 252, 0.3);
  border-top-color: #a5b4fc;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.research-report {
  margin-top: 12px;
  padding: 20px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  background: var(--bg-secondary, #12121a);
}
</style>
