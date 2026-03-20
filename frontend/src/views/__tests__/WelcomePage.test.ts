import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import WelcomePage from '../WelcomePage.vue';

const mockPush = vi.fn();

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock('../../composables/useToast', () => ({
  useToast: () => vi.fn(),
}));

vi.mock('../../services/api', () => ({
  healthApi: {
    setup: vi.fn().mockResolvedValue({ api_key: 'test-key-abc123', role: 'admin' }),
  },
}));

vi.mock('../../services/api/client', () => ({
  setApiKey: vi.fn(),
}));

// Import mocked modules after vi.mock declarations
import { healthApi } from '../../services/api';
import { setApiKey } from '../../services/api/client';

describe('WelcomePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset default resolved value
    vi.mocked(healthApi.setup).mockResolvedValue({
      api_key: 'test-key-abc123',
      role: 'admin',
      role_id: 'role-abc',
      label: 'Admin',
      message: 'ok',
    });
  });

  it('renders welcome view by default', () => {
    const wrapper = mount(WelcomePage);
    expect(wrapper.text()).toContain('Your virtual startup');
    expect(wrapper.text()).toContain('Begin setup');
  });

  it('transitions to key generation on Begin Setup click', async () => {
    const wrapper = mount(WelcomePage);
    await wrapper.find('.cta-btn').trigger('click');
    expect(wrapper.text()).toContain('Generate Admin Key');
  });

  it('generates and displays API key', async () => {
    const wrapper = mount(WelcomePage);
    await wrapper.find('.cta-btn').trigger('click');
    await wrapper.find('[data-test="generate-key-btn"]').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('test-key-abc123');
  });

  it('shows continue button after key generation', async () => {
    const wrapper = mount(WelcomePage);
    await wrapper.find('.cta-btn').trigger('click');
    await wrapper.find('[data-test="generate-key-btn"]').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-test="continue-btn"]').exists()).toBe(true);
  });

  it('stores API key and navigates on Continue click', async () => {
    const wrapper = mount(WelcomePage);
    await wrapper.find('.cta-btn').trigger('click');
    await wrapper.find('[data-test="generate-key-btn"]').trigger('click');
    await flushPromises();
    await wrapper.find('[data-test="continue-btn"]').trigger('click');
    expect(setApiKey).toHaveBeenCalledWith('test-key-abc123');
    expect(mockPush).toHaveBeenCalledWith('/?tour=start');
  });

  it('shows error state when key generation fails', async () => {
    vi.mocked(healthApi.setup).mockRejectedValueOnce(new Error('Setup failed'));
    const wrapper = mount(WelcomePage);
    await wrapper.find('.cta-btn').trigger('click');
    await wrapper.find('[data-test="generate-key-btn"]').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('Failed to generate');
  });
});
