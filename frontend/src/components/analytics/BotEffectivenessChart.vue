<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue';
import { Chart, registerables } from 'chart.js';
import 'chartjs-adapter-date-fns';
import type { EffectivenessOverTimePoint } from '../../services/api';

Chart.register(...registerables);

const props = defineProps<{
  summary: {
    accepted: number;
    ignored: number;
    pending: number;
    acceptance_rate: number;
  };
  overTime: EffectivenessOverTimePoint[];
}>();

const doughnutRef = ref<HTMLCanvasElement | null>(null);
const lineRef = ref<HTMLCanvasElement | null>(null);
let doughnutInstance: Chart | null = null;
let lineInstance: Chart | null = null;

const colors = {
  emerald: '#00ff88',
  crimson: '#ff4444',
  amber: '#ffaa00',
  violet: '#8855ff',
  violetBg: 'rgba(136, 85, 255, 0.1)',
  grid: 'rgba(255, 255, 255, 0.06)',
  text: 'rgba(255, 255, 255, 0.5)',
  textMuted: 'rgba(255, 255, 255, 0.35)',
};

function formatDateShort(dateStr: string): string {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function renderDoughnut() {
  if (!doughnutRef.value) return;
  if (doughnutInstance) {
    doughnutInstance.destroy();
    doughnutInstance = null;
  }

  doughnutInstance = new Chart(doughnutRef.value, {
    type: 'doughnut',
    data: {
      labels: ['Accepted', 'Ignored', 'Pending'],
      datasets: [{
        data: [props.summary.accepted, props.summary.ignored, props.summary.pending],
        backgroundColor: [colors.emerald, colors.crimson, colors.amber],
        borderColor: 'transparent',
        borderWidth: 0,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '70%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            color: colors.text,
            usePointStyle: true,
            pointStyle: 'circle',
            padding: 12,
            font: { family: "'Geist Mono', 'SF Mono', monospace", size: 10 },
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
        },
      },
      animation: { duration: 800, easing: 'easeOutQuart' },
    },
  });
}

function renderLine() {
  if (!lineRef.value) return;
  if (lineInstance) {
    lineInstance.destroy();
    lineInstance = null;
  }

  const sorted = [...props.overTime].sort((a, b) => a.period.localeCompare(b.period));
  const labels = sorted.map(d => formatDateShort(d.period));

  lineInstance = new Chart(lineRef.value, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Acceptance Rate (%)',
        data: sorted.map(d => d.acceptance_rate * 100),
        borderColor: colors.violet,
        backgroundColor: colors.violetBg,
        fill: true,
        tension: 0.3,
        borderWidth: 2,
        pointRadius: 3,
        pointHoverRadius: 5,
      }],
    },
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
            label: (context: any) => `Acceptance: ${Number(context.parsed.y).toFixed(1)}%`, // eslint-disable-line @typescript-eslint/no-explicit-any -- Chart.js tooltip callback
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
            stepSize: 25,
          },
          grid: { color: colors.grid },
          border: { display: false },
        },
      },
      animation: { duration: 800, easing: 'easeOutQuart' },
    },
  });
}

function renderCharts() {
  renderDoughnut();
  renderLine();
}

onMounted(renderCharts);
onUnmounted(() => {
  if (doughnutInstance) { doughnutInstance.destroy(); doughnutInstance = null; }
  if (lineInstance) { lineInstance.destroy(); lineInstance = null; }
});
watch(() => [props.summary, props.overTime], renderCharts, { deep: true });
</script>

<template>
  <div class="effectiveness-container">
    <div class="doughnut-section">
      <div class="doughnut-wrapper">
        <canvas ref="doughnutRef"></canvas>
      </div>
      <div class="acceptance-rate-display">
        <span class="rate-value">{{ (summary.acceptance_rate * 100).toFixed(0) }}%</span>
        <span class="rate-label">Acceptance Rate</span>
      </div>
    </div>
    <div class="line-section">
      <div class="line-chart-wrapper">
        <canvas ref="lineRef"></canvas>
      </div>
    </div>
  </div>
</template>

<style scoped>
.effectiveness-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 8px;
}

.doughnut-section {
  display: flex;
  align-items: center;
  gap: 16px;
}

.doughnut-wrapper {
  position: relative;
  width: 140px;
  height: 140px;
  flex-shrink: 0;
}

.acceptance-rate-display {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.rate-value {
  font-family: 'Geist Mono', 'SF Mono', monospace;
  font-size: 2rem;
  font-weight: 700;
  color: var(--accent-emerald, #00ff88);
  line-height: 1;
}

.rate-label {
  font-size: 0.75rem;
  color: var(--text-tertiary, rgba(255, 255, 255, 0.35));
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.line-section {
  position: relative;
}

.line-chart-wrapper {
  position: relative;
  height: 140px;
}
</style>
