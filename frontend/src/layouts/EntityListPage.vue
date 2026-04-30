<script setup lang="ts" generic="T">
import { onMounted, shallowRef, ref } from 'vue';
import PageLayout from '../components/base/PageLayout.vue';
import PageHeader from '../components/base/PageHeader.vue';
import LoadingState from '../components/base/LoadingState.vue';
import ErrorState from '../components/base/ErrorState.vue';
import EmptyState from '../components/base/EmptyState.vue';

const props = defineProps<{
  title: string;
  subtitle?: string;
  loadItems: () => Promise<T[]>;
  emptyTitle: string;
  emptyDescription?: string;
  loadingMessage?: string;
}>();

const items = shallowRef<T[]>([]);
const isLoading = ref(true);
const error = ref<string | null>(null);

async function refresh() {
  isLoading.value = true;
  error.value = null;
  try {
    items.value = await props.loadItems();
  } catch (err: unknown) {
    const e = err as { message?: string };
    error.value = e?.message || 'Failed to load';
  } finally {
    isLoading.value = false;
  }
}

defineExpose({ refresh });

onMounted(refresh);
</script>

<template>
  <PageLayout>
    <PageHeader :title="title" :subtitle="subtitle">
      <template v-if="$slots.actions" #actions>
        <slot name="actions" :refresh="refresh" />
      </template>
    </PageHeader>

    <LoadingState v-if="isLoading" :message="loadingMessage || 'Loading...'" />

    <ErrorState v-else-if="error" :message="error" @retry="refresh" />

    <EmptyState
      v-else-if="items.length === 0"
      :title="emptyTitle"
      :description="emptyDescription"
    >
      <template v-if="$slots.emptyIcon" #icon>
        <slot name="emptyIcon" />
      </template>
      <template v-if="$slots.emptyActions" #actions>
        <slot name="emptyActions" :refresh="refresh" />
      </template>
    </EmptyState>

    <slot v-else :items="items" :refresh="refresh" />
  </PageLayout>
</template>
