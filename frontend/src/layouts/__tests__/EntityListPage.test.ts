import { describe, it, expect, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { defineComponent } from 'vue';
import EntityListPage from '../EntityListPage.vue';

interface Item { id: string; name: string }

function makeHost(loadItems: () => Promise<Item[]>) {
  return defineComponent({
    components: { EntityListPage },
    setup() {
      return { loadItems };
    },
    template: `
      <EntityListPage
        title="Backends"
        subtitle="Manage AI providers"
        :load-items="loadItems"
        empty-title="No backends"
        empty-description="Add one to get started"
      >
        <template #default="{ items }">
          <div data-test="content">
            <span v-for="i in items" :key="i.id" data-test="row">{{ i.name }}</span>
          </div>
        </template>
      </EntityListPage>
    `,
  });
}

describe('EntityListPage', () => {
  it('renders the loading state during the first fetch', async () => {
    let resolve!: (v: Item[]) => void;
    const loadItems = vi.fn(() => new Promise<Item[]>((r) => { resolve = r; }));
    const wrapper = mount(makeHost(loadItems));

    expect(wrapper.find('.ds-loading-state').exists()).toBe(true);
    expect(wrapper.find('[data-test="content"]').exists()).toBe(false);

    resolve([{ id: '1', name: 'Claude' }]);
    await flushPromises();

    expect(wrapper.find('.ds-loading-state').exists()).toBe(false);
    expect(wrapper.findAll('[data-test="row"]').map(w => w.text())).toEqual(['Claude']);
  });

  it('shows the empty state when the loader returns []', async () => {
    const loadItems = vi.fn(() => Promise.resolve<Item[]>([]));
    const wrapper = mount(makeHost(loadItems));
    await flushPromises();

    expect(wrapper.find('.ds-empty-state').exists()).toBe(true);
    expect(wrapper.text()).toContain('No backends');
    expect(wrapper.text()).toContain('Add one to get started');
    expect(wrapper.find('[data-test="content"]').exists()).toBe(false);
  });

  it('shows the error state with retry on loader rejection', async () => {
    const loadItems = vi.fn(() => Promise.reject(new Error('boom')));
    const wrapper = mount(makeHost(loadItems));
    await flushPromises();

    const errorRoot = wrapper.find('.ds-error-state');
    expect(errorRoot.exists()).toBe(true);
    expect(errorRoot.text()).toContain('boom');
  });

  it('Retry click re-invokes loadItems', async () => {
    let attempts = 0;
    const loadItems = vi.fn(() => {
      attempts++;
      if (attempts === 1) return Promise.reject(new Error('first fail'));
      return Promise.resolve<Item[]>([{ id: 'x', name: 'Codex' }]);
    });
    const wrapper = mount(makeHost(loadItems));
    await flushPromises();
    expect(wrapper.find('.ds-error-state').exists()).toBe(true);

    const retry = wrapper.find('.ds-error-state button');
    await retry.trigger('click');
    await flushPromises();

    expect(loadItems).toHaveBeenCalledTimes(2);
    expect(wrapper.findAll('[data-test="row"]').map(w => w.text())).toEqual(['Codex']);
  });

  it('exposes refresh via slot prop', async () => {
    let attempts = 0;
    const loadItems = vi.fn(() => {
      attempts++;
      return Promise.resolve<Item[]>([{ id: String(attempts), name: `Run ${attempts}` }]);
    });
    const Host = defineComponent({
      components: { EntityListPage },
      setup() { return { loadItems }; },
      template: `
        <EntityListPage
          title="x"
          :load-items="loadItems"
          empty-title="empty"
        >
          <template #default="{ items, refresh }">
            <button data-test="reload" @click="refresh">reload</button>
            <span v-for="i in items" :key="i.id" data-test="row">{{ i.name }}</span>
          </template>
        </EntityListPage>
      `,
    });
    const wrapper = mount(Host);
    await flushPromises();
    expect(wrapper.findAll('[data-test="row"]').map(w => w.text())).toEqual(['Run 1']);

    await wrapper.find('[data-test="reload"]').trigger('click');
    await flushPromises();
    expect(loadItems).toHaveBeenCalledTimes(2);
    expect(wrapper.findAll('[data-test="row"]').map(w => w.text())).toEqual(['Run 2']);
  });
});
