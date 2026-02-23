<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import type { Product, Project, ProductDashboardData } from '../services/api';
import { productApi, projectApi, ApiError } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import EntityLayout from '../layouts/EntityLayout.vue';
import LoadingState from '../components/base/LoadingState.vue';
import ProductRoadmapTimeline from '../components/product/ProductRoadmapTimeline.vue';
import ProductHealthGrid from '../components/product/ProductHealthGrid.vue';
import ProductDecisionLog from '../components/product/ProductDecisionLog.vue';
import ProductActivityFeed from '../components/product/ProductActivityFeed.vue';
import { useToast } from '../composables/useToast';
import { useFocusTrap } from '../composables/useFocusTrap';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const props = defineProps<{
  productId?: string;
}>();

const route = useRoute();
const router = useRouter();
const productId = computed(() => (route.params.productId as string) || props.productId || '');

const showToast = useToast();

const product = ref<Product | null>(null);
const dashboardData = ref<ProductDashboardData | null>(null);
const isDashboardLoading = ref(false);

// Add Project modal state
const showAddProjectModal = ref(false);
const allProjects = ref<Project[]>([]);
const selectedProjectId = ref('');
const isAddingProject = ref(false);

// Inline project creation state
const createMode = ref(false);
const newProjectName = ref('');
const newProjectDescription = ref('');
const newProjectGithubRepo = ref('');
const isCreatingProject = ref(false);

useWebMcpTool({
  name: 'agented_product_dashboard_get_state',
  description: 'Returns the current state of the ProductDashboard',
  page: 'ProductDashboard',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'ProductDashboard',
        productId: product.value?.id ?? null,
        productName: product.value?.name ?? null,
        isDashboardLoading: isDashboardLoading.value,
        projectCount: product.value?.projects?.length ?? 0,
        showAddProjectModal: showAddProjectModal.value,
        hasDashboardData: !!dashboardData.value,
      }),
    }],
  }),
  deps: [product, isDashboardLoading, dashboardData, showAddProjectModal],
});

// Filter to only show unassigned projects
const unassignedProjects = computed(() => {
  return allProjects.value.filter(p => !p.product_id);
});

async function loadData() {
  const data = await productApi.get(productId.value);
  product.value = data;
  // Fire-and-forget: load supplementary dashboard data
  loadDashboard();
  return data;
}

async function loadDashboard() {
  isDashboardLoading.value = true;
  try {
    dashboardData.value = await productApi.getDashboard(productId.value);
  } catch {
    // Dashboard data is supplementary; don't block the page on failure
    dashboardData.value = null;
  } finally {
    isDashboardLoading.value = false;
  }
}

async function openAddProjectModal() {
  selectedProjectId.value = '';
  newProjectName.value = '';
  newProjectDescription.value = '';
  newProjectGithubRepo.value = '';
  isCreatingProject.value = false;
  // Default to "Create New" until we know there are unassigned projects
  createMode.value = true;
  showAddProjectModal.value = true;
  try {
    const data = await projectApi.list();
    allProjects.value = data.projects || [];
    const hasUnassigned = allProjects.value.some(p => !p.product_id);
    // Only switch to "Assign Existing" if there are projects to assign
    if (hasUnassigned) {
      createMode.value = false;
    }
  } catch (err) {
    showToast('Failed to load projects', 'error');
  }
}

async function createAndAssignProject() {
  if (!newProjectName.value.trim()) return;
  isCreatingProject.value = true;
  try {
    await projectApi.create({
      name: newProjectName.value.trim(),
      description: newProjectDescription.value.trim() || undefined,
      product_id: productId.value,
      github_repo: newProjectGithubRepo.value.trim() || undefined,
    });
    showToast('Project created and assigned', 'success');
    showAddProjectModal.value = false;
    await loadData();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to create project';
    showToast(message, 'error');
  } finally {
    isCreatingProject.value = false;
  }
}

async function addProjectToProduct() {
  if (!selectedProjectId.value) return;
  isAddingProject.value = true;
  try {
    await projectApi.update(selectedProjectId.value, { product_id: productId.value });
    showToast('Project added to product', 'success');
    showAddProjectModal.value = false;
    // Reload product data to show new project
    await loadData();
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to add project';
    showToast(message, 'error');
  } finally {
    isAddingProject.value = false;
  }
}

// Modal overlay ref for Escape key handling
const addProjectOverlay = ref<HTMLElement | null>(null);
useFocusTrap(addProjectOverlay, showAddProjectModal);

function getStatusClass(status: string): string {
  switch (status) {
    case 'active': return 'status-active';
    case 'archived': return 'status-archived';
    case 'planning': return 'status-planning';
    default: return '';
  }
}

