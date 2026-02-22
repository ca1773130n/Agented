<script setup lang="ts">
import type { BackendCheck } from '../../services/api';

defineProps<{
  claudeStatus: BackendCheck | null;
  opencodeStatus: BackendCheck | null;
}>();
</script>

<template>
  <div class="card">
    <div class="card-header">
      <h3>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="2" y="6" width="20" height="12" rx="2"/>
          <path d="M6 10h.01M10 10h.01M6 14h.01M10 14h.01M14 10h4M14 14h4"/>
        </svg>
        Backend Status
      </h3>
    </div>
    <div class="backend-grid">
      <div class="backend-card" :class="{ active: claudeStatus?.installed }">
        <div class="backend-icon claude">
          <svg viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.94-.49-7-3.85-7-7.93s3.06-7.44 7-7.93v15.86zm2-15.86c3.94.49 7 3.85 7 7.93s-3.06 7.44-7 7.93V4.07z"/>
          </svg>
        </div>
        <div class="backend-info">
          <div class="backend-name">Claude CLI</div>
          <div class="backend-version">
            {{ claudeStatus?.installed ? (claudeStatus.version || 'Installed') : 'Not installed' }}
          </div>
        </div>
        <div class="backend-status-dot" :class="{ active: claudeStatus?.installed }"></div>
      </div>
      <div class="backend-card" :class="{ active: opencodeStatus?.installed }">
        <div class="backend-icon opencode">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <polyline points="16,18 22,12 16,6"/>
            <polyline points="8,6 2,12 8,18"/>
          </svg>
        </div>
        <div class="backend-info">
          <div class="backend-name">OpenCode CLI</div>
          <div class="backend-version">
            {{ opencodeStatus?.installed ? (opencodeStatus.version || 'Installed') : 'Not installed' }}
          </div>
        </div>
        <div class="backend-status-dot" :class="{ active: opencodeStatus?.installed }"></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.card { padding: 24px; }
.card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
.card-header h3 { display: flex; align-items: center; gap: 10px; font-size: 0.95rem; font-weight: 600; color: var(--text-primary); }
.card-header h3 svg { width: 18px; height: 18px; color: var(--accent-cyan); }
.backend-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; }
.backend-card { display: flex; align-items: center; gap: 16px; padding: 20px; background: var(--bg-primary); border: 1px solid var(--border-subtle); border-radius: 10px; transition: border-color var(--transition-fast); }
.backend-card.active { border-color: var(--accent-emerald); }
.backend-icon { width: 44px; height: 44px; border-radius: 10px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.backend-icon svg { width: 22px; height: 22px; }
.backend-icon.claude { background: var(--accent-cyan-dim); color: var(--accent-cyan); }
.backend-icon.opencode { background: var(--accent-violet-dim); color: var(--accent-violet); }
.backend-info { flex: 1; }
.backend-name { font-weight: 600; color: var(--text-primary); font-size: 0.9rem; }
.backend-version { font-size: 0.8rem; color: var(--text-tertiary); font-family: var(--font-mono); margin-top: 2px; }
.backend-status-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--text-muted); flex-shrink: 0; }
.backend-status-dot.active { background: var(--accent-emerald); box-shadow: 0 0 10px var(--accent-emerald); }
</style>
