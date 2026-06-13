<script setup lang="ts">
/**
 * SharedForgeBrowser (REQ-16) — lists shared-forge bindings
 * (listSharedForge) and adopts one into the current project via
 * adoptShared(projectId, bindingId).
 */
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { grdHarnessApi } from '../../../services/api';
import { ApiError } from '../../../services/api';
import type { SharedForgeBinding } from '../../../services/api/grdHarness';
import { useToast } from '../../../composables/useToast';

const props = defineProps<{ projectId: string }>();

const { t } = useI18n();
const showToast = useToast();

const bindings = ref<SharedForgeBinding[]>([]);
const isLoading = ref(true);
const adoptingId = ref<number | null>(null);

async function load() {
  try {
    isLoading.value = true;
    const res = await grdHarnessApi.listSharedForge();
    bindings.value = res.shared || [];
  } catch {
    bindings.value = [];
  } finally {
    isLoading.value = false;
  }
}

async function adopt(bindingId: number) {
  try {
    adoptingId.value = bindingId;
    await grdHarnessApi.adoptShared(props.projectId, bindingId);
    showToast(t('surface.harness.forge.adopted'), 'success');
  } catch (e) {
    const message = e instanceof ApiError ? e.message : t('surface.harness.forge.adoptFailed');
    showToast(message, 'error');
  } finally {
    adoptingId.value = null;
  }
}

onMounted(load);
</script>

<template>
  <div class="forge-browser card">
    <div class="card-header"><h3>{{ t('surface.harness.forge.title') }}</h3></div>
    <div class="card-body">
      <span v-if="isLoading" class="muted">{{ t('surface.harness.forge.loading') }}</span>
      <span v-else-if="bindings.length === 0" class="muted">{{ t('surface.harness.forge.empty') }}</span>
      <ul v-else class="rows">
        <li v-for="b in bindings" :key="String(b.id)" class="row">
          <span class="bid">{{ b.id }}</span>
          <button
            class="btn"
            :disabled="adoptingId === b.id || b.id == null"
            @click="adopt(b.id as number)"
          >
            {{ adoptingId === b.id ? t('surface.harness.forge.adopting') : t('surface.harness.forge.adopt') }}
          </button>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.forge-browser { border: 1px solid var(--border-default); border-radius: 8px; }
.card-header { padding: 1rem 1.25rem; border-bottom: 1px solid var(--border-default); }
.card-header h3 { margin: 0; font-size: 0.95rem; color: var(--text-primary, #fff); }
.card-body { padding: 1rem 1.25rem; }
.rows { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.row { display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 0.75rem; border-radius: 6px; background: var(--bg-tertiary, #1a1a24); }
.bid { color: var(--text-primary, #fff); font-size: 0.85rem; font-family: monospace; }
.muted { color: var(--text-tertiary, #666); font-size: 0.85rem; }
</style>
