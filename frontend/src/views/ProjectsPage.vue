<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue';
import type { Project, Product, Team } from '../services/api';
import { projectApi, productApi, teamApi, ApiError } from '../services/api';
import PageHeader from '../components/base/PageHeader.vue';
import EmptyState from '../components/base/EmptyState.vue';
import ErrorState from '../components/base/ErrorState.vue';
import LoadingState from '../components/base/LoadingState.vue';
import ListSearchSort from '../components/base/ListSearchSort.vue';
import PaginationBar from '../components/base/PaginationBar.vue';
import ConfirmModal from '../components/base/ConfirmModal.vue';
import ProjectDiscoveryModal from '../components/projects/ProjectDiscoveryModal.vue';
import { useToast } from '../composables/useToast';
import { useListFilter } from '../composables/useListFilter';
import { useFocusTrap } from '../composables/useFocusTrap';
import { usePagination } from '../composables/usePagination';
import { useWebMcpPageTools } from '../composables/useWebMcpPageTools';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();

const showToast = useToast();

const projects = ref<Project[]>([]);
const products = ref<Product[]>([]);
const teams = ref<Team[]>([]);
const isLoading = ref(true);
const loadError = ref<string | null>(null);
const showCreateModal = ref(false);
const showDiscoverModal = ref(false);
const showDeleteConfirm = ref(false);
const projectToDelete = ref<Project | null>(null);
const deletingId = ref<string | null>(null);
const { searchQuery, sortField, sortOrder, filteredAndSorted, hasActiveFilter, resultCount, totalCount } = useListFilter({
  items: projects,
  searchFields: ['name', 'description', 'github_repo'] as (keyof Project)[],
  storageKey: 'projects-list-filter',
});

const pagination = usePagination({ defaultPageSize: 25, storageKey: 'projects-pagination' });

const sortOptions = [
  { value: 'name', label: t('projects.sortName') },
  { value: 'created_at', label: t('projects.sortCreated') },
];

const showLocalPath = ref(false);
const creatingProject = ref(false);
const newProject = ref({ name: '', description: '', status: 'active', product_id: '', github_repo: '', local_path: '' });

// Modal overlay refs for Escape key handling
const createModalOverlay = ref<HTMLElement | null>(null);
useFocusTrap(createModalOverlay, showCreateModal);
watch(showCreateModal, (val) => { if (val) nextTick(() => createModalOverlay.value?.focus()); });

useWebMcpPageTools({
  page: 'ProjectsPage',
  domain: 'projects',
  stateGetter: () => ({
    items: projects.value,
    itemCount: projects.value.length,
    isLoading: isLoading.value,
    error: loadError.value,
    searchQuery: searchQuery.value,
    sortField: sortField.value,
    sortOrder: sortOrder.value,
    currentPage: pagination.currentPage.value,
    pageSize: pagination.pageSize.value,
    totalCount: pagination.totalCount.value,
    showLocalPath: showLocalPath.value,
  }),
  modalGetter: () => ({
    showCreateModal: showCreateModal.value,
    showDeleteConfirm: showDeleteConfirm.value,
    formValues: newProject.value,
  }),
  modalActions: {
    openCreate: () => { showCreateModal.value = true; },
    openDelete: (id: string) => {
      const project = projects.value.find((p) => p.id === id);
      if (project) { projectToDelete.value = project; showDeleteConfirm.value = true; }
    },
  },
  deps: [projects, searchQuery, sortField, sortOrder],
});

async function loadProjects() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const [projectsData, productsData, teamsData] = await Promise.all([
      projectApi.list({ limit: pagination.pageSize.value, offset: pagination.offset.value }),
      productApi.list(),
      teamApi.list()
    ]);
    projects.value = projectsData.projects || [];
    if (projectsData.total_count != null) pagination.totalCount.value = projectsData.total_count;
    products.value = productsData.products || [];
    teams.value = teamsData.teams || [];
  } catch (e) {
    loadError.value = e instanceof ApiError ? e.message : t('projects.loadError');
    showToast(loadError.value, 'error');
  } finally {
    isLoading.value = false;
  }
}

watch([() => pagination.currentPage.value, () => pagination.pageSize.value], () => { loadProjects(); });
watch([searchQuery, sortField, sortOrder], () => { pagination.resetToFirstPage(); });

