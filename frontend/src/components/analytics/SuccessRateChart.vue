<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue';
import { Chart, registerables } from 'chart.js';
import type { Plugin as ChartPlugin } from 'chart.js';
import 'chartjs-adapter-date-fns';
import type { ExecutionDataPoint } from '../../services/api';

Chart.register(...registerables);

const props = defineProps<{
  data: ExecutionDataPoint[];
}>();

const chartRef = ref<HTMLCanvasElement | null>(null);
let chartInstance: Chart | null = null;

const colors = {
  cyan: '#00d4ff',
  cyanBg: 'rgba(0, 212, 255, 0.1)',
  baseline: 'rgba(255, 255, 255, 0.15)',
  grid: 'rgba(255, 255, 255, 0.06)',
  text: 'rgba(255, 255, 255, 0.5)',
  textMuted: 'rgba(255, 255, 255, 0.35)',
};

// Custom plugin to draw the 80% baseline reference line
const baselinePlugin: ChartPlugin = {
  id: 'successRateBaseline',
  afterDraw(chart) {
    const yScale = chart.scales['y'];
    if (!yScale) return;
    const y = yScale.getPixelForValue(80);
    const ctx = chart.ctx;
    ctx.save();
    ctx.beginPath();
    ctx.setLineDash([6, 4]);
    ctx.strokeStyle = colors.baseline;
    ctx.lineWidth = 1;
    ctx.moveTo(chart.chartArea.left, y);
    ctx.lineTo(chart.chartArea.right, y);
    ctx.stroke();
    // Label
    ctx.fillStyle = colors.textMuted;
    ctx.font = "10px 'Geist Mono', 'SF Mono', monospace";
    ctx.textAlign = 'right';
    ctx.fillText('80% baseline', chart.chartArea.right - 4, y - 4);
    ctx.restore();
  },
};

function formatDateShort(dateStr: string): string {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function renderChart() {
  if (!chartRef.value) return;
  if (chartInstance) {
    chartInstance.destroy();
    chartInstance = null;
  }

  const sorted = [...props.data].sort((a, b) => a.period.localeCompare(b.period));
  const labels = sorted.map(d => formatDateShort(d.period));
  const rateData = sorted.map(d =>
    d.total_executions > 0 ? (d.success_count / d.total_executions) * 100 : 0
  );

  chartInstance = new Chart(chartRef.value, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Success Rate (%)',
          data: rateData,
          borderColor: colors.cyan,
          backgroundColor: colors.cyanBg,
          fill: true,
          tension: 0.3,
          borderWidth: 2,
          pointRadius: 4,
          pointHoverRadius: 6,
        },
      ],
    },
    plugins: [baselinePlugin],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(18, 18, 26, 0.95)',
          titleColor: '#f0f0f0',
          bodyColor: 'rgba(255, 255, 255, 0.7)',
          borderColor: 'rgba(255, 255, 255, 0.1)',
          borderWidth: 1,
          cornerRadius: 8,
          padding: 12,
          titleFont: { family: "'Geist Mono', 'SF Mono', monospace", size: 12, weight: 'bold' },
          bodyFont: { family: "'Geist', sans-serif", size: 12 },
          callbacks: {
            label: (context: any) => `Success Rate: ${Number(context.parsed.y).toFixed(1)}%`, // eslint-disable-line @typescript-eslint/no-explicit-any -- Chart.js tooltip callback
          },
        },
      },
      scales: {
        x: {
          ticks: {
            color: colors.textMuted,
            maxRotation: 45,
            font: { family: "'Geist Mono', 'SF Mono', monospace", size: 10 },
          },
          grid: { color: colors.grid },
          border: { display: false },
        },
        y: {
          min: 0,
          max: 100,
          ticks: {
            color: colors.textMuted,
            font: { family: "'Geist Mono', 'SF Mono', monospace", size: 10 },
            callback: (value: string | number) => `${value}%`,
            stepSize: 20,
          },
          grid: { color: colors.grid },
          border: { display: false },
        },
      },
      animation: { duration: 800, easing: 'easeOutQuart' },
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
watch(() => props.data, renderChart, { deep: true });
</script>

<template>
  <div class="chart-container">
    <canvas ref="chartRef"></canvas>
  </div>
</template>

<style scoped>
.chart-container {
  position: relative;
  height: 300px;
  padding: 8px;
}
</style>
