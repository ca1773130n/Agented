/**
 * Team Leader chat resolution API.
 *
 * Server resolves ``project.manager_super_agent_id`` + ensures a
 * per-project SA instance + a leader chat session exist. Returns the
 * IDs the chat panel uses to drive the EXISTING super-agent chat
 * surface (no new chat I/O endpoints — only this resolution layer):
 *
 *   POST /admin/super-agents/{sa}/sessions/{sid}/chat          (send)
 *   GET  /admin/super-agents/{sa}/sessions/{sid}/chat/stream   (SSE)
 */

import { apiFetch } from './client';

export interface TeamLeaderChatSession {
  project_id: string;
  super_agent_id: string;       // template SA id (used in chat URL)
  session_id: string;
  leader_template_id: string;
  leader_name: string;
  tesserae_enabled: boolean;
}

export const teamLeaderChatApi = {
  openSession: (projectId: string) =>
    apiFetch<TeamLeaderChatSession>(
      `/admin/projects/${encodeURIComponent(projectId)}/team-leader/chat/session`,
      { method: 'POST' },
    ),
};
