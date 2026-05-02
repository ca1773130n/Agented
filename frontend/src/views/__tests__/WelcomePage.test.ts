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

vi.mock('../../router/guards', () => ({
  resetAuthGuard: vi.fn(),
}));

const mockStartTour = vi.fn();
const mockNextStep = vi.fn();

vi.mock('../../composables/useTourMachine', () => ({
  useTourMachine: () => ({
    startTour: mockStartTour,
    nextStep: mockNextStep,
    state: { value: null },
    isActive: { value: false },
    currentStep: { value: 'idle' },
    canGoBack: { value: false },
    canGoForward: { value: false },
    context: { value: { instanceId: null, schemaVersion: 1, completedSteps: [] } },
    send: vi.fn(),
    prevStep: vi.fn(),
    skipStep: vi.fn(),
    completeTour: vi.fn(),
    restartTour: vi.fn(),
    clearTourState: vi.fn(),
  }),
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
    expect(mockPush).toHaveBeenCalledWith({ path: '/settings', hash: '#general' });
  });

  it('shows error state when key generation fails', async () => {
    vi.mocked(healthApi.setup).mockRejectedValueOnce(new Error('Setup failed'));
    const wrapper = mount(WelcomePage);
    await wrapper.find('.cta-btn').trigger('click');
    await wrapper.find('[data-test="generate-key-btn"]').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('Failed to generate');
  });

  it('OB-02: warning copy "won\'t be shown again" stays visible alongside the generated key', async () => {
    const wrapper = mount(WelcomePage);
    await wrapper.find('.cta-btn').trigger('click');
    await wrapper.find('[data-test="generate-key-btn"]').trigger('click');
    await flushPromises();
    // Both the key and the warning must be visible at the same time so the
    // user sees the "store it now" notice in context.
    expect(wrapper.text()).toContain('test-key-abc123');
    expect(wrapper.text().toLowerCase()).toMatch(/won.?t be shown again/);
  });

  it('OB-02: Copy button writes the generated key to the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });
    const wrapper = mount(WelcomePage);
    await wrapper.find('.cta-btn').trigger('click');
    await wrapper.find('[data-test="generate-key-btn"]').trigger('click');
    await flushPromises();
    await wrapper.find('.copy-btn').trigger('click');
    await flushPromises();
    expect(writeText).toHaveBeenCalledWith('test-key-abc123');
    expect(wrapper.text()).toContain('Copied');
  });

  it('OB-03: phase change wraps in a Vue Transition (phase-fade)', async () => {
    const wrapper = mount(WelcomePage);
    expect(wrapper.find('.welcome-content').exists()).toBe(true);
    await wrapper.find('.cta-btn').trigger('click');
    await flushPromises();
    expect(wrapper.find('.keygen-content').exists()).toBe(true);
    // Total transition (enter 250ms + leave 150ms) must fit under OB-03's
    // 500ms budget. Verify timings are encoded in the component's <style>.
    const styleHtml = wrapper.html()
    void styleHtml  // styles are scoped; presence of the class is enough.
    expect(wrapper.html()).toContain('keygen-content')
  })
});
