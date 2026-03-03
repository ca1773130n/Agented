import { ref, computed, onUnmounted } from 'vue';
import type { Ref } from 'vue';
import type { NodeExecutionStatus, AuthenticatedEventSource } from '../services/api';
import { workflowExecutionApi } from '../services/api';

/**
 * SSE-based workflow execution monitoring composable.
 *
 * Connects to the backend SSE stream for a running execution,
 * tracks node states reactively, and handles all 6 event types:
 *   status, node_start, node_complete, node_failed, execution_complete, error
 *
 * EventSource is properly cleaned up on component unmount.
 */
export function useWorkflowExecution() {
  // -- State --
  const executionId = ref<string | null>(null);
  const executionStatus = ref<string>('pending');
  const nodeStates = ref<Record<string, string>>({});
  const isMonitoring = ref(false);
  const error = ref<string | null>(null);

  // Approval gate state
  const showApprovalModal = ref(false);
  const pendingApprovalNodeId = ref<string | null>(null);
  const pendingApprovalNodeLabel = ref<string>('');

  // Computed: nodes currently in pending_approval state
  const pendingApprovals = computed(() => {
    return Object.entries(nodeStates.value)
      .filter(([, status]) => status === 'pending_approval')
      .map(([nodeId]) => nodeId);
  });

  let eventSource: AuthenticatedEventSource | null = null;

  // -- Functions --

  /**
   * Start monitoring an execution via SSE.
   * Closes any existing connection before opening a new one.
   */
  function startMonitoring(workflowId: string, execId: string): void {
    // Close existing connection if any
    closeEventSource();

    // Initialize state
    executionId.value = execId;
    executionStatus.value = 'running';
    isMonitoring.value = true;
    error.value = null;
    nodeStates.value = {};

    // Create SSE connection via API client
    eventSource = workflowExecutionApi.stream(workflowId, execId);

    eventSource.onmessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        handleEvent(data);
      } catch {
        // Ignore unparseable events
      }
    };

    eventSource.onerror = () => {
      isMonitoring.value = false;
      error.value = 'Connection lost';
      closeEventSource();
    };
  }

  /**
   * Handle a parsed SSE event based on its type field.
   */
  function handleEvent(data: {
    type: string;
    status?: string;
    node_id?: string;
    node_states?: Record<string, string>;
    error?: string;
    [key: string]: unknown;
  }): void {
    switch (data.type) {
      case 'status':
        if (data.status) {
          executionStatus.value = data.status;
        }
        if (data.node_states) {
          // Detect newly pending_approval nodes
          const prevStates = nodeStates.value;
          const newStates = data.node_states;
          for (const [nodeId, status] of Object.entries(newStates)) {
            if (status === 'pending_approval' && prevStates[nodeId] !== 'pending_approval') {
              pendingApprovalNodeId.value = nodeId;
              pendingApprovalNodeLabel.value = nodeId;
              showApprovalModal.value = true;
            }
          }
          nodeStates.value = { ...nodeStates.value, ...data.node_states };
        }
        break;

      case 'node_start':
        if (data.node_id) {
          const nodeStatus = data.status === 'pending_approval' ? 'pending_approval' : 'running';
          nodeStates.value = { ...nodeStates.value, [data.node_id]: nodeStatus };
          // If this is a pending_approval status, trigger the approval modal
          if (data.status === 'pending_approval') {
            pendingApprovalNodeId.value = data.node_id;
            pendingApprovalNodeLabel.value = (data.node_label as string) || data.node_id;
            showApprovalModal.value = true;
          }
        }
        break;

      case 'node_complete':
        if (data.node_id) {
          nodeStates.value = { ...nodeStates.value, [data.node_id]: 'completed' };
        }
        break;

      case 'node_failed':
        if (data.node_id) {
          nodeStates.value = { ...nodeStates.value, [data.node_id]: 'failed' };
        }
        break;

      case 'node_pending_approval':
        if (data.node_id) {
          nodeStates.value = { ...nodeStates.value, [data.node_id]: 'pending_approval' };
          pendingApprovalNodeId.value = data.node_id;
          pendingApprovalNodeLabel.value = (data.node_label as string) || data.node_id;
          showApprovalModal.value = true;
        }
        break;

      case 'execution_complete':
        if (data.status) {
          executionStatus.value = data.status;
        }
        isMonitoring.value = false;
        closeEventSource();
        break;

      case 'error':
        error.value = data.error || 'Execution error';
        isMonitoring.value = false;
        closeEventSource();
        break;
    }
  }

  /**
   * Stop monitoring the current execution.
   */
  function stopMonitoring(): void {
    isMonitoring.value = false;
    closeEventSource();
  }

  /**
   * Cancel the currently monitored execution.
   */
  async function cancelExecution(workflowId: string): Promise<void> {
    if (!executionId.value) return;
    try {
      await workflowExecutionApi.cancel(workflowId, executionId.value);
      executionStatus.value = 'cancelled';
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to cancel execution';
    }
  }

  /**
   * Reset all state back to defaults.
   */
  function resetState(): void {
    closeEventSource();
    executionId.value = null;
    executionStatus.value = 'pending';
    nodeStates.value = {};
    isMonitoring.value = false;
    error.value = null;
    showApprovalModal.value = false;
    pendingApprovalNodeId.value = null;
    pendingApprovalNodeLabel.value = '';
  }

  /**
   * Apply execution node states to canvas nodes.
   * Sets each node's data.executionStatus field based on nodeStates.
   *
   * The consuming component should call this in a watcher on nodeStates.
   */
  function applyToCanvas(nodes: Ref<Array<{ id: string; data: Record<string, unknown>; [key: string]: unknown }>>): void {
    const states = nodeStates.value;
    nodes.value = nodes.value.map((node) => ({
      ...node,
      data: {
        ...node.data,
        executionStatus: (states[node.id] as NodeExecutionStatus | undefined) || 'pending',
      },
      class: `execution-${states[node.id] || 'pending'}`,
    }));
  }

  /**
   * Close the EventSource connection and null the reference.
   */
  function closeEventSource(): void {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
  }

  // Cleanup on component unmount to prevent SSE connection leaks
  onUnmounted(() => {
    closeEventSource();
  });

  return {
    // State
    executionId,
    executionStatus,
    nodeStates,
    isMonitoring,
    error,

    // Approval gate state
    showApprovalModal,
    pendingApprovalNodeId,
    pendingApprovalNodeLabel,
    pendingApprovals,

    // Functions
    startMonitoring,
    stopMonitoring,
    cancelExecution,
    resetState,
    applyToCanvas,
  };
}
