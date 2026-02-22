<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue';
import { Chart, registerables } from 'chart.js';
import type { UsageSummaryEntry } from '../../services/api';

Chart.register(...registerables);

const props = withDefaults(defineProps<{
  data: UsageSummaryEntry[];
  title?: string;
  chartType?: 'bar' | 'line';
}>(), {
  title: 'Cost Trend',
  chartType: 'bar',
});

const chartRef = ref<HTMLCanvasElement | null>(null);
let chartInstance: Chart | null = null;

function formatDateShort(dateStr: string): string {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatCurrency(value: number): string {
  return `$${value.toFixed(2)}`;
}

function renderChart() {
  if (!chartRef.value) return;

  const sorted = [...props.data].sort((a, b) => a.period_start.localeCompare(b.period_start));

  const labels = sorted.map(d => formatDateShort(d.period_start));

  if (chartInstance) {
    chartInstance.destroy();
  }

  const colors = {
    cost: '#8855ff',          // --accent-violet
    costBg: 'rgba(136, 85, 255, 0.3)',
    executions: '#00d4ff',    // --accent-cyan
    grid: 'rgba(255, 255, 255, 0.06)',
    text: 'rgba(255, 255, 255, 0.5)',
    textMuted: 'rgba(255, 255, 255, 0.35)',
  };

  const costDataset: any = {
    label: 'Cost (USD)',
    data: sorted.map(d => d.total_cost_usd),
    backgroundColor: colors.costBg,
    borderColor: colors.cost,
    borderWidth: 2,
    borderRadius: props.chartType === 'bar' ? 4 : 0,
    yAxisID: 'y',
  };

  if (props.chartType === 'line') {
    costDataset.fill = true;
    costDataset.tension = 0.3;
    costDataset.pointRadius = 4;
    costDataset.pointHoverRadius = 6;
  }

  const executionDataset: any = {
    label: 'Executions',
    data: sorted.map(d => d.execution_count),
    borderColor: colors.executions,
    backgroundColor: `${colors.executions}20`,
    borderWidth: 2,
    borderDash: [5, 5],
    type: 'line' as const,
    fill: false,
    tension: 0.3,
    pointRadius: 3,
    pointHoverRadius: 5,
    yAxisID: 'y1',
  };

  chartInstance = new Chart(chartRef.value, {
    type: props.chartType,
    data: {
      labels,
      datasets: [costDataset, executionDataset],
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
          callbacks: {
            label: (context: any) => {
              const dataIndex = context.dataIndex;
              const entry = sorted[dataIndex];
              if (context.dataset.label === 'Cost (USD)') {
                return `Cost: ${formatCurrency(entry.total_cost_usd)}`;
              }
              return `Executions: ${entry.execution_count}`;
            },
            afterBody: (contexts: any[]) => {
              const dataIndex = contexts[0]?.dataIndex;
              if (dataIndex == null) return '';
              const entry = sorted[dataIndex];
              if (entry.execution_count > 0) {
                const avg = entry.total_cost_usd / entry.execution_count;
                return `Avg/execution: ${formatCurrency(avg)}`;
              }
              return '';
            },
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
          position: 'left',
          ticks: {
            color: colors.textMuted,
            font: {
              family: "'Geist Mono', 'SF Mono', monospace",
              size: 10,
            },
            callback: (value: any) => `$${Number(value).toFixed(2)}`,
          },
          grid: {
            color: colors.grid,
          },
          border: {
            display: false,
          },
        },
        y1: {
          beginAtZero: true,
          position: 'right',
          ticks: {
            color: colors.textMuted,
            font: {
              family: "'Geist Mono', 'SF Mono', monospace",
              size: 10,
            },
            stepSize: 1,
          },
          grid: {
            drawOnChartArea: false,
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
onUnmounted(() => {
  if (chartInstance) {
    chartInstance.destroy();
    chartInstance = null;
  }
});
watch(() => [props.data, props.chartType], renderChart, { deep: true });
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
