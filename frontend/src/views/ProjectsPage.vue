<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import type { Project, Product, Team } from '../services/api';
import { projectApi, productApi, teamApi, ApiError } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import EmptyState from '../components/base/EmptyState.vue';
import ErrorState from '../components/base/ErrorState.vue';
import LoadingState from '../components/base/LoadingState.vue';
import ListSearchSort from '../components/base/ListSearchSort.vue';
import PaginationBar from '../components/base/PaginationBar.vue';
import ConfirmModal from '../components/base/ConfirmModal.vue';
import { useToast } from '../composables/useToast';
import { useListFilter } from '../composables/useListFilter';
import { useFocusTrap } from '../composables/useFocusTrap';
import { usePagination } from '../composables/usePagination';
import { useWebMcpPageTools } from '../webmcp/useWebMcpPageTools';

const showToast = useToast();

const projects = ref<Project[]>([]);
const products = ref<Product[]>([]);
const teams = ref<Team[]>([]);
const isLoading = ref(true);
const loadError = ref<string | null>(null);
const showCreateModal = ref(false);
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
  { value: 'name', label: 'Name' },
  { value: 'created_at', label: 'Date Created' },
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
      const project = projects.value.find((p: any) => p.id === id);
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
    loadError.value = e instanceof ApiError ? e.message : 'Failed to load projects';
    showToast(loadError.value, 'error');
  } finally {
    isLoading.value = false;
  }
}

watch([() => pagination.currentPage.value, () => pagination.pageSize.value], () => { loadProjects(); });
watch([searchQuery, sortField, sortOrder], () => { pagination.resetToFirstPage(); });

const router = useRouter();

async function createProject() {
  if (!newProject.value.name.trim()) {
    showToast('Project name is required', 'error');
    return;
  }
  if (!newProject.value.github_repo.trim() && !(showLocalPath.value && newProject.value.local_path.trim())) {
    showToast('GitHub repository is required', 'error');
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
      showToast('Project created and repository cloned', 'success');
    } else if (project?.clone_error) {
      showToast(`Project created. Clone deferred: ${project.clone_error}`, 'info');
    } else {
      showToast('Project created successfully', 'success');
    }
    showCreateModal.value = false;
    newProject.value = { name: '', description: '', status: 'active', product_id: '', github_repo: '', local_path: '' };
    showLocalPath.value = false;
    await loadProjects();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to create project', 'error');
    }
  } finally {
    creatingProject.value = false;
  }
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
    showToast(`Project "${projectToDelete.value.name}" deleted`, 'success');
    showDeleteConfirm.value = false;
    projectToDelete.value = null;
    await loadProjects();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to delete project', 'error');
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
  <div class="projects-page">
    <AppBreadcrumb :items="[{ label: 'Projects' }]" />
    <PageHeader title="Projects" subtitle="Manage your projects and their team assignments">
      <template #actions>
        <button class="btn btn-primary" @click="showCreateModal = true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          Create Project
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
      placeholder="Search projects..."
    />

    <LoadingState v-if="isLoading" message="Loading projects..." />

    <ErrorState v-else-if="loadError" title="Failed to load projects" :message="loadError" @retry="loadProjects" />

    <EmptyState v-else-if="projects.length === 0" title="No projects yet" description="Create your first project to start organizing your work">
      <template #actions>
        <button class="btn btn-primary" @click="showCreateModal = true">Create Your First Project</button>
      </template>
    </EmptyState>

    <EmptyState v-else-if="filteredAndSorted.length === 0 && hasActiveFilter" title="No matching projects" description="Try a different search term" />

    <div v-else class="projects-grid">
      <div
        v-for="project in filteredAndSorted"
        :key="project.id"
        class="project-card clickable"
        @click="router.push({ name: 'project-dashboard', params: { projectId: project.id } })"
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
            <span class="meta-label">Product:</span>
            <span class="meta-value">{{ project.product_name }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">Teams:</span>
            <span class="meta-value">{{ project.team_count }}</span>
          </div>
          <div v-if="project.github_repo" class="meta-item full-width">
            <span class="meta-label">GitHub:</span>
            <span class="meta-value github">{{ project.github_repo }}</span>
          </div>
          <div v-if="project.local_path" class="meta-item full-width">
            <span class="meta-label">Local:</span>
            <span class="meta-value">{{ project.local_path }}</span>
          </div>
        </div>

        <div class="project-actions">
          <button class="btn btn-small btn-danger" @click.stop="confirmDelete(project)" :disabled="deletingId === project.id">
            <span v-if="deletingId === project.id" class="btn-spinner"></span>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
            </svg>
            {{ deletingId === project.id ? 'Deleting...' : 'Delete' }}
          </button>
        </div>
      </div>
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
            <h2 id="modal-title-create-project">Create Project</h2>
            <button class="modal-close" @click="showCreateModal = false">&times;</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label>Project Name *</label>
              <input v-model="newProject.name" type="text" placeholder="e.g., API Gateway" />
            </div>
            <div class="form-group">
              <label>Description</label>
              <textarea v-model="newProject.description" placeholder="Describe the project..."></textarea>
            </div>
            <div class="form-group">
              <label>Status</label>
              <select v-model="newProject.status">
                <option value="active">Active</option>
                <option value="planning">Planning</option>
                <option value="archived">Archived</option>
              </select>
            </div>
            <div class="form-group">
              <label>Product</label>
              <select v-model="newProject.product_id">
                <option value="">No product</option>
                <option v-for="product in products" :key="product.id" :value="product.id">{{ product.name }}</option>
              </select>
            </div>
            <div class="form-group">
              <label>GitHub Repository *</label>
              <input v-model="newProject.github_repo" type="text" placeholder="e.g., org/repo" />
              <span class="local-path-toggle" @click="showLocalPath = !showLocalPath">
                {{ showLocalPath ? 'Hide local path' : 'or use a local path' }}
              </span>
            </div>
            <div v-if="showLocalPath" class="form-group">
              <label>Local Path</label>
              <input v-model="newProject.local_path" type="text" placeholder="e.g., /home/user/projects/my-app" />
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showCreateModal = false">Cancel</button>
            <button class="btn btn-primary" @click="createProject" :disabled="creatingProject">
              <span v-if="creatingProject" class="btn-spinner"></span>
              {{ creatingProject ? 'Creating...' : 'Create Project' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <ConfirmModal
      :open="showDeleteConfirm"
      title="Delete Project"
      :message="`Are you sure you want to delete \u201C${projectToDelete?.name}\u201D? This action cannot be undone.`"
      confirm-label="Delete"
      cancel-label="Cancel"
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
</style>
