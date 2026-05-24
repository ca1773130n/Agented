/**
 * HarnessLayersCard — read+toggle surface for harness layers + per-bot run
 * history snapshots.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { defineComponent, h } from 'vue';

const { listForBot, getLayer, toggle, runHistory, triggerList } = vi.hoisted(
  () => ({
    listForBot: vi.fn(),
    getLayer: vi.fn(),
    toggle: vi.fn(),
    runHistory: vi.fn(),
    triggerList: vi.fn(),
  }),
);

vi.mock('../../../../services/api/harness-layers', async () => {
  const actual = await vi.importActual<
    typeof import('../../../../services/api/harness-layers')
  >('../../../../services/api/harness-layers');
  return {
    ...actual,
    harnessLayersApi: { listForBot, getLayer, toggle, runHistory },
  };
});

vi.mock('../../../../services/api', () => ({
  triggerApi: { list: triggerList },
}));

vi.mock('../../../../components/base/LoadingState.vue', () => ({
  default: defineComponent({ render: () => h('div', { class: 'loading-stub' }) }),
}));
vi.mock('../../../../components/base/ErrorState.vue', () => ({
  default: defineComponent({ render: () => h('div', { class: 'error-stub' }) }),
}));

import HarnessLayersCard from '../HarnessLayersCard.vue';

function _layer(over: Partial<{ id: string; layer: string; name: string;
                                enabled: boolean; payload: Record<string, unknown> }>) {
  return {
    id: over.id || 'hl-1',
    bot_id: 'bot-x',
    trigger_id: null,
    layer: over.layer || 'h3',
    name: over.name || 'rule',
    enabled: over.enabled ?? true,
    version: 1,
    parent_layer_id: null,
    source_kind: 'manual',
    payload: over.payload || { title: 'r', rule_text: 'ok' },
    created_at: '2026-05-25T00:00:00Z',
    updated_at: '2026-05-25T00:00:00Z',
  };
}

beforeEach(() => {
  for (const fn of [listForBot, getLayer, toggle, runHistory, triggerList]) {
    fn.mockReset();
  }
  triggerList.mockResolvedValue({
    triggers: [{ id: 'bot-x', name: 'X' }],
  });
});

describe('HarnessLayersCard', () => {
  it('lists layers grouped by H2/H3/H4/H5 and toggle works', async () => {
    listForBot.mockResolvedValue({
      bot_id: 'bot-x',
      layers: {
        h2: [_layer({ id: 'hl-h2', layer: 'h2', name: 'block-rm' })],
        h3: [_layer({ id: 'hl-h3', layer: 'h3', name: 'quote-cols' })],
        h4: [],
        h5: [_layer({ id: 'hl-h5', layer: 'h5', name: 'refund-recipe' })],
      },
    });
    runHistory.mockResolvedValue({ bot_id: 'bot-x', snapshots: [] });
    toggle.mockResolvedValue({ ..._layer({ id: 'hl-h2' }), enabled: false });

    const w = mount(HarnessLayersCard);
    await flushPromises();

    expect(w.find('[data-testid="layers-kind-h2"]').text()).toContain('block-rm');
    expect(w.find('[data-testid="layers-kind-h3"]').text()).toContain('quote-cols');
    expect(w.find('[data-testid="layers-kind-h4"]').text()).toContain('0');
    expect(w.find('[data-testid="layers-kind-h5"]').text()).toContain('refund-recipe');

    // Toggle a layer
    await w.find('[data-testid="layer-toggle-hl-h2"]').trigger('click');
    await flushPromises();
    expect(toggle).toHaveBeenCalledWith('hl-h2', false);
    // listForBot reloaded after the toggle.
    expect(listForBot).toHaveBeenCalledTimes(2);
  });

  it('expand reveals the payload JSON', async () => {
    listForBot.mockResolvedValue({
      bot_id: 'bot-x',
      layers: {
        h2: [], h4: [], h5: [],
        h3: [_layer({ id: 'hl-exp', payload: { title: 'foo', rule_text: 'bar' } })],
      },
    });
    runHistory.mockResolvedValue({ bot_id: 'bot-x', snapshots: [] });

    const w = mount(HarnessLayersCard);
    await flushPromises();

    expect(w.find('[data-testid="layer-payload-hl-exp"]').exists()).toBe(false);
    await w.find('[data-testid="layer-expand-hl-exp"]').trigger('click');
    const pre = w.find('[data-testid="layer-payload-hl-exp"]');
    expect(pre.exists()).toBe(true);
    expect(pre.text()).toContain('"title": "foo"');
  });

  it('empty state shows when no layers are enabled', async () => {
    listForBot.mockResolvedValue({
      bot_id: 'bot-x',
      layers: { h2: [], h3: [], h4: [], h5: [] },
    });
    runHistory.mockResolvedValue({ bot_id: 'bot-x', snapshots: [] });
    const w = mount(HarnessLayersCard);
    await flushPromises();
    expect(w.find('[data-testid="layers-empty"]').exists()).toBe(true);
  });

  it('renders recent run history with versions and applied flag', async () => {
    listForBot.mockResolvedValue({
      bot_id: 'bot-x',
      layers: {
        h2: [], h3: [_layer({})], h4: [], h5: [],
      },
    });
    runHistory.mockResolvedValue({
      bot_id: 'bot-x',
      snapshots: [
        {
          execution_id: 'exec-a',
          harness_kind: 'claude',
          layer_versions: { h3: 1, h2: 2 },
          applied: true,
          created_at: '2026-05-25T00:00:00Z',
        },
        {
          execution_id: 'exec-b',
          harness_kind: 'codex',
          layer_versions: { h3: 1 },
          applied: false,
          created_at: '2026-05-25T00:01:00Z',
        },
      ],
    });
    const w = mount(HarnessLayersCard);
    await flushPromises();

    const history = w.find('[data-testid="layers-run-history"]');
    expect(history.text()).toContain('Recent runs (2)');
    const a = w.find('[data-testid="history-row-exec-a"]');
    expect(a.text()).toContain('exec-a');
    expect(a.text()).toContain('applied');
    expect(a.text()).toContain('H2@v2');
    expect(a.text()).toContain('H3@v1');
    const b = w.find('[data-testid="history-row-exec-b"]');
    expect(b.text()).toContain('snapshot-only');
  });

  it('changing the bot reloads layers + history', async () => {
    triggerList.mockResolvedValue({
      triggers: [
        { id: 'bot-x', name: 'X' },
        { id: 'bot-y', name: 'Y' },
      ],
    });
    listForBot
      .mockResolvedValueOnce({
        bot_id: 'bot-x',
        layers: { h2: [], h3: [_layer({})], h4: [], h5: [] },
      })
      .mockResolvedValueOnce({
        bot_id: 'bot-y',
        layers: { h2: [_layer({ layer: 'h2', name: 'block-y' })],
                  h3: [], h4: [], h5: [] },
      });
    runHistory.mockResolvedValue({ bot_id: 'bot-x', snapshots: [] });

    const w = mount(HarnessLayersCard);
    await flushPromises();
    expect(listForBot).toHaveBeenCalledWith('bot-x');

    const select = w.find<HTMLSelectElement>('[data-testid="layers-bot-select"]');
    await select.setValue('bot-y');
    await flushPromises();
    expect(listForBot).toHaveBeenCalledWith('bot-y');
    expect(w.text()).toContain('block-y');
  });
});
