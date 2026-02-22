import type { RouteRecordRaw } from 'vue-router';

export const skillRoutes: RouteRecordRaw[] = [
  {
    path: '/skills',
    name: 'my-skills',
    component: () => import('../../views/MySkills.vue'),
    meta: { title: 'My Skills' },
  },
  {
    path: '/skills/new',
    name: 'skill-create',
    component: () => import('../../views/SkillCreateWizard.vue'),
    meta: { title: 'Create Skill' },
  },
  {
    path: '/skills/playground',
    name: 'skills-playground',
    component: () => import('../../views/SkillsPlayground.vue'),
    meta: { title: 'Skills Playground' },
  },
  {
    path: '/skills/explore',
    name: 'explore-skills',
    component: () => import('../../views/ExploreSkills.vue'),
    meta: { title: 'Explore Skills' },
  },
  {
    path: '/skills/:skillId',
    name: 'skill-detail',
    component: () => import('../../views/SkillDetailPage.vue'),
    props: true,
    meta: { title: 'Skill Detail', requiresEntity: 'skillId' },
  },
];
