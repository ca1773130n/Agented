<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import type { Product, Team } from '../services/api';
import { productApi, teamApi, ApiError } from '../services/api';
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
import { useWebMcpPageTools } from '../composables/useWebMcpPageTools';
import { useTourMachine } from '../composables/useTourMachine';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();

const router = useRouter();
const tourMachine = useTourMachine();
const showToast = useToast();

const products = ref<Product[]>([]);
const teams = ref<Team[]>([]);
const isLoading = ref(true);
const loadError = ref<string | null>(null);
const showCreateModal = ref(false);
const showDeleteConfirm = ref(false);
const productToDelete = ref<Product | null>(null);
const deletingId = ref<string | null>(null);
const { searchQuery, sortField, sortOrder, filteredAndSorted, hasActiveFilter, resultCount, totalCount } = useListFilter({
  items: products,
  searchFields: ['name', 'description'] as (keyof Product)[],
  storageKey: 'products-list-filter',
});

const pagination = usePagination({ defaultPageSize: 25, storageKey: 'products-pagination' });

const sortOptions = [
  { value: 'name', label: t('products.sortName') },
  { value: 'created_at', label: t('products.sortCreated') },
];

const newProduct = ref({ name: '', description: '', status: 'active', owner_team_id: '' });

// Modal overlay refs for Escape key handling
const createModalOverlay = ref<HTMLElement | null>(null);
useFocusTrap(createModalOverlay, showCreateModal);
watch(showCreateModal, (val) => { if (val) nextTick(() => createModalOverlay.value?.focus()); });

useWebMcpPageTools({
  page: 'ProductsPage',
  domain: 'products',
  stateGetter: () => ({
    items: products.value,
    itemCount: products.value.length,
    isLoading: isLoading.value,
    error: loadError.value,
    searchQuery: searchQuery.value,
    sortField: sortField.value,
    sortOrder: sortOrder.value,
    currentPage: pagination.currentPage.value,
    pageSize: pagination.pageSize.value,
    totalCount: pagination.totalCount.value,
  }),
  modalGetter: () => ({
    showCreateModal: showCreateModal.value,
    showDeleteConfirm: showDeleteConfirm.value,
    formValues: newProduct.value,
  }),
  modalActions: {
    openCreate: () => { showCreateModal.value = true; },
    openDelete: (id: string) => {
      const product = products.value.find((p) => p.id === id);
      if (product) { productToDelete.value = product; showDeleteConfirm.value = true; }
    },
  },
  deps: [products, searchQuery, sortField, sortOrder],
});

async function loadProducts() {
  isLoading.value = true;
  loadError.value = null;
  try {
    const [productsData, teamsData] = await Promise.all([
      productApi.list({ limit: pagination.pageSize.value, offset: pagination.offset.value }),
      teamApi.list()
    ]);
    products.value = productsData.products || [];
    if (productsData.total_count != null) pagination.totalCount.value = productsData.total_count;
    teams.value = teamsData.teams || [];
  } catch (e) {
    loadError.value = e instanceof ApiError ? e.message : t('products.loadError');
    showToast(loadError.value, 'error');
  } finally {
    isLoading.value = false;
  }
}

watch([() => pagination.currentPage.value, () => pagination.pageSize.value], () => { loadProducts(); });
watch([searchQuery, sortField, sortOrder], () => { pagination.resetToFirstPage(); });

// Tracks the in-flight create so the modal's submit button is disabled
// while the request is on the wire — prevents double-submit duplicates.
const isCreating = ref(false);
async function createProduct() {
  if (isCreating.value) return;
  if (!newProduct.value.name.trim()) {
    showToast(t('products.nameRequired'), 'error');
    return;
  }
  isCreating.value = true;
  try {
    const result = await productApi.create({
      name: newProduct.value.name,
      description: newProduct.value.description || undefined,
      status: newProduct.value.status,
      owner_team_id: newProduct.value.owner_team_id || undefined
    });
    showToast(t('products.createSuccess'), 'success');
    showCreateModal.value = false;
    newProduct.value = { name: '', description: '', status: 'active', owner_team_id: '' };
    await loadProducts();
    // Advance tour past create_product step and navigate to product detail
    if (tourMachine.isActive.value) {
      const productId = result?.product?.id;
      if (productId) {
        await router.push(`/products/${productId}`);
      }
      tourMachine.nextStep();
    }
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast(t('products.createError'), 'error');
    }
  } finally {
    isCreating.value = false;
  }
}

