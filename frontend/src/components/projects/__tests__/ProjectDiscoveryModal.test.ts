import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import ProjectDiscoveryModal from '../ProjectDiscoveryModal.vue';
import { projectApi } from '../../../services/api';

vi.mock('../../../services/api', () => ({
  projectApi: { discover: vi.fn(), importRepos: vi.fn() },
  settingsApi: { get: vi.fn().mockResolvedValue({ key: 'workspace_root', value: '' }) },
  utilityApi: { browseDirectory: vi.fn() },
  ApiError: class extends Error {
    status: number;
    constructor(status: number, message: string) { super(message); this.status = status; }
  },
}));

import { settingsApi } from '../../../services/api';

describe('ProjectDiscoveryModal', () => {
  const teams = [{ id: 'team-1', name: 'Backend', color: '#fff', member_count: 0 }] as any;
  const products = [{ id: 'prod-1', name: 'Core', status: 'active', project_count: 0 }] as any;

  function mountComponent() {
    return mount(ProjectDiscoveryModal, {
      props: { teams, products },
      global: {
        provide: { showToast: vi.fn() },
        stubs: { teleport: true, DirectoryBrowser: true },
      },
    });
  }

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(settingsApi.get).mockResolvedValue({ key: 'workspace_root', value: '' } as never);
    vi.mocked(projectApi.discover).mockResolvedValue({
      repos: [
        { name: 'alpha', local_path: '/p/alpha', remote_url: 'git@github.com:o/alpha.git', already_imported: false, existing_project_id: null },
        { name: 'beta', local_path: '/p/beta', remote_url: null, already_imported: true, existing_project_id: 'proj-x' },
      ],
      scanned: 2, found: 2, new_count: 1, unreadable: 0,
    });
    vi.mocked(projectApi.importRepos).mockResolvedValue({
      imported: [{ project_id: 'proj-new', name: 'alpha' }], skipped: [], setup_started: false,
    });
  });

  it('scans and lists repos with new/imported state', async () => {
    const wrapper = mountComponent();
    await wrapper.find('input[data-testid="discover-root"]').setValue('/p');
    await wrapper.find('[data-testid="discover-scan"]').trigger('click');
    await flushPromises();
    expect(projectApi.discover).toHaveBeenCalledWith({ root: '/p', nested: false, max_depth: 3 });
    expect(wrapper.text()).toContain('alpha');
    expect(wrapper.text()).toContain('beta');
    // Only the 1 new repo is pre-selected (scope to the repo list, ignoring
    // the directOnly / runSetup control checkboxes).
    const checked = wrapper.findAll('.repo-list input[type="checkbox"]:checked');
    expect(checked.length).toBe(1);
  });

  it('prefills the scan folder from the workspace_root setting on open', async () => {
    vi.mocked(settingsApi.get).mockResolvedValue({
      key: 'workspace_root',
      value: '/Users/neo/Developer/Projects',
    } as never);
    const wrapper = mountComponent();
    await flushPromises();
    expect(settingsApi.get).toHaveBeenCalledWith('workspace_root');
    const input = wrapper.find('input[data-testid="discover-root"]').element as HTMLInputElement;
    expect(input.value).toBe('/Users/neo/Developer/Projects');
  });

  it('opens the directory browser when Browse is clicked', async () => {
    const wrapper = mountComponent();
    await flushPromises();
    expect(wrapper.findComponent({ name: 'DirectoryBrowser' }).props('visible')).toBe(false);
    await wrapper.find('[data-testid="discover-browse"]').trigger('click');
    await wrapper.vm.$nextTick();
    expect(wrapper.findComponent({ name: 'DirectoryBrowser' }).props('visible')).toBe(true);
  });

  it('imports the selected new repos with team + setup flag', async () => {
    const wrapper = mountComponent();
    await wrapper.find('input[data-testid="discover-root"]').setValue('/p');
    await wrapper.find('[data-testid="discover-scan"]').trigger('click');
    await flushPromises();

    await wrapper.find('[data-testid="discover-team"]').setValue('team-1');
    await wrapper.find('[data-testid="discover-import"]').trigger('click');
    await flushPromises();

    expect(projectApi.importRepos).toHaveBeenCalledWith({
      repos: [{ name: 'alpha', local_path: '/p/alpha', github_repo: 'git@github.com:o/alpha.git' }],
      product_id: undefined,
      owner_team_id: 'team-1',
      run_harness_setup: true,
    });
    expect(wrapper.emitted('imported')).toBeTruthy();
  });
});
