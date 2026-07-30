import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

// The two GRD 0.5.0 steering settings write to the project's OWN
// .planning/config.json — the file GRD reads. The failure this guards against is
// a settings control that looks saved but changes nothing: either by not
// reaching the API at all, or by being offered for a project that has no GRD
// config, where the write is guaranteed to fail.

const steering = vi.hoisted(() => ({ list: vi.fn(), set: vi.fn() }));
const settings = vi.hoisted(() => ({ getAll: vi.fn(), set: vi.fn() }));

vi.mock('../../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  grdSteeringApi: steering,
  settingsApi: settings,
}));
vi.mock('../../../composables/useToast', () => ({ useToast: () => vi.fn() }));

import GrdSettings from '../GrdSettings.vue';

const CONFIGURED = {
  project_id: 'proj-1',
  project_name: 'P1',
  local_path: '/tmp/p1',
  config_path: '/tmp/p1/.planning/config.json',
  configured: true,
  autonomous_mode: true,
  interactive_enabled: true,
  interactive_fallback: 'panel' as const,
};

async function mountWith(projects: unknown[]) {
  settings.getAll.mockResolvedValue({ settings: {} });
  steering.list.mockResolvedValue({ projects });
  const w = mount(GrdSettings);
  await flushPromises();
  return w;
}

beforeEach(() => {
  steering.set.mockReset();
  steering.list.mockReset();
  settings.getAll.mockReset();
});

describe('GRD steering settings', () => {
  it('renders a row per project', async () => {
    const w = await mountWith([CONFIGURED]);
    expect(w.find('[data-testid="grd-steering-row-proj-1"]').exists()).toBe(true);
    expect(w.text()).toContain('/tmp/p1/.planning/config.json');
  });

  it('toggling autonomous mode PATCHes the real config', async () => {
    const w = await mountWith([CONFIGURED]);
    steering.set.mockResolvedValue({
      project: { ...CONFIGURED, autonomous_mode: false },
    });

    await w.find('[data-testid="grd-steering-autonomous-proj-1"]').trigger('click');
    await flushPromises();

    // It must send the INVERSE of the current value, not the current one.
    expect(steering.set).toHaveBeenCalledWith('proj-1', { autonomous_mode: false });
  });

  it('changing the fallback PATCHes only the fallback', async () => {
    const w = await mountWith([CONFIGURED]);
    steering.set.mockResolvedValue({
      project: { ...CONFIGURED, interactive_fallback: 'recommended' },
    });

    const select = w.find('[data-testid="grd-steering-fallback-proj-1"]');
    (select.element as HTMLSelectElement).value = 'recommended';
    await select.trigger('change');
    await flushPromises();

    // autonomous_mode must NOT be in the patch — sending it would rewrite a
    // setting the operator did not touch.
    expect(steering.set).toHaveBeenCalledWith('proj-1', {
      interactive_fallback: 'recommended',
    });
  });

  it('offers no controls for a project without a GRD config', async () => {
    const w = await mountWith([
      {
        ...CONFIGURED,
        project_id: 'proj-2',
        configured: false,
        config_path: null,
        local_path: null,
      },
    ]);

    expect(w.find('[data-testid="grd-steering-unconfigured"]').exists()).toBe(true);
    // No toggle and no select — the write would fail closed on the backend, so
    // offering it would be a control that cannot work.
    expect(w.find('[data-testid="grd-steering-autonomous-proj-2"]').exists()).toBe(false);
    expect(w.find('[data-testid="grd-steering-fallback-proj-2"]').exists()).toBe(false);
  });

  it('says the fallback is what is in force while autonomous mode is on', async () => {
    const w = await mountWith([CONFIGURED]);
    const note = w.find('[data-testid="grd-steering-note-proj-1"]');
    expect(note.text()).toContain('never pauses');
  });

  it('says checkpoints will ask directly once autonomous mode is off', async () => {
    const w = await mountWith([{ ...CONFIGURED, autonomous_mode: false }]);
    const note = w.find('[data-testid="grd-steering-note-proj-1"]');
    expect(note.text()).toContain('ask you directly');
  });

  it('warns that neither setting does anything while interactive is disabled', async () => {
    const w = await mountWith([{ ...CONFIGURED, interactive_enabled: false }]);
    const note = w.find('[data-testid="grd-steering-note-proj-1"]');
    // This is the case where both controls are live but inert — the UI has to
    // say so rather than imply the toggle took effect.
    expect(note.text()).toContain('no checkpoint is raised');
  });

  it('surfaces a load failure instead of rendering an empty, editable list', async () => {
    settings.getAll.mockResolvedValue({ settings: {} });
    steering.list.mockRejectedValue(new Error('boom'));
    const w = mount(GrdSettings);
    await flushPromises();
    expect(w.find('[data-testid="grd-steering-error"]').exists()).toBe(true);
  });
});
