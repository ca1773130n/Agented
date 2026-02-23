<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import type { Product, Team } from '../services/api';
import { productApi, teamApi, ApiError } from '../services/api';
import AppBreadcrumb from '../components/base/AppBreadcrumb.vue';
import PageHeader from '../components/base/PageHeader.vue';
import EntityLayout from '../layouts/EntityLayout.vue';
import { useToast } from '../composables/useToast';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const props = defineProps<{
  productId?: string;
}>();

const route = useRoute();
const router = useRouter();
const productId = computed(() => (route.params.productId as string) || props.productId || '');

const showToast = useToast();

const product = ref<Product | null>(null);
const teams = ref<Team[]>([]);
const isSaving = ref(false);
const selectedOwnerTeamId = ref<string>('');
const editName = ref('');
const originalName = ref('');
const editDescription = ref('');
const originalDescription = ref('');

useWebMcpTool({
  name: 'agented_product_settings_get_state',
  description: 'Returns the current state of the ProductSettingsPage',
  page: 'ProductSettingsPage',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'ProductSettingsPage',
        productId: product.value?.id ?? null,
        productName: product.value?.name ?? null,
        isSaving: isSaving.value,
        editName: editName.value,
        editDescription: editDescription.value,
        selectedOwnerTeamId: selectedOwnerTeamId.value,
        teamsCount: teams.value.length,
      }),
    }],
  }),
  deps: [product, isSaving, editName, editDescription, selectedOwnerTeamId, teams],
});

async function loadData() {
  const [productData, teamsData] = await Promise.all([
    productApi.get(productId.value),
    teamApi.list(),
  ]);
  product.value = productData;
  teams.value = teamsData.teams || [];
  selectedOwnerTeamId.value = product.value.owner_team_id || '';
  editName.value = product.value.name;
  originalName.value = product.value.name;
  editDescription.value = product.value.description || '';
  originalDescription.value = product.value.description || '';
  return product.value;
}

async function saveSettings() {
  if (!product.value) return;
  isSaving.value = true;
  try {
    const updateData: { name?: string; description?: string; owner_team_id?: string } = {};
    if (editName.value !== originalName.value) updateData.name = editName.value;
    if (editDescription.value !== originalDescription.value) updateData.description = editDescription.value;
    if (selectedOwnerTeamId.value !== (product.value?.owner_team_id || '')) updateData.owner_team_id = selectedOwnerTeamId.value || undefined;
    if (Object.keys(updateData).length > 0) {
      await productApi.update(productId.value, updateData);
      originalName.value = editName.value;
      originalDescription.value = editDescription.value;
    }
    showToast('Product settings saved', 'success');
  } catch (err) {
    const message = err instanceof ApiError ? err.message : 'Failed to save settings';
    showToast(message, 'error');
  } finally {
    isSaving.value = false;
  }
}


</script>

<template>
  <EntityLayout :load-entity="loadData" entity-label="product settings">
    <template #default="{ reload: _reload }">
  <div class="settings-page">
    <AppBreadcrumb :items="[
      { label: 'Products', action: () => router.push({ name: 'products' }) },
      { label: product?.name || 'Product', action: () => router.push({ name: 'product-dashboard', params: { productId: productId } }) },
      { label: 'Settings' },
    ]" />

    <template v-if="product">
      <PageHeader :title="(product?.name ?? '') + ' Settings'" subtitle="Configure product settings and ownership" />

      <!-- Product Details Section -->
      <div class="card">
        <div class="card-header">
          <h3>Product Details</h3>
        </div>
        <div class="card-body">
          <div class="form-group">
            <label class="form-label">Name</label>
            <input v-model="editName" type="text" class="settings-input" placeholder="Product name" />
          </div>
          <div class="form-group">
            <label class="form-label">Description</label>
            <textarea v-model="editDescription" class="settings-textarea" placeholder="Product description..." rows="3"></textarea>
          </div>
        </div>
      </div>

      <!-- Owner Team Section -->
      <div class="card">
        <div class="card-header">
          <h3>Owner Team</h3>
        </div>
        <div class="card-body">
          <p class="section-description">Select the team responsible for this product.</p>

          <div v-if="teams.length === 0" class="empty-state">
            <p>No teams available. Create teams first.</p>
          </div>

          <div v-else class="teams-grid">
            <div
              v-for="team in teams"
              :key="team.id"
              class="team-option"
              :class="{ selected: selectedOwnerTeamId === team.id }"
              @click="selectedOwnerTeamId = team.id"
            >
              <div class="team-radio">
                <div v-if="selectedOwnerTeamId === team.id" class="radio-dot"></div>
              </div>
              <div class="team-icon" :style="{ background: team.color }">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                  <circle cx="9" cy="7" r="4"/>
                </svg>
              </div>
              <div class="team-info">
                <span class="team-name">{{ team.name }}</span>
                <span class="team-members">{{ team.member_count }} members</span>
              </div>
            </div>
          </div>

          <button
            v-if="selectedOwnerTeamId"
            class="btn btn-text"
            @click="selectedOwnerTeamId = ''"
          >
            Clear selection
          </button>
        </div>
      </div>

      <!-- Actions -->
      <div class="actions-row">
        <button class="btn btn-secondary" @click="router.push({ name: 'product-dashboard', params: { productId: productId } })">
          Cancel
        </button>
        <button class="btn btn-primary" :disabled="isSaving" @click="saveSettings">
          <span v-if="isSaving">Saving...</span>
          <span v-else>Save Settings</span>
        </button>
      </div>
    </template>
  </div>
    </template>
  </EntityLayout>
</template>

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  gap: 24px;
  max-width: 800px;
  animation: fadeIn 0.4s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
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

.card-header h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.card-body {
  padding: 20px;
}

.section-description {
  color: var(--text-secondary);
  font-size: 0.9rem;
  margin-bottom: 16px;
}

/* Teams Grid */
.teams-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.team-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--bg-tertiary);
  border: 2px solid transparent;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.team-option:hover {
  border-color: var(--border-subtle);
}

.team-option.selected {
  border-color: var(--accent-cyan);
  background: rgba(0, 212, 255, 0.05);
}

.team-radio {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border-subtle);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s;
}

.team-option.selected .team-radio {
  border-color: var(--accent-cyan);
}

.radio-dot {
  width: 10px;
  height: 10px;
  background: var(--accent-cyan);
  border-radius: 50%;
}

.team-icon {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.team-icon svg {
  width: 18px;
  height: 18px;
  color: var(--bg-primary);
}

.team-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.team-name {
  font-weight: 500;
  color: var(--text-primary);
}

.team-members {
  font-size: 0.75rem;
  color: var(--text-tertiary);
}

/* Empty State */

/* Actions */
.actions-row {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
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

.btn-text {
  background: none;
  color: var(--text-tertiary);
  padding: 8px 0;
}

.btn-text:hover {
  color: var(--accent-cyan);
}

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

.settings-input {
  width: 100%;
  max-width: 500px;
  padding: 12px 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.9rem;
  transition: border-color 0.2s;
}

.settings-input:hover,
.settings-input:focus {
  border-color: var(--accent-cyan);
  outline: none;
}

.settings-textarea {
  width: 100%;
  max-width: 500px;
  padding: 12px 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  color: var(--text-primary);
  font-size: 0.9rem;
  font-family: inherit;
  transition: border-color 0.2s;
  resize: vertical;
  min-height: 60px;
}

.settings-textarea:hover,
.settings-textarea:focus {
  border-color: var(--accent-cyan);
  outline: none;
}
</style>
