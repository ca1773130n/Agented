import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

vi.mock('../../services/api', () => ({
  botHealthApi: {
    list: vi.fn(),
  },
}));

import { botHealthApi } from '../../services/api';
import BotHealthPage from '../BotHealthPage.vue';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('BotHealthPage', () => {
  it('renders loading state initially', () => {
    (botHealthApi.list as ReturnType<typeof vi.fn>).mockImplementation(
      () => new Promise(() => {}),
    );
    const wrapper = mount(BotHealthPage);
    expect(wrapper.find('[data-testid="loading"]').exists()).toBe(true);
  });

  it('renders rollup cards on success', async () => {
    (botHealthApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      window_days: 7,
      rollups: [
        {
          bot_id: 'bot-1',
          bot_name: 'Bot One',
          success_count: 9,
          fail_count: 1,
          success_rate: 0.9,
          p50_duration_ms: 100,
          p95_duration_ms: 200,
          p99_duration_ms: 300,
          last_run_at: '2026-05-05T00:00:00Z',
          last_failure_at: '2026-05-04T00:00:00Z',
          last_failure_message: 'something went wrong',
          status_pill: 'healthy',
        },
      ],
    });
    const wrapper = mount(BotHealthPage);
    await flushPromises();
    expect(wrapper.find('[data-testid="grid"]').exists()).toBe(true);
    expect(wrapper.text()).toContain('Bot One');
    expect(wrapper.text()).toContain('90%');
    expect(wrapper.text()).toContain('200 ms');
  });

  it('renders error state on failure', async () => {
    (botHealthApi.list as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('boom'));
    const wrapper = mount(BotHealthPage);
    await flushPromises();
    expect(wrapper.find('[data-testid="error"]').exists()).toBe(true);
    expect(wrapper.text()).toContain('boom');
  });

  it('renders empty state when no rollups', async () => {
    (botHealthApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      window_days: 7,
      rollups: [],
    });
    const wrapper = mount(BotHealthPage);
    await flushPromises();
    expect(wrapper.find('[data-testid="empty"]').exists()).toBe(true);
    expect(wrapper.text()).toContain('No bots yet');
  });

  it('shows correct pill for each status', async () => {
    (botHealthApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      window_days: 7,
      rollups: [
        {
          bot_id: 'b1', bot_name: 'Healthy', success_count: 10, fail_count: 0,
          success_rate: 1.0, p50_duration_ms: 100, p95_duration_ms: 110, p99_duration_ms: 120,
          last_run_at: null, last_failure_at: null, last_failure_message: null,
          status_pill: 'healthy',
        },
        {
          bot_id: 'b2', bot_name: 'Degraded', success_count: 7, fail_count: 3,
          success_rate: 0.7, p50_duration_ms: 100, p95_duration_ms: 110, p99_duration_ms: 120,
          last_run_at: null, last_failure_at: null, last_failure_message: 'x',
          status_pill: 'degraded',
        },
        {
          bot_id: 'b3', bot_name: 'Down', success_count: 0, fail_count: 5,
          success_rate: 0.0, p50_duration_ms: 100, p95_duration_ms: 110, p99_duration_ms: 120,
          last_run_at: null, last_failure_at: null, last_failure_message: 'y',
          status_pill: 'down',
        },
      ],
    });
    const wrapper = mount(BotHealthPage);
    await flushPromises();
    const pills = wrapper.findAll('.bh-card__pill');
    expect(pills.map((p) => p.attributes('data-status'))).toEqual([
      'healthy',
      'degraded',
      'down',
    ]);
  });

  it('refetches when the window selector changes', async () => {
    (botHealthApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      window_days: 7,
      rollups: [],
    });
    const wrapper = mount(BotHealthPage);
    await flushPromises();
    expect(botHealthApi.list).toHaveBeenCalledWith(7);

    const select = wrapper.find<HTMLSelectElement>('[data-testid="window-select"]');
    // setValue on @vue/test-utils sends the literal string; force the
    // .number modifier outcome by setting the value then dispatching change.
    select.element.value = '30';
    await select.trigger('change');
    await flushPromises();
    // Last call should be with windowDays === 30 (numeric, via .number).
    const calls = (botHealthApi.list as ReturnType<typeof vi.fn>).mock.calls;
    expect(calls[calls.length - 1][0]).toBe(30);
  });
});
