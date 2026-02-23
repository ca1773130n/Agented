<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import type { Node, Edge } from '@vue-flow/core';
import type { Workflow } from '../services/api';
import { workflowApi, workflowExecutionApi, ApiError } from '../services/api';
import type { ValidationResult } from '../composables/useWorkflowValidation';
import { useWorkflowValidation } from '../composables/useWorkflowValidation';
import EntityLayout from '../layouts/EntityLayout.vue';
import WorkflowCanvas from '../components/workflow/WorkflowCanvas.vue';
import WorkflowSidebar from '../components/workflow/WorkflowSidebar.vue';
import WorkflowToolbar from '../components/workflow/WorkflowToolbar.vue';
import NodeConfigPanel from '../components/workflow/NodeConfigPanel.vue';
import WorkflowValidationPanel from '../components/workflow/WorkflowValidationPanel.vue';
import ExecutionHistoryPanel from '../components/workflow/ExecutionHistoryPanel.vue';
import ExecutionMonitorPanel from '../components/workflow/ExecutionMonitorPanel.vue';
import ConfirmModal from '../components/base/ConfirmModal.vue';
import { useToast } from '../composables/useToast';
import { useWorkflowExecution } from '../composables/useWorkflowExecution';
import { useWebMcpTool } from '../composables/useWebMcpTool';

const router = useRouter();
const route = useRoute();
const workflowId = computed(() => route.params.workflowId as string);

const showToast = useToast();

const {
  executionId,
  executionStatus,
  nodeStates,
  isMonitoring,
  startMonitoring,
  cancelExecution,
} = useWorkflowExecution();

const { validateGraph } = useWorkflowValidation();

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const workflow = ref<Workflow | null>(null);
const selectedNodeId = ref<string | null>(null);
const showValidation = ref(false);
const showExecutionHistory = ref(false);
const showExecutionMonitor = ref(false);
const isDirty = ref(false);
const isRunning = ref(false);
const showLeaveConfirm = ref(false);
const canvasRef = ref<InstanceType<typeof WorkflowCanvas> | null>(null);

// Metadata editor state
const showMetadataEditor = ref(false);
const metadataForm = ref({
  name: '',
  trigger_type: 'manual',
  enabled: 1 as number,
});

// Validation results (updated on every canvas-changed event)
const validationResults = ref<ValidationResult[]>([]);

// ---------------------------------------------------------------------------
// Computed
// ---------------------------------------------------------------------------

const workflowName = computed(() => workflow.value?.name || 'Untitled Workflow');

const metadataEnabled = computed({
  get: () => !!metadataForm.value.enabled,
  set: (val: boolean) => { metadataForm.value.enabled = val ? 1 : 0; },
});

const validationErrorCount = computed(() =>
  validationResults.value.filter((r) => r.level === 'error').length
);

// selectedNode: resolve actual Node from canvas nodes array via canvasRef expose
const selectedNode = computed<Node | null>(() => {
  if (!selectedNodeId.value || !canvasRef.value) return null;
  const nodes = canvasRef.value.nodes as Node[] | undefined;
  if (!nodes) return null;
  return nodes.find((n) => n.id === selectedNodeId.value) || null;
});

useWebMcpTool({
  name: 'agented_workflow_builder_get_state',
  description: 'Returns the current state of the WorkflowBuilderPage',
  page: 'WorkflowBuilderPage',
  execute: async () => ({
    content: [{
      type: 'text' as const,
      text: JSON.stringify({
        page: 'WorkflowBuilderPage',
        workflowId: workflow.value?.id ?? null,
        workflowName: workflowName.value,
        isDirty: isDirty.value,
        isRunning: isRunning.value,
        validationErrorCount: validationErrorCount.value,
        showValidation: showValidation.value,
        showExecutionHistory: showExecutionHistory.value,
        showExecutionMonitor: showExecutionMonitor.value,
        selectedNodeId: selectedNodeId.value,
        isMonitoring: isMonitoring.value,
      }),
    }],
  }),
  deps: [workflow, isDirty, isRunning, validationResults, showValidation, showExecutionHistory, showExecutionMonitor, selectedNodeId, isMonitoring],
});

// ---------------------------------------------------------------------------
// Data Loading
// ---------------------------------------------------------------------------

async function loadWorkflow() {
  const data = await workflowApi.get(workflowId.value);
  workflow.value = data;
  metadataForm.value = {
    name: data.name,
    trigger_type: data.trigger_type || 'manual',
    enabled: data.enabled ?? 1,
  };
  return data;
}

// ---------------------------------------------------------------------------
// Canvas event handlers
// ---------------------------------------------------------------------------

function onNodeSelected(nodeId: string | null) {
  selectedNodeId.value = nodeId;
}

