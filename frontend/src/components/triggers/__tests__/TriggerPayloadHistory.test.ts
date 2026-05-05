import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import TriggerPayloadHistory from '../TriggerPayloadHistory.vue';

const showToast = vi.fn();

vi.mock('../../../services/api', () => ({
  triggerEventApi: {
    list: vi.fn(),
    get: vi.fn(),
    replay: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    constructor(public status: number, message: string) {
      super(message);
    }
  },
}));

import { triggerEventApi } from '../../../services/api';

const mockEvent = {
  id: 1,
  trigger_id: 'trig-abc',
  source: 'webhook',
  status: 'fired',
  received_at: '2026-05-05T10:00:00Z',
  payload: { foo: 'bar', n: 42 },
  headers: { 'x-test': 'y' },
  error_message: null,
};

const mountComponent = (triggerId = 'trig-abc') =>
  mount(TriggerPayloadHistory, {
    props: { triggerId },
    global: {
      provide: {
        showToast,
      },
    },
  });

beforeEach(() => {
  vi.clearAllMocks();
  showToast.mockReset();
});

describe('TriggerPayloadHistory', () => {
  it('shows loading state then renders events', async () => {
    let resolveList!: (v: unknown) => void;
    (triggerEventApi.list as ReturnType<typeof vi.fn>).mockReturnValue(
      new Promise((r) => {
        resolveList = r;
      }),
    );
    const wrapper = mountComponent();
    // wait for onMounted to run loadEvents() and flip isLoading=true
    await wrapper.vm.$nextTick();
    expect(wrapper.find('[data-testid="loading"]').exists()).toBe(true);

    resolveList({ events: [mockEvent] });
    await flushPromises();

    expect(wrapper.find('[data-testid="loading"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="event-1"]').exists()).toBe(true);
    expect(wrapper.text()).toContain('webhook');
    expect(wrapper.text()).toContain('fired');
  });

  it('renders empty state when no events', async () => {
    (triggerEventApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({ events: [] });
    const wrapper = mountComponent();
    await flushPromises();

    expect(wrapper.find('[data-testid="empty"]').exists()).toBe(true);
    expect(wrapper.text()).toContain('No trigger events yet');
  });

  it('expands an event to show JSON payload', async () => {
    (triggerEventApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      events: [mockEvent],
    });
    const wrapper = mountComponent();
    await flushPromises();

    expect(wrapper.find('[data-testid="event-body"]').exists()).toBe(false);

    await wrapper.find('.event-header').trigger('click');
    await flushPromises();

    const body = wrapper.find('[data-testid="event-body"]');
    expect(body.exists()).toBe(true);
    expect(body.text()).toContain('"foo"');
    expect(body.text()).toContain('"bar"');
    expect(body.text()).toContain('"n": 42');
  });

  it('shows confirm dialog before replay and fires on confirm', async () => {
    (triggerEventApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      events: [mockEvent],
    });
    (triggerEventApi.replay as ReturnType<typeof vi.fn>).mockResolvedValue({ fired: true });
    const wrapper = mountComponent();
    await flushPromises();

    expect(wrapper.find('[data-testid="confirm-replay"]').exists()).toBe(false);

    await wrapper.find('[data-testid="replay-btn"]').trigger('click');
    expect(wrapper.find('[data-testid="confirm-replay"]').exists()).toBe(true);
    expect(triggerEventApi.replay).not.toHaveBeenCalled();

    await wrapper.find('[data-testid="confirm-replay-btn"]').trigger('click');
    await flushPromises();

    expect(triggerEventApi.replay).toHaveBeenCalledWith(1);
    expect(showToast).toHaveBeenCalledWith('Trigger replayed successfully', 'success');
  });

  it('cancels replay without calling the API', async () => {
    (triggerEventApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      events: [mockEvent],
    });
    const wrapper = mountComponent();
    await flushPromises();

    await wrapper.find('[data-testid="replay-btn"]').trigger('click');
    expect(wrapper.find('[data-testid="confirm-replay"]').exists()).toBe(true);

    await wrapper.find('[data-testid="cancel-replay"]').trigger('click');
    await flushPromises();

    expect(wrapper.find('[data-testid="confirm-replay"]').exists()).toBe(false);
    expect(triggerEventApi.replay).not.toHaveBeenCalled();
  });

  it('renders error state and retries on click', async () => {
    const { ApiError } = await import('../../../services/api');
    (triggerEventApi.list as ReturnType<typeof vi.fn>)
      .mockRejectedValueOnce(new (ApiError as never as { new (s: number, m: string): Error })(500, 'boom'))
      .mockResolvedValueOnce({ events: [mockEvent] });

    const wrapper = mountComponent();
    await flushPromises();

    expect(wrapper.find('[data-testid="error"]').exists()).toBe(true);
    expect(wrapper.text()).toContain('boom');

    await wrapper.find('.retry-btn').trigger('click');
    await flushPromises();

    expect(wrapper.find('[data-testid="error"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="event-1"]').exists()).toBe(true);
  });
});
