<script setup lang="ts">
defineProps<{
  classification: Record<string, any> | null;
}>();

const phaseColors: Record<string, string> = {
  research: '#3b82f6',
  planning: '#a855f7',
  execution: '#22c55e',
  review: '#f97316',
};

function getPhaseColor(phase: string): string {
  return phaseColors[phase] || 'var(--accent-primary)';
}

function getComplexityIcon(complexity: string): string {
  switch (complexity) {
    case 'low': return '1';
    case 'medium': return '2';
    case 'high': return '3';
    default: return '?';
  }
}
</script>

<template>
  <div class="sketch-classification">
    <h4 class="panel-title">Classification</h4>
    <div v-if="!classification" class="placeholder-text">Not yet classified</div>
    <div v-else class="classification-details">
      <div class="detail-row">
        <span class="detail-label">Phase</span>
        <span
          class="phase-badge"
          :style="{ backgroundColor: getPhaseColor(classification.phase || '') }"
        >
          {{ classification.phase || 'unknown' }}
        </span>
      </div>
      <div v-if="classification.domains && classification.domains.length" class="detail-row">
        <span class="detail-label">Domains</span>
        <span class="domain-tags">
          <span
            v-for="(domain, idx) in classification.domains"
            :key="idx"
            class="domain-tag"
          >{{ domain }}</span>
        </span>
      </div>
      <div class="detail-row">
        <span class="detail-label">Complexity</span>
        <span class="complexity-indicator" :class="`complexity-${classification.complexity || 'unknown'}`">
          <span class="complexity-icon">{{ getComplexityIcon(classification.complexity || '') }}</span>
          {{ classification.complexity || 'unknown' }}
        </span>
      </div>
      <div class="detail-row">
        <span class="detail-label">Confidence</span>
        <div class="confidence-bar-wrapper">
          <div
            class="confidence-bar"
            :style="{ width: `${(classification.confidence || 0) * 100}%` }"
          ></div>
          <span class="confidence-pct">{{ Math.round((classification.confidence || 0) * 100) }}%</span>
        </div>
      </div>
      <div v-if="classification.source" class="detail-row">
        <span class="detail-label">Source</span>
        <span class="source-label">{{ classification.source }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sketch-classification {
  padding: 12px;
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--border-default);
}

.panel-title {
  margin: 0 0 12px 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.placeholder-text {
  color: var(--text-secondary);
  font-size: 13px;
  font-style: italic;
}

.classification-details {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.detail-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.detail-label {
  font-size: 12px;
  color: var(--text-secondary);
  min-width: 80px;
  flex-shrink: 0;
}

.phase-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  color: #fff;
  text-transform: capitalize;
}

.domain-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.domain-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
}

.complexity-indicator {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-primary);
  text-transform: capitalize;
}

.complexity-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  font-size: 11px;
  font-weight: 600;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
}

.complexity-low .complexity-icon { color: #22c55e; border-color: #22c55e; }
.complexity-medium .complexity-icon { color: #f59e0b; border-color: #f59e0b; }
.complexity-high .complexity-icon { color: #ef4444; border-color: #ef4444; }

.confidence-bar-wrapper {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  height: 18px;
  position: relative;
  overflow: hidden;
}

.confidence-bar {
  height: 100%;
  background: var(--accent-primary);
  border-radius: 4px;
  transition: width 0.3s ease;
}

.confidence-pct {
  position: absolute;
  right: 6px;
  font-size: 11px;
  color: var(--text-primary);
  font-weight: 500;
}

.source-label {
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
</style>
