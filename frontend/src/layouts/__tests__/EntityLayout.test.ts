import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { defineComponent, h, reactive } from 'vue';
import EntityLayout from '../EntityLayout.vue';

const route = reactive<{ params: Record<string, string> }>({ params: { backendId: 'backend-claude' } });
const replace = vi.fn();
const back = vi.fn();

vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ replace, back }),
}));

function makeHost(loadEntity: () => Promise<unknown>, entityLabel = 'backend') {
  return defineComponent({
    components: { EntityLayout },
    setup() {
      return { loadEntity, entityLabel };
    },
    template: `
      <EntityLayout :load-entity="loadEntity" :entity-label="entityLabel">
        <template #default="{ entity }">
          <div data-test="slot">slot:{{ (entity && entity.id) || 'none' }}</div>
        </template>
      </EntityLayout>
    `,
  });
}

describe('EntityLayout', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    route.params = { backendId: 'backend-claude' };
  });

  it('shows the loading spinner during the first load', async () => {
    let resolve!: (v: unknown) => void;
    const loadEntity = vi.fn(() => new Promise((r) => { resolve = r; }));
    const wrapper = mount(makeHost(loadEntity));

    expect(wrapper.find('.entity-layout__spinner').exists()).toBe(true);
    expect(wrapper.find('[data-test="slot"]').exists()).toBe(false);

    resolve({ id: 'backend-claude' });
    await flushPromises();

    expect(wrapper.find('.entity-layout__spinner').exists()).toBe(false);
    expect(wrapper.find('[data-test="slot"]').text()).toBe('slot:backend-claude');
  });

  it('keeps the previous slot rendered while re-fetching on route-param change', async () => {
    const calls: string[] = [];
    const loadEntity = vi.fn(() => {
      const id = route.params.backendId;
      calls.push(id);
      // Resolve immediately for first call; delay second so we can observe the
      // stale-while-revalidate window.
      if (calls.length === 1) {
        return Promise.resolve({ id });
      }
      return new Promise((r) => { setTimeout(() => r({ id }), 50); });
    });
    const wrapper = mount(makeHost(loadEntity));
    await flushPromises();
    expect(wrapper.find('[data-test="slot"]').text()).toBe('slot:backend-claude');

    route.params = { backendId: 'backend-codex' };
    // Wait for watcher to trigger load() but NOT for the inner promise to resolve.
    await flushPromises();

    expect(wrapper.find('.entity-layout__spinner').exists()).toBe(false);
    expect(wrapper.find('[data-test="slot"]').text()).toBe('slot:backend-claude');

    await new Promise((r) => setTimeout(r, 80));
    await flushPromises();
    expect(wrapper.find('[data-test="slot"]').text()).toBe('slot:backend-codex');
    expect(loadEntity).toHaveBeenCalledTimes(2);
  });

  it('redirects to not-found on a 404 from loadEntity', async () => {
    const loadEntity = vi.fn(() => Promise.reject({ status: 404, message: 'Not found' }));
    mount(makeHost(loadEntity));
    await flushPromises();

    expect(replace).toHaveBeenCalledWith({ name: 'not-found' });
  });

  it('shows the error state with retry/back when loadEntity throws non-404', async () => {
    const loadEntity = vi.fn(() => Promise.reject(new Error('boom')));
    const wrapper = mount(makeHost(loadEntity));
    await flushPromises();

    expect(wrapper.find('.entity-layout__error').exists()).toBe(true);
    expect(wrapper.find('.entity-layout__error-message').text()).toBe('boom');
    const buttons = wrapper.findAll('.entity-layout__error-actions .btn');
    expect(buttons).toHaveLength(2);
    expect(buttons[0].text()).toBe('Retry');
    expect(buttons[1].text()).toBe('Go Back');
  });

  it('Retry re-invokes loadEntity', async () => {
    let attempt = 0;
    const loadEntity = vi.fn(() => {
      attempt++;
      if (attempt === 1) return Promise.reject(new Error('first fail'));
      return Promise.resolve({ id: 'backend-claude' });
    });
    const wrapper = mount(makeHost(loadEntity));
    await flushPromises();
    expect(wrapper.find('.entity-layout__error').exists()).toBe(true);

    await wrapper.findAll('.entity-layout__error-actions .btn')[0].trigger('click');
    await flushPromises();

    expect(loadEntity).toHaveBeenCalledTimes(2);
    expect(wrapper.find('[data-test="slot"]').text()).toBe('slot:backend-claude');
  });
});
