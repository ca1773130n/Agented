import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import BranchNavigator from '../BranchNavigator.vue';

// Mock the API package consumed by useConversationBranch (Phase 25 follow-up B).
vi.mock('../../../services/api', () => ({
  branchApi: {
    getBranches: vi.fn(),
    getBranchTree: vi.fn(),
    getMessages: vi.fn(),
    createBranch: vi.fn(),
    addMessage: vi.fn(),
  },
  sessionForkApi: {
    fork: vi.fn(),
  },
}));

import { branchApi, sessionForkApi } from '../../../services/api';

const branch = {
  id: 'branch-main',
  name: 'main',
  message_count: 2,
  created_at: '2026-06-01T10:00:00Z',
};

const messages = [
  { id: 'm0', role: 'user', content: 'hi', message_index: 0, created_at: '2026-06-01T10:00:00Z' },
  {
    id: 'm1',
    role: 'assistant',
    content: 'hello',
    message_index: 1,
    created_at: '2026-06-01T10:00:01Z',
  },
];

function stubBranchLoad() {
  (branchApi.getBranches as ReturnType<typeof vi.fn>).mockResolvedValue({ branches: [branch] });
  (branchApi.getBranchTree as ReturnType<typeof vi.fn>).mockResolvedValue(null);
  (branchApi.getMessages as ReturnType<typeof vi.fn>).mockResolvedValue({ messages });
}

async function mountWithSelectedBranch(props: {
  conversationId: string;
  projectId?: string;
  sessionId?: string;
}) {
  stubBranchLoad();
  const wrapper = mount(BranchNavigator, {
    props,
    global: { stubs: { MarkdownContent: true } },
  });
  await flushPromises();
  // Select the (only) branch to render its message thread.
  await wrapper.find('.tree-node').trigger('click');
  await flushPromises();
  // Hover the assistant message so its per-message actions render.
  const items = wrapper.findAll('.message-item');
  await items[1].trigger('mouseenter');
  return wrapper;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('BranchNavigator — Fork to run (Phase 25)', () => {
  it('calls sessionForkApi.fork with the right args and surfaces the new psess- id on success', async () => {
    (sessionForkApi.fork as ReturnType<typeof vi.fn>).mockResolvedValue({
      branch_id: 'branch-forked',
      session_id: 'psess-newrun',
    });

    const wrapper = await mountWithSelectedBranch({
      conversationId: 'conv-1',
      projectId: 'proj-1',
      sessionId: 'psess-origin',
    });

    const forkRunBtn = wrapper.find('.fork-run-btn');
    expect(forkRunBtn.exists()).toBe(true);

    await forkRunBtn.trigger('click');
    await flushPromises();

    // API called with (projectId, sessionId, {conversationId, forkMessageIndex}).
    expect(sessionForkApi.fork).toHaveBeenCalledTimes(1);
    expect(sessionForkApi.fork).toHaveBeenCalledWith('proj-1', 'psess-origin', {
      conversationId: 'conv-1',
      forkMessageIndex: 1,
      name: undefined,
    });

    // Emits the new run so the parent can navigate to it.
    const forkedEvents = wrapper.emitted('forked-run');
    expect(forkedEvents).toBeTruthy();
    expect(forkedEvents![0][0]).toEqual({ sessionId: 'psess-newrun', branchId: 'branch-forked' });

    // Surfaces the new psess- id in the UI.
    expect(wrapper.text()).toContain('psess-newrun');
  });

  it('does not offer the run-fork action without projectId + sessionId', async () => {
    const wrapper = await mountWithSelectedBranch({ conversationId: 'conv-1' });
    expect(wrapper.find('.fork-run-btn').exists()).toBe(false);
    // The in-place branch fork is still available.
    expect(wrapper.find('.fork-btn').exists()).toBe(true);
  });

  it('does not emit or surface a run when the fork call fails', async () => {
    (sessionForkApi.fork as ReturnType<typeof vi.fn>).mockResolvedValue(null);

    const wrapper = await mountWithSelectedBranch({
      conversationId: 'conv-1',
      projectId: 'proj-1',
      sessionId: 'psess-origin',
    });

    await wrapper.find('.fork-run-btn').trigger('click');
    await flushPromises();

    expect(sessionForkApi.fork).toHaveBeenCalledTimes(1);
    expect(wrapper.emitted('forked-run')).toBeFalsy();
    expect(wrapper.find('.fork-run-success').exists()).toBe(false);
  });
});
