<script setup lang="ts">
import { ref, onMounted, watch, onUnmounted } from 'vue';
import { Chart, registerables } from 'chart.js';
import type { AuditRecord } from '../../services/api';

Chart.register(...registerables);

const props = defineProps<{
  audits: AuditRecord[];
}>();

const canvasRef = ref<HTMLCanvasElement | null>(null);
let chartInstance: Chart | null = null;

function formatDateShort(dateStr: string): string {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function renderChart() {
  if (!canvasRef.value) return;

  const sorted = [...props.audits].sort((a, b) => a.audit_date.localeCompare(b.audit_date));

  const labels = sorted.map(a => {
    const name = a.project_name || a.project_path || 'Unknown';
    const shortName = name.length > 15 ? name.substring(0, 15) + '...' : name;
    return `${shortName} (${formatDateShort(a.audit_date)})`;
  });

  if (chartInstance) {
    chartInstance.destroy();
  }

  // Design system colors
  const colors = {
    critical: '#ff3366',  // --accent-crimson
    high: '#ffaa00',      // --accent-amber
    medium: '#00d4ff',    // --accent-cyan
    low: '#00ff88',       // --accent-emerald
    grid: 'rgba(255, 255, 255, 0.06)',
    text: 'rgba(255, 255, 255, 0.5)',
    textMuted: 'rgba(255, 255, 255, 0.35)',
  };

  chartInstance = new Chart(canvasRef.value, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'Critical',
          data: sorted.map(a => a.critical),
          backgroundColor: colors.critical,
          borderRadius: 4,
          stack: 'severity',
        },
        {
          label: 'High',
          data: sorted.map(a => a.high),
          backgroundColor: colors.high,
          borderRadius: 4,
          stack: 'severity',
        },
        {
          label: 'Medium',
          data: sorted.map(a => a.medium),
          backgroundColor: colors.medium,
          borderRadius: 4,
          stack: 'severity',
        },
        {
          label: 'Low',
          data: sorted.map(a => a.low),
          backgroundColor: colors.low,
          borderRadius: 4,
          stack: 'severity',
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'top',
          align: 'end',
          labels: {
            color: colors.text,
            usePointStyle: true,
            pointStyle: 'rectRounded',
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
          stacked: true,
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
          stacked: true,
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
watch(() => props.audits, renderChart, { deep: true });

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
