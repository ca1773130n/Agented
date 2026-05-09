import { onMounted, onUnmounted, ref, watch, type Ref } from 'vue';
import type { MonitoringStatus } from '../services/api';

/**
 * Manages a 10-second interval that recomputes per-window countdown text
 * (e.g. "1d 3h", "5m 22s") for every window in the provided status.
 *
 * Returns a getter that the template can call to look up the text for
 * a given (accountId, windowType) pair.
 */
export function useMonitoringCountdowns(monitoringStatus: Ref<MonitoringStatus | null>) {
  const countdownInterval = ref<ReturnType<typeof setInterval> | null>(null);
  const countdownTexts = ref<Record<string, string>>({});

  function updateCountdowns() {
    const status = monitoringStatus.value;
    if (!status?.windows?.length) return;
    for (const w of status.windows) {
      if (!w.resets_at) continue;
      const key = `${w.account_id}-${w.window_type}`;
      const diffMs = new Date(w.resets_at).getTime() - Date.now();
      let text: string;
      if (diffMs <= 0) {
        text = 'Resetting...';
      } else {
        const totalMin = Math.floor(diffMs / 60000);
        const d = Math.floor(totalMin / 1440);
        const h = Math.floor((totalMin % 1440) / 60);
        const m = totalMin % 60;
        if (h === 0 && m < 5) {
          const totalSec = Math.floor(diffMs / 1000);
          const dispMin = Math.floor(totalSec / 60);
          const dispSec = totalSec % 60;
          text = `${dispMin}m ${dispSec}s`;
        } else if (d > 0) text = h > 0 ? `${d}d ${h}h ${m}m` : `${d}d ${m}m`;
        else if (h > 0) text = m > 0 ? `${h}h ${m}m` : `${h}h`;
        else text = `${m}m`;
      }
      // Only update if changed to avoid unnecessary reactive notifications
      if (countdownTexts.value[key] !== text) {
        countdownTexts.value[key] = text;
      }
    }
  }

  function startCountdowns() {
    if (countdownInterval.value) clearInterval(countdownInterval.value);
    updateCountdowns();
    countdownInterval.value = setInterval(updateCountdowns, 10000);
  }

  onMounted(() => {
    if (monitoringStatus.value?.windows?.length) startCountdowns();
  });

  watch(
    monitoringStatus,
    () => {
      startCountdowns();
    },
    { deep: true },
  );

  onUnmounted(() => {
    if (countdownInterval.value) {
      clearInterval(countdownInterval.value);
      countdownInterval.value = null;
    }
  });

  function getCountdownText(accountId: number, windowType: string): string | undefined {
    return countdownTexts.value[`${accountId}-${windowType}`];
  }

  return { getCountdownText };
}
