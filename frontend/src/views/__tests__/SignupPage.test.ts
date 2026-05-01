import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import SignupPage from '../SignupPage.vue';

const signupMock = vi.fn();
const pushMock = vi.fn();
const routeRef = { query: {} as Record<string, string> };

vi.mock('vue-router', () => ({
  useRoute: () => routeRef,
  useRouter: () => ({ push: pushMock }),
  RouterLink: { template: '<a><slot /></a>' },
}));

vi.mock('../../composables/useAuth', () => ({
  useAuth: () => ({ signup: signupMock }),
}));

describe('SignupPage', () => {
  beforeEach(() => {
    signupMock.mockReset();
    pushMock.mockReset();
    routeRef.query = {};
  });

  function setupAndSubmit(email = 'a@b.com', password = 'longenough', display = '') {
    const wrapper = mount(SignupPage);
    wrapper.find('[data-test="signup-email"]').setValue(email);
    wrapper.find('[data-test="signup-password"]').setValue(password);
    if (display) {
      wrapper.find('[data-test="signup-display-name"]').setValue(display);
    }
    return wrapper;
  }

  it('disables submit until email + password length valid', async () => {
    const wrapper = mount(SignupPage);
    const btn = () => wrapper.find('[data-test="signup-submit"]').element as HTMLButtonElement;

    expect(btn().disabled).toBe(true);
    await wrapper.find('[data-test="signup-email"]').setValue('a@b.com');
    expect(btn().disabled).toBe(true); // no password yet
    await wrapper.find('[data-test="signup-password"]').setValue('short');
    expect(btn().disabled).toBe(true); // < 8 chars
    await wrapper.find('[data-test="signup-password"]').setValue('longenough');
    expect(btn().disabled).toBe(false);
  });

  it('calls signup and pushes to next on success', async () => {
    routeRef.query = { next: '/products' };
    signupMock.mockResolvedValue({ id: 'user-1', email: 'a@b.com', display_name: null });
    const wrapper = setupAndSubmit();
    await wrapper.find('form').trigger('submit.prevent');
    await flushPromises();

    expect(signupMock).toHaveBeenCalledWith('a@b.com', 'longenough', '');
    expect(pushMock).toHaveBeenCalledWith('/products');
  });

  it('shows the error message on signup failure', async () => {
    signupMock.mockRejectedValue(new Error('Email already registered'));
    const wrapper = setupAndSubmit();
    await wrapper.find('form').trigger('submit.prevent');
    await flushPromises();

    expect(wrapper.find('[data-test="signup-error"]').text()).toBe('Email already registered');
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('passes display_name through when provided', async () => {
    signupMock.mockResolvedValue({ id: 'u', email: 'x@y.com', display_name: 'X' });
    const wrapper = setupAndSubmit('x@y.com', 'aaaaaaaa', 'Display');
    await wrapper.find('form').trigger('submit.prevent');
    await flushPromises();
    expect(signupMock).toHaveBeenCalledWith('x@y.com', 'aaaaaaaa', 'Display');
  });

  it('defaults next to / when query param missing', async () => {
    signupMock.mockResolvedValue({ id: 'u', email: 'x@y.com', display_name: null });
    const wrapper = setupAndSubmit();
    await wrapper.find('form').trigger('submit.prevent');
    await flushPromises();
    expect(pushMock).toHaveBeenCalledWith('/');
  });
});
