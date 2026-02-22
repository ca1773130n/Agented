<script setup lang="ts">
import { ref, onMounted, watch, onUnmounted } from 'vue';
import { Chart, registerables } from 'chart.js';
import type { PrHistoryPoint } from '../../services/api';

Chart.register(...registerables);

const props = defineProps<{
  history: PrHistoryPoint[];
}>();

const canvasRef = ref<HTMLCanvasElement | null>(null);
let chartInstance: Chart | null = null;

function formatDateShort(dateStr: string): string {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function renderChart() {
  if (!canvasRef.value) return;

  const sorted = [...props.history].sort((a, b) => a.date.localeCompare(b.date));

  const labels = sorted.map(h => formatDateShort(h.date));

  if (chartInstance) {
    chartInstance.destroy();
  }

  // Design system colors
  const colors = {
    created: '#00d4ff',   // --accent-cyan
    merged: '#00ff88',    // --accent-emerald
    closed: '#ffaa00',    // --accent-amber
    grid: 'rgba(255, 255, 255, 0.06)',
    text: 'rgba(255, 255, 255, 0.5)',
    textMuted: 'rgba(255, 255, 255, 0.35)',
  };

  chartInstance = new Chart(canvasRef.value, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Created',
          data: sorted.map(h => h.created),
          borderColor: colors.created,
          backgroundColor: `${colors.created}20`,
          fill: true,
          tension: 0.3,
          pointRadius: 4,
          pointHoverRadius: 6,
        },
        {
          label: 'Merged',
          data: sorted.map(h => h.merged),
          borderColor: colors.merged,
          backgroundColor: `${colors.merged}20`,
          fill: true,
          tension: 0.3,
          pointRadius: 4,
          pointHoverRadius: 6,
        },
        {
          label: 'Closed',
          data: sorted.map(h => h.closed),
          borderColor: colors.closed,
          backgroundColor: `${colors.closed}20`,
          fill: true,
          tension: 0.3,
          pointRadius: 4,
          pointHoverRadius: 6,
        },
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
        legend: {
          position: 'top',
          align: 'end',
          labels: {
            color: colors.text,
            usePointStyle: true,
            pointStyle: 'circle',
            padding: 16,
            font: {
              family: "'Geist Mono', 'SF Mono', monospace",
              size: 11,
            },
          },
        },
        tooltip: {
          backgroundColor: 'rgba(18, 18, 26, 0.95)',
          titleColor: '#f0f0f0',
          bodyColor: 'rgba(255, 255, 255, 0.7)',
          borderColor: 'rgba(255, 255, 255, 0.1)',
          borderWidth: 1,
          cornerRadius: 8,
          padding: 12,
          titleFont: {
            family: "'Geist Mono', 'SF Mono', monospace",
            size: 12,
            weight: 'bold',
          },
          bodyFont: {
            family: "'Geist', sans-serif",
            size: 12,
          },
        },
      },
      scales: {
        x: {
          ticks: {
            color: colors.textMuted,
            maxRotation: 45,
            font: {
              family: "'Geist Mono', 'SF Mono', monospace",
              size: 10,
            },
          },
          grid: {
            color: colors.grid,
          },
          border: {
            display: false,
          },
        },
        y: {
          beginAtZero: true,
          ticks: {
            color: colors.textMuted,
            font: {
              family: "'Geist Mono', 'SF Mono', monospace",
              size: 10,
            },
            stepSize: 1,
          },
          grid: {
            color: colors.grid,
          },
          border: {
            display: false,
          },
        },
      },
      animation: {
        duration: 800,
        easing: 'easeOutQuart',
      },
    },
  });
}

onMounted(renderChart);
watch(() => props.history, renderChart, { deep: true });

onUnmounted(() => {
  if (chartInstance) {
    chartInstance.destroy();
    chartInstance = null;
  }
});
</script>

<template>
  <div class="chart-container">
    <canvas ref="canvasRef"></canvas>
  </div>
</template>

<style scoped>
.chart-container {
  position: relative;
  height: 300px;
  padding: 8px;
}
</style>
