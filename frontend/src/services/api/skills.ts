/**
 * Skills, user skills, skills.sh, harness, and skill conversation API modules.
 */
import { API_BASE, apiFetch, createAuthenticatedEventSource } from './client';
import type { AuthenticatedEventSource } from './client';
import type {
  SkillInfo,
  UserSkill,
  HarnessConfig,
  FileNode,
  SkillsShResult,
  LoadFromMarketplaceResponse,
  DeployToMarketplaceResponse,
  SkillConversation,
} from './types';

// Skills API
export const skillsApi = {
  // Discover skills from .claude/skills directories
  list: (triggerId?: string) => {
    const params = new URLSearchParams();
    if (triggerId) params.set('trigger_id', triggerId);
    const query = params.toString();
    return apiFetch<{ skills: SkillInfo[] }>(`/api/skills/${query ? `?${query}` : ''}`);
  },

  get: (skillName: string) =>
    apiFetch<SkillInfo>(`/api/skills/discover/${encodeURIComponent(skillName)}`),

  // Test a skill in the playground
  test: (skillName: string, input?: string) =>
    apiFetch<{ test_id: string; message: string; status: string }>('/api/skills/test', {
      method: 'POST',
      body: JSON.stringify({ skill_name: skillName, input: input || '' }),
    }),

  streamTest: (testId: string): AuthenticatedEventSource => {
    return createAuthenticatedEventSource(`${API_BASE}/api/skills/test/${testId}/stream`);
  },

  stopTest: (testId: string) =>
    apiFetch<{ message: string }>(`/api/skills/test/${testId}/stop`, { method: 'POST' }),

  // Get playground file browser structure
  getPlaygroundFiles: () =>
    apiFetch<{ working_dir: string; files: FileNode[] }>('/api/skills/playground/files'),
};

// User Skills API (My Skills)
export const userSkillsApi = {
  list: () => apiFetch<{ skills: UserSkill[] }>('/api/skills/user'),

  get: (skillId: number) =>
    apiFetch<{ skill: UserSkill }>(`/api/skills/user/${skillId}`),

  add: (data: {
    skill_name: string;
    skill_path: string;
    description?: string;
    enabled?: number;
    selected_for_harness?: number;
  }) => apiFetch<{ message: string; id: number; skill_name: string }>('/api/skills/user', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  update: (skillId: number, data: Partial<{
    skill_name: string;
    skill_path: string;
    description: string;
    enabled: number;
    selected_for_harness: number;
  }>) => apiFetch<{ message: string }>(`/api/skills/user/${skillId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),

  delete: (skillId: number) => apiFetch<{ message: string }>(`/api/skills/user/${skillId}`, {
    method: 'DELETE',
  }),
};

// Skills.sh API
export const skillsShApi = {
  search: (query: string = '') =>
    apiFetch<{ results: SkillsShResult[]; source: string; npx_available?: boolean }>(
      `/api/skills/skills-sh/search${query ? `?q=${encodeURIComponent(query)}` : ''}`
    ),

  install: (source: string) =>
    apiFetch<{ message: string; output?: string }>(
      '/api/skills/skills-sh/install',
      { method: 'POST', body: JSON.stringify({ source }) }
    ),
};

// Harness API
export const harnessApi = {
  getSkills: () => apiFetch<{ skills: UserSkill[] }>('/api/skills/harness'),

  toggleSkill: (skillId: number, selected: boolean) =>
    apiFetch<{ message: string }>(`/api/skills/harness/${skillId}`, {
      method: 'PUT',
      body: JSON.stringify({ selected }),
    }),

  getConfig: () => apiFetch<HarnessConfig>('/api/skills/harness/config'),

  loadFromMarketplace: () =>
    apiFetch<LoadFromMarketplaceResponse>('/api/skills/harness/load-from-marketplace', {
      method: 'POST',
    }),

  deployToMarketplace: () =>
    apiFetch<DeployToMarketplaceResponse>('/api/skills/harness/deploy-to-marketplace', {
      method: 'POST',
    }),
};

// Skill Conversation API
export const skillConversationApi = {
  start: () => apiFetch<{ conversation_id: string; message: string }>('/api/skills/conversations/start', {
    method: 'POST',
  }),

  get: (convId: string) => apiFetch<SkillConversation>(`/api/skills/conversations/${convId}`),

  sendMessage: (convId: string, message: string, options?: { backend?: string; account_id?: string; model?: string }) =>
    apiFetch<{ message_id: string; status: string }>(`/api/skills/conversations/${convId}/message`, {
      method: 'POST',
      body: JSON.stringify({ message, ...options }),
    }),

  stream: (convId: string): AuthenticatedEventSource => {
    return createAuthenticatedEventSource(`${API_BASE}/api/skills/conversations/${convId}/stream`);
  },

  finalize: (convId: string) =>
    apiFetch<{ message: string; skill_id: number; skill: UserSkill }>(`/api/skills/conversations/${convId}/finalize`, {
      method: 'POST',
    }),

  abandon: (convId: string) =>
    apiFetch<{ message: string }>(`/api/skills/conversations/${convId}/abandon`, {
      method: 'POST',
    }),
};
