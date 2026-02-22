<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed, nextTick } from 'vue';
import { Chart, registerables } from 'chart.js';

Chart.register(...registerables);

const props = withDefaults(defineProps<{
  percentage: number;
  label: string;
  tokensUsed: number;
  tokensLimit: number;
  thresholdLevel: string;
  accentColor: string;
}>(), {
  percentage: 0,
  label: '',
  tokensUsed: 0,
  tokensLimit: 0,
  thresholdLevel: 'normal',
  accentColor: '',
});

const chartRef = ref<HTMLCanvasElement | null>(null);
let chartInstance: Chart | null = null;

const thresholdColor = computed(() => {
  if (props.percentage >= 90) return '#ef4444';  // critical - red
  if (props.percentage >= 75) return '#f59e0b';  // warning - amber
  return '';
});

const gaugeColor = computed(() => {
  // Critical/warning override accent color
  if (thresholdColor.value) return thresholdColor.value;
  // Use accent color if provided, otherwise percentage-based
  if (props.accentColor) return props.accentColor;
  if (props.percentage >= 50) return '#3b82f6';  // info - blue
  return '#10b981';                               // normal - green
});

function formatTokens(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(0) + 'K';
  return n.toString();
}

function renderChart() {
  if (!chartRef.value) return;

  if (chartInstance) {
    chartInstance.destroy();
  }

  const pct = Math.min(Math.max(props.percentage, 0), 100);

  chartInstance = new Chart(chartRef.value, {
    type: 'doughnut',
    data: {
      labels: ['Used', 'Remaining'],
      datasets: [{
        data: [pct, 100 - pct],
        backgroundColor: [gaugeColor.value, 'rgba(255,255,255,0.06)'],
        borderWidth: 0,
        borderRadius: 2,
      }],
    },
    options: {
      rotation: -90,
      circumference: 180,
      cutout: '75%',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false },
      },
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
watch(
  () => [props.percentage, props.thresholdLevel, props.accentColor],
  renderChart,
  { deep: true }
);
</script>

<template>
  <div class="gauge-container">
    <div class="gauge-chart-wrapper">
      <canvas ref="chartRef"></canvas>
      <div class="gauge-center-text">
        <span class="gauge-percentage" :style="{ color: gaugeColor }">
          {{ Math.round(percentage) }}%
        </span>
      </div>
    </div>
    <div class="gauge-label" v-html="label"></div>
    <div class="gauge-tokens" v-if="tokensLimit > 0">
      {{ formatTokens(tokensUsed) }} / {{ formatTokens(tokensLimit) }}
    </div>
  </div>
</template>

<style scoped>
.gauge-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  width: 100%;
}

.gauge-chart-wrapper {
  position: relative;
  width: 100%;
  max-width: 160px;
  height: 80px;
}

.gauge-center-text {
  position: absolute;
  bottom: 4px;
  left: 50%;
  transform: translateX(-50%);
  text-align: center;
}

.gauge-percentage {
  font-family: var(--font-mono);
  font-size: 1.4rem;
  font-weight: 700;
}

.gauge-label {
  font-size: 0.65rem;
  color: var(--text-tertiary);
  letter-spacing: 0.04em;
  text-align: center;
  margin-top: 1px;
  line-height: 1.4;
}

.gauge-label :deep(.gauge-model) {
  display: block;
  font-weight: 700;
  color: var(--text-primary);
  font-size: 0.7rem;
}

.gauge-label :deep(.gauge-window) {
  display: block;
  font-weight: 600;
  color: var(--accent-cyan);
  font-size: 0.6rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.gauge-tokens {
  font-family: var(--font-mono);
  font-size: 0.6rem;
  color: var(--text-secondary);
  text-align: center;
}

</style>
