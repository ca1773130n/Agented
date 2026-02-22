<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue';
import { Chart, registerables } from 'chart.js';
import 'chartjs-adapter-date-fns';
import type { SnapshotHistoryEntry } from '../../services/api';

Chart.register(...registerables);

const props = withDefaults(defineProps<{
  history: SnapshotHistoryEntry[];
  label: string;
  resetsAt: string | null;
  timeRangeStart?: string;
  timeRangeEnd?: string;
  ratePerHour?: number;
}>(), {
  label: 'Remaining Capacity',
  resetsAt: null,
  timeRangeStart: '',
  timeRangeEnd: '',
});

const chartRef = ref<HTMLCanvasElement | null>(null);
let chartInstance: Chart | null = null;

function renderChart() {
  if (!chartRef.value) return;
  if (chartInstance) {
    chartInstance.destroy();
  }
  if (!props.history?.length) return;

  const sorted = [...props.history].sort(
    (a, b) => new Date(a.recorded_at).getTime() - new Date(b.recorded_at).getTime()
  );

  const data = sorted.map(h => ({
    x: new Date(h.recorded_at).getTime(),
    y: Math.max(0, 100 - h.percentage),
  }));

  const datasets: any[] = [
    {
      label: 'Remaining %',
      data,
      borderColor: '#10b981',
      backgroundColor: 'rgba(16, 185, 129, 0.12)',
      borderWidth: 2,
      fill: true,
      tension: 0.3,
      pointRadius: 1,
      pointHoverRadius: 4,
      pointBackgroundColor: '#10b981',
    },
  ];

  // Projected dotted line (rate is usage %/hr, so remaining decreases when rate > 0)
  if (props.ratePerHour != null && data.length >= 2) {
    const lastPt = data[data.length - 1];
    const projectionDuration = 2 * 3600000; // 2 hours
    const steps = 12;
    const stepMs = projectionDuration / steps;
    const projData: { x: number; y: number }[] = [{ x: lastPt.x, y: lastPt.y }];
    for (let i = 1; i <= steps; i++) {
      const t = lastPt.x + stepMs * i;
      // remaining = 100 - usage, so remaining drops when usage rate is positive
      const y = lastPt.y - (props.ratePerHour * (stepMs * i) / 3600000);
      // Clamp to 0-100 range
      if (y <= 0) {
        if (props.ratePerHour > 0) {
          const msToZero = (lastPt.y / props.ratePerHour) * 3600000;
          projData.push({ x: lastPt.x + msToZero, y: 0 });
        }
        break;
      }
      if (y > 100) {
        if (props.ratePerHour < 0) {
          const msTo100 = ((100 - lastPt.y) / Math.abs(props.ratePerHour)) * 3600000;
          projData.push({ x: lastPt.x + msTo100, y: 100 });
        }
        break;
      }
      projData.push({ x: t, y });
    }

    datasets.push({
      label: 'Projected',
      data: projData,
      borderColor: 'rgba(16, 185, 129, 0.5)',
      backgroundColor: 'transparent',
      borderWidth: 2,
      borderDash: [6, 4],
      fill: false,
      tension: 0,
      pointRadius: 0,
      pointHoverRadius: 3,
      pointBackgroundColor: 'rgba(16, 185, 129, 0.5)',
      spanGaps: true,
    });
  }

  // x-axis bounds are computed by the parent (MonitoringSection) so both
  // "All Windows Usage" and "Remaining Capacity" share the same time axis.
  const xMin = props.timeRangeStart ? new Date(props.timeRangeStart).getTime() : undefined;
  const xMax = props.timeRangeEnd ? new Date(props.timeRangeEnd).getTime() : undefined;

  const colors = {
    grid: 'rgba(255, 255, 255, 0.06)',
    textMuted: 'rgba(255, 255, 255, 0.35)',
  };

  // Vertical reset line plugin — drawn directly on canvas, no tooltip interference
  const resetLinePlugin = {
    id: 'resetLine',
    afterDraw(chart: Chart) {
      if (!props.resetsAt) return;
      const resetTime = new Date(props.resetsAt).getTime();
      const xScale = chart.scales.x;
      const yScale = chart.scales.y;
      const x = xScale.getPixelForValue(resetTime);
      if (x < xScale.left || x > xScale.right) return;
      const ctx = chart.ctx;
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(x, yScale.top);
      ctx.lineTo(x, yScale.bottom);
      ctx.strokeStyle = 'rgba(234, 179, 8, 0.5)';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([6, 4]);
      ctx.stroke();
      // Label
      ctx.fillStyle = 'rgba(234, 179, 8, 0.7)';
      ctx.font = "10px 'Geist Mono', 'SF Mono', monospace";
      ctx.textAlign = 'center';
      ctx.fillText('Reset', x, yScale.top - 4);
      ctx.restore();
    },
  };

  chartInstance = new Chart(chartRef.value, {
    type: 'line',
    data: { datasets },
    plugins: [resetLinePlugin],
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
          padding: 10,
          titleFont: { family: "'Geist Mono', 'SF Mono', monospace", size: 11 },
          bodyFont: { family: "'Geist', sans-serif", size: 11 },
          callbacks: {
            label: (context) => {
              const suffix = context.dataset.borderDash ? ' (est.)' : '';
              return `Remaining${suffix}: ${(context.parsed.y ?? 0).toFixed(1)}%`;
            },
          },
        },
      },
      scales: {
        x: {
          type: 'time',
          min: xMin,
          max: xMax,
          time: {
            displayFormats: {
              minute: 'HH:mm',
              hour: 'M/d HH:mm',
              day: 'M/d',
              week: 'M/d',
            },
          },
          ticks: {
            color: colors.textMuted,
            maxRotation: 0,
            maxTicksLimit: 8,
            font: { family: "'Geist Mono', 'SF Mono', monospace", size: 10 },
          },
          grid: { color: colors.grid },
          border: { display: false },
        },
        y: {
          beginAtZero: true,
          max: 100,
          ticks: {
            color: colors.textMuted,
            font: { family: "'Geist Mono', 'SF Mono', monospace", size: 10 },
            callback: (value: string | number) => `${value}%`,
          },
          grid: { color: colors.grid },
          border: { display: false },
        },
      },
      animation: { duration: 600, easing: 'easeOutQuart' },
    },
  });
}

onMounted(() => nextTick(renderChart));
onUnmounted(() => {
  if (chartInstance) {
    chartInstance.destroy();
    chartInstance = null;
  }
});
watch(() => [props.history, props.resetsAt, props.timeRangeStart, props.timeRangeEnd, props.ratePerHour], renderChart, { deep: true });
</script>

<template>
  <div class="remaining-chart-container">
    <div class="remaining-chart-header">
      <span class="remaining-chart-label">{{ label }}</span>
      <span v-if="resetsAt" class="remaining-reset-tag">
        Reset: {{ new Date(resetsAt).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }) }}
      </span>
    </div>
    <div v-if="!history?.length" class="chart-no-data">
      No data yet
    </div>
    <canvas v-else ref="chartRef"></canvas>
  </div>
</template>

<style scoped>
.remaining-chart-container {
  position: relative;
  height: 200px;
  width: 100%;
}

.remaining-chart-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.remaining-chart-label {
  font-size: 0.7rem;
  color: rgba(255, 255, 255, 0.5);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.remaining-reset-tag {
  font-family: var(--font-mono);
  font-size: 0.65rem;
  color: var(--accent-cyan);
  padding: 2px 8px;
  border-radius: 8px;
  background: var(--accent-cyan-dim);
}

.chart-no-data {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  font-size: 0.85rem;
}
</style>
