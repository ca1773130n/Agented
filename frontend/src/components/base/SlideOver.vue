<script setup lang="ts">
import { ref, toRef } from 'vue';
import ConfirmModal from './ConfirmModal.vue';
import { useFocusTrap } from '../../composables/useFocusTrap';

const props = defineProps<{
  open: boolean;
  title?: string;
  width?: string;
  dirty?: boolean;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
}>();

const panelRef = ref<HTMLElement | null>(null);
const isOpen = toRef(props, 'open');
useFocusTrap(panelRef, isOpen);

const showDiscardConfirm = ref(false);

function tryClose() {
  if (props.dirty) {
    showDiscardConfirm.value = true;
  } else {
    emit('close');
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="slideover">
      <div
        v-if="open"
        ref="panelRef"
        class="slideover-backdrop"
        role="dialog"
        aria-modal="true"
        aria-labelledby="slideover-title"
        @click.self="tryClose"
        @keydown.escape="tryClose"
        tabindex="-1"
      >
        <div class="slideover-panel" :style="{ width: width || '480px' }">
          <div class="slideover-header">
            <h2 v-if="title" id="slideover-title">{{ title }}</h2>
            <span v-else></span>
            <button class="btn-close" @click="tryClose" aria-label="Close panel">&times;</button>
          </div>
          <div class="slideover-body">
            <slot />
          </div>
          <div v-if="$slots.footer" class="slideover-footer">
            <slot name="footer" />
          </div>
        </div>
      </div>
    </Transition>

    <ConfirmModal
      :open="showDiscardConfirm"
      title="Discard Changes?"
      message="You have unsaved changes. Are you sure you want to discard them?"
      confirm-label="Discard"
      cancel-label="Keep Editing"
      variant="danger"
      @confirm="showDiscardConfirm = false; $emit('close')"
      @cancel="showDiscardConfirm = false"
    />
  </Teleport>
</template>

<style scoped>
.slideover-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 900;
  display: flex;
  justify-content: flex-end;
}

.slideover-panel {
  background: var(--bg-secondary, #1a1a2e);
  height: 100%;
  display: flex;
  flex-direction: column;
  box-shadow: -4px 0 24px rgba(0, 0, 0, 0.3);
}

.slideover-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-default);
}

.slideover-header h2 {
  margin: 0;
  font-size: 1.1rem;
  color: var(--text-primary, #e0e0e0);
}

.btn-close {
  background: none;
  border: none;
  color: var(--text-secondary, #8888aa);
  font-size: 1.2rem;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  transition: color 0.15s;
}

.btn-close:hover {
  color: var(--text-primary, #e0e0e0);
}

.slideover-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.slideover-footer {
  padding: 16px 20px;
  border-top: 1px solid var(--border-default);
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

/* Transition: backdrop fades, panel slides */
.slideover-enter-active,
.slideover-leave-active {
  transition: opacity 0.2s ease;
}

.slideover-enter-active .slideover-panel,
.slideover-leave-active .slideover-panel {
  transition: transform 0.2s ease;
}

.slideover-enter-from,
.slideover-leave-to {
  opacity: 0;
}

.slideover-enter-from .slideover-panel,
.slideover-leave-to .slideover-panel {
  transform: translateX(100%);
}
</style>
