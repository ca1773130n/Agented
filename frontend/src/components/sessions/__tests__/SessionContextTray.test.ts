import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import SessionContextTray from '../SessionContextTray.vue';
import type { ForgeAttachment } from '../../../services/api/projects';

describe('SessionContextTray', () => {
  it('renders all four add buttons', () => {
    const wrapper = mount(SessionContextTray, {
      props: { attachments: [] },
    });
    const labels = wrapper.findAll('.action-btn').map((b) => b.text());
    expect(labels.join(' ')).toContain('File');
    expect(labels.join(' ')).toContain('Snippet');
    expect(labels.join(' ')).toContain('URL');
    expect(labels.join(' ')).toContain('Entity');
  });

  it('renders one chip per attachment', () => {
    const attachments: ForgeAttachment[] = [
      { kind: 'file', path: 'src/foo.vue' },
      { kind: 'snippet', label: 'tip', text: 'be brief' },
    ];
    const wrapper = mount(SessionContextTray, { props: { attachments } });
    const chips = wrapper.findAll('.chip');
    expect(chips).toHaveLength(2);
    expect(chips[0].text()).toContain('src/foo.vue');
    expect(chips[1].text()).toContain('tip');
  });

  it('emits update:attachments without the removed chip', async () => {
    const attachments: ForgeAttachment[] = [
      { kind: 'file', path: 'a.ts' },
      { kind: 'file', path: 'b.ts' },
    ];
    const wrapper = mount(SessionContextTray, { props: { attachments } });
    await wrapper.findAll('.chip-remove')[0].trigger('click');
    const emitted = wrapper.emitted('update:attachments');
    expect(emitted).toBeDefined();
    expect(emitted![0][0]).toEqual([{ kind: 'file', path: 'b.ts' }]);
  });

  it('opens the file editor and emits a new file attachment on Add', async () => {
    const wrapper = mount(SessionContextTray, { props: { attachments: [] } });
    await wrapper.findAll('.action-btn')[0].trigger('click');
    expect(wrapper.find('[data-testid="file-editor"]').exists()).toBe(true);

    await wrapper.find('[data-testid="file-editor"] input').setValue('docs/spec.md');
    await wrapper
      .findAll('[data-testid="file-editor"] button')[0]
      .trigger('click');

    const emitted = wrapper.emitted('update:attachments');
    expect(emitted).toBeDefined();
    expect(emitted![0][0]).toEqual([{ kind: 'file', path: 'docs/spec.md' }]);
  });

  it('parses JSON entity payload when valid', async () => {
    const wrapper = mount(SessionContextTray, { props: { attachments: [] } });
    await wrapper.findAll('.action-btn')[3].trigger('click');
    await wrapper
      .find('[data-testid="entity-editor"] input')
      .setValue('team-abc');
    await wrapper
      .find('[data-testid="entity-editor"] textarea')
      .setValue('{"id":"team-abc","name":"Core"}');
    await wrapper
      .findAll('[data-testid="entity-editor"] button')[0]
      .trigger('click');

    const emitted = wrapper.emitted('update:attachments');
    expect(emitted).toBeDefined();
    const payload = emitted![0][0] as ForgeAttachment[];
    expect(payload[0]).toMatchObject({
      kind: 'entity',
      ref: 'team-abc',
      payload: { id: 'team-abc', name: 'Core' },
    });
  });

  it('respects disabled state on chip remove buttons', () => {
    const wrapper = mount(SessionContextTray, {
      props: {
        attachments: [{ kind: 'file', path: 'a.ts' }],
        disabled: true,
      },
    });
    const removeBtn = wrapper.find('.chip-remove');
    expect((removeBtn.element as HTMLButtonElement).disabled).toBe(true);
  });
});
