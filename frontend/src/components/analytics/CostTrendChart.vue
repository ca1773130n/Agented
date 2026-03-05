<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue';
import { Chart, registerables } from 'chart.js';
import 'chartjs-adapter-date-fns';
import type { CostDataPoint } from '../../services/api';

Chart.register(...registerables);

const props = defineProps<{
  data: CostDataPoint[];
}>();

const chartRef = ref<HTMLCanvasElement | null>(null);
let chartInstance: Chart | null = null;

const colors = {
  violet: '#8855ff',
  violetBg: 'rgba(136, 85, 255, 0.1)',
  cyan: '#00d4ff',
  emerald: '#00ff88',
  amber: '#ffaa00',
  crimson: '#ff4444',
  grid: 'rgba(255, 255, 255, 0.06)',
  text: 'rgba(255, 255, 255, 0.5)',
  textMuted: 'rgba(255, 255, 255, 0.35)',
};

const entityColors = [colors.violet, colors.cyan, colors.emerald, colors.amber, colors.crimson];

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

  // Group data by entity_id
  const entityMap = new Map<string, CostDataPoint[]>();
  for (const point of props.data) {
    const key = point.entity_id || 'all';
    if (!entityMap.has(key)) entityMap.set(key, []);
    entityMap.get(key)!.push(point);
  }

  const entities = Array.from(entityMap.keys());
  const useMultiLine = entities.length > 1;

  // Collect all unique periods as labels
  const periodSet = new Set<string>();
  for (const point of props.data) periodSet.add(point.period);
  const labels = Array.from(periodSet).sort().map(formatDateShort);
  const periods = Array.from(periodSet).sort();

  const datasets = entities.map((entityId, idx) => {
    const pointMap = new Map<string, number>();
    for (const p of entityMap.get(entityId)!) pointMap.set(p.period, p.total_cost_usd);
    const color = useMultiLine ? entityColors[idx % entityColors.length] : colors.violet;
    return {
      label: useMultiLine ? entityId : 'Cost (USD)',
      data: periods.map(period => pointMap.get(period) ?? 0),
      borderColor: color,
      backgroundColor: `${color}1A`,
      fill: !useMultiLine,
      tension: 0.3,
      borderWidth: 2,
      pointRadius: 4,
      pointHoverRadius: 6,
    };
  });

  chartInstance = new Chart(chartRef.value, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          display: useMultiLine,
          position: 'top',
          align: 'end',
          labels: {
            color: colors.text,
            usePointStyle: true,
            pointStyle: 'circle',
            padding: 16,
            font: { family: "'Geist Mono', 'SF Mono', monospace", size: 11 },
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
          titleFont: { family: "'Geist Mono', 'SF Mono', monospace", size: 12, weight: 'bold' },
          bodyFont: { family: "'Geist', sans-serif", size: 12 },
          callbacks: {
            label: (context: any) => `${context.dataset.label}: $${Number(context.parsed.y).toFixed(2)}`, // eslint-disable-line @typescript-eslint/no-explicit-any -- Chart.js tooltip callback
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
          beginAtZero: true,
          ticks: {
            color: colors.textMuted,
            font: { family: "'Geist Mono', 'SF Mono', monospace", size: 10 },
            callback: (value: string | number) => `$${Number(value).toFixed(2)}`,
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