// ``useRouter`` was used by the old @click navigation; v0.7.28 swapped
// cards to <router-link> so the imperative router instance is no
// longer needed on this page.

async function createProject() {
  if (!newProject.value.name.trim()) {
    showToast(t('projects.nameRequired'), 'error');
    return;
  }
  if (!newProject.value.github_repo.trim() && !(showLocalPath.value && newProject.value.local_path.trim())) {
    showToast(t('projects.githubRequired'), 'error');
    return;
  }
  creatingProject.value = true;
  try {
    const result = await projectApi.create({
      name: newProject.value.name,
      description: newProject.value.description || undefined,
      status: newProject.value.status,
      product_id: newProject.value.product_id || undefined,
      github_repo: newProject.value.github_repo || undefined,
      local_path: showLocalPath.value && newProject.value.local_path ? newProject.value.local_path : undefined,
    });
    // Show clone feedback
    const project = (result as { project?: { clone_path?: string; clone_error?: string } }).project;
    if (project?.clone_path) {
      showToast(t('projects.createdAndCloned'), 'success');
    } else if (project?.clone_error) {
      showToast(t('projects.cloneDeferred', { error: project.clone_error }), 'info');
    } else {
      showToast(t('projects.createSuccess'), 'success');
    }
    showCreateModal.value = false;
    newProject.value = { name: '', description: '', status: 'active', product_id: '', github_repo: '', local_path: '' };
    showLocalPath.value = false;
    await loadProjects();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast(t('projects.createError'), 'error');
    }
  } finally {
    creatingProject.value = false;
  }
}

async function onReposImported() {
  showDiscoverModal.value = false;
  await loadProjects();
}

function confirmDelete(project: Project) {
  projectToDelete.value = project;
  showDeleteConfirm.value = true;
}

async function deleteProject() {
  if (!projectToDelete.value) return;
  deletingId.value = projectToDelete.value.id;
  try {
    await projectApi.delete(projectToDelete.value.id);
    showToast(t('projects.deleteSuccess', { name: projectToDelete.value.name }), 'success');
    showDeleteConfirm.value = false;
    projectToDelete.value = null;
    await loadProjects();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast(t('projects.deleteError'), 'error');
    }
  } finally {
    deletingId.value = null;
  }
}

function getStatusClass(status: string) {
  switch (status) {
    case 'active': return 'status-active';
    case 'archived': return 'status-archived';
    case 'planning': return 'status-planning';
    default: return '';
  }
}

onMounted(() => {
  loadProjects();
});
</script>

