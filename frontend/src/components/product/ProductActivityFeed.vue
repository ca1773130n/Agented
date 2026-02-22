<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue';
import { Chart, registerables } from 'chart.js';
import type { MeetingMessage, TokenSpendDay } from '../../services/api';

Chart.register(...registerables);

const props = defineProps<{
  activity: MeetingMessage[];
  tokenSpend: TokenSpendDay[];
}>();

const chartRef = ref<HTMLCanvasElement | null>(null);
let chartInstance: Chart | null = null;

function relativeTime(dateStr?: string): string {
  if (!dateStr) return '';
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60000);
  const diffHr = Math.floor(diffMs / 3600000);
  const diffDay = Math.floor(diffMs / 86400000);

  if (diffMin < 1) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  if (diffDay === 1) return 'yesterday';
  if (diffDay < 30) return `${diffDay}d ago`;
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + '...';
}

function isStandup(msg: MeetingMessage): boolean {
  return msg.subject?.toLowerCase() === 'standup';
}

function renderChart() {
  if (!chartRef.value) return;
  if (chartInstance) {
    chartInstance.destroy();
  }

  const sorted = [...props.tokenSpend].sort((a, b) => a.day.localeCompare(b.day));
  const labels = sorted.map(d => {
    const dt = new Date(d.day);
    return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  });

  const colors = {
    input: '#0088ff',
    inputBg: 'rgba(0, 136, 255, 0.6)',
    output: '#ff8800',
    outputBg: 'rgba(255, 136, 0, 0.6)',
    grid: 'rgba(255, 255, 255, 0.06)',
    text: 'rgba(255, 255, 255, 0.5)',
    textMuted: 'rgba(255, 255, 255, 0.35)',
  };

  chartInstance = new Chart(chartRef.value, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'Input Tokens',
          data: sorted.map(d => d.input_tokens),
          backgroundColor: colors.inputBg,
          borderColor: colors.input,
          borderWidth: 1,
          borderRadius: 3,
        },
        {
          label: 'Output Tokens',
          data: sorted.map(d => d.output_tokens),
          backgroundColor: colors.outputBg,
          borderColor: colors.output,
          borderWidth: 1,
          borderRadius: 3,
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

onMounted(() => {
  if (props.tokenSpend.length > 0) {
    renderChart();
  }
});

onUnmounted(() => {
  if (chartInstance) {
    chartInstance.destroy();
    chartInstance = null;
  }
});

watch(() => props.tokenSpend, () => {
  if (props.tokenSpend.length > 0) {
    renderChart();
  }
}, { deep: true });
</script>

<template>
  <div class="card">
    <div class="card-header">
      <h3>Activity & Token Spend</h3>
    </div>

    <!-- Recent Activity Section -->
    <div class="section">
      <h4 class="section-title">Recent Activity</h4>

      <div v-if="activity.length === 0" class="empty-inline">
        <span>No recent activity</span>
      </div>

      <div v-else class="activity-list">
        <div v-for="msg in activity" :key="msg.id" class="activity-item">
          <div class="activity-header">
            <span class="activity-time">{{ relativeTime(msg.created_at) }}</span>
            <span class="activity-from">{{ msg.from_agent_id }}</span>
            <span class="activity-type-badge" :class="{ 'meeting-badge': isStandup(msg) }">
              <svg v-if="isStandup(msg)" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="meeting-icon">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                <circle cx="9" cy="7" r="4"/>
                <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
                <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
              </svg>
              {{ msg.message_type }}
            </span>
          </div>
          <span class="activity-subject">{{ msg.subject }}</span>
          <p class="activity-content">{{ truncate(msg.content, 100) }}</p>
        </div>
      </div>
    </div>

    <!-- Token Spend Section -->
    <div class="section">
      <h4 class="section-title">Token Spend</h4>

      <div v-if="tokenSpend.length === 0" class="empty-inline">
        <span>No token usage data</span>
      </div>

      <div v-else class="chart-container">
        <canvas ref="chartRef"></canvas>
      </div>
    </div>
  </div>
</template>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.card-header h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.section {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.section:last-child {
  border-bottom: none;
}

.section-title {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 12px;
}

.empty-inline {
  padding: 20px 0;
  text-align: center;
}

.empty-inline span {
  font-size: 0.85rem;
  color: var(--text-tertiary);
}

.activity-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 300px;
  overflow-y: auto;
}

.activity-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.activity-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.activity-time {
  font-size: 0.7rem;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
}

.activity-from {
  font-size: 0.75rem;
  color: var(--text-secondary);
  font-weight: 500;
}

.activity-type-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.65rem;
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(136, 85, 255, 0.15);
  color: #8855ff;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.activity-type-badge.meeting-badge {
  background: rgba(0, 212, 255, 0.15);
  color: #00d4ff;
}

.meeting-icon {
  width: 12px;
  height: 12px;
}

.activity-subject {
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--text-primary);
}

.activity-content {
  font-size: 0.8rem;
  color: var(--text-tertiary);
  line-height: 1.4;
}

.chart-container {
  position: relative;
  height: 280px;
  padding: 8px 0;
}
</style>
