import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import PlanningCommandBar from '../PlanningCommandBar.vue';
import { GRD_COMMAND_MANIFEST } from '../planningCommands';
import en from '../../../locales/en.json';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en },
  missingWarn: false,
  fallbackWarn: false,
});

function mountBar(status = 'idle') {
  return mount(PlanningCommandBar, {
    props: { status: status as never, grdInitStatus: 'ready' },
    global: { plugins: [i18n] },
  });
}

describe('PlanningCommandBar', () => {
  it('renders all six groups from the manifest with >=1 item each', () => {
    const wrapper = mountBar();
    const groups = wrapper.findAll('.command-group');
    expect(groups).toHaveLength(GRD_COMMAND_MANIFEST.length);
    for (const g of groups) {
      expect(g.findAll('.command-btn').length).toBeGreaterThanOrEqual(1);
    }
  });

  it('renders the full manifest command roster', () => {
    const wrapper = mountBar();
    const total = GRD_COMMAND_MANIFEST.flatMap((g) => g.commands).length;
    expect(wrapper.findAll('.command-btn')).toHaveLength(total);
  });

  it('emits invoke with the command name and its group on click', async () => {
    const wrapper = mountBar();
    const research = wrapper.find('button[data-command="research"]');
    expect(research.exists()).toBe(true);
    await research.trigger('click');
    const events = wrapper.emitted('invoke');
    expect(events).toBeTruthy();
    expect(events![0]).toEqual(['research', { group: 'Research' }]);
  });

  it('emits the harness group for harness commands', async () => {
    const wrapper = mountBar();
    await wrapper.find('button[data-command="harness"]').trigger('click');
    const events = wrapper.emitted('invoke');
    expect(events![0]).toEqual(['harness', { group: 'Harness' }]);
  });

  it('marks deprecated commands with a badge', () => {
    const wrapper = mountBar();
    const evolve = wrapper.find('button[data-command="evolve"]');
    expect(evolve.exists()).toBe(true);
    expect(evolve.classes()).toContain('is-deprecated');
    expect(evolve.find('.deprecated-badge').exists()).toBe(true);
  });

  it('disables buttons while a session is running', () => {
    const wrapper = mountBar('running');
    const btn = wrapper.find('.command-btn');
    expect((btn.element as HTMLButtonElement).disabled).toBe(true);
  });

  it('emits build-loop when the Build Loop command is clicked', async () => {
    const wrapper = mountBar();
    const buildLoop = wrapper.find('[data-command="build-loop"]');
    expect(buildLoop.exists()).toBe(true);
    await buildLoop.trigger('click');
    expect(wrapper.emitted('build-loop')).toBeTruthy();
    expect(wrapper.emitted('build-loop')!).toHaveLength(1);
    // Build Loop is a host-handled action, not a /grd: planning command.
    expect(wrapper.emitted('invoke')).toBeFalsy();
  });
});
