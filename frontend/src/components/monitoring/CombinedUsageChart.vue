<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue';
import { Chart, registerables } from 'chart.js';
import 'chartjs-adapter-date-fns';
import type { SnapshotHistoryEntry } from '../../services/api';

Chart.register(...registerables);

interface WindowHistory {
  windowType: string;
  label: string;
  history: SnapshotHistoryEntry[];
  color?: string;
  ratePerHour?: number;
  resetsAt?: string | null;
}

const props = withDefaults(defineProps<{
  windowHistories: WindowHistory[];
  timeRangeStart?: string;
  timeRangeEnd?: string;
}>(), {
  timeRangeStart: '',
  timeRangeEnd: '',
});

const chartRef = ref<HTMLCanvasElement | null>(null);
let chartInstance: Chart | null = null;

const windowColors: Record<string, string> = {
  five_hour: '#8855ff',
  seven_day: '#00d4ff',
  seven_day_sonnet: '#f59e0b',
};

// Fallback palette for dynamic window types (codex, gemini)
const fallbackPalette = ['#10a37f', '#3b82f6', '#f59e0b', '#e879f9', '#8855ff', '#00d4ff'];
let fallbackIndex = 0;
const assignedColors: Record<string, string> = {};

function getColor(windowType: string, passedColor?: string): string {
  if (passedColor) return passedColor;
  if (windowColors[windowType]) return windowColors[windowType];
  if (!assignedColors[windowType]) {
    assignedColors[windowType] = fallbackPalette[fallbackIndex % fallbackPalette.length];
    fallbackIndex++;
  }
  return assignedColors[windowType];
}

// Compute rate from recent data slope (last 60 min or last 10 points)
function computeRecentRate(data: { x: number; y: number }[]): number | null {
  if (data.length < 2) return null;
  const last = data[data.length - 1];
  const windowMs = 60 * 60000; // 60 min
  let recentPoints = data.filter(d => d.x >= last.x - windowMs);
  if (recentPoints.length < 2) {
    recentPoints = data.slice(-10);
  }
  if (recentPoints.length < 2) return null;
  const first = recentPoints[0];
  const dx = last.x - first.x;
  if (dx <= 0) return null;
  const dy = last.y - first.y;
  return (dy / dx) * 3600000; // convert to %/hr
}

