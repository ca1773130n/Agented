<script setup lang="ts">
/**
 * ProjectHarnessPage (REQ-16) — the life-harness completion surface. Composes
 * the autonomy editor, evolution rounds (list + confirm-guarded revert detail),
 * shared-forge browse/adopt, and the seven GRD-route panels. Mounted under the
 * project surface (NOT a top-level sidebar slot — sidebar IA is a product
 * judgment, not auto-classified).
 */
import { computed, ref } from 'vue';
import { useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { projectApi } from '../services/api';
import type { Project } from '../services/api';
import PageHeader from '../components/base/PageHeader.vue';
import EntityLayout from '../layouts/EntityLayout.vue';
import AutonomyEditor from '../components/grd/harness/AutonomyEditor.vue';
import HarnessPanelHost from '../components/grd/harness/HarnessPanelHost.vue';
import RoundList from '../components/grd/harness/RoundList.vue';
import RoundDetail from '../components/grd/harness/RoundDetail.vue';
import SharedForgeBrowser from '../components/grd/harness/SharedForgeBrowser.vue';

const props = defineProps<{ projectId?: string }>();
const route = useRoute();
const { t } = useI18n();

const projectId = computed(() => (route.params.projectId as string) || props.projectId || '');
const project = ref<Project | null>(null);
const selectedRound = ref<string | null>(null);
const roundListRef = ref<InstanceType<typeof RoundList> | null>(null);

async function loadData() {
  project.value = await projectApi.get(projectId.value);
  return project.value;
}

function onRoundChanged() {
  roundListRef.value?.load();
}
</script>

<template>
  <EntityLayout :load-entity="loadData" entity-label="harness">
    <template #default>
      <div class="harness-page">
        <PageHeader
          :title="t('surface.harness.title')"
          :subtitle="project?.name || t('surface.harness.subtitle')"
        />

        <AutonomyEditor :project-id="projectId" />

        <HarnessPanelHost :project-id="projectId" />

        <div class="rounds-grid">
          <RoundList
            ref="roundListRef"
            :project-id="projectId"
            @select="selectedRound = $event"
          />
          <RoundDetail :round-id="selectedRound" @changed="onRoundChanged" />
        </div>

        <SharedForgeBrowser :project-id="projectId" />
      </div>
    </template>
  </EntityLayout>
</template>

<style scoped>
.harness-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
  animation: fadeIn 0.4s ease;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}
.rounds-grid {
  display: grid;
  grid-template-columns: 1fr 1.5fr;
  gap: 16px;
}
@media (max-width: 900px) {
  .rounds-grid { grid-template-columns: 1fr; }
}
</style>