</script>

<template>
  <EntityLayout :load-entity="loadData" entity-label="product">
    <template #default="{ reload: _reload }">
  <div class="product-dashboard">
    <AppBreadcrumb :items="[{ label: 'Products', action: () => router.push({ name: 'products' }) }, { label: product?.name || 'Product' }]" />

    <template v-if="product">
      <!-- Product Status Card -->
      <div class="status-card">
        <div class="status-card-header">
          <div class="product-icon-lg">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
              <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
              <line x1="12" y1="22.08" x2="12" y2="12"/>
            </svg>
          </div>
          <div class="status-info">
            <h2>{{ product.name }}</h2>
            <div class="status-meta">
              <span class="meta-pill" :class="getStatusClass(product.status)">
                {{ product.status }}
              </span>
              <span v-if="product.owner_team_name" class="meta-pill team">
                {{ product.owner_team_name }}
              </span>
              <span v-if="product.owner_agent_name" class="meta-pill agent">
                {{ product.owner_agent_name }}
              </span>
            </div>
          </div>
        </div>
        <p v-if="product.description" class="product-description">{{ product.description }}</p>
      </div>

      <!-- Quick Actions -->
      <div class="actions-row">
        <button class="action-btn secondary" @click="router.push({ name: 'products' })">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
          All Products
        </button>
        <button class="action-btn secondary" @click="router.push({ name: 'product-settings', params: { productId: productId } })">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
          </svg>
          Edit Product
        </button>
      </div>

      <!-- Projects -->
      <div class="card">
        <div class="card-header">
          <div class="header-left">
            <h3>Projects</h3>
            <span class="card-count">{{ product.projects?.length || 0 }} projects</span>
          </div>
          <button class="add-btn" @click="openAddProjectModal">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 5v14M5 12h14"/>
            </svg>
            Add Project
          </button>
        </div>

        <div v-if="!product.projects || product.projects.length === 0" class="empty-state">
          <div class="empty-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>
          </div>
          <h3>No projects yet</h3>
          <p>Create projects and assign them to this product</p>
          <button class="btn btn-primary" @click="openAddProjectModal">Add Your First Project</button>
        </div>

        <div v-else class="projects-list">
          <div v-for="proj in product.projects" :key="proj.id" class="project-row">
            <div class="project-info">
              <div class="project-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                </svg>
              </div>
              <div class="project-details">
                <span class="project-name entity-link" @click="router.push({ name: 'project-dashboard', params: { projectId: proj.id } })">{{ proj.name }}</span>
                <span v-if="proj.github_repo" class="project-repo">{{ proj.github_repo }}</span>
              </div>
            </div>
            <span class="status-badge" :class="getStatusClass(proj.status)">{{ proj.status }}</span>
          </div>
        </div>
      </div>

      <!-- Product Info -->
      <div class="card">
        <div class="card-header">
          <h3>Product Info</h3>
        </div>
        <div class="info-grid">
          <div class="info-item">
            <span class="info-label">Product ID</span>
            <span class="info-value mono">{{ product.id }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Status</span>
            <span class="info-value">{{ product.status }}</span>
          </div>
          <div v-if="product.owner_team_name" class="info-item">
            <span class="info-label">Owner Team</span>
            <span class="info-value">{{ product.owner_team_name }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Owner Agent</span>
            <span class="info-value">{{ product.owner_agent_name || 'Not assigned' }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">Projects</span>
            <span class="info-value">{{ product.project_count }} total</span>
          </div>
          <div v-if="product.created_at" class="info-item">
            <span class="info-label">Created</span>
            <span class="info-value">{{ new Date(product.created_at).toLocaleDateString() }}</span>
          </div>
        </div>
      </div>
      <!-- Product Dashboard Sections -->
      <div v-if="dashboardData" class="dashboard-sections">
        <ProductRoadmapTimeline :milestones="dashboardData.milestones" />
        <ProductHealthGrid
          :health="dashboardData.health"
          :projects="product?.projects || []"
          @navigateToProject="(id: string) => router.push({ name: 'project-dashboard', params: { projectId: id } })"
        />
        <ProductDecisionLog
          :decisions="dashboardData.decisions"
          :productId="productId"
          @refresh="loadDashboard"
        />
        <ProductActivityFeed
          :activity="dashboardData.activity"
          :tokenSpend="dashboardData.token_spend"
        />
      </div>
      <LoadingState v-else-if="isDashboardLoading" message="Loading dashboard data..." />
    </template>

    <!-- Add Project Modal -->
    <div v-if="showAddProjectModal" ref="addProjectOverlay" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-add-project" tabindex="-1" @click.self="showAddProjectModal = false" @keydown.escape="showAddProjectModal = false">
      <div class="modal">
        <div class="modal-header">
          <h3 id="modal-title-add-project">Add Project to Product</h3>
          <button class="modal-close" @click="showAddProjectModal = false">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
        </div>
        <div class="modal-body">
          <!-- Tab toggle -->
          <div class="modal-tabs">
            <button
              class="modal-tab"
              :class="{ active: !createMode }"
              @click="createMode = false"
            >
              Assign Existing
            </button>
            <button
              class="modal-tab"
              :class="{ active: createMode }"
              @click="createMode = true"
            >
              Create New
            </button>
          </div>

          <!-- Assign Existing tab -->
          <template v-if="!createMode">
            <p class="modal-description">Select an unassigned project to add to this product.</p>

            <div v-if="unassignedProjects.length === 0" class="empty-modal-state">
              <p>No existing projects — create one below.</p>
              <button class="btn btn-link" @click="createMode = true">Switch to Create New</button>
            </div>

            <div v-else class="project-select-wrapper">
              <select v-model="selectedProjectId" class="project-select">
                <option value="">Select a project...</option>
                <option v-for="proj in unassignedProjects" :key="proj.id" :value="proj.id">
                  {{ proj.name }}
                  <template v-if="proj.github_repo"> ({{ proj.github_repo }})</template>
                </option>
              </select>
              <svg class="select-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M6 9l6 6 6-6"/>
              </svg>
            </div>
          </template>

          <!-- Create New tab -->
          <template v-if="createMode">
            <p class="modal-description">Create a new project and assign it to this product.</p>
            <div class="form-group">
              <label class="form-label" for="new-project-name">Name <span class="required">*</span></label>
              <input
                id="new-project-name"
                v-model="newProjectName"
                type="text"
                class="form-input"
                placeholder="e.g., My Project"
              />
            </div>
            <div class="form-group">
              <label class="form-label" for="new-project-desc">Description</label>
              <textarea
                id="new-project-desc"
                v-model="newProjectDescription"
                class="form-textarea"
                placeholder="Optional description..."
                rows="3"
              ></textarea>
            </div>
            <div class="form-group">
              <label class="form-label" for="new-project-repo">GitHub Repository</label>
              <input
                id="new-project-repo"
                v-model="newProjectGithubRepo"
                type="text"
                class="form-input"
                placeholder="e.g., org/repo"
              />
            </div>
          </template>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showAddProjectModal = false">Cancel</button>
          <button
            v-if="!createMode"
            class="btn btn-primary"
            :disabled="!selectedProjectId || isAddingProject"
            @click="addProjectToProduct"
          >
            <span v-if="isAddingProject">Adding...</span>
            <span v-else>Add Project</span>
          </button>
          <button
            v-else
            class="btn btn-primary"
            :disabled="!newProjectName.trim() || isCreatingProject"
            @click="createAndAssignProject"
          >
            <span v-if="isCreatingProject">Creating...</span>
            <span v-else>Create &amp; Assign</span>
          </button>
        </div>
      </div>
    </div>
  </div>
    </template>
  </EntityLayout>
</template>

<style scoped>
.product-dashboard {
  display: flex;
  flex-direction: column;
  gap: 24px;
  width: 100%;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Status Card */
.status-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 28px;
}

.status-card-header {
  display: flex;
  align-items: center;
  gap: 20px;
}

.product-icon-lg {
  width: 56px;
  height: 56px;
  background: linear-gradient(135deg, var(--accent-violet, #8855ff), var(--accent-cyan, #00d4ff));
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.product-icon-lg svg {
  width: 28px;
  height: 28px;
  color: var(--bg-primary);
}

.status-info h2 {
  font-family: var(--font-mono);
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.02em;
  margin-bottom: 8px;
}

.status-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.meta-pill {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.meta-pill.status-active {
  background: rgba(0, 255, 136, 0.2);
  color: #00ff88;
}

.meta-pill.status-archived {
  background: rgba(136, 136, 136, 0.2);
  color: #888;
}

.meta-pill.status-planning {
  background: rgba(136, 85, 255, 0.2);
  color: #8855ff;
}

.meta-pill.team {
  background: var(--accent-amber-dim, rgba(255, 187, 0, 0.15));
  color: var(--accent-amber, #ffbb00);
}

.product-description {
  margin-top: 16px;
  color: var(--text-secondary);
  line-height: 1.6;
}

/* Actions */
.actions-row {
  display: flex;
  gap: 12px;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 20px;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  border: none;
  transition: all 0.2s;
}

.action-btn svg {
  width: 18px;
  height: 18px;
}

.action-btn.secondary {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-subtle);
}

.action-btn.secondary:hover {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}

/* Cards */
.card {
  overflow: hidden;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.card-header h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.card-count {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
  padding: 4px 8px;
  border-radius: 4px;
}

.add-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.add-btn svg {
  width: 14px;
  height: 14px;
}

.add-btn:hover {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}

/* Projects List */
.projects-list {
  display: flex;
  flex-direction: column;
}

.project-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.project-row:last-child {
  border-bottom: none;
}

.project-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.project-icon {
  width: 36px;
  height: 36px;
  background: linear-gradient(135deg, var(--accent-emerald, #00ff88), var(--accent-cyan, #00d4ff));
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.project-icon svg {
  width: 18px;
  height: 18px;
  color: var(--bg-primary);
}

.project-details {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.project-name {
  font-weight: 500;
  color: var(--text-primary);
}

.project-repo {
  font-size: 0.8rem;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
}

.status-badge {
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
}

.status-badge.status-active {
  background: rgba(0, 255, 136, 0.2);
  color: #00ff88;
}

.status-badge.status-archived {
  background: rgba(136, 136, 136, 0.2);
  color: #888;
}

.status-badge.status-planning {
  background: rgba(136, 85, 255, 0.2);
  color: #8855ff;
}

/* Info Grid */
.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
  padding: 20px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-label {
  font-size: 0.75rem;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.info-value {
  font-size: 0.9rem;
  color: var(--text-primary);
}

.info-value.mono {
  font-family: var(--font-mono);
  font-size: 0.8rem;
}

/* Empty State */

.empty-icon {
  width: 48px;
  height: 48px;
  color: var(--text-muted);
  margin-bottom: 12px;
}

.empty-icon svg {
  width: 100%;
  height: 100%;
}

.empty-state span {
  font-size: 0.85rem;
  color: var(--text-tertiary);
}

/* Modal */

.modal {
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  width: 90%;
  max-width: 480px;
  animation: slideUp 0.3s ease;
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.modal-header h3 {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.modal-close {
  width: 32px;
  height: 32px;
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.modal-close:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.modal-close svg {
  width: 18px;
  height: 18px;
}

.modal-description {
  color: var(--text-secondary);
  font-size: 0.9rem;
  margin-bottom: 16px;
}

.empty-modal-state {
  text-align: center;
  padding: 20px;
  color: var(--text-tertiary);
}

.empty-modal-state p {
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.project-select-wrapper {
  position: relative;
}

.project-select {
  width: 100%;
  padding: 12px 40px 12px 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.9rem;
  cursor: pointer;
  appearance: none;
  transition: border-color 0.2s;
}

.project-select:hover,
.project-select:focus {
  border-color: var(--accent-cyan);
  outline: none;
}

.select-arrow {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  width: 18px;
  height: 18px;
  color: var(--text-tertiary);
  pointer-events: none;
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 212, 255, 0.3);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-subtle);
}

.btn-secondary:hover {
  border-color: var(--accent-cyan);
  color: var(--accent-cyan);
}

/* Modal Tabs */
.modal-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 16px;
  background: var(--bg-tertiary);
  padding: 4px;
  border-radius: 8px;
}

.modal-tab {
  flex: 1;
  padding: 8px 12px;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.modal-tab.active {
  background: var(--bg-secondary);
  color: var(--text-primary);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.modal-tab:hover:not(.active) {
  color: var(--text-primary);
}

/* Form elements */
.form-group {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.form-label .required {
  color: var(--accent-crimson, #ff4081);
}

.form-input,
.form-textarea {
  width: 100%;
  padding: 10px 14px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.9rem;
  font-family: inherit;
  transition: border-color 0.2s;
  box-sizing: border-box;
}

.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: var(--accent-cyan);
}

.form-textarea {
  resize: vertical;
  min-height: 60px;
}

.btn-link {
  background: none;
  border: none;
  color: var(--accent-cyan);
  font-size: 0.85rem;
  cursor: pointer;
  padding: 4px 0;
  text-decoration: underline;
}

.btn-link:hover {
  color: var(--text-primary);
}

/* Dashboard Sections */
.dashboard-sections {
  display: flex;
  flex-direction: column;
  gap: 20px;
  margin-top: 4px;
}

/* Owner Agent meta pill */
.meta-pill.agent {
  background: rgba(0, 212, 255, 0.15);
  color: var(--accent-cyan, #00d4ff);
}
</style>