function renderChart() {
  if (!chartRef.value) return;
  if (chartInstance) {
    chartInstance.destroy();
  }
  if (!props.windowHistories?.length) return;

  // Reset fallback index for consistent coloring
  fallbackIndex = 0;
  Object.keys(assignedColors).forEach(k => delete assignedColors[k]);

  // Build datasets using {x, y} point format for time scale
  const datasets: any[] = [];

  for (const wh of props.windowHistories) {
    const color = getColor(wh.windowType, wh.color);
    const data = wh.history
      .map(h => ({ x: new Date(h.recorded_at).getTime(), y: h.percentage }))
      .sort((a, b) => a.x - b.x);

    // Actual data line
    datasets.push({
      label: wh.label,
      data,
      borderColor: color,
      backgroundColor: color + '20',
      borderWidth: 2,
      fill: false,
      tension: 0.3,
      pointRadius: 1,
      pointHoverRadius: 4,
      pointBackgroundColor: color,
      spanGaps: true,
    });

    // Projected dotted line: prefer slope from actual data, fall back to backend rate
    const localRate = computeRecentRate(data);
    const effectiveRate = localRate ?? wh.ratePerHour;
    if (effectiveRate != null && Math.abs(effectiveRate) > 0.01 && data.length >= 2) {
      const lastPt = data[data.length - 1];
      const projectionDuration = 2 * 3600000; // project 2 hours forward
      const steps = 12;
      const stepMs = projectionDuration / steps;
      const projData: { x: number; y: number }[] = [{ x: lastPt.x, y: lastPt.y }];
      for (let i = 1; i <= steps; i++) {
        const t = lastPt.x + stepMs * i;
        const y = lastPt.y + (effectiveRate * (stepMs * i) / 3600000);
        if (y > 100) {
          if (effectiveRate > 0) {
            const remainPct = 100 - lastPt.y;
            const msTo100 = (remainPct / effectiveRate) * 3600000;
            projData.push({ x: lastPt.x + msTo100, y: 100 });
          }
          break;
        }
        if (y < 0) {
          if (effectiveRate < 0) {
            const msToZero = (lastPt.y / Math.abs(effectiveRate)) * 3600000;
            projData.push({ x: lastPt.x + msToZero, y: 0 });
          }
          break;
        }
        projData.push({ x: t, y });
      }

      datasets.push({
        label: wh.label + ' (projected)',
        data: projData,
        borderColor: color + '80',
        backgroundColor: 'transparent',
        borderWidth: 2,
        borderDash: [6, 4],
        fill: false,
        tension: 0,
        pointRadius: 0,
        pointHoverRadius: 3,
        pointBackgroundColor: color + '80',
        spanGaps: true,
      });
    }
  }

  // x-axis bounds are computed by the parent (MonitoringSection) so both
  // "All Windows Usage" and "Remaining Capacity" share the same time axis.
  const xMin = props.timeRangeStart ? new Date(props.timeRangeStart).getTime() : undefined;
  const xMax = props.timeRangeEnd ? new Date(props.timeRangeEnd).getTime() : undefined;

  const colors = {
    grid: 'rgba(255, 255, 255, 0.06)',
    text: 'rgba(255, 255, 255, 0.6)',
    textMuted: 'rgba(255, 255, 255, 0.35)',
  };

  // Collect reset lines per window (deduplicate by time to avoid overlapping lines)
  const resetLines: { time: number; color: string; label: string }[] = [];
  const seenResetTimes = new Set<number>();
  for (const wh of props.windowHistories) {
    if (!wh.resetsAt) continue;
    const t = new Date(wh.resetsAt).getTime();
    if (seenResetTimes.has(t)) continue;
    seenResetTimes.add(t);
    resetLines.push({ time: t, color: getColor(wh.windowType, wh.color), label: wh.label });
  }

  const resetLinePlugin = {
    id: 'resetLines',
    afterDraw(chart: Chart) {
      if (!resetLines.length) return;
      const xScale = chart.scales.x;
      const yScale = chart.scales.y;
      const ctx = chart.ctx;
      ctx.save();
      for (const rl of resetLines) {
        const x = xScale.getPixelForValue(rl.time);
        if (x < xScale.left || x > xScale.right) continue;
        ctx.beginPath();
        ctx.moveTo(x, yScale.top);
        ctx.lineTo(x, yScale.bottom);
        ctx.strokeStyle = 'rgba(234, 179, 8, 0.5)';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([6, 4]);
        ctx.stroke();
        ctx.fillStyle = 'rgba(234, 179, 8, 0.7)';
        ctx.font = "10px 'Geist Mono', 'SF Mono', monospace";
        ctx.textAlign = 'center';
        ctx.fillText('Reset', x, yScale.top - 4);
      }
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
        legend: {
          display: true,
          position: 'top',
          labels: {
            color: colors.text,
            boxWidth: 12,
            padding: 12,
            font: {
              family: "'Geist', sans-serif",
              size: 11,
            },
            filter: (item) => !item.text?.includes('(projected)'),
          },
        },
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
              return `${context.dataset.label?.replace(' (projected)', '')}${suffix}: ${(context.parsed.y ?? 0).toFixed(1)}%`;
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
watch(() => [props.windowHistories, props.timeRangeStart, props.timeRangeEnd], renderChart, { deep: true });
</script>

<template>
  <div class="combined-chart-container">
    <div v-if="!windowHistories?.length" class="chart-no-data">
      No data yet
    </div>
    <canvas v-else ref="chartRef"></canvas>
  </div>
</template>

<style scoped>
.combined-chart-container {
  position: relative;
  height: 240px;
  width: 100%;
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
