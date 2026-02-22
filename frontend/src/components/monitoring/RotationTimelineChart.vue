<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue';
import { Chart, registerables } from 'chart.js';
import 'chartjs-adapter-date-fns';
import type { RotationEvent } from '../../services/api';

Chart.register(...registerables);

interface Props {
  events: RotationEvent[];
}

const props = defineProps<Props>();

const chartCanvas = ref<HTMLCanvasElement | null>(null);
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let chartInstance: Chart<any> | null = null;

const statusColors: Record<string, string> = {
  completed: '#22c55e',
  failed: '#ef4444',
  pending: '#eab308',
  skipped: '#6b7280',
};

function getUniqueAccountNames(events: RotationEvent[]): string[] {
  const names = new Set<string>();
  for (const e of events) {
    if (e.from_account_name) names.add(e.from_account_name);
    if (e.to_account_name) names.add(e.to_account_name);
  }
  return [...names].sort();
}

function buildChart() {
  if (!chartCanvas.value || !props.events.length) {
    if (chartInstance) {
      chartInstance.destroy();
      chartInstance = null;
    }
    return;
  }

  if (chartInstance) {
    chartInstance.destroy();
    chartInstance = null;
  }

  const accountLabels = getUniqueAccountNames(props.events);

  // Group events by status
  const grouped: Record<string, { x: number; y: string; meta: RotationEvent }[]> = {};
  for (const event of props.events) {
    const status = event.rotation_status || 'other';
    if (!grouped[status]) grouped[status] = [];
    grouped[status].push({
      x: new Date(event.created_at).getTime(),
      y: event.to_account_name,
      meta: event,
    });
  }

  const datasets = Object.entries(grouped).map(([status, points]) => ({
    label: status.charAt(0).toUpperCase() + status.slice(1),
    data: points as any[],
    backgroundColor: statusColors[status] || '#6b7280',
    borderColor: statusColors[status] || '#6b7280',
    pointRadius: 6,
    pointHoverRadius: 8,
    showLine: false,
  }));

  // Use 'as any' for Chart constructor because scatter with categorical Y-axis
  // uses string y-values which Chart.js supports at runtime but not in its types
  chartInstance = new Chart(chartCanvas.value as HTMLCanvasElement, {
    type: 'scatter' as const,
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          type: 'time',
          time: {
            tooltipFormat: 'MMM d, HH:mm',
            unit: 'hour',
          },
          title: {
            display: true,
            text: 'Time',
            color: '#a1a1aa',
            font: { family: "'Geist', sans-serif", size: 11 },
          },
          ticks: {
            color: 'rgba(255, 255, 255, 0.35)',
            maxRotation: 0,
            maxTicksLimit: 8,
            font: { family: "'Geist Mono', 'SF Mono', monospace", size: 10 },
          },
          grid: { color: 'rgba(255, 255, 255, 0.06)' },
          border: { display: false },
        },
        y: {
          type: 'category',
          labels: accountLabels,
          title: {
            display: true,
            text: 'Account',
            color: '#a1a1aa',
            font: { family: "'Geist', sans-serif", size: 11 },
          },
          ticks: {
            color: 'rgba(255, 255, 255, 0.6)',
            font: { family: "'Geist', sans-serif", size: 11 },
          },
          grid: { color: 'rgba(255, 255, 255, 0.06)' },
          border: { display: false },
        },
      },
      plugins: {
        tooltip: {
          backgroundColor: 'rgba(18, 18, 26, 0.95)',
          titleColor: '#f0f0f0',
          bodyColor: 'rgba(255, 255, 255, 0.7)',
          borderColor: 'rgba(255, 255, 255, 0.1)',
          borderWidth: 1,
          cornerRadius: 8,
          padding: 10,
          titleFont: { family: "'Geist Mono', 'SF Mono', monospace", size: 11 },
          bodyFont: { family: "'Geist', sans-serif", size: 11 },
          callbacks: {
            title: (items) => {
              const raw = items[0]?.raw as { meta: RotationEvent } | undefined;
              if (!raw?.meta) return '';
              return new Date(raw.meta.created_at).toLocaleString();
            },
            label: (ctx) => {
              const raw = ctx.raw as { meta: RotationEvent } | undefined;
              if (!raw?.meta) return '';
              const event = raw.meta;
              return [
                `From: ${event.from_account_name}`,
                `To: ${event.to_account_name}`,
                `Reason: ${event.reason || 'N/A'}`,
                `Status: ${event.rotation_status}`,
                `Urgency: ${event.urgency}`,
                event.utilization_at_rotation != null ? `Utilization: ${event.utilization_at_rotation}%` : '',
              ].filter(Boolean);
            },
          },
        },
        legend: {
          display: true,
          position: 'top',
          labels: {
            color: '#a1a1aa',
            boxWidth: 12,
            padding: 12,
            font: { family: "'Geist', sans-serif", size: 11 },
          },
        },
      },
      animation: { duration: 600, easing: 'easeOutQuart' },
    },
  });
}

onMounted(buildChart);
onUnmounted(() => {
  if (chartInstance) {
    chartInstance.destroy();
    chartInstance = null;
  }
});
watch(() => props.events, buildChart, { deep: true });
</script>

<template>
  <div class="rotation-timeline-container">
    <div v-if="!events.length" class="timeline-empty">
      No rotation events recorded yet
    </div>
    <canvas v-else ref="chartCanvas"></canvas>
  </div>
</template>

<style scoped>
.rotation-timeline-container {
  position: relative;
  height: 280px;
  width: 100%;
  background: var(--bg-tertiary, #1a1a2e);
  border-radius: 10px;
  padding: 1rem;
}

.timeline-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted, #6b7280);
  font-size: 0.85rem;
}
</style>
