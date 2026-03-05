<script setup lang="ts">
defineProps<{
  includedTeamsCount: number;
}>();
</script>

<template>
  <!-- Workflow Steps: shows the GitHub harness integration pipeline progress -->
  <div class="workflow-steps">
    <div class="step" :class="{ active: true, completed: includedTeamsCount > 0 }">
      <div class="step-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="8"/>
          <path d="M21 21l-4.35-4.35"/>
        </svg>
      </div>
      <div class="step-info">
        <span class="step-label">Discover</span>
        <span class="step-desc">Load components from GitHub</span>
      </div>
    </div>
    <div class="step-connector"></div>
    <div class="step" :class="{ active: includedTeamsCount > 0, completed: includedTeamsCount > 0 }">
      <div class="step-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/>
        </svg>
      </div>
      <div class="step-info">
        <span class="step-label">Import</span>
        <span class="step-desc">Select components to include</span>
      </div>
    </div>
    <div class="step-connector"></div>
    <div class="step" :class="{ active: includedTeamsCount > 0 }">
      <div class="step-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 20h9M16.5 3.5a2.121 2.121 0 113 3L7 19l-4 1 1-4L16.5 3.5z"/>
        </svg>
      </div>
      <div class="step-info">
        <span class="step-label">Configure</span>
        <span class="step-desc">Customize settings</span>
      </div>
    </div>
    <div class="step-connector"></div>
    <div class="step">
      <div class="step-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M9 11l3 3L22 4"/>
          <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>
        </svg>
      </div>
      <div class="step-info">
        <span class="step-label">Validate</span>
        <span class="step-desc">Check configuration</span>
      </div>
    </div>
    <div class="step-connector"></div>
    <div class="step">
      <div class="step-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
        </svg>
      </div>
      <div class="step-info">
        <span class="step-label">Deploy</span>
        <span class="step-desc">Push to GitHub</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Workflow Steps */
.workflow-steps {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 20px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  margin-bottom: 24px;
  overflow-x: auto;
}

.step {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: var(--bg-tertiary);
  border-radius: 8px;
  border: 1px solid transparent;
  opacity: 0.5;
  transition: all 0.2s;
}

.step.active {
  opacity: 1;
}

.step.completed {
  border-color: var(--accent-emerald);
  background: rgba(0, 255, 136, 0.08);
}

.step-icon {
  width: 32px;
  height: 32px;
  background: var(--bg-elevated);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
}

.step.active .step-icon {
  color: var(--accent-cyan);
}

.step.completed .step-icon {
  background: var(--accent-emerald-dim);
  color: var(--accent-emerald);
}

.step-icon svg {
  width: 16px;
  height: 16px;
}

.step-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.step-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.step-desc {
  font-size: 11px;
  color: var(--text-tertiary);
}

.step-connector {
  width: 24px;
  height: 2px;
  background: var(--border-default);
  flex-shrink: 0;
}
</style>
