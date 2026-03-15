/**
 * Skill sets API — manages saved skill compositions for the Visual Skill Composer.
 */
import { apiFetch } from './client';

export interface SkillSet {
  id: string;
  name: string;
  skill_ids: string; // JSON array string e.g. '["sk-safety","sk-review"]'
  created_at: string;
  updated_at: string;
}

export const skillSetsApi = {
  list: () => apiFetch<{ skill_sets: SkillSet[] }>('/api/skill-sets/'),

  create: (data: { name: string; skill_ids: string[] }) =>
    apiFetch<{ message: string; skill_set: SkillSet }>('/api/skill-sets/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (setId: string, data: { name?: string; skill_ids?: string[] }) =>
    apiFetch<{ message: string; skill_set: SkillSet }>(`/api/skill-sets/${setId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (setId: string) =>
    apiFetch<{ message: string }>(`/api/skill-sets/${setId}`, {
      method: 'DELETE',
    }),
};