function onDirtyChange(dirty: boolean) {
  isDirty.value = dirty;
}

function onSaved() {
  showToast('Workflow saved successfully', 'success');
}

function onCanvasChanged(nodes: Node[], edges: Edge[]) {
  validationResults.value = validateGraph(nodes, edges);
}

function onHighlightNodes(nodeIds: string[]) {
  canvasRef.value?.highlightNodes(nodeIds);
}

// ---------------------------------------------------------------------------
// Toolbar event handlers
// ---------------------------------------------------------------------------

function handleBack() {
  if (isDirty.value) {
    showLeaveConfirm.value = true;
  } else {
    router.push({ name: 'workflows' });
  }
}

function handleToggleMetadata() {
  showMetadataEditor.value = !showMetadataEditor.value;
}

async function handleSaveMetadata() {
  try {
    await workflowApi.update(workflowId.value, {
      name: metadataForm.value.name,
      trigger_type: metadataForm.value.trigger_type,
      enabled: metadataForm.value.enabled,
    });
    workflow.value = { ...workflow.value!, ...metadataForm.value };
    showMetadataEditor.value = false;
    showToast('Workflow metadata updated', 'success');
  } catch {
    showToast('Failed to update workflow metadata', 'error');
  }
}

async function handleSave() {
  canvasRef.value?.save();
}

function handleAutoLayout() {
  canvasRef.value?.autoLayout();
}

async function handleRun() {
  if (isRunning.value) return;
  isRunning.value = true;
  try {
    const result = await workflowExecutionApi.run(workflowId.value);
    showToast(`Workflow execution started (${result.execution_id})`, 'success');
    startMonitoring(workflowId.value, result.execution_id);
    showExecutionMonitor.value = true;
  } catch (e) {
    if (e instanceof ApiError) {
      showToast(e.message, 'error');
    } else {
      showToast('Failed to start workflow execution', 'error');
    }
  } finally {
    isRunning.value = false;
  }
}

function handleToggleValidation() {
  showValidation.value = !showValidation.value;
}

function handleToggleExecution() {
  showExecutionMonitor.value = !showExecutionMonitor.value;
}

// ---------------------------------------------------------------------------
// Node config panel handlers
// ---------------------------------------------------------------------------

function handleUpdateConfig(nodeId: string, config: Record<string, unknown>) {
  canvasRef.value?.updateNodeConfig(nodeId, config);
}

function handleUpdateLabel(nodeId: string, label: string) {
  canvasRef.value?.updateNodeLabel(nodeId, label);
}

function handleDeleteNode(nodeId: string) {
  canvasRef.value?.removeNode(nodeId);
  selectedNodeId.value = null;
}

function handleCloseConfig() {
  selectedNodeId.value = null;
}

// ---------------------------------------------------------------------------
// Auto-show validation panel when errors appear
// ---------------------------------------------------------------------------

watch(validationResults, (results) => {
  const errorCount = results.filter((r) => r.level === 'error').length;
  if (errorCount > 0 && !showValidation.value) {
    showValidation.value = true;
  }
});

// ---------------------------------------------------------------------------
// Keyboard shortcut: Cmd+S / Ctrl+S
// ---------------------------------------------------------------------------

function onKeyDown(event: KeyboardEvent) {
  if ((event.metaKey || event.ctrlKey) && event.key === 's') {
    event.preventDefault();
    if (isDirty.value) {
      handleSave();
    }
  }
}

// ---------------------------------------------------------------------------
// Unsaved changes guard (browser close/refresh)
// ---------------------------------------------------------------------------

