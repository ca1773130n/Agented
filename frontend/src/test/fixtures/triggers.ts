import type { Trigger, ProjectPath, ExecutionStatus } from '../../services/api'

export const mockExecutionStatus: ExecutionStatus = {
  status: 'idle'
}

export const mockProjectPaths: ProjectPath[] = [
  {
    id: 1,
    local_project_path: '/path/to/project1',
    symlink_name: 'project1',
    path_type: 'local',
    created_at: '2024-01-01T00:00:00Z'
  },
  {
    id: 2,
    local_project_path: '/path/to/project2',
    symlink_name: 'project2',
    path_type: 'local',
    created_at: '2024-01-02T00:00:00Z'
  }
]

export const mockTrigger: Trigger = {
  id: 'bot-1',
  name: 'Test Trigger',
  group_id: 1,
  detection_keyword: 'security',
  match_field_path: 'event.type',
  match_field_value: 'security_scan',
  text_field_path: 'text',
  prompt_template: 'Scan for vulnerabilities',
  backend_type: 'claude',
  trigger_source: 'manual',
  is_predefined: 0,
  enabled: 1,
  auto_resolve: 0,
  created_at: '2024-01-01T00:00:00Z',
  path_count: 2,
  execution_status: mockExecutionStatus,
  paths: mockProjectPaths
}

export const mockTriggers: Trigger[] = [
  mockTrigger,
  {
    id: 'bot-2',
    name: 'Security Scanner',
    group_id: 2,
    detection_keyword: 'audit',
    match_field_path: 'action',
    match_field_value: 'security_audit',
    text_field_path: 'message',
    prompt_template: 'Run security audit',
    backend_type: 'claude',
    trigger_source: 'scheduled',
    is_predefined: 0,
    enabled: 1,
    auto_resolve: 1,
    schedule_type: 'daily',
    schedule_time: '09:00',
    schedule_timezone: 'UTC',
    created_at: '2024-01-02T00:00:00Z',
    path_count: 1
  },
  {
    id: 'bot-3',
    name: 'Empty Trigger',
    group_id: 1,
    detection_keyword: 'test',
    match_field_path: 'type',
    match_field_value: 'test',
    text_field_path: 'text',
    prompt_template: 'Test prompt',
    backend_type: 'opencode',
    trigger_source: 'manual',
    is_predefined: 0,
    enabled: 0,
    auto_resolve: 0,
    created_at: '2024-01-03T00:00:00Z',
    path_count: 0
  }
]

export const mockTriggerWithGitHub: Trigger = {
  ...mockTrigger,
  id: 'bot-github',
  name: 'GitHub Trigger',
  trigger_source: 'github',
  paths: [
    {
      id: 3,
      local_project_path: '/tmp/github-repo',
      path_type: 'github',
      github_repo_url: 'https://github.com/owner/repo',
      created_at: '2024-01-04T00:00:00Z'
    }
  ]
}

export const mockTriggerWithWebhook: Trigger = {
  ...mockTrigger,
  id: 'bot-webhook',
  name: 'Webhook Trigger',
  trigger_source: 'webhook',
  match_field_path: 'event.type',
  match_field_value: 'security_alert',
  text_field_path: 'event.text',
  detection_keyword: 'vulnerability'
}