function confirmDelete(product: Product) {
  productToDelete.value = product;
  showDeleteConfirm.value = true;
}

async function deleteProduct() {
  if (!productToDelete.value) return;
  deletingId.value = productToDelete.value.id;
  try {
    await productApi.delete(productToDelete.value.id);
    showToast(t('products.deleteSuccess', { name: productToDelete.value.name }), 'success');
    showDeleteConfirm.value = false;
    productToDelete.value = null;
    await loadProducts();
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast(t('products.deleteError'), 'error');
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
  loadProducts();
});
</script>

<template>
  <div class="products-page">
    <PageHeader :title="t('products.title')" :subtitle="t('products.subtitle')">
      <template #actions>
        <button class="btn btn-primary" data-tour="create-product" @click="showCreateModal = true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          {{ t('products.createProduct') }}
        </button>
      </template>
    </PageHeader>

    <ListSearchSort
      v-if="!isLoading && !loadError && products.length > 0"
      v-model:searchQuery="searchQuery"
      v-model:sortField="sortField"
      v-model:sortOrder="sortOrder"
      :sort-options="sortOptions"
      :result-count="resultCount"
      :total-count="totalCount"
      :placeholder="t('products.searchPlaceholder')"
    />

    <LoadingState v-if="isLoading" :message="t('products.loading')" />

    <ErrorState v-else-if="loadError" :title="t('products.loadFailed')" :message="loadError" @retry="loadProducts" />

    <EmptyState v-else-if="products.length === 0" :title="t('products.emptyTitle')" :description="t('products.emptyDescription')">
      <template #actions>
        <button class="btn btn-primary" @click="showCreateModal = true">{{ t('products.createFirst') }}</button>
      </template>
    </EmptyState>

    <EmptyState v-else-if="filteredAndSorted.length === 0 && hasActiveFilter" :title="t('products.noMatchTitle')" :description="t('products.noMatchDescription')" />

    <div v-else class="products-grid">
      <router-link
        v-for="product in filteredAndSorted"
        :key="product.id"
        :to="{ name: 'product-dashboard', params: { productId: product.id } }"
        class="product-card clickable"
      >
        <div class="product-header">
          <div class="product-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
            </svg>
          </div>
          <div class="product-info">
            <h3>{{ product.name }}</h3>
            <span class="product-id">{{ product.id }}</span>
          </div>
          <span :class="['status-badge', getStatusClass(product.status)]">{{ product.status }}</span>
        </div>

        <p v-if="product.description" class="product-description">{{ product.description }}</p>

        <div class="product-meta">
          <div v-if="product.owner_team_name" class="meta-item">
            <span class="meta-label">{{ t('products.ownerLabel') }}</span>
            <span class="meta-value">{{ product.owner_team_name }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">{{ t('products.projectsLabel') }}</span>
            <span class="meta-value">{{ product.project_count }}</span>
          </div>
        </div>

        <div class="product-actions">
          <button class="btn btn-small btn-danger" @click.stop="confirmDelete(product)" :disabled="deletingId === product.id">
            <span v-if="deletingId === product.id" class="btn-spinner"></span>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
            </svg>
            {{ deletingId === product.id ? t('products.deleting') : t('common.delete') }}
          </button>
        </div>
      </router-link>
    </div>

    <PaginationBar
      v-if="!isLoading && !loadError && products.length > 0"
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
      <div v-if="showCreateModal" ref="createModalOverlay" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-title-create-product" tabindex="-1" @click.self="showCreateModal = false" @keydown.escape="showCreateModal = false">
        <div class="modal">
          <div class="modal-header">
            <h2 id="modal-title-create-product">{{ t('products.createProduct') }}</h2>
            <button class="modal-close" :aria-label="t('common.close')" @click="showCreateModal = false">&times;</button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label>{{ t('products.productNameLabel') }}</label>
              <input v-model="newProduct.name" type="text" :placeholder="t('products.productNamePlaceholder')" />
            </div>
            <div class="form-group">
              <label>{{ t('products.descriptionLabel') }}</label>
              <textarea v-model="newProduct.description" :placeholder="t('products.descriptionPlaceholder')"></textarea>
            </div>
            <div class="form-group">
              <label>{{ t('products.statusLabel') }}</label>
              <select v-model="newProduct.status">
                <option value="active">{{ t('products.statusActive') }}</option>
                <option value="planning">{{ t('products.statusPlanning') }}</option>
                <option value="archived">{{ t('products.statusArchived') }}</option>
              </select>
            </div>
            <div class="form-group">
              <label>{{ t('products.ownerTeamLabel') }}</label>
              <select v-model="newProduct.owner_team_id">
                <option value="">{{ t('products.noOwner') }}</option>
                <option v-for="team in teams" :key="team.id" :value="team.id">{{ team.name }}</option>
              </select>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showCreateModal = false">{{ t('common.cancel') }}</button>
            <button class="btn btn-primary" :disabled="isCreating" @click="createProduct">
              {{ isCreating ? t('products.creating') : t('products.createProduct') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <ConfirmModal
      :open="showDeleteConfirm"
      :title="t('products.deleteTitle')"
      :message="t('products.deleteConfirm', { name: productToDelete?.name })"
      :confirm-label="t('common.delete')"
      :cancel-label="t('common.cancel')"
      variant="danger"
      @confirm="deleteProduct"
      @cancel="showDeleteConfirm = false"
    />

  </div>
</template>

<style scoped>
.products-page {
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

.products-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 1.5rem;
}

.product-card.clickable {
  cursor: pointer;
}

.product-card {
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

.product-card:hover {
  border-color: var(--accent-amber, #ffaa00);
  box-shadow: 0 0 20px rgba(255, 170, 0, 0.1);
}

.product-header {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 1rem;
}

.product-icon {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--accent-amber, #ffaa00), var(--accent-cyan, #00d4ff));
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.product-icon svg {
  width: 24px;
  height: 24px;
  color: #000;
}

.product-info { flex: 1; min-width: 0; }
.product-info h3 { font-size: 1.1rem; font-weight: 600; margin-bottom: 0.25rem; }
.product-id { font-size: 0.75rem; color: var(--text-secondary, #888); font-family: monospace; }

.status-badge {
  padding: 0.25rem 0.75rem;
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: 500;
}

.status-badge.small { padding: 0.15rem 0.5rem; font-size: 0.7rem; }

.status-active { background: rgba(0, 255, 136, 0.2); color: #00ff88; }
.status-archived { background: rgba(136, 136, 136, 0.2); color: #888; }
.status-planning { background: rgba(136, 85, 255, 0.2); color: #8855ff; }

.product-description {
  color: var(--text-secondary, #888);
  font-size: 0.9rem;
  margin-bottom: 1rem;
  line-height: 1.5;
}

.product-meta {
  display: flex;
  gap: 1.5rem;
  margin-bottom: 1rem;
}

.meta-item { font-size: 0.85rem; }
.meta-label { color: var(--text-secondary, #888); margin-right: 0.5rem; }
.meta-value { color: var(--text-primary, #fff); }

.product-actions {
  display: flex;
  gap: 0.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-default);
}

/* Modal styles - same as TeamsPage */

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

@media (max-width: 480px) {
  .products-grid {
    grid-template-columns: 1fr;
  }
}
</style>