function onBeforeUnload(event: BeforeUnloadEvent) {
  if (isDirty.value) {
    event.preventDefault();
    event.returnValue = '';
  }
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMounted(() => {
  window.addEventListener('keydown', onKeyDown);
  window.addEventListener('beforeunload', onBeforeUnload);
});

onUnmounted(() => {
  window.removeEventListener('keydown', onKeyDown);
  window.removeEventListener('beforeunload', onBeforeUnload);
});


</script>

<template>
  <EntityLayout :load-entity="loadWorkflow" entity-label="workflow">
    <template #default="{ reload: _reload }">
  <div class="workflow-builder-page">
    <!-- Toolbar -->
    <WorkflowToolbar
      :workflow-name="workflowName"
      :is-dirty="isDirty"
      :is-running="isRunning"
      :validation-errors="validationErrorCount"
      @save="handleSave"
      @auto-layout="handleAutoLayout"
      @run="handleRun"
      @toggle-validation="handleToggleValidation"
      @toggle-execution="handleToggleExecution"
      @back="handleBack"
      @toggle-metadata="handleToggleMetadata"
    />

    <!-- Metadata editor (collapsible) -->
    <div v-if="showMetadataEditor" class="metadata-editor">
      <div class="metadata-field">
        <label>Name</label>
        <input v-model="metadataForm.name" type="text" />
      </div>
      <div class="metadata-field">
        <label>Trigger Type</label>
        <select v-model="metadataForm.trigger_type">
          <option value="manual">Manual</option>
          <option value="cron">Cron</option>
          <option value="poll">Poll</option>
          <option value="file_watch">File Watch</option>
          <option value="completion">Completion</option>
        </select>
      </div>
      <div class="metadata-field">
        <label>Enabled</label>
        <label class="toggle-label">
          <input type="checkbox" v-model="metadataEnabled" />
          <span>{{ metadataForm.enabled ? 'Enabled' : 'Disabled' }}</span>
        </label>
      </div>
      <div class="metadata-actions">
        <button class="btn btn-sm" @click="showMetadataEditor = false">Cancel</button>
        <button class="btn btn-sm btn-primary" @click="handleSaveMetadata">Save Metadata</button>
      </div>
    </div>

    <!-- Main content area -->
    <div class="builder-body">
      <!-- Left: Node palette sidebar -->
      <div class="builder-sidebar">
        <WorkflowSidebar />
      </div>

      <!-- Center: Canvas -->
      <div class="builder-canvas">
        <WorkflowCanvas
          ref="canvasRef"
          :workflow-id="workflowId"
          @node-selected="onNodeSelected"
          @dirty-change="onDirtyChange"
          @saved="onSaved"
          @canvas-changed="onCanvasChanged"
        />
      </div>

      <!-- Right: Node config panel (shown when a node is selected) -->
      <div v-if="selectedNodeId" class="builder-config-panel">
        <NodeConfigPanel
          :node="selectedNode"
          @update-config="handleUpdateConfig"
          @update-label="handleUpdateLabel"
          @delete-node="handleDeleteNode"
          @close="handleCloseConfig"
        />
      </div>

      <!-- Right: Execution monitor (shown when monitoring) -->
      <div v-if="showExecutionMonitor" class="builder-execution-panel">
        <ExecutionMonitorPanel
          :execution-id="executionId"
          :execution-status="executionStatus"
          :node-states="nodeStates"
          :is-monitoring="isMonitoring"
          :visible="showExecutionMonitor"
          @cancel="cancelExecution(workflowId)"
          @close="showExecutionMonitor = false"
          @view-history="showExecutionMonitor = false; showExecutionHistory = true"
        />
      </div>

      <!-- Right: Execution history panel -->
      <div v-if="showExecutionHistory" class="builder-history-panel">
        <ExecutionHistoryPanel
          :workflow-id="workflowId"
          :visible="showExecutionHistory"
          @replay-execution="(execId: string) => { startMonitoring(workflowId, execId); showExecutionHistory = false; showExecutionMonitor = true; }"
          @close="showExecutionHistory = false"
        />
      </div>
    </div>

    <!-- Bottom: Validation panel (collapsible) -->
    <WorkflowValidationPanel
      v-if="showValidation"
      :results="validationResults"
      :visible="showValidation"
      @close="showValidation = false"
      @highlight-nodes="onHighlightNodes"
    />

    <ConfirmModal
      :open="showLeaveConfirm"
      title="Unsaved Changes"
      message="You have unsaved changes. Are you sure you want to leave?"
      confirm-label="Leave"
      cancel-label="Stay"
      variant="danger"
      @confirm="showLeaveConfirm = false; router.push({ name: 'workflows' })"
      @cancel="showLeaveConfirm = false"
    />
  </div>
    </template>
  </EntityLayout>
</template>

<style scoped>
.workflow-builder-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  background: var(--bg-primary);
}

.builder-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.builder-sidebar {
  width: 220px;
  flex-shrink: 0;
  border-right: 1px solid var(--border-subtle);
  overflow-y: auto;
  background: var(--bg-secondary);
}

.builder-canvas {
  flex: 1;
  min-width: 0;
  min-height: 0;
  position: relative;
}

.builder-config-panel {
  width: 320px;
  flex-shrink: 0;
  border-left: 1px solid var(--border-subtle);
  overflow-y: auto;
  background: var(--bg-secondary);
}

.builder-execution-panel,
.builder-history-panel {
  flex-shrink: 0;
  overflow-y: auto;
}

/* Metadata editor */
.metadata-editor {
  padding: 16px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  gap: 16px;
  align-items: flex-end;
  flex-wrap: wrap;
  flex-shrink: 0;
}

.metadata-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.metadata-field label {
  font-size: 11px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  font-weight: 600;
}

.metadata-field input[type="text"],
.metadata-field select {
  padding: 6px 10px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 13px;
}

.metadata-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-secondary);
}
</style>
