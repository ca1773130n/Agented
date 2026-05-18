/**
 * CredentialStatusBanner tests — verify the banner only renders when
 * at least one account has missing credentials, respects the backend
 * filter, and shows the remediation command.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import CredentialStatusBanner from '../CredentialStatusBanner.vue';

vi.mock('../../../services/api', () => ({
  monitoringApi: {
    getCredentials: vi.fn(),
  },
}));

vi.mock('../../../composables/useToast', () => ({
  useToast: () => vi.fn(),
}));

import { monitoringApi } from '../../../services/api';

const ok = {
  account_id: 1,
  account_name: 'Personal1',
  backend_type: 'claude',
  config_path: '~/.claude-personal1',
  credential_status: 'ok' as const,
  remediation: null,
  expected_location: null,
};
const missingClaude = {
  account_id: 2,
  account_name: 'Personal2',
  backend_type: 'claude',
  config_path: '~/.claude-personal2',
  credential_status: 'missing' as const,
  remediation: 'CLAUDE_CONFIG_DIR=~/.claude-personal2 claude  # then /login',
  expected_location: 'Claude Code-credentials-d552d744',
};
const missingGemini = {
  account_id: 5,
  account_name: 'Personal1',
  backend_type: 'gemini',
  config_path: '~/.gemini-personal1',
  credential_status: 'missing' as const,
  remediation: 'GEMINI_DIR=~/.gemini-personal1 gemini auth',
  expected_location: '/home/me/.gemini-personal1/oauth_creds.json',
};

describe('CredentialStatusBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when all accounts are ok', async () => {
    (monitoringApi.getCredentials as ReturnType<typeof vi.fn>).mockResolvedValue({
      accounts: [ok],
    });
    const w = mount(CredentialStatusBanner);
    await flushPromises();
    expect(w.find('[data-testid="credential-status-banner"]').exists()).toBe(false);
  });

  it('lists missing accounts with remediation command', async () => {
    (monitoringApi.getCredentials as ReturnType<typeof vi.fn>).mockResolvedValue({
      accounts: [ok, missingClaude, missingGemini],
    });
    const w = mount(CredentialStatusBanner);
    await flushPromises();
    const banner = w.find('[data-testid="credential-status-banner"]');
    expect(banner.exists()).toBe(true);
    const html = banner.html();
    // Both missing accounts visible.
    expect(html).toContain('Personal2');
    expect(html).toContain('Personal1');
    // Remediation commands visible (raw text, not just title attr).
    expect(html).toContain('CLAUDE_CONFIG_DIR=~/.claude-personal2 claude');
    expect(html).toContain('GEMINI_DIR=~/.gemini-personal1 gemini auth');
    // Expected locations visible.
    expect(html).toContain('Claude Code-credentials-d552d744');
  });

  it('respects backendFilter prop', async () => {
    (monitoringApi.getCredentials as ReturnType<typeof vi.fn>).mockResolvedValue({
      accounts: [missingClaude, missingGemini],
    });
    const w = mount(CredentialStatusBanner, {
      props: { backendFilter: 'claude' },
    });
    await flushPromises();
    const html = w.find('[data-testid="credential-status-banner"]').html();
    expect(html).toContain('Personal2'); // claude — included
    expect(html).not.toContain('GEMINI_DIR'); // gemini — filtered out
  });

  it('silently degrades on API error (does not throw)', async () => {
    (monitoringApi.getCredentials as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('network down'),
    );
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const w = mount(CredentialStatusBanner);
    await flushPromises();
    expect(w.find('[data-testid="credential-status-banner"]').exists()).toBe(false);
    expect(warnSpy).toHaveBeenCalled();
    warnSpy.mockRestore();
  });

  it('Copy button falls back to execCommand when clipboard API is unavailable', async () => {
    (monitoringApi.getCredentials as ReturnType<typeof vi.fn>).mockResolvedValue({
      accounts: [missingClaude],
    });
    // Simulate an http:// origin: secure context off + clipboard
    // undefined. The component must reach for the textarea +
    // execCommand fallback rather than throwing.
    Object.defineProperty(window, 'isSecureContext', {
      value: false,
      configurable: true,
    });
    const origClipboard = navigator.clipboard;
    Object.defineProperty(navigator, 'clipboard', {
      value: undefined,
      configurable: true,
    });
    // happy-dom doesn't define execCommand by default — install
    // a stub before spying.
    if (typeof document.execCommand !== 'function') {
      (document as Document & { execCommand: (cmd: string) => boolean }).execCommand =
        () => false;
    }
    const execSpy = vi
      .spyOn(document, 'execCommand')
      .mockReturnValue(true);
    const w = mount(CredentialStatusBanner);
    await flushPromises();
    await w.find('.cred-copy').trigger('click');
    expect(execSpy).toHaveBeenCalledWith('copy');
    // Restore.
    Object.defineProperty(navigator, 'clipboard', {
      value: origClipboard,
      configurable: true,
    });
    execSpy.mockRestore();
  });
});
