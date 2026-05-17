/**
 * Tests for useWizardAutoResume (v0.7.83).
 *
 * Focused on the parts codex flagged as subtle: per-user
 * localStorage namespacing, legacy → user migration on late
 * auth, and anon → user migration when ``currentUser``
 * resolves after mount.
 */
import { defineComponent, h, ref } from 'vue';
import { mount } from '@vue/test-utils';
import { describe, it, expect, beforeEach, vi } from 'vitest';

// Mock useAuth so the test controls when ``currentUser`` resolves.
const currentUser = ref<{ id: string } | null>(null);
vi.mock('../useAuth', () => ({
  useAuth: () => ({ currentUser }),
}));

import { useWizardAutoResume } from '../useWizardAutoResume';

interface FakeConv {
  conversationId: { value: string | null };
  startConversation: ReturnType<typeof vi.fn>;
  resumeConversation: ReturnType<typeof vi.fn>;
}

interface FakeApi {
  listActive: ReturnType<typeof vi.fn>;
}

function makeConv(): FakeConv {
  return {
    conversationId: ref<string | null>(null),
    startConversation: vi.fn(async () => {}),
    resumeConversation: vi.fn(async (id: string) => {}),
  } as unknown as FakeConv;
}

function makeApi(activeIds: string[] = []): FakeApi {
  return {
    listActive: vi.fn(async () => ({
      active_conversations: activeIds.map(id => ({
        id,
        status: 'active',
        updated_at: '',
        message_count: 0,
      })),
    })),
  };
}

function mountHarness(conv: FakeConv, api: FakeApi, keyPrefix: string) {
  const Harness = defineComponent({
    setup() {
      useWizardAutoResume(conv, api, keyPrefix);
      return () => h('div');
    },
  });
  return mount(Harness);
}

describe('useWizardAutoResume', () => {
  beforeEach(() => {
    localStorage.clear();
    currentUser.value = null;
    vi.clearAllMocks();
  });

  it('falls back to startConversation when nothing is cached', async () => {
    currentUser.value = { id: 'u1' };
    const conv = makeConv();
    const api = makeApi();
    mountHarness(conv, api, 'agented_x_conv_id');
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(api.listActive).toHaveBeenCalled();
    expect(conv.startConversation).toHaveBeenCalled();
  });

  it('resumes from a per-user localStorage entry when present', async () => {
    currentUser.value = { id: 'u1' };
    localStorage.setItem('agented_x_conv_id:u1', 'conv_uno');
    const conv = makeConv();
    (conv.resumeConversation as any).mockImplementation(async (id: string) => {
      (conv.conversationId as any).value = id;
    });
    const api = makeApi();
    mountHarness(conv, api, 'agented_x_conv_id');
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(conv.resumeConversation).toHaveBeenCalledWith('conv_uno');
    expect(conv.startConversation).not.toHaveBeenCalled();
    expect(api.listActive).not.toHaveBeenCalled();
  });

  it('resumes from listActive when localStorage is empty', async () => {
    currentUser.value = { id: 'u1' };
    const conv = makeConv();
    (conv.resumeConversation as any).mockImplementation(async (id: string) => {
      (conv.conversationId as any).value = id;
    });
    const api = makeApi(['conv_from_server']);
    mountHarness(conv, api, 'agented_x_conv_id');
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(conv.resumeConversation).toHaveBeenCalledWith('conv_from_server');
    expect(conv.startConversation).not.toHaveBeenCalled();
    // Should have written the resumed id back to localStorage.
    expect(localStorage.getItem('agented_x_conv_id:u1')).toBe('conv_from_server');
  });

  it('migrates legacy unnamespaced key when user is known at mount', async () => {
    currentUser.value = { id: 'u1' };
    localStorage.setItem('agented_x_conv_id', 'legacy_conv');
    const conv = makeConv();
    (conv.resumeConversation as any).mockImplementation(async (id: string) => {
      (conv.conversationId as any).value = id;
    });
    const api = makeApi();
    mountHarness(conv, api, 'agented_x_conv_id');
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(conv.resumeConversation).toHaveBeenCalledWith('legacy_conv');
    expect(localStorage.getItem('agented_x_conv_id:u1')).toBe('legacy_conv');
    expect(localStorage.getItem('agented_x_conv_id')).toBeNull();
  });

  it('does not migrate legacy key while user is unresolved (would strand under :anon)', async () => {
    currentUser.value = null;
    localStorage.setItem('agented_x_conv_id', 'legacy_conv');
    const conv = makeConv();
    const api = makeApi();
    mountHarness(conv, api, 'agented_x_conv_id');
    await new Promise(resolve => setTimeout(resolve, 0));
    // Legacy key still on disk so the late-auth watcher can drain it later.
    expect(localStorage.getItem('agented_x_conv_id')).toBe('legacy_conv');
  });

  it('migrates :anon entry under :uid when auth resolves after mount', async () => {
    currentUser.value = null;
    localStorage.setItem('agented_x_conv_id:anon', 'anon_conv');
    const conv = makeConv();
    // Resume succeeds so the onMounted flow preserves the
    // ``:anon`` entry instead of clearing it (the cleared-on-fail
    // path is intentional — see useWizardAutoResume.ts).
    (conv.resumeConversation as any).mockImplementation(async (id: string) => {
      (conv.conversationId as any).value = id;
    });
    const api = makeApi();
    mountHarness(conv, api, 'agented_x_conv_id');
    await new Promise(resolve => setTimeout(resolve, 0));
    // Now auth resolves.
    currentUser.value = { id: 'u1' };
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(localStorage.getItem('agented_x_conv_id:u1')).toBe('anon_conv');
    expect(localStorage.getItem('agented_x_conv_id:anon')).toBeNull();
  });

  it('does not overwrite an existing :uid entry when migrating from :anon', async () => {
    currentUser.value = null;
    localStorage.setItem('agented_x_conv_id:anon', 'anon_conv');
    localStorage.setItem('agented_x_conv_id:u1', 'real_user_conv');
    const conv = makeConv();
    (conv.resumeConversation as any).mockImplementation(async (id: string) => {
      (conv.conversationId as any).value = id;
    });
    const api = makeApi();
    mountHarness(conv, api, 'agented_x_conv_id');
    await new Promise(resolve => setTimeout(resolve, 0));
    currentUser.value = { id: 'u1' };
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(localStorage.getItem('agented_x_conv_id:u1')).toBe('real_user_conv');
    expect(localStorage.getItem('agented_x_conv_id:anon')).toBeNull();
  });
});
