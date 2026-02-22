<script lang="ts">
export default { inheritAttrs: false }
</script>

<script setup lang="ts">
import { computed } from 'vue'
import { BaseEdge, EdgeLabelRenderer, getBezierPath, Position } from '@vue-flow/core'
import type { CanvasEdgeType } from '../../services/api/types'

const props = defineProps<{
  id: string
  sourceX: number
  sourceY: number
  targetX: number
  targetY: number
  sourcePosition?: Position
  targetPosition?: Position
  style?: Record<string, string>
  markerEnd?: string
  data?: {
    edge_type?: CanvasEdgeType
    label?: string
  }
}>()

const pathParams = computed(() => {
  return getBezierPath({
    sourceX: props.sourceX,
    sourceY: props.sourceY,
    sourcePosition: props.sourcePosition ?? Position.Bottom,
    targetX: props.targetX,
    targetY: props.targetY,
    targetPosition: props.targetPosition ?? Position.Top,
  })
})

const edgePath = computed(() => pathParams.value[0])
const labelX = computed(() => pathParams.value[1])
const labelY = computed(() => pathParams.value[2])

const edgeType = computed<CanvasEdgeType>(() => props.data?.edge_type || 'messaging')

const edgeStyle = computed(() => {
  switch (edgeType.value) {
    case 'command':
      return {
        stroke: '#00d4ff',
        strokeWidth: '3',
        strokeDasharray: 'none',
        ...props.style,
      }
    case 'report':
      return {
        stroke: 'rgba(160, 160, 176, 0.6)',
        strokeWidth: '1.5',
        strokeDasharray: '6 4',
        ...props.style,
      }
    case 'peer':
      return {
        stroke: '#22c55e',
        strokeWidth: '2',
        strokeDasharray: '3 3',
        ...props.style,
      }
    case 'inter_team':
      return {
        stroke: '#f59e0b',
        strokeWidth: '2.5',
        strokeDasharray: '8 3 2 3',
        ...props.style,
      }
    case 'messaging':
    default:
      return {
        stroke: 'rgba(168, 85, 247, 0.6)',
        strokeWidth: '2',
        strokeDasharray: '10 5',
        animation: 'dash-flow 1s linear infinite',
        ...props.style,
      }
  }
})

const edgeLabelColor = computed(() => {
  switch (edgeType.value) {
    case 'command':
      return '#00d4ff'
    case 'report':
      return 'rgba(160, 160, 176, 0.6)'
    case 'peer':
      return '#22c55e'
    case 'inter_team':
      return '#f59e0b'
    case 'messaging':
    default:
      return 'rgba(168, 85, 247, 0.8)'
  }
})

const displayLabel = computed(() => props.data?.label || '')
</script>

<template>
  <BaseEdge
    :id="id"
    :path="edgePath"
    :marker-end="markerEnd"
    :style="edgeStyle"
  />

  <EdgeLabelRenderer>
    <div
      class="edge-label-container"
      :style="{
        position: 'absolute',
        transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
        pointerEvents: 'all',
        borderColor: edgeLabelColor,
        color: edgeLabelColor,
      }"
    >
      <!-- Command: chevron-right arrow -->
      <svg
        v-if="edgeType === 'command'"
        class="edge-icon"
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        :stroke="edgeLabelColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <polyline points="9 18 15 12 9 6" />
      </svg>
      <!-- Report: clipboard icon -->
      <svg
        v-else-if="edgeType === 'report'"
        class="edge-icon"
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        :stroke="edgeLabelColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
        <rect x="8" y="2" width="8" height="4" rx="1" ry="1" />
      </svg>
      <!-- Peer: double-arrow icon -->
      <svg
        v-else-if="edgeType === 'peer'"
        class="edge-icon"
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        :stroke="edgeLabelColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <polyline points="17 1 21 5 17 9" />
        <polyline points="7 15 3 19 7 23" />
        <line x1="21" y1="5" x2="9" y2="5" />
        <line x1="3" y1="19" x2="15" y2="19" />
      </svg>
      <!-- Inter-team: link icon -->
      <svg
        v-else-if="edgeType === 'inter_team'"
        class="edge-icon"
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        :stroke="edgeLabelColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
        <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
      </svg>
      <!-- Messaging: envelope icon (default) -->
      <svg
        v-else
        class="edge-icon"
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        :stroke="edgeLabelColor"
        stroke-width="2"
      >
        <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
        <polyline points="22,6 12,13 2,6" />
      </svg>
      <span v-if="displayLabel" class="edge-label-text">{{ displayLabel }}</span>
    </div>
  </EdgeLabelRenderer>
</template>

<style>
/* Global keyframe — not scoped so the SVG animation works */
@keyframes dash-flow {
  from {
    stroke-dashoffset: 15;
  }
  to {
    stroke-dashoffset: 0;
  }
}
</style>

<style scoped>
.edge-label-container {
  display: flex;
  align-items: center;
  gap: 4px;
  background: var(--bg-secondary, #12121a);
  border: 1px solid rgba(168, 85, 247, 0.3);
  border-radius: 6px;
  padding: 2px 6px;
  font-size: 10px;
  color: rgba(168, 85, 247, 0.9);
  white-space: nowrap;
}

.edge-icon {
  flex-shrink: 0;
}

.edge-label-text {
  font-weight: 500;
  letter-spacing: 0.3px;
}
</style>
