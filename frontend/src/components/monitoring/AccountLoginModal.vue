<script setup lang="ts">
/**
 * AccountLoginModal -- Stub component for backend account login.
 *
 * TODO: Implement full login flow (created as stub to unblock build).
 */

defineProps<{
  open: boolean
  backendId: string
  backendType: string
  backendName: string
  configPath?: string
}>()

const emit = defineEmits<{
  close: []
  success: []
}>()
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="modal-overlay"
      role="dialog"
      aria-modal="true"
      tabindex="-1"
      @click.self="emit('close')"
      @keydown.escape="emit('close')"
    >
      <div class="modal login-modal">
        <h2 class="modal-title">Login to {{ backendName }}</h2>
        <p class="modal-message">Account login is not yet implemented.</p>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="emit('close')">Close</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.login-modal {
  max-width: 420px;
  width: 90%;
  text-align: left;
}
.modal-title {
  font-size: 1.15rem;
  font-weight: 600;
  margin-bottom: 12px;
}
.modal-message {
  color: var(--text-secondary, #888);
  font-size: 0.95rem;
  line-height: 1.5;
  margin-bottom: 24px;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
</style>
