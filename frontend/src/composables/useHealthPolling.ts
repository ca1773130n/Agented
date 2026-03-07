import { ref, computed, onUnmounted } from 'vue';
import type { HealthStatus } from '../services/api';
import { healthApi, isAbortError } from '../services/api';

export function useHealthPolling() {
  const isConnected = ref(true);
  const systemHealth = ref<HealthStatus | null>(null);
  const activeExecutionCount = ref(0);
  let healthInterval: ReturnType<typeof setInterval> | null = null;

  // AbortController for cancelling in-flight health polls on unmount
  let abortController = new AbortController();

  async function pollHealth() {
    try {
      const health = await healthApi.readiness();
      if (abortController.signal.aborted) return;
      systemHealth.value = health;
      activeExecutionCount.value =
        health.components?.process_manager?.active_executions ?? 0;
      isConnected.value = true;
    } catch (err) {
      if (isAbortError(err) || abortController.signal.aborted) return;
      systemHealth.value = {
        status: 'error',
        components: {
          database: { status: 'error' },
          process_manager: { status: 'error', active_executions: 0, active_execution_ids: [] },
        },
      };
      activeExecutionCount.value = 0;
      isConnected.value = false;
    }
  }

  const healthColor = computed(() => {
    if (!systemHealth.value) return 'var(--text-tertiary)';
    switch (systemHealth.value.status) {
      case 'ok':
        return 'var(--accent-emerald)';
      case 'degraded':
        return 'var(--accent-amber)';
      default:
        return 'var(--accent-crimson)';
    }
  });

  const healthTooltip = computed(() => {
    if (!systemHealth.value) return 'Checking system health...';
    const db = systemHealth.value.components?.database;
    const pm = systemHealth.value.components?.process_manager;
    const parts: string[] = [];
    if (db) parts.push(`DB: ${db.status}${db.journal_mode ? ` (${db.journal_mode})` : ''}`);
    if (pm) parts.push(`Active: ${pm.active_executions}`);
    return parts.join(' | ');
  });

  function startPolling(intervalMs = 10000) {
    pollHealth();
    healthInterval = setInterval(pollHealth, intervalMs);
  }

  function stopPolling() {
    if (healthInterval) clearInterval(healthInterval);
  }

  onUnmounted(() => {
    stopPolling();
    abortController.abort();
  });

  return {
    isConnected,
    systemHealth,
    activeExecutionCount,
    healthColor,
    healthTooltip,
    pollHealth,
    startPolling,
    stopPolling,
  };
}
