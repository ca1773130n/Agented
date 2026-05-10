import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

vi.mock('../../services/api', () => ({
  superAgentActivityApi: {
    rollup: vi.fn(),
    list: vi.fn(),
    listForSession: vi.fn(),
  },
}));

import { superAgentActivityApi } from '../../services/api';
import SuperAgentInspectorPage from '../SuperAgentInspectorPage.vue';

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

const baseRollup = {
  super_agent_id: 'sa-1',
  event_count: 5,
  error_count: 1,
  total_cost_usd: 0.25,
  last_active_at: '2026-05-10T00:00:00Z',
  status_pill: 'healthy' as const,
  cost_per_event_avg: 0.05,
  error_rate: 0.2,
};

const baseEvent = {
  id: 1,
  super_agent_id: 'sa-1',
  session_id: null,
  event_type: 'message_turn',
  recorded_at: '2026-05-10T00:00:00Z',
  payload: '{"role":"user"}',
  cost_tokens_in: null,
  cost_tokens_out: null,
  cost_usd: 0.01,
  status: 'ok',
  error_message: null,
  duration_ms: null,
};

function mountInspector() {
  return mount(SuperAgentInspectorPage, { props: { superAgentId: 'sa-1' } });
}

describe('SuperAgentInspectorPage', () => {
  it('renders loading state initially', () => {
    (superAgentActivityApi.rollup as ReturnType<typeof vi.fn>).mockImplementation(
      () => new Promise(() => {}),
    );
    (superAgentActivityApi.list as ReturnType<typeof vi.fn>).mockImplementation(
      () => new Promise(() => {}),
    );
    const wrapper = mountInspector();
    expect(wrapper.find('[data-testid="loading"]').exists()).toBe(true);
  });

  it('renders rollup card and timeline on success', async () => {
    (superAgentActivityApi.rollup as ReturnType<typeof vi.fn>).mockResolvedValue(
      baseRollup,
    );
    (superAgentActivityApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      events: [baseEvent],
    });
    const wrapper = mountInspector();
    await flushPromises();
    expect(wrapper.find('[data-testid="rollup-card"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="timeline"]').exists()).toBe(true);
    expect(wrapper.text()).toContain('message_turn');
    expect(wrapper.text()).toContain('Healthy');
  });

  it('renders error state on rollup failure', async () => {
    (superAgentActivityApi.rollup as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('boom'),
    );
    (superAgentActivityApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      events: [],
    });
    const wrapper = mountInspector();
    await flushPromises();
    expect(wrapper.find('[data-testid="error"]').exists()).toBe(true);
    expect(wrapper.text()).toContain('boom');
  });

  it('renders empty state when no events', async () => {
    (superAgentActivityApi.rollup as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...baseRollup,
      event_count: 0,
      status_pill: 'idle',
    });
    (superAgentActivityApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      events: [],
    });
    const wrapper = mountInspector();
    await flushPromises();
    expect(wrapper.find('[data-testid="empty"]').exists()).toBe(true);
    expect(wrapper.text()).toContain('No activity yet');
  });

  it('shows the correct status pill', async () => {
    (superAgentActivityApi.rollup as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...baseRollup,
      status_pill: 'errored',
    });
    (superAgentActivityApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      events: [],
    });
    const wrapper = mountInspector();
    await flushPromises();
    const pill = wrapper.find('.sa-rollup__pill');
    expect(pill.attributes('data-status')).toBe('errored');
    expect(pill.text()).toBe('Errored');
  });

  it('expands a row to reveal payload JSON when clicked', async () => {
    (superAgentActivityApi.rollup as ReturnType<typeof vi.fn>).mockResolvedValue(
      baseRollup,
    );
    (superAgentActivityApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      events: [baseEvent],
    });
    const wrapper = mountInspector();
    await flushPromises();
    expect(wrapper.find('[data-testid="payload-1"]').exists()).toBe(false);
    await wrapper.find('[data-testid="expand-1"]').trigger('click');
    expect(wrapper.find('[data-testid="payload-1"]').exists()).toBe(true);
    // Pretty-printed JSON contains the parsed key
    expect(wrapper.find('[data-testid="payload-1"]').text()).toContain('"role"');
    // Click again collapses it.
    await wrapper.find('[data-testid="expand-1"]').trigger('click');
    expect(wrapper.find('[data-testid="payload-1"]').exists()).toBe(false);
  });

  it('refetches with the right since param when the time-window changes', async () => {
    (superAgentActivityApi.rollup as ReturnType<typeof vi.fn>).mockResolvedValue(
      baseRollup,
    );
    (superAgentActivityApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      events: [],
    });
    const wrapper = mountInspector();
    await flushPromises();
    // Default is 7d → rollup called with 7
    expect(superAgentActivityApi.rollup).toHaveBeenLastCalledWith('sa-1', 7);
    const initialList = (superAgentActivityApi.list as ReturnType<typeof vi.fn>)
      .mock.calls.at(-1);
    expect(initialList?.[1]).toMatchObject({ limit: 200 });
    expect(typeof initialList?.[1]?.since).toBe('string');

    const select = wrapper.find<HTMLSelectElement>('[data-testid="window-select"]');
    select.element.value = '1h';
    await select.trigger('change');
    await flushPromises();

    // Rollup uses 1 day for sub-day windows (clamped server-side min).
    expect(superAgentActivityApi.rollup).toHaveBeenLastCalledWith('sa-1', 1);

    const lastList = (superAgentActivityApi.list as ReturnType<typeof vi.fn>).mock
      .calls.at(-1);
    expect(lastList?.[1]?.since).toBeDefined();
    // since for 1h must be more recent than since for 7d.
    const initialSince = new Date(initialList?.[1]?.since as string).getTime();
    const newSince = new Date(lastList?.[1]?.since as string).getTime();
    expect(newSince).toBeGreaterThan(initialSince);
  });

  it('multi-select type filter applies selected types to the list call', async () => {
    (superAgentActivityApi.rollup as ReturnType<typeof vi.fn>).mockResolvedValue(
      baseRollup,
    );
    (superAgentActivityApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      events: [],
    });
    const wrapper = mountInspector();
    await flushPromises();

    const messageChip = wrapper.find<HTMLInputElement>(
      '[data-testid="type-chip-message_turn"] input',
    );
    const toolChip = wrapper.find<HTMLInputElement>(
      '[data-testid="type-chip-tool_call"] input',
    );
    await messageChip.setValue(true);
    await toolChip.setValue(true);
    await flushPromises();

    const lastCall = (superAgentActivityApi.list as ReturnType<typeof vi.fn>).mock
      .calls.at(-1);
    expect(lastCall?.[0]).toBe('sa-1');
    expect(lastCall?.[1]).toMatchObject({
      types: expect.arrayContaining(['message_turn', 'tool_call']),
    });
  });

  it('status filter "errored" hides ok events', async () => {
    const okEvent = { ...baseEvent, id: 1, status: 'ok' };
    const errorEvent = {
      ...baseEvent,
      id: 2,
      status: 'error',
      error_message: 'boom',
    };
    (superAgentActivityApi.rollup as ReturnType<typeof vi.fn>).mockResolvedValue(
      baseRollup,
    );
    (superAgentActivityApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      events: [okEvent, errorEvent],
    });
    const wrapper = mountInspector();
    await flushPromises();
    // Both visible by default
    expect(wrapper.find('[data-testid="row-1"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="row-2"]').exists()).toBe(true);

    const statusSelect = wrapper.find<HTMLSelectElement>(
      '[data-testid="status-filter"]',
    );
    statusSelect.element.value = 'error';
    await statusSelect.trigger('change');
    await flushPromises();

    expect(wrapper.find('[data-testid="row-1"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="row-2"]').exists()).toBe(true);
  });

  it('polls the API every 10s', async () => {
    (superAgentActivityApi.rollup as ReturnType<typeof vi.fn>).mockResolvedValue(
      baseRollup,
    );
    (superAgentActivityApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      events: [],
    });
    mountInspector();
    await flushPromises();
    const initialCount = (superAgentActivityApi.rollup as ReturnType<typeof vi.fn>)
      .mock.calls.length;
    vi.advanceTimersByTime(10_000);
    await flushPromises();
    expect(
      (superAgentActivityApi.rollup as ReturnType<typeof vi.fn>).mock.calls
        .length,
    ).toBeGreaterThan(initialCount);
  });
});
