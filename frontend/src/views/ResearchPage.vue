<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import { RouterLink } from 'vue-router';
import { projectApi } from '../services/api';
import type { Project } from '../services/api';
import { useI18n } from 'vue-i18n';
import ProjectResearchPage from './ProjectResearchPage.vue';
import PageHeader from '../components/base/PageHeader.vue';

const { t } = useI18n();

const projects = ref<Project[]>([]);
const selectedProjectId = ref<string>('');
const loading = ref(true);

onMounted(async () => {
  try {
    projects.value = (await projectApi.list()).projects || [];
    const saved = localStorage.getItem('research:last-project');
    selectedProjectId.value =
      (saved && projects.value.some((p) => p.id === saved) ? saved : projects.value[0]?.id) || '';
  } finally {
    loading.value = false;
  }
});

watch(selectedProjectId, (v) => {
  if (v) localStorage.setItem('research:last-project', v);
});
</script>

<template>
  <div class="research-surface">
    <div v-if="loading" class="research-surface-loading">
      <div class="loading-spinner"></div>
    </div>

    <template v-else-if="projects.length === 0">
      <PageHeader
        :title="t('surface.research.title')"
        :subtitle="t('surface.research.pickProjectHint')"
      />
      <div class="research-empty">
        <p>{{ t('surface.research.noProjects') }}</p>
        <RouterLink :to="{ name: 'projects' }" class="research-empty-link">
          {{ t('surface.research.goToProjects') }}
        </RouterLink>
      </div>
    </template>

    <template v-else>
      <div class="research-project-bar">
        <label for="research-project-select">{{ t('surface.research.pickProject') }}</label>
        <select
          id="research-project-select"
          v-model="selectedProjectId"
          class="research-project-select"
        >
          <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
      </div>
      <ProjectResearchPage
        v-if="selectedProjectId"
        :key="selectedProjectId"
        :project-id="selectedProjectId"
      />
    </template>
  </div>
</template>

<style scoped>
.research-surface-loading {
  display: flex;
  justify-content: center;
  padding: 48px 0;
}

.loading-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--border-subtle);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: research-spin 0.8s linear infinite;
}

@keyframes research-spin {
  to {
    transform: rotate(360deg);
  }
}

.research-project-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 0;
  margin-bottom: 4px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-subtle);
}

.research-project-bar label {
  font-size: 13px;
  color: var(--text-tertiary);
}

.research-project-select {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 13px;
}

.research-empty {
  padding: 24px 0;
  color: var(--text-secondary);
  font-size: 13px;
}

.research-empty-link {
  display: inline-block;
  margin-top: 8px;
  color: var(--accent-cyan);
  text-decoration: none;
}

.research-empty-link:hover {
  text-decoration: underline;
}
</style>
