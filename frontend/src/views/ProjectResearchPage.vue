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
import DeepReportList from '../components/grd/research/DeepReportList.vue';

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
// Deep-research mode hides the loop panels (thread/hypothesis/report/portfolio)
// — deep-research's standalone report is incompatible with them.
const deepMode = ref(false);
const deepReportList = ref<InstanceType<typeof DeepReportList> | null>(null);

// Research session composable (SSE)
const research = useResearchSession(projectId);

// Surface a failed run — an SSE error, or a session that exited non-zero (e.g.
// exit 1 when the harness account isn't logged in) — instead of silently
// leaving the panels at zero. Dismissible; reset on the next submit.
const dismissedFailure = ref(false);
const runFailed = computed(
  () =>
    !dismissedFailure.value &&
    (research.status.value === 'error' ||
      (research.status.value === 'complete' &&
        research.exitCode.value != null &&
        research.exitCode.value !== 0)),
);
const failureReason = computed(() => {
  if (research.error.value) return research.error.value;
  if (research.exitCode.value != null && research.exitCode.value !== 0)
    return t('surface.research.exitCode', { code: research.exitCode.value });
  return '';
});

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

function handleSubmit(
  question: string,
  opts: { max_iterations?: number; no_gates?: boolean; deep?: boolean; ultracode?: boolean },
) {
  deepMode.value = !!opts.deep;
  dismissedFailure.value = false;
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
      if (deepMode.value) {
        deepReportList.value?.refresh();
      } else {
        loadThreads().then(() => {
          if (selectedThreadId.value) selectThread(selectedThreadId.value);
        });
      }
    }
  },
);
</script>

<template>
  <EntityLayout :load-entity="loadData" entity-label="research">
    <template #default>
      <div class="research-page">
        <PageHeader :title="t('surface.research.title')" :subtitle="project?.name || undefined" />

        <div v-if="runFailed" class="research-failure" role="alert" data-testid="research-failure">
          <div class="research-failure__main">
            <strong>{{ t('surface.research.runFailed') }}</strong>
            <span v-if="failureReason" class="research-failure__reason">— {{ failureReason }}</span>
          </div>
          <p class="research-failure__hint">{{ t('surface.research.runFailedHint') }}</p>
          <button
            type="button"
            class="research-failure__dismiss"
            :aria-label="t('surface.research.dismiss')"
            @click="dismissedFailure = true"
          >×</button>
        </div>

        <div class="research-layout" :class="{ 'session-open': showSessionPanel }">
          <div class="research-left">
            <QuestionIntake
              :status="research.status.value"
              @submit="handleSubmit"
              @mode-change="(deep) => (deepMode = deep)"
            />
            <template v-if="!deepMode">
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
            </template>
            <DeepReportList v-else ref="deepReportList" :project-id="projectId" />
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

.research-failure {
  position: relative;
  padding: 12px 40px 12px 14px;
  background: color-mix(in srgb, var(--danger) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--danger) 45%, transparent);
  border-radius: 10px;
}
.research-failure__main {
  font-size: 13px;
  color: var(--text-primary);
}
.research-failure__reason {
  color: var(--danger);
  font-weight: 500;
}
.research-failure__hint {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
}
.research-failure__dismiss {
  position: absolute;
  top: 8px;
  right: 10px;
  background: none;
  border: none;
  color: var(--text-tertiary);
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
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
