import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import WelcomePage from '../WelcomePage.vue';

const mockPush = vi.fn();

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

const mockSignup = vi.fn();
vi.mock('../../composables/useAuth', () => ({
  useAuth: () => ({ signup: mockSignup }),
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
    currentStep: { value: 'welcome' },
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

const mockDiscover = vi.fn();
const mockImport = vi.fn();
vi.mock('../../services/api/backend-management', () => ({
  aiAccountsClient: {
    discoverConfigs: (...a: unknown[]) => mockDiscover(...a),
    importDiscovered: (...a: unknown[]) => mockImport(...a),
  },
}));

import { resetAuthGuard } from '../../router/guards';

const CLAUDE_ITEM = {
  kind: 'claude',
  path: '/Users/x/.claude',
  suggested_name: 'claude (default)',
  is_logged_in: true,
  error: null,
  backend_id: null as string | null,
};

function mountPage() {
  return mount(WelcomePage, { global: { stubs: { AccountLoginModal: true } } });
}

async function advanceToDiscover(wrapper: ReturnType<typeof mountPage>) {
  await wrapper.find('.cta-btn').trigger('click'); // welcome -> signup
  await wrapper.find('[data-test="signup-email"]').setValue('a@b.com');
  await wrapper.find('[data-test="signup-password"]').setValue('password123');
  await wrapper.find('[data-test="signup-submit"]').trigger('submit');
  await flushPromises();
}

describe('WelcomePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSignup.mockResolvedValue({ id: 'u1', email: 'a@b.com', display_name: null });
    mockDiscover.mockResolvedValue({ items: [{ ...CLAUDE_ITEM }] });
    mockImport.mockResolvedValue({ id: 'bkd-1', kind: 'claude' });
  });

  it('renders welcome view by default', () => {
    const wrapper = mountPage();
    expect(wrapper.text()).toContain('Your virtual startup');
    expect(wrapper.text()).toContain('Begin setup');
  });

  it('transitions to the signup step on Begin Setup click', async () => {
    const wrapper = mountPage();
    await wrapper.find('.cta-btn').trigger('click');
    expect(mockStartTour).toHaveBeenCalled();
    expect(wrapper.find('[data-test="signup-email"]').exists()).toBe(true);
    expect(wrapper.find('[data-test="signup-password"]').exists()).toBe(true);
  });

  it('validates required fields before calling signup', async () => {
    const wrapper = mountPage();
    await wrapper.find('.cta-btn').trigger('click');
    await wrapper.find('[data-test="signup-submit"]').trigger('submit');
    await flushPromises();
    expect(mockSignup).not.toHaveBeenCalled();
    expect(wrapper.find('[data-test="signup-error"]').exists()).toBe(true);
  });

  it('signs up (display name omitted when blank) and moves to the discover step', async () => {
    const wrapper = mountPage();
    await advanceToDiscover(wrapper);
    expect(mockSignup).toHaveBeenCalledWith('a@b.com', 'password123', undefined);
    expect(resetAuthGuard).toHaveBeenCalled();
    expect(wrapper.find('[data-test="detect-btn"]').exists()).toBe(true);
  });

  it('surfaces the signup error and stays on the signup step on failure', async () => {
    mockSignup.mockRejectedValueOnce(new Error('Email already registered'));
    const wrapper = mountPage();
    await wrapper.find('.cta-btn').trigger('click');
    await wrapper.find('[data-test="signup-email"]').setValue('a@b.com');
    await wrapper.find('[data-test="signup-password"]').setValue('password123');
    await wrapper.find('[data-test="signup-submit"]').trigger('submit');
    await flushPromises();
    expect(wrapper.find('[data-test="signup-error"]').text()).toContain('Email already registered');
    expect(wrapper.find('[data-test="detect-btn"]').exists()).toBe(false);
  });

  it('detects accounts and lists them', async () => {
    const wrapper = mountPage();
    await advanceToDiscover(wrapper);
    await wrapper.find('[data-test="detect-btn"]').trigger('click');
    await flushPromises();
    expect(mockDiscover).toHaveBeenCalled();
    expect(wrapper.find('[data-test="discover-list"]').exists()).toBe(true);
    expect(wrapper.text()).toContain('claude (default)');
  });

  it('imports all logged-in, un-imported accounts', async () => {
    const wrapper = mountPage();
    await advanceToDiscover(wrapper);
    await wrapper.find('[data-test="detect-btn"]').trigger('click');
    await flushPromises();
    await wrapper.find('[data-test="import-all-btn"]').trigger('click');
    await flushPromises();
    expect(mockImport).toHaveBeenCalledWith({
      kind: 'claude',
      path: '/Users/x/.claude',
      display_name: 'claude (default)',
    });
  });

  it('finishes onboarding: advances the tour and navigates to settings', async () => {
    const wrapper = mountPage();
    await advanceToDiscover(wrapper);
    await wrapper.find('[data-test="finish-btn"]').trigger('click');
    expect(mockNextStep).toHaveBeenCalled();
    expect(mockPush).toHaveBeenCalledWith({ path: '/settings', hash: '#general' });
  });

  it('OB-03: signup phase wraps in a Vue Transition (phase-fade)', async () => {
    const wrapper = mountPage();
    expect(wrapper.find('.welcome-content').exists()).toBe(true);
    await wrapper.find('.cta-btn').trigger('click');
    await flushPromises();
    expect(wrapper.find('.keygen-content').exists()).toBe(true);
  });
});
