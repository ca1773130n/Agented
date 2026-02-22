<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue';
import { Chart, registerables } from 'chart.js';
import type { SnapshotHistoryEntry } from '../../services/api';

Chart.register(...registerables);

const props = withDefaults(defineProps<{
  history: SnapshotHistoryEntry[];
  label: string;
}>(), {
  label: 'Usage Trend',
});

const chartRef = ref<HTMLCanvasElement | null>(null);
let chartInstance: Chart | null = null;

function renderChart() {
  if (!chartRef.value) return;

  if (chartInstance) {
    chartInstance.destroy();
  }

  if (!props.history || props.history.length === 0) {
    return;
  }

  const sorted = [...props.history].sort(
    (a, b) => new Date(a.recorded_at).getTime() - new Date(b.recorded_at).getTime()
  );

  const labels = sorted.map(h => {
    const d = new Date(h.recorded_at);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  });
  const percentages = sorted.map(h => h.percentage);

  // Create threshold line datasets
  const makeThresholdDataset = (value: number, color: string, dashLabel: string) => ({
    label: dashLabel,
    data: Array(sorted.length).fill(value),
    borderColor: color,
    borderDash: [5, 5],
    borderWidth: 1,
    pointRadius: 0,
    pointHoverRadius: 0,
    fill: false,
    tension: 0,
  });

  const colors = {
    line: '#8855ff',
    lineFill: 'rgba(136, 85, 255, 0.15)',
    grid: 'rgba(255, 255, 255, 0.06)',
    text: 'rgba(255, 255, 255, 0.6)',
    textMuted: 'rgba(255, 255, 255, 0.35)',
  };

  chartInstance = new Chart(chartRef.value, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Usage %',
          data: percentages,
          borderColor: colors.line,
          backgroundColor: colors.lineFill,
          borderWidth: 2,
          fill: true,
          tension: 0.3,
          pointRadius: 2,
          pointHoverRadius: 5,
          pointBackgroundColor: colors.line,
        },
        makeThresholdDataset(50, '#3b82f6', '50% Info'),
        makeThresholdDataset(75, '#f59e0b', '75% Warning'),
        makeThresholdDataset(90, '#ef4444', '90% Critical'),
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false,
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(18, 18, 26, 0.95)',
          titleColor: '#f0f0f0',
          bodyColor: 'rgba(255, 255, 255, 0.7)',
          borderColor: 'rgba(255, 255, 255, 0.1)',
          borderWidth: 1,
          cornerRadius: 8,
          padding: 10,
          titleFont: {
            family: "'Geist Mono', 'SF Mono', monospace",
            size: 11,
          },
          bodyFont: {
            family: "'Geist', sans-serif",
            size: 11,
          },
          filter: (tooltipItem) => tooltipItem.datasetIndex === 0,
          callbacks: {
            label: (context) => `Usage: ${(context.parsed.y ?? 0).toFixed(1)}%`,
          },
        },
      },
      scales: {
        x: {
          ticks: {
            color: colors.textMuted,
            maxRotation: 0,
            maxTicksLimit: 8,
            font: {
              family: "'Geist Mono', 'SF Mono', monospace",
              size: 10,
            },
          },
          grid: { color: colors.grid },
          border: { display: false },
        },
        y: {
          beginAtZero: true,
          max: 100,
          ticks: {
            color: colors.textMuted,
            font: {
              family: "'Geist Mono', 'SF Mono', monospace",
              size: 10,
            },
            callback: (value: string | number) => `${value}%`,
          },
          grid: { color: colors.grid },
          border: { display: false },
        },
      },
      animation: {
        duration: 600,
        easing: 'easeOutQuart',
      },
    },
  });
}

onMounted(renderChart);
onUnmounted(() => {
  if (chartInstance) {
    chartInstance.destroy();
    chartInstance = null;
  }
});
watch(() => props.history, renderChart, { deep: true });
</script>

<template>
  <div class="trend-chart-container">
    <div v-if="!history || history.length === 0" class="trend-no-data">
      No data yet
    </div>
    <canvas v-else ref="chartRef"></canvas>
  </div>
</template>

<style scoped>
.trend-chart-container {
  position: relative;
  height: 200px;
  width: 100%;
}

.trend-no-data {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  font-size: 0.85rem;
}
</style>
