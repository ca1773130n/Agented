import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import ExecutionHistory from '../ExecutionHistory.vue';
import * as api from '../../services/api';

// Mock the entire api module
vi.mock('../../services/api', () => ({
  executionApi: {
    listAll: vi.fn(),
    listForBot: vi.fn(),
    redispatch: vi.fn(),
  },
  triggerApi: {
    get: vi.fn(),
  },
  chunkApi: {
    getResults: vi.fn(),
  },
  ApiError: class ApiError extends Error {},
}));

// Mock composables that use browser APIs
vi.mock('../../composables/useToast', () => ({
  useToast: () => vi.fn(),
}));
vi.mock('../../composables/useFocusTrap', () => ({
  useFocusTrap: () => undefined,
}));
vi.mock('../../composables/useWebMcpTool', () => ({
  useWebMcpTool: () => undefined,
}));
vi.mock('../../composables/useCollaborativeViewer', () => ({
  useCollaborativeViewer: () => ({ viewers: [], isJoined: false }),
}));

// Stub child components
vi.mock('../../components/triggers/ExecutionLogViewer.vue', () => ({
  default: { template: '<div />' },
}));
vi.mock('../../components/executions/HarnessStatePanel.vue', () => ({
  default: { template: '<div />' },
}));
vi.mock('../../components/triggers/ReplayComparison.vue', () => ({
  default: { template: '<div />' },
}));
vi.mock('../../components/triggers/PresenceIndicator.vue', () => ({
  default: { template: '<div />' },
}));
vi.mock('../../components/triggers/ChunkResults.vue', () => ({
  default: { template: '<div />' },
}));
vi.mock('../../components/triggers/BranchNavigator.vue', () => ({
  default: { template: '<div />' },
}));
vi.mock('../../components/base/PageHeader.vue', () => ({
  default: { template: '<div><slot name="actions" /></div>' },
}));
vi.mock('../../components/base/LoadingState.vue', () => ({
  default: { template: '<div />' },
}));
vi.mock('../../components/base/EmptyState.vue', () => ({
  default: { template: '<div />' },
}));

const INTERRUPTED_EXECUTION = {
  id: 1,
  execution_id: 'exec-interrupted',
  trigger_id: 'trig-1',
  trigger_name: 'Test Trigger',
  trigger_type: 'manual' as const,
  started_at: '2026-06-11T00:00:00',
  duration_ms: 5000,
  backend_type: 'claude' as const,
  status: 'interrupted' as const,
  source_type: 'bot' as const,
};

const FAILED_EXECUTION = {
  id: 2,
  execution_id: 'exec-failed',
  trigger_id: 'trig-1',
  trigger_name: 'Test Trigger',
  trigger_type: 'manual' as const,
  started_at: '2026-06-11T00:01:00',
  duration_ms: 3000,
  backend_type: 'claude' as const,
  status: 'failed' as const,
  source_type: 'bot' as const,
};

const SUCCESS_EXECUTION = {
  id: 3,
  execution_id: 'exec-success',
  trigger_id: 'trig-1',
  trigger_name: 'Test Trigger',
  trigger_type: 'manual' as const,
  started_at: '2026-06-11T00:02:00',
  duration_ms: 2000,
  backend_type: 'claude' as const,
  status: 'success' as const,
  source_type: 'bot' as const,
};

const RUNNING_EXECUTION = {
  id: 4,
  execution_id: 'exec-running',
  trigger_id: 'trig-1',
  trigger_name: 'Test Trigger',
  trigger_type: 'manual' as const,
  started_at: '2026-06-11T00:03:00',
  backend_type: 'claude' as const,
  status: 'running' as const,
  source_type: 'bot' as const,
};

describe('ExecutionHistory — Re-dispatch button', () => {
  let wrappers: Array<{ unmount: () => void }> = [];

  beforeEach(() => {
    vi.mocked(api.executionApi.listAll).mockResolvedValue({
      executions: [
        INTERRUPTED_EXECUTION,
        FAILED_EXECUTION,
        SUCCESS_EXECUTION,
        RUNNING_EXECUTION,
      ],
      total: 4,
    });
    vi.mocked(api.executionApi.redispatch).mockResolvedValue({ execution_id: 'exec-new' });
  });

  afterEach(() => {
    wrappers.forEach((w) => w.unmount());
    wrappers = [];
    vi.clearAllMocks();
  });

  function mountView() {
    const wrapper = mount(ExecutionHistory, {
      global: {
        stubs: {
          'vue-router': true,
        },
      },
    });
    wrappers.push(wrapper);
    return wrapper;
  }

  it('renders re-dispatch button for interrupted executions', async () => {
    const wrapper = mountView();
    await flushPromises();
    const allBtns = wrapper.findAll('button.btn-redispatch');
    const ids = allBtns.map(b => b.attributes('data-execution-id') || '');
    expect(ids).toContain('exec-interrupted');
  });

  it('renders re-dispatch button for failed executions', async () => {
    const wrapper = mountView();
    await flushPromises();
    const allBtns = wrapper.findAll('button.btn-redispatch');
    const ids = allBtns.map(b => b.attributes('data-execution-id') || '');
    expect(ids).toContain('exec-failed');
  });

  it('does NOT render re-dispatch button for success executions', async () => {
    const wrapper = mountView();
    await flushPromises();
    const allBtns = wrapper.findAll('button.btn-redispatch');
    const ids = allBtns.map(b => b.attributes('data-execution-id') || '');
    expect(ids).not.toContain('exec-success');
  });

  it('does NOT render re-dispatch button for running executions', async () => {
    const wrapper = mountView();
    await flushPromises();
    const allBtns = wrapper.findAll('button.btn-redispatch');
    const ids = allBtns.map(b => b.attributes('data-execution-id') || '');
    expect(ids).not.toContain('exec-running');
  });

  it('clicking re-dispatch calls executionApi.redispatch with the execution id and refreshes', async () => {
    const wrapper = mountView();
    await flushPromises();

    const redispatchBtns = wrapper.findAll('button.btn-redispatch');
    const interruptedBtn = redispatchBtns.find(b => b.attributes('data-execution-id') === 'exec-interrupted');
    expect(interruptedBtn).toBeDefined();

    await interruptedBtn!.trigger('click');
    await flushPromises();

    expect(api.executionApi.redispatch).toHaveBeenCalledWith('exec-interrupted');
    // After click, loadData() should be called (listAll called again = 2 total)
    expect(api.executionApi.listAll).toHaveBeenCalledTimes(2);
  });
});
