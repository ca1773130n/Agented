<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

const props = defineProps<{
  /** Async function that fetches the entity. Throw on not-found. */
  loadEntity: () => Promise<any>;
  /** Label for error messages (e.g., "team", "agent") */
  entityLabel?: string;
}>();

const route = useRoute();
const router = useRouter();
const isLoading = ref(true);
const loadError = ref<string | null>(null);
const entityData = ref<any>(null);

async function load() {
  isLoading.value = true;
  loadError.value = null;
  try {
    entityData.value = await props.loadEntity();
  } catch (err: any) {
    if (err?.status === 404 || err?.message?.includes('not found')) {
      router.replace({ name: 'not-found' });
      return;
    }
    loadError.value = err?.message || `Failed to load ${props.entityLabel || 'entity'}`;
  } finally {
    isLoading.value = false;
  }
}

onMounted(load);

// Re-fetch when the route params change (e.g., navigating between two teams)
watch(() => route.params, load, { deep: true });
</script>

<template>
  <div class="entity-layout">
    <!-- Loading state -->
    <div v-if="isLoading" class="entity-layout__loading">
      <div class="entity-layout__spinner" />
      <span class="entity-layout__loading-text">Loading {{ entityLabel || 'entity' }}...</span>
    </div>
    <!-- Error state -->
    <div v-else-if="loadError" class="entity-layout__error">
      <svg class="entity-layout__error-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <circle cx="12" cy="12" r="10"/>
        <path d="M15 9l-6 6M9 9l6 6"/>
      </svg>
      <p class="entity-layout__error-message">{{ loadError }}</p>
      <div class="entity-layout__error-actions">
        <button class="btn" @click="load">Retry</button>
        <button class="btn" @click="router.back()">Go Back</button>
      </div>
    </div>
    <!-- Content slot (only rendered when entity is loaded) -->
    <slot v-else :entity="entityData" :reload="load" />
  </div>
</template>

<style scoped>
.entity-layout {
  width: 100%;
  height: 100%;
  min-height: 100%;
}

.entity-layout__loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  min-height: 50vh;
  gap: 16px;
}

.entity-layout__spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border-default);
  border-top-color: var(--accent-cyan);
  border-radius: 50%;
  animation: entity-spin 1s linear infinite;
}

@keyframes entity-spin {
  to { transform: rotate(360deg); }
}

.entity-layout__loading-text {
  color: var(--text-tertiary);
  font-size: 14px;
}

.entity-layout__error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  min-height: 50vh;
  text-align: center;
  gap: 16px;
}

.entity-layout__error-icon {
  width: 48px;
  height: 48px;
  color: var(--accent-crimson);
}

.entity-layout__error-message {
  color: var(--text-secondary);
  font-size: 14px;
  max-width: 400px;
  margin: 0;
}

.entity-layout__error-actions {
  display: flex;
  gap: 12px;
  margin-top: 8px;
}
</style>
