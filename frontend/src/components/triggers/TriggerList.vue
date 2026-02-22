<script setup lang="ts">
import type { Trigger, TriggerSource } from '../../services/api';

defineProps<{
  triggers: Trigger[];
  selectedTriggerId: string | null;
  isLoading: boolean;
}>();

const emit = defineEmits<{
  (e: 'selectTrigger', id: string): void;
  (e: 'toggleEnabled', id: string, enabled: number): void;
  (e: 'deleteTrigger', id: string): void;
  (e: 'addTrigger'): void;
}>();

function getTriggerIcon(triggerSource: TriggerSource | string): string {
  switch (triggerSource) {
    case 'webhook':
      return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9"/><path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5"/><circle cx="12" cy="12" r="2"/><path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5"/><path d="M19.1 4.9C23 8.8 23 15.1 19.1 19"/></svg>`;
    case 'github':
      return `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>`;
    case 'manual':
      return `<svg viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>`;
    case 'scheduled':
      return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`;
    default:
      return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/></svg>`;
  }
}

function getTriggerIconClass(triggerSource: TriggerSource | string): string {
  switch (triggerSource) {
    case 'webhook': return 'trigger-icon-webhook';
    case 'github': return 'trigger-icon-github';
    case 'manual': return 'trigger-icon-manual';
    case 'scheduled': return 'trigger-icon-scheduled';
    default: return '';
  }
}

function formatTriggerSource(source: TriggerSource | string): string {
  switch (source) {
    case 'webhook': return 'JSON Webhook';
    case 'github': return 'GitHub Webhook';
    case 'manual': return 'Manual';
    case 'scheduled': return 'Scheduled';
    default: return source;
  }
}

function isBackendInstalled(_backendType: string): boolean {
  // Delegate to parent via prop — for now show badge text only
  return false;
}
</script>

<template>
  <div class="card">
    <div class="card-header">
      <h3>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="4" y="4" width="16" height="16" rx="2"/>
          <circle cx="9" cy="10" r="1.5" fill="currentColor"/>
          <circle cx="15" cy="10" r="1.5" fill="currentColor"/>
          <path d="M9 15h6"/>
        </svg>
        Trigger Registry
      </h3>
      <button class="btn btn-primary" @click="emit('addTrigger')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
        Add Trigger
      </button>
    </div>

    <div v-if="isLoading" class="loading-state">
      <div class="loading-spinner"></div>
      <span>Loading triggers...</span>
    </div>

    <div v-else-if="triggers.length === 0" class="empty-state">
      <div class="empty-icon">&#9671;</div>
      <p>No triggers configured</p>
      <span>Add a trigger to get started</span>
    </div>

    <div v-else class="trigger-list">
      <div
        v-for="(trigger, index) in triggers"
        :key="trigger.id"
        class="trigger-item"
        :class="{ selected: selectedTriggerId === trigger.id, disabled: !trigger.enabled }"
        :style="{ '--delay': `${index * 40}ms` }"
        @click="emit('selectTrigger', trigger.id)"
      >
        <div class="trigger-icon" :class="getTriggerIconClass(trigger.trigger_source)" v-html="getTriggerIcon(trigger.trigger_source)"></div>
        <div class="trigger-info">
          <div class="trigger-name-row">
            <span class="trigger-name">{{ trigger.name }}</span>
            <span v-if="trigger.is_predefined" class="badge predefined">System</span>
            <span v-if="!trigger.enabled" class="badge disabled-badge">Disabled</span>
          </div>
          <div class="trigger-meta">
            <span class="badge trigger-badge" :class="trigger.trigger_source">{{ formatTriggerSource(trigger.trigger_source) }}</span>
            <span v-if="trigger.trigger_source === 'webhook' && trigger.match_field_path" class="meta-item">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/></svg>
              {{ trigger.match_field_path }}={{ trigger.match_field_value }}
            </span>
            <span class="meta-item">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>
              {{ trigger.path_count || 0 }} paths
            </span>
            <span class="badge backend-badge" :class="isBackendInstalled(trigger.backend_type) ? 'available' : 'unavailable'">{{ trigger.backend_type }}</span>
          </div>
        </div>
        <div class="trigger-actions" @click.stop>
          <button class="btn-icon" :class="trigger.enabled ? 'btn-disable' : 'btn-enable'" :title="trigger.enabled ? 'Disable' : 'Enable'" @click="emit('toggleEnabled', trigger.id, trigger.enabled ? 0 : 1)">
            <svg v-if="trigger.enabled" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18.36 6.64a9 9 0 11-12.73 0"/><line x1="12" y1="2" x2="12" y2="12"/></svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polygon points="10,8 16,12 10,16"/></svg>
          </button>
          <button v-if="!trigger.is_predefined" class="btn-icon btn-delete" title="Delete" @click="emit('deleteTrigger', trigger.id)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3,6 5,6 21,6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.card { padding: 24px; }
