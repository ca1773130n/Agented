import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import LoginPage from '../LoginPage.vue';

const mockPush = vi.fn();
const mockAuthStatus = vi.fn();
const mockSetApiKey = vi.fn();
const mockClearApiKey = vi.fn();

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({ query: {} }),
}));
vi.mock('../../composables/useAuth', () => ({
  useAuth: () => ({ login: vi.fn() }),
}));
vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}));
vi.mock('../../services/api', () => ({
  healthApi: { authStatus: () => mockAuthStatus() },
}));
vi.mock('../../services/api/client', () => ({
  setApiKey: (...a: unknown[]) => mockSetApiKey(...a),
  clearApiKey: (...a: unknown[]) => mockClearApiKey(...a),
}));

function submitApiKey(w: ReturnType<typeof mount>, key: string) {
  w.find('[data-test="login-api-key"]').setValue(key);
  // the API-key form is the second <form> on the page
  return w.findAll('form')[1].trigger('submit');
}

describe('LoginPage — API-key sign-in', () => {
  beforeEach(() => vi.clearAllMocks());

  it('stores a VALID key and navigates in (no clear)', async () => {
    mockAuthStatus.mockResolvedValue({ authenticated: true });
    const w = mount(LoginPage);
    await submitApiKey(w, 'good-key');
    await flushPromises();

    expect(mockSetApiKey).toHaveBeenCalledWith('good-key');
    expect(mockPush).toHaveBeenCalledWith('/');
    expect(mockClearApiKey).not.toHaveBeenCalled();
  });

  it('clears an INVALID key and shows an error (no navigation)', async () => {
    mockAuthStatus.mockResolvedValue({ authenticated: false });
    const w = mount(LoginPage);
    await submitApiKey(w, 'bad-key');
    await flushPromises();

    expect(mockSetApiKey).toHaveBeenCalledWith('bad-key');
    expect(mockClearApiKey).toHaveBeenCalled();
    expect(mockPush).not.toHaveBeenCalled();
    expect(w.find('[data-test="login-api-key-error"]').exists()).toBe(true);
  });
});
