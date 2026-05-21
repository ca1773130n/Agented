/**
 * PR-D — MySkills "+ Create Skill" CTA regression guard.
 *
 * The audit identified MySkills as the only wizard parent list page
 * without a wizard CTA. This test mounts the page, asserts the CTA
 * renders, and asserts clicking it routes to the `skill-create` named
 * route.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createRouter, createMemoryHistory } from 'vue-router';
import { defineComponent, h } from 'vue';

vi.mock('../../services/api', () => ({
  ApiError: class ApiError extends Error { status = 0; },
  skillsApi: { list: vi.fn().mockResolvedValue({ skills: [] }) },
  userSkillsApi: {
    list: vi.fn().mockResolvedValue({ skills: [] }),
    add: vi.fn().mockResolvedValue({}),
    update: vi.fn().mockResolvedValue({}),
  },
}));

vi.mock('../../composables/useToast', () => ({ useToast: () => vi.fn() }));
vi.mock('../../composables/useWebMcpPageTools', () => ({ useWebMcpPageTools: vi.fn() }));
vi.mock('../../composables/useFocusTrap', () => ({ useFocusTrap: vi.fn() }));

import MySkills from '../MySkills.vue';

function buildRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/skills', name: 'my-skills', component: MySkills },
      { path: '/skills/create', name: 'skill-create', component: defineComponent({ render: () => h('div', 'skill-create') }) },
      { path: '/skills/:skillId', name: 'skill-detail', component: defineComponent({ render: () => h('div', 'skill-detail') }) },
    ],
  });
}

describe('PR-D MySkills — "+ Create Skill" CTA', () => {
  let router: ReturnType<typeof buildRouter>;

  beforeEach(async () => {
    router = buildRouter();
    await router.push('/skills');
    await router.isReady();
  });

  it('renders the Create Skill CTA in the header actions', async () => {
    const w = mount(MySkills, { global: { plugins: [router] } });
    await flushPromises();
    expect(w.find('[data-testid="create-skill-cta"]').exists()).toBe(true);
  });

  it('clicking the CTA navigates to the skill-create route', async () => {
    const push = vi.spyOn(router, 'push');
    const w = mount(MySkills, { global: { plugins: [router] } });
    await flushPromises();
    await w.find('[data-testid="create-skill-cta"]').trigger('click');
    expect(push).toHaveBeenCalledWith({ name: 'skill-create' });
  });
});
