<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useRoute } from 'vue-router';
import type { Project } from '../services/api';
import { projectApi, researchApi } from '../services/api';
import type { ResearchThread, ResearchThreadBundle } from '../services/api/research';
import { useToast } from '../composables/useToast';
import { handleApiError } from '../services/api/error-handler';
import { useResearchSession } from '../composables/useResearchSession';
import { useI18n } from 'vue-i18n';
import PageHeader from '../components/base/PageHeader.vue';
import EntityLayout from '../layouts/EntityLayout.vue';
import PlanningSessionPanel from '../components/grd/PlanningSessionPanel.vue';
import QuestionIntake from '../components/grd/research/QuestionIntake.vue';
import ThreadList from '../components/grd/research/ThreadList.vue';
import HypothesisLedger from '../components/grd/research/HypothesisLedger.vue';
import ReportViewer from '../components/grd/research/ReportViewer.vue';
import PortfolioRuns from '../components/grd/research/PortfolioRuns.vue';

const props = defineProps<{
  projectId?: string;
}>();

const route = useRoute();
const projectId = computed(() => (route.params.projectId as string) || props.projectId || '');

const showToast = useToast();
const { t } = useI18n();

// State
const project = ref<Project | null>(null);
const threads = ref<ResearchThread[]>([]);
const selectedThreadId = ref<string | null>(null);
const selectedBundle = ref<ResearchThreadBundle | null>(null);
const showSessionPanel = ref(false);

// Research session composable (SSE)
const research = useResearchSession(projectId);

async function loadData() {
  try {
    const [projectData, threadsRes] = await Promise.all([
      projectApi.get(projectId.value),
      researchApi.listThreads(projectId.value),
    ]);
    project.value = projectData;
    threads.value = threadsRes.threads || [];
    if (!selectedThreadId.value && threads.value.length > 0) {
      await selectThread(threads.value[0].id);
    }
    return project.value;
  } catch (err) {
    handleApiError(err, showToast, t('surface.research.loadError'));
    throw err;
  }
}

async function loadThreads() {
  try {
    const res = await researchApi.listThreads(projectId.value);
    threads.value = res.threads || [];
  } catch {
    showToast(t('surface.research.loadError'), 'error');
  }
}

async function selectThread(threadId: string) {
  selectedThreadId.value = threadId;
  try {
    selectedBundle.value = await researchApi.getThread(projectId.value, threadId);
  } catch {
    selectedBundle.value = null;
    showToast(t('surface.research.loadThreadError'), 'error');
  }
}

function handleSubmit(question: string, opts: { max_iterations?: number; no_gates?: boolean }) {
  research.start(question, opts);
  showSessionPanel.value = true;
}

function handleClearSession() {
  research.clearOutput();
  showSessionPanel.value = false;
}

// Refresh threads (and the selected bundle) when a session completes.
watch(
  () => research.status.value,
  (newStatus) => {
    if (newStatus === 'complete') {
      loadThreads().then(() => {
        if (selectedThreadId.value) selectThread(selectedThreadId.value);
      });
    }
  },
);
</script>

<template>
  <EntityLayout :load-entity="loadData" entity-label="research">
    <template #default>
      <div class="research-page">
        <PageHeader :title="t('surface.research.title')" :subtitle="project?.name || undefined" />

        <div class="research-layout" :class="{ 'session-open': showSessionPanel }">
          <div class="research-left">
            <QuestionIntake :status="research.status.value" @submit="handleSubmit" />
            <PortfolioRuns :threads="threads" />
            <ThreadList
              :threads="threads"
              :selected-id="selectedThreadId"
              @select="selectThread"
            />
            <div class="research-detail">
              <HypothesisLedger :hypotheses="selectedBundle?.hypotheses" />
              <ReportViewer :finding="selectedBundle?.finding" />
            </div>
          </div>
          <div v-if="showSessionPanel" class="research-right">
            <PlanningSessionPanel
              :output-lines="research.outputLines.value"
              :status="research.status.value"
              :current-question="research.currentQuestion.value"
              :exit-code="research.exitCode.value"
              @clear="handleClearSession"
            />
          </div>
        </div>
      </div>
    </template>
  </EntityLayout>
</template>

<style scoped>
.research-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(12px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.research-layout {
  display: flex;
  gap: 16px;
  height: calc(100vh - 200px);
}

.research-left {
  flex: 1;
  overflow-y: auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.research-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.research-right {
  width: 420px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
}
</style>