<template>
  <div class="projects-page" data-tour="assign-teams">
    <PageHeader :title="t('projects.title')" :subtitle="t('projects.subtitle')">
      <template #actions>
        <button class="btn btn-secondary" data-testid="discover-repos-btn" @click="showDiscoverModal = true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="7" /><path d="M21 21l-4.35-4.35" />
          </svg>
          {{ t('projectsDiscovery.button') }}
        </button>
        <button class="btn btn-primary" @click="showCreateModal = true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          {{ t('projects.createProject') }}
        </button>
      </template>
    </PageHeader>

    <ListSearchSort
      v-if="!isLoading && !loadError && projects.length > 0"
      v-model:searchQuery="searchQuery"
      v-model:sortField="sortField"
      v-model:sortOrder="sortOrder"
      :sort-options="sortOptions"
      :result-count="resultCount"
      :total-count="totalCount"
      :placeholder="t('projects.searchPlaceholder')"
    />

    <LoadingState v-if="isLoading" :message="t('projects.loading')" />

    <ErrorState v-else-if="loadError" :title="t('projects.loadFailed')" :message="loadError" @retry="loadProjects" />

    <EmptyState v-else-if="projects.length === 0" :title="t('projects.emptyTitle')" :description="t('projects.emptyDescription')">
      <template #actions>
        <button class="btn btn-primary" @click="showCreateModal = true">{{ t('projects.createFirst') }}</button>
      </template>
    </EmptyState>

    <EmptyState v-else-if="filteredAndSorted.length === 0 && hasActiveFilter" :title="t('projects.noMatchTitle')" :description="t('projects.noMatchDescription')" />

    <div v-else class="projects-grid">
      <router-link
        v-for="project in filteredAndSorted"
        :key="project.id"
        :to="{ name: 'project-dashboard', params: { projectId: project.id } }"
        class="project-card clickable"
      >
        <div class="project-header">
          <div class="project-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>
          </div>
          <div class="project-info">
            <h3>{{ project.name }}</h3>
            <span class="project-id">{{ project.id }}</span>
          </div>
          <span :class="['status-badge', getStatusClass(project.status)]">{{ project.status }}</span>
        </div>

        <p v-if="project.description" class="project-description">{{ project.description }}</p>

        <div class="project-meta">
          <div v-if="project.product_name" class="meta-item">
            <span class="meta-label">{{ t('projects.productLabel') }}</span>
            <span class="meta-value">{{ project.product_name }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">{{ t('projects.teamsLabel') }}</span>
            <span class="meta-value">{{ project.team_count }}</span>
          </div>
          <div v-if="project.github_repo" class="meta-item full-width">
            <span class="meta-label">{{ t('projects.githubLabel') }}</span>
            <span class="meta-value github">{{ project.github_repo }}</span>
          </div>
          <div v-if="project.local_path" class="meta-item full-width">
            <span class="meta-label">{{ t('projects.localLabel') }}</span>
            <span class="meta-value">{{ project.local_path }}</span>
          </div>
        </div>

        <div class="project-actions">
          <button class="btn btn-small btn-danger" @click.stop="confirmDelete(project)" :disabled="deletingId === project.id">
            <span v-if="deletingId === project.id" class="btn-spinner"></span>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
            </svg>
            {{ deletingId === project.id ? t('projects.deleting') : t('common.delete') }}
          </button>
        </div>
      </router-link>
    </div>

    <PaginationBar
      v-if="!isLoading && !loadError && projects.length > 0"
      v-model:currentPage="pagination.currentPage.value"
      v-model:pageSize="pagination.pageSize.value"
      :total-pages="pagination.totalPages.value"
      :page-size-options="pagination.pageSizeOptions"
      :range-start="pagination.rangeStart.value"
      :range-end="pagination.rangeEnd.value"
      :total-count="pagination.totalCount.value"
      :is-first-page="pagination.isFirstPage.value"
      :is-last-page="pagination.isLastPage.value"
    />

    <!-- Create Modal -->
    <Teleport to="body">
      <div v-if="showCreateModal" ref="createModalOverlay" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-create-project" tabindex="-1" @click.self="showCreateModal = false" @keydown.escape="showCreateModal = false">
        <div class="modal">
          <div class="modal-header">
            <h2 id="modal-title-create-project">{{ t('projects.createProject') }}</h2>
            <button class="modal-close" @click="showCreateModal = false">&times;</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label>{{ t('projects.projectNameLabel') }}</label>
              <input v-model="newProject.name" type="text" :placeholder="t('projects.projectNamePlaceholder')" />
            </div>
            <div class="form-group">
              <label>{{ t('projects.descriptionLabel') }}</label>
              <textarea v-model="newProject.description" :placeholder="t('projects.descriptionPlaceholder')"></textarea>
            </div>
            <div class="form-group">
              <label>{{ t('projects.statusLabel') }}</label>
              <select v-model="newProject.status">
                <option value="active">{{ t('projects.statusActive') }}</option>
                <option value="planning">{{ t('projects.statusPlanning') }}</option>
                <option value="archived">{{ t('projects.statusArchived') }}</option>
              </select>
            </div>
            <div class="form-group">
              <label>{{ t('projects.productSelectLabel') }}</label>
              <select v-model="newProject.product_id">
                <option value="">{{ t('projects.noProduct') }}</option>
                <option v-for="product in products" :key="product.id" :value="product.id">{{ product.name }}</option>
              </select>
            </div>
            <div class="form-group">
              <label>{{ t('projects.githubRepoLabel') }}</label>
              <input v-model="newProject.github_repo" type="text" :placeholder="t('projects.githubRepoPlaceholder')" />
              <span class="local-path-toggle" @click="showLocalPath = !showLocalPath">
                {{ showLocalPath ? t('projects.hideLocalPath') : t('projects.orUseLocalPath') }}
              </span>
            </div>
            <div v-if="showLocalPath" class="form-group">
              <label>{{ t('projects.localPathLabel') }}</label>
              <input v-model="newProject.local_path" type="text" :placeholder="t('projects.localPathPlaceholder')" />
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showCreateModal = false">{{ t('common.cancel') }}</button>
            <button class="btn btn-primary" @click="createProject" :disabled="creatingProject">
              <span v-if="creatingProject" class="btn-spinner"></span>
              {{ creatingProject ? t('projects.creating') : t('projects.createProject') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <ProjectDiscoveryModal
      v-if="showDiscoverModal"
      :teams="teams"
      :products="products"
      @close="showDiscoverModal = false"
      @imported="onReposImported"
    />

    <ConfirmModal
      :open="showDeleteConfirm"
      :title="t('projects.deleteTitle')"
      :message="t('projects.deleteConfirm', { name: projectToDelete?.name })"
      :confirm-label="t('common.delete')"
      :cancel-label="t('common.cancel')"
      variant="danger"
      @confirm="deleteProject"
      @cancel="showDeleteConfirm = false"
    />

  </div>
</template>

<style scoped>
.projects-page {
}

.btn-secondary {
  background: var(--bg-tertiary, #1a1a24);
  color: var(--text-primary, #fff);
  border: 1px solid var(--border-default);
}

.btn-danger {
  background: rgba(255, 77, 77, 0.2);
  color: #ff4d4d;
  border: 1px solid rgba(255, 77, 77, 0.3);
}

.btn-small { padding: 0.5rem 0.75rem; font-size: 0.85rem; }
.btn-small svg { width: 14px; height: 14px; }

.btn-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.projects-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 1.5rem;
}

.project-card {
  background: var(--bg-secondary, #12121a);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 1.5rem;
  transition: all 0.2s;
  /* router-link anchor reset (was a div). */
  display: block;
  text-decoration: none;
  color: inherit;
}

.project-card.clickable {
  cursor: pointer;
}

.project-card:hover {
  border-color: var(--accent-emerald, #00ff88);
  box-shadow: 0 0 20px rgba(0, 255, 136, 0.1);
  transform: translateY(-2px);
}

.project-header {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 1rem;
}

.project-icon {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--accent-emerald, #00ff88), var(--accent-cyan, #00d4ff));
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.project-icon svg {
  width: 24px;
  height: 24px;
  color: #000;
}

.project-info { flex: 1; min-width: 0; }
.project-info h3 { font-size: 1.1rem; font-weight: 600; margin-bottom: 0.25rem; }
.project-id { font-size: 0.75rem; color: var(--text-secondary, #888); font-family: monospace; }

.status-badge {
  padding: 0.25rem 0.75rem;
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: 500;
}

.status-active { background: rgba(0, 255, 136, 0.2); color: #00ff88; }
.status-archived { background: rgba(136, 136, 136, 0.2); color: #888; }
.status-planning { background: rgba(136, 85, 255, 0.2); color: #8855ff; }

.project-description {
  color: var(--text-secondary, #888);
  font-size: 0.9rem;
  margin-bottom: 1rem;
  line-height: 1.5;
}

.project-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin-bottom: 1rem;
}

.meta-item { font-size: 0.85rem; }
.meta-item.full-width { width: 100%; }
.meta-label { color: var(--text-secondary, #888); margin-right: 0.5rem; }
.meta-value { color: var(--text-primary, #fff); }
.meta-value.github { font-family: monospace; font-size: 0.8rem; }

.project-actions {
  display: flex;
  gap: 0.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-default);
}

/* Modal styles */

.modal-large { max-width: 700px; }
.modal-small { max-width: 400px; }

.modal-header h2 { font-size: 1.25rem; font-weight: 600; }

.modal-close {
  background: none;
  border: none;
  font-size: 1.5rem;
  color: var(--text-secondary, #888);
  cursor: pointer;
}

.form-group input,
.form-group textarea,
.form-group select {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
}

.warning-text { color: #ff4d4d; font-size: 0.9rem; margin-top: 0.5rem; }

.local-path-toggle {
  display: inline-block;
  margin-top: 6px;
  font-size: 0.8rem;
  color: var(--text-secondary, #888);
  cursor: pointer;
  transition: color 0.15s;
}

.local-path-toggle:hover {
  color: var(--accent-cyan, #00d4ff);
}

@media (max-width: 480px) {
  .projects-grid {
    grid-template-columns: 1fr;
  }
}
</style>