.card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
.card-header h3 { display: flex; align-items: center; gap: 10px; font-size: 0.95rem; font-weight: 600; color: var(--text-primary); }
.card-header h3 svg { width: 18px; height: 18px; color: var(--accent-cyan); }
.loading-spinner { width: 20px; height: 20px; border: 2px solid var(--border-default); border-top-color: var(--accent-cyan); border-radius: 50%; animation: spin 0.8s linear infinite; }
.empty-icon { font-size: 2.5rem; color: var(--text-muted); margin-bottom: 12px; }
.empty-state span { font-size: 0.85rem; color: var(--text-tertiary); }
.trigger-list { display: flex; flex-direction: column; gap: 8px; }
.trigger-item { display: flex; align-items: center; gap: 16px; padding: 16px 20px; background: var(--bg-primary); border: 1px solid var(--border-subtle); border-radius: 10px; cursor: pointer; transition: all var(--transition-fast); animation: slideIn 0.3s ease backwards; animation-delay: var(--delay, 0ms); }
@keyframes slideIn {
  from { opacity: 0; transform: translateX(-10px); }
  to { opacity: 1; transform: translateX(0); }
}
.trigger-item:hover { border-color: var(--accent-cyan); }
.trigger-item.selected { border-color: var(--accent-cyan); background: var(--bg-tertiary); }
.trigger-item.disabled { opacity: 0.6; }
.trigger-icon { width: 40px; height: 40px; border-radius: 10px; background: linear-gradient(135deg, var(--accent-cyan), var(--accent-violet)); display: flex; align-items: center; justify-content: center; color: white; flex-shrink: 0; }
.trigger-icon :deep(svg) { width: 20px; height: 20px; }
.trigger-icon.trigger-icon-webhook { background: linear-gradient(135deg, var(--accent-cyan), var(--accent-emerald)); }
.trigger-icon.trigger-icon-github { background: linear-gradient(135deg, var(--accent-violet), var(--accent-cyan)); }
.trigger-icon.trigger-icon-manual { background: linear-gradient(135deg, var(--accent-amber), var(--accent-crimson)); }
.trigger-icon.trigger-icon-scheduled { background: linear-gradient(135deg, var(--accent-emerald), var(--accent-cyan)); }
.trigger-info { flex: 1; min-width: 0; }
.trigger-name-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.trigger-name { font-weight: 600; color: var(--text-primary); }
.trigger-meta { display: flex; align-items: center; gap: 16px; margin-top: 6px; flex-wrap: wrap; }
.meta-item { display: flex; align-items: center; gap: 5px; font-size: 0.75rem; color: var(--text-tertiary); }
.meta-item svg { width: 12px; height: 12px; }
.badge { display: inline-flex; align-items: center; padding: 3px 8px; border-radius: 4px; font-size: 0.65rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em; }
.badge.predefined { background: var(--accent-cyan-dim); color: var(--accent-cyan); }
.badge.trigger-badge.webhook { background: var(--accent-cyan-dim); color: var(--accent-cyan); }
.badge.trigger-badge.github { background: var(--accent-violet-dim); color: var(--accent-violet); }
.badge.trigger-badge.manual { background: var(--accent-amber-dim); color: var(--accent-amber); }
.badge.trigger-badge.scheduled { background: var(--accent-emerald-dim); color: var(--accent-emerald); }
.badge.disabled-badge { background: var(--accent-crimson-dim); color: var(--accent-crimson); }
.badge.backend-badge.available { background: var(--accent-emerald-dim); color: var(--accent-emerald); }
.badge.backend-badge.unavailable { background: var(--accent-crimson-dim); color: var(--accent-crimson); }
.trigger-actions { display: flex; gap: 8px; flex-shrink: 0; }
.btn-icon { width: 36px; height: 36px; border-radius: 8px; border: none; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all var(--transition-fast); background: var(--bg-tertiary); color: var(--text-secondary); }
.btn-icon:hover { background: var(--bg-elevated); }
.btn-icon svg { width: 16px; height: 16px; }
.btn-icon.btn-enable { color: var(--accent-emerald); }
.btn-icon.btn-disable { color: var(--accent-amber); }
.btn-icon.btn-delete { color: var(--accent-crimson); }
.btn-icon.btn-delete:hover { background: var(--accent-crimson-dim); }
</style>
