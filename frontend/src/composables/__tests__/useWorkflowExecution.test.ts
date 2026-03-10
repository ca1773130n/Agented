import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref } from 'vue';

// ---------------------------------------------------------------------------
// Mocks -- declared before composable import (vi.mock hoisting)
// ---------------------------------------------------------------------------

const mockStream = vi.fn();
const mockCancel = vi.fn();

vi.mock('../../services/api', () => ({
  workflowExecutionApi: {
    stream: (...a: unknown[]) => mockStream(...a),
    cancel: (...a: unknown[]) => mockCancel(...a),
  },
}));

vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue');
  return { ...actual, onUnmounted: vi.fn() };
});

import { useWorkflowExecution } from '../useWorkflowExecution';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Create a mock EventSource with controllable handlers. */
function createMockEventSource() {
  return {
    onmessage: null as ((event: MessageEvent) => void) | null,
    onerror: null as (() => void) | null,
    close: vi.fn(),
    addEventListener: vi.fn(),
  };
}

/** Build a MessageEvent-like object. */
function msgEvent(data: unknown): MessageEvent {
  return { data: JSON.stringify(data) } as unknown as MessageEvent;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useWorkflowExecution', () => {
  let exec: ReturnType<typeof useWorkflowExecution>;

  beforeEach(() => {
    vi.clearAllMocks();
    exec = useWorkflowExecution();
  });

  // -----------------------------------------------------------------------
  // Initial state
  // -----------------------------------------------------------------------
  describe('initial state', () => {
    it('has null execution id', () => {
      expect(exec.executionId.value).toBeNull();
    });

    it('has pending status', () => {
      expect(exec.executionStatus.value).toBe('pending');
    });

    it('has empty node states', () => {
      expect(exec.nodeStates.value).toEqual({});
    });

    it('is not monitoring', () => {
      expect(exec.isMonitoring.value).toBe(false);
    });

    it('has no error', () => {
      expect(exec.error.value).toBeNull();
    });

    it('has no pending approvals', () => {
      expect(exec.pendingApprovals.value).toEqual([]);
    });
  });

  // -----------------------------------------------------------------------
  // startMonitoring
  // -----------------------------------------------------------------------
  describe('startMonitoring', () => {
    it('initializes state and creates SSE connection', () => {
      const mockEs = createMockEventSource();
      mockStream.mockReturnValue(mockEs);

      exec.startMonitoring('wf-1', 'exec-1');

      expect(exec.executionId.value).toBe('exec-1');
      expect(exec.executionStatus.value).toBe('running');
      expect(exec.isMonitoring.value).toBe(true);
      expect(exec.error.value).toBeNull();
      expect(mockStream).toHaveBeenCalledWith('wf-1', 'exec-1');
    });

    it('closes existing connection before opening new one', () => {
      const mockEs1 = createMockEventSource();
      const mockEs2 = createMockEventSource();
      mockStream.mockReturnValueOnce(mockEs1).mockReturnValueOnce(mockEs2);

      exec.startMonitoring('wf-1', 'exec-1');
      exec.startMonitoring('wf-1', 'exec-2');

      expect(mockEs1.close).toHaveBeenCalled();
      expect(exec.executionId.value).toBe('exec-2');
    });
  });

  // -----------------------------------------------------------------------
  // SSE event handling
  // -----------------------------------------------------------------------
  describe('SSE event handling', () => {
    let mockEs: ReturnType<typeof createMockEventSource>;

    beforeEach(() => {
      mockEs = createMockEventSource();
      mockStream.mockReturnValue(mockEs);
      exec.startMonitoring('wf-1', 'exec-1');
    });

    it('handles status event', () => {
      mockEs.onmessage!(msgEvent({
        type: 'status',
        status: 'running',
        node_states: { 'node-1': 'running', 'node-2': 'pending' },
      }));

      expect(exec.executionStatus.value).toBe('running');
      expect(exec.nodeStates.value).toEqual({ 'node-1': 'running', 'node-2': 'pending' });
    });

    it('handles node_start event', () => {
      mockEs.onmessage!(msgEvent({ type: 'node_start', node_id: 'node-1' }));

      expect(exec.nodeStates.value['node-1']).toBe('running');
    });

    it('handles node_start with pending_approval status', () => {
      mockEs.onmessage!(msgEvent({
        type: 'node_start',
        node_id: 'node-1',
        status: 'pending_approval',
        node_label: 'Approval Gate',
      }));

      expect(exec.nodeStates.value['node-1']).toBe('pending_approval');
      expect(exec.showApprovalModal.value).toBe(true);
      expect(exec.pendingApprovalNodeId.value).toBe('node-1');
      expect(exec.pendingApprovalNodeLabel.value).toBe('Approval Gate');
    });

    it('handles node_complete event', () => {
      mockEs.onmessage!(msgEvent({ type: 'node_start', node_id: 'node-1' }));
      mockEs.onmessage!(msgEvent({ type: 'node_complete', node_id: 'node-1' }));

      expect(exec.nodeStates.value['node-1']).toBe('completed');
    });

    it('handles node_failed event', () => {
      mockEs.onmessage!(msgEvent({ type: 'node_failed', node_id: 'node-1' }));

      expect(exec.nodeStates.value['node-1']).toBe('failed');
    });

    it('handles node_pending_approval event', () => {
      mockEs.onmessage!(msgEvent({
        type: 'node_pending_approval',
        node_id: 'node-2',
        node_label: 'Review Step',
      }));

      expect(exec.nodeStates.value['node-2']).toBe('pending_approval');
      expect(exec.showApprovalModal.value).toBe(true);
      expect(exec.pendingApprovalNodeLabel.value).toBe('Review Step');
    });

    it('handles execution_complete event', () => {
      mockEs.onmessage!(msgEvent({ type: 'execution_complete', status: 'completed' }));

      expect(exec.executionStatus.value).toBe('completed');
      expect(exec.isMonitoring.value).toBe(false);
      expect(mockEs.close).toHaveBeenCalled();
    });

    it('handles error event', () => {
      mockEs.onmessage!(msgEvent({ type: 'error', error: 'Step timeout' }));

      expect(exec.error.value).toBe('Step timeout');
      expect(exec.isMonitoring.value).toBe(false);
      expect(mockEs.close).toHaveBeenCalled();
    });

    it('handles error event with no message', () => {
      mockEs.onmessage!(msgEvent({ type: 'error' }));

      expect(exec.error.value).toBe('Execution error');
    });

    it('ignores unparseable events', () => {
      // Should not throw
      mockEs.onmessage!({ data: 'not-json' } as unknown as MessageEvent);
      expect(exec.nodeStates.value).toEqual({});
    });

    it('handles SSE connection error', () => {
      mockEs.onerror!();

      expect(exec.isMonitoring.value).toBe(false);
      expect(exec.error.value).toBe('Connection lost');
      expect(mockEs.close).toHaveBeenCalled();
    });

    it('detects newly pending_approval nodes in status event', () => {
      // First set node-1 to running
      mockEs.onmessage!(msgEvent({
        type: 'status',
        status: 'running',
        node_states: { 'node-1': 'running' },
      }));

      // Now set node-1 to pending_approval
      mockEs.onmessage!(msgEvent({
        type: 'status',
        status: 'running',
        node_states: { 'node-1': 'pending_approval' },
      }));

      expect(exec.showApprovalModal.value).toBe(true);
      expect(exec.pendingApprovalNodeId.value).toBe('node-1');
    });
  });

  // -----------------------------------------------------------------------
  // pendingApprovals computed
  // -----------------------------------------------------------------------
  describe('pendingApprovals computed', () => {
    it('returns node ids with pending_approval status', () => {
      const mockEs = createMockEventSource();
      mockStream.mockReturnValue(mockEs);
      exec.startMonitoring('wf-1', 'exec-1');

      mockEs.onmessage!(msgEvent({
        type: 'status',
        status: 'running',
        node_states: { 'node-1': 'pending_approval', 'node-2': 'running', 'node-3': 'pending_approval' },
      }));

      expect(exec.pendingApprovals.value).toContain('node-1');
      expect(exec.pendingApprovals.value).toContain('node-3');
      expect(exec.pendingApprovals.value).not.toContain('node-2');
    });
  });

  // -----------------------------------------------------------------------
  // stopMonitoring
  // -----------------------------------------------------------------------
  describe('stopMonitoring', () => {
    it('stops monitoring and closes event source', () => {
      const mockEs = createMockEventSource();
      mockStream.mockReturnValue(mockEs);

      exec.startMonitoring('wf-1', 'exec-1');
      exec.stopMonitoring();

      expect(exec.isMonitoring.value).toBe(false);
      expect(mockEs.close).toHaveBeenCalled();
    });
  });

  // -----------------------------------------------------------------------
  // cancelExecution
  // -----------------------------------------------------------------------
  describe('cancelExecution', () => {
    it('does nothing when no execution id', async () => {
      await exec.cancelExecution('wf-1');

      expect(mockCancel).not.toHaveBeenCalled();
    });

    it('cancels execution and updates status', async () => {
      exec.executionId.value = 'exec-1';
      mockCancel.mockResolvedValue({});

      await exec.cancelExecution('wf-1');

      expect(mockCancel).toHaveBeenCalledWith('wf-1', 'exec-1');
      expect(exec.executionStatus.value).toBe('cancelled');
    });

    it('sets error on cancel failure', async () => {
      exec.executionId.value = 'exec-1';
      mockCancel.mockRejectedValue(new Error('Cancel denied'));

      await exec.cancelExecution('wf-1');

      expect(exec.error.value).toBe('Cancel denied');
    });

    it('sets generic error for non-Error throws', async () => {
      exec.executionId.value = 'exec-1';
      mockCancel.mockRejectedValue('boom');

      await exec.cancelExecution('wf-1');

      expect(exec.error.value).toBe('Failed to cancel execution');
    });
  });

  // -----------------------------------------------------------------------
  // resetState
  // -----------------------------------------------------------------------
  describe('resetState', () => {
    it('resets all state to defaults', () => {
      const mockEs = createMockEventSource();
      mockStream.mockReturnValue(mockEs);
      exec.startMonitoring('wf-1', 'exec-1');

      exec.resetState();

      expect(exec.executionId.value).toBeNull();
      expect(exec.executionStatus.value).toBe('pending');
      expect(exec.nodeStates.value).toEqual({});
      expect(exec.isMonitoring.value).toBe(false);
      expect(exec.error.value).toBeNull();
      expect(exec.showApprovalModal.value).toBe(false);
      expect(exec.pendingApprovalNodeId.value).toBeNull();
      expect(exec.pendingApprovalNodeLabel.value).toBe('');
      expect(mockEs.close).toHaveBeenCalled();
    });
  });

  // -----------------------------------------------------------------------
  // applyToCanvas
  // -----------------------------------------------------------------------
  describe('applyToCanvas', () => {
    it('applies node states to canvas nodes', () => {
      exec.nodeStates.value = { 'node-1': 'completed', 'node-2': 'failed' };

      const nodes = ref<{ id: string; data: Record<string, string>; class?: string }[]>([
        { id: 'node-1', data: { label: 'A' } },
        { id: 'node-2', data: { label: 'B' } },
        { id: 'node-3', data: { label: 'C' } },
      ]);

      exec.applyToCanvas(nodes);

      expect(nodes.value[0].data.executionStatus).toBe('completed');
      expect(nodes.value[0].class).toBe('execution-completed');
      expect(nodes.value[1].data.executionStatus).toBe('failed');
      expect(nodes.value[2].data.executionStatus).toBe('pending');
      expect(nodes.value[2].class).toBe('execution-pending');
    });
  });
});
