<script setup lang="ts">
import { ref, toRef } from 'vue';
import { useFocusTrap } from '../../composables/useFocusTrap';

const props = withDefaults(
  defineProps<{
    open: boolean;
    title?: string;
    message: string;
    confirmLabel?: string;
    cancelLabel?: string;
    variant?: 'danger' | 'default';
  }>(),
  {
    title: 'Confirm',
    confirmLabel: 'Confirm',
    cancelLabel: 'Cancel',
    variant: 'default',
  },
);

const emit = defineEmits<{
  (e: 'confirm'): void;
  (e: 'cancel'): void;
}>();

const confirmModalRef = ref<HTMLElement | null>(null);
const isOpen = toRef(props, 'open');
useFocusTrap(confirmModalRef, isOpen);
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      ref="confirmModalRef"
      class="modal-overlay"
      role="dialog"
      aria-modal="true"
      :aria-labelledby="'confirm-title-' + $.uid"
      tabindex="-1"
      @click.self="emit('cancel')"
      @keydown.escape="emit('cancel')"
    >
      <div class="modal confirm-modal">
        <h2 :id="'confirm-title-' + $.uid" class="confirm-title">{{ title }}</h2>
        <p class="confirm-message">{{ message }}</p>
        <div class="confirm-actions">
          <button class="btn btn-secondary" @click="emit('cancel')">
            {{ cancelLabel }}
          </button>
          <button
            :class="['btn', variant === 'danger' ? 'btn-danger' : 'btn-primary']"
            @click="emit('confirm')"
          >
            {{ confirmLabel }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.confirm-modal {
  max-width: 420px;
  width: 90%;
  text-align: left;
}

.confirm-title {
  font-size: 1.15rem;
  font-weight: 600;
  margin-bottom: 12px;
}

.confirm-message {
  color: var(--text-secondary, #888);
  font-size: 0.95rem;
  line-height: 1.5;
  margin-bottom: 24px;
}

.confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.btn-danger {
  background: var(--accent-crimson-dim, rgba(255, 64, 129, 0.15));
  color: var(--accent-crimson, #ff4081);
  border: 1px solid rgba(255, 64, 129, 0.3);
}

.btn-danger:hover {
  background: var(--accent-crimson, #ff4081);
  color: #fff;
}
</style>
