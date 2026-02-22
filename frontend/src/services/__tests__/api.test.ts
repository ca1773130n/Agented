import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  triggerApi,
  auditApi,
  resolveApi,
  utilityApi,
  healthApi,
  executionApi,
  prReviewApi,
  agentApi,
  ApiError
} from '../api'
import { mockTrigger, mockTriggers, mockProjectPaths } from '../../test/fixtures/triggers'
import { mockAuditRecords, mockAuditStats } from '../../test/fixtures/audits'

describe('API Service', () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  // Helper to create mock Response
  function mockResponse(data: unknown, ok = true, status = 200) {
    return {
      ok,
      status,
      text: () => Promise.resolve(JSON.stringify(data)),
      json: () => Promise.resolve(data)
    } as Response
  }

  describe('ApiError', () => {
    it('should create error with status and message', () => {
      const error = new ApiError(404, 'Not found')
      expect(error.status).toBe(404)
      expect(error.message).toBe('Not found')
      expect(error.name).toBe('ApiError')
    })
  })

  describe('triggerApi', () => {
    describe('list', () => {
      it('should fetch triggers list', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ triggers: mockTriggers }))

        const result = await triggerApi.list()

        expect(fetch).toHaveBeenCalledWith('/admin/triggers', expect.objectContaining({
          headers: { 'Content-Type': 'application/json' },
          signal: expect.any(AbortSignal),
        }))
        expect(result.triggers).toEqual(mockTriggers)
      })

      it('should throw ApiError on failure', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ error: 'Server error' }, false, 500))

        await expect(triggerApi.list()).rejects.toThrow(ApiError)
      })
    })

    describe('get', () => {
      it('should fetch a single trigger', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse(mockTrigger))

        const result = await triggerApi.get('bot-1')

        expect(fetch).toHaveBeenCalledWith('/admin/triggers/bot-1', expect.any(Object))
        expect(result).toEqual(mockTrigger)
      })
    })

    describe('getStatus', () => {
      it('should fetch trigger execution status', async () => {
        const status = { status: 'running', started_at: '2024-01-01T00:00:00Z' }
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse(status))

        const result = await triggerApi.getStatus('bot-1')

        expect(fetch).toHaveBeenCalledWith('/admin/triggers/bot-1/status', expect.any(Object))
        expect(result.status).toBe('running')
      })
    })

    describe('create', () => {
      it('should create a new trigger', async () => {
        const createResponse = { message: 'Created', trigger_id: 'new-trigger', name: 'New Trigger' }
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse(createResponse))

        const data = { name: 'New Trigger', prompt_template: 'Test prompt' }
        const result = await triggerApi.create(data)

        expect(fetch).toHaveBeenCalledWith('/admin/triggers', expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data)
        }))
        expect(result.trigger_id).toBe('new-trigger')
      })
    })

    describe('update', () => {
      it('should update an existing trigger', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ message: 'Updated' }))

        const data = { name: 'Updated Trigger' }
        await triggerApi.update('bot-1', data)

        expect(fetch).toHaveBeenCalledWith('/admin/triggers/bot-1', expect.objectContaining({
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data)
        }))
      })
    })

    describe('delete', () => {
      it('should delete a trigger', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ message: 'Deleted' }))

        await triggerApi.delete('bot-1')

        expect(fetch).toHaveBeenCalledWith('/admin/triggers/bot-1', expect.objectContaining({
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' }
        }))
      })
    })

    describe('run', () => {
      it('should run a trigger without message', async () => {
        const runResponse = { message: 'Started', trigger_id: 'bot-1', status: 'running', execution_id: 'exec-1' }
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse(runResponse))

        const result = await triggerApi.run('bot-1')

        expect(fetch).toHaveBeenCalledWith('/admin/triggers/bot-1/run', expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: '' })
        }))
        expect(result.execution_id).toBe('exec-1')
      })

      it('should run a trigger with custom message', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ message: 'Started', trigger_id: 'bot-1', status: 'running' }))

        await triggerApi.run('bot-1', 'Custom message')

        expect(fetch).toHaveBeenCalledWith('/admin/triggers/bot-1/run', expect.objectContaining({
          body: JSON.stringify({ message: 'Custom message' })
        }))
      })
    })

    describe('path operations', () => {
      it('should list paths for a trigger', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ paths: mockProjectPaths }))

        const result = await triggerApi.listPaths('bot-1')

        expect(fetch).toHaveBeenCalledWith('/admin/triggers/bot-1/paths', expect.any(Object))
        expect(result.paths).toEqual(mockProjectPaths)
      })

      it('should add a local path', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({
          message: 'Added',
          local_project_path: '/new/path',
          path_type: 'local'
        }))

        const result = await triggerApi.addPath('bot-1', '/new/path')

        expect(fetch).toHaveBeenCalledWith('/admin/triggers/bot-1/paths', expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ local_project_path: '/new/path' })
        }))
        expect(result.path_type).toBe('local')
      })

      it('should add a GitHub repo', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({
          message: 'Added',
          github_repo_url: 'https://github.com/owner/repo',
          path_type: 'github'
        }))

        const result = await triggerApi.addGitHubRepo('bot-1', 'https://github.com/owner/repo')

        expect(fetch).toHaveBeenCalledWith('/admin/triggers/bot-1/paths', expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ github_repo_url: 'https://github.com/owner/repo' })
        }))
        expect(result.path_type).toBe('github')
      })

      it('should remove a local path', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ message: 'Removed' }))

        await triggerApi.removePath('bot-1', '/path/to/remove')

        expect(fetch).toHaveBeenCalledWith('/admin/triggers/bot-1/paths', expect.objectContaining({
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ local_project_path: '/path/to/remove' })
        }))
      })

      it('should remove a GitHub repo', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ message: 'Removed' }))

        await triggerApi.removeGitHubRepo('bot-1', 'https://github.com/owner/repo')

        expect(fetch).toHaveBeenCalledWith('/admin/triggers/bot-1/paths', expect.objectContaining({
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ github_repo_url: 'https://github.com/owner/repo' })
        }))
      })
    })

    describe('setAutoResolve', () => {
      it('should enable auto-resolve', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ message: 'Updated' }))

        await triggerApi.setAutoResolve('bot-1', true)

        expect(fetch).toHaveBeenCalledWith('/admin/triggers/bot-1/auto-resolve', expect.objectContaining({
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ auto_resolve: true })
        }))
      })
    })
  })

  describe('auditApi', () => {
    describe('getHistory', () => {
      it('should fetch audit history without options', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ audits: mockAuditRecords }))

        const result = await auditApi.getHistory()

        expect(fetch).toHaveBeenCalledWith('/api/audit/history', expect.any(Object))
        expect(result.audits).toEqual(mockAuditRecords)
      })

      it('should fetch audit history with limit', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ audits: mockAuditRecords }))

        await auditApi.getHistory({ limit: 10 })

        expect(fetch).toHaveBeenCalledWith('/api/audit/history?limit=10', expect.any(Object))
      })

      it('should fetch audit history with all options', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ audits: [] }))

        await auditApi.getHistory({ limit: 5, project_path: '/path', trigger_id: 'bot-1' })

        expect(fetch).toHaveBeenCalledWith(
          '/api/audit/history?limit=5&project_path=%2Fpath&trigger_id=bot-1',
          expect.any(Object)
        )
      })
    })

    describe('getStats', () => {
      it('should fetch audit stats without options', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse(mockAuditStats))

        const result = await auditApi.getStats()

        expect(fetch).toHaveBeenCalledWith('/api/audit/stats', expect.any(Object))
        expect(result).toEqual(mockAuditStats)
      })

      it('should fetch audit stats with string path', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse(mockAuditStats))

        await auditApi.getStats('/path/to/project')

        expect(fetch).toHaveBeenCalledWith('/api/audit/stats?project_path=%2Fpath%2Fto%2Fproject', expect.any(Object))
      })

      it('should fetch audit stats with options object', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse(mockAuditStats))

        await auditApi.getStats({ project_path: '/path', trigger_id: 'bot-1' })

        expect(fetch).toHaveBeenCalledWith('/api/audit/stats?project_path=%2Fpath&trigger_id=bot-1', expect.any(Object))
      })
    })

    describe('getProjects', () => {
      it('should fetch projects list', async () => {
        const projects = [{ project_path: '/path', project_name: 'test' }]
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ projects }))

        const result = await auditApi.getProjects()

        expect(fetch).toHaveBeenCalledWith('/api/audit/projects', expect.any(Object))
        expect(result.projects).toEqual(projects)
      })
    })

    describe('getDetail', () => {
      it('should fetch audit detail', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse(mockAuditRecords[0]))

        const result = await auditApi.getDetail('audit-1')

        expect(fetch).toHaveBeenCalledWith('/api/audit/audit-1', expect.any(Object))
        expect(result.audit_id).toBe('audit-1')
      })
    })
  })

  describe('resolveApi', () => {
    describe('resolveIssues', () => {
      it('should send resolve request', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ message: 'Resolving' }))

        await resolveApi.resolveIssues('audit summary', ['/path1', '/path2'])

        expect(fetch).toHaveBeenCalledWith('/api/resolve-issues', expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ audit_summary: 'audit summary', project_paths: ['/path1', '/path2'] })
        }))
      })
    })
  })

  describe('utilityApi', () => {
    describe('checkBackend', () => {
      it('should check claude backend', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ backend: 'claude', installed: true }))

        const result = await utilityApi.checkBackend('claude')

        expect(fetch).toHaveBeenCalledWith('/api/check-backend?name=claude', expect.any(Object))
        expect(result.installed).toBe(true)
      })
    })

    describe('validatePath', () => {
      it('should validate a path', async () => {
        const validation = { path: '/test', exists: true, is_directory: true, is_file: false, is_absolute: true }
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse(validation))

        const result = await utilityApi.validatePath('/test')

        expect(fetch).toHaveBeenCalledWith('/api/validate-path?path=%2Ftest', expect.any(Object))
        expect(result.exists).toBe(true)
      })
    })

    describe('validateGitHubUrl', () => {
      it('should validate a GitHub URL', async () => {
        const validation = { url: 'https://github.com/owner/repo', valid: true, owner: 'owner', repo: 'repo' }
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse(validation))

        const result = await utilityApi.validateGitHubUrl('https://github.com/owner/repo')

        expect(fetch).toHaveBeenCalledWith(
          '/api/validate-github-url?url=https%3A%2F%2Fgithub.com%2Fowner%2Frepo',
          expect.any(Object)
        )
        expect(result.valid).toBe(true)
      })
    })

    describe('discoverSkills', () => {
      it('should discover skills without bot ID', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ skills: [{ name: 'skill1', description: 'desc' }] }))

        const result = await utilityApi.discoverSkills()

        expect(fetch).toHaveBeenCalledWith('/api/discover-skills', expect.any(Object))
        expect(result.skills).toHaveLength(1)
      })

      it('should discover skills with trigger ID', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ skills: [] }))

        await utilityApi.discoverSkills('bot-1')

        expect(fetch).toHaveBeenCalledWith('/api/discover-skills?trigger_id=bot-1', expect.any(Object))
      })
    })
  })

  describe('healthApi', () => {
    describe('liveness', () => {
      it('should return true when healthy', async () => {
        vi.mocked(fetch).mockResolvedValueOnce({ ok: true } as Response)

        const result = await healthApi.liveness()

        expect(fetch).toHaveBeenCalledWith('/health/liveness')
        expect(result).toBe(true)
      })

      it('should return false when unhealthy', async () => {
        vi.mocked(fetch).mockResolvedValueOnce({ ok: false } as Response)

        const result = await healthApi.liveness()

        expect(result).toBe(false)
      })
    })

    describe('readiness', () => {
      it('should return health status when ready', async () => {
        const mockHealth = {
          status: 'ok',
          components: {
            database: { status: 'ok', journal_mode: 'wal' },
            process_manager: { status: 'ok', active_executions: 0, active_execution_ids: [] }
          }
        }
        vi.mocked(fetch).mockResolvedValueOnce({
          ok: true,
          text: () => Promise.resolve(JSON.stringify(mockHealth)),
        } as unknown as Response)

        const result = await healthApi.readiness()

        expect(result).toEqual(mockHealth)
        expect(result.status).toBe('ok')
      })
    })
  })

  describe('executionApi', () => {
    const mockExecution = {
      id: 1,
      execution_id: 'exec-1',
      trigger_id: 'bot-1',
      trigger_name: 'Test Trigger',
      trigger_type: 'manual' as const,
      started_at: '2024-01-01T00:00:00Z',
      backend_type: 'claude' as const,
      status: 'success' as const
    }

    describe('listForBot', () => {
      it('should list executions for a trigger', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({
          executions: [mockExecution],
          running_execution: null,
          total: 1
        }))

        const result = await executionApi.listForBot('bot-1')

        expect(fetch).toHaveBeenCalledWith('/admin/triggers/bot-1/executions', expect.any(Object))
        expect(result.executions).toHaveLength(1)
      })

      it('should list executions with pagination', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ executions: [], running_execution: null, total: 0 }))

        await executionApi.listForBot('bot-1', { limit: 10, offset: 5, status: 'success' })

        expect(fetch).toHaveBeenCalledWith(
          '/admin/triggers/bot-1/executions?limit=10&offset=5&status=success',
          expect.any(Object)
        )
      })
    })

    describe('listAll', () => {
      it('should list all executions', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ executions: [mockExecution], total: 1 }))

        const result = await executionApi.listAll()

        expect(fetch).toHaveBeenCalledWith('/admin/executions', expect.any(Object))
        expect(result.total).toBe(1)
      })
    })

    describe('get', () => {
      it('should get a single execution', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse(mockExecution))

        const result = await executionApi.get('exec-1')

        expect(fetch).toHaveBeenCalledWith('/admin/executions/exec-1', expect.any(Object))
        expect(result.execution_id).toBe('exec-1')
      })
    })

    describe('getRunning', () => {
      it('should get running execution for a trigger', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ running: true, execution: mockExecution }))

        const result = await executionApi.getRunning('bot-1')

        expect(fetch).toHaveBeenCalledWith('/admin/triggers/bot-1/executions/running', expect.any(Object))
        expect(result.running).toBe(true)
      })
    })

    describe('streamLogs', () => {
      it('should create EventSource for log streaming', () => {
        const mockEventSource = vi.fn()
        vi.stubGlobal('EventSource', mockEventSource)

        executionApi.streamLogs('exec-1')

        expect(mockEventSource).toHaveBeenCalledWith('/admin/executions/exec-1/stream')
      })
    })
  })

  describe('prReviewApi', () => {
    const mockPrReview = {
      id: 1,
      trigger_id: 'bot-1',
      project_name: 'test-project',
      pr_number: 123,
      pr_url: 'https://github.com/owner/repo/pull/123',
      pr_title: 'Test PR',
      pr_status: 'open' as const,
      review_status: 'pending' as const,
      fixes_applied: 0
    }

    describe('list', () => {
      it('should list PR reviews', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ reviews: [mockPrReview], total: 1 }))

        const result = await prReviewApi.list()

        expect(fetch).toHaveBeenCalledWith('/api/pr-reviews/', expect.any(Object))
        expect(result.reviews).toHaveLength(1)
      })

      it('should list with filters', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ reviews: [], total: 0 }))

        await prReviewApi.list({ limit: 10, pr_status: 'open', review_status: 'pending' })

        expect(fetch).toHaveBeenCalledWith(
          '/api/pr-reviews/?limit=10&pr_status=open&review_status=pending',
          expect.any(Object)
        )
      })
    })

    describe('getStats', () => {
      it('should get PR review stats', async () => {
        const stats = { total_prs: 10, open_prs: 5, merged_prs: 3, closed_prs: 2 }
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse(stats))

        const result = await prReviewApi.getStats()

        expect(fetch).toHaveBeenCalledWith('/api/pr-reviews/stats', expect.any(Object))
        expect(result.total_prs).toBe(10)
      })
    })

    describe('create', () => {
      it('should create a PR review', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ message: 'Created', id: 2 }))

        const data = {
          project_name: 'test',
          pr_number: 456,
          pr_url: 'https://github.com/owner/repo/pull/456',
          pr_title: 'New PR'
        }
        const result = await prReviewApi.create(data)

        expect(fetch).toHaveBeenCalledWith('/api/pr-reviews/', expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data)
        }))
        expect(result.id).toBe(2)
      })
    })

    describe('update', () => {
      it('should update a PR review', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ message: 'Updated' }))

        await prReviewApi.update(1, { review_status: 'approved' })

        expect(fetch).toHaveBeenCalledWith('/api/pr-reviews/1', expect.objectContaining({
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ review_status: 'approved' })
        }))
      })
    })

    describe('delete', () => {
      it('should delete a PR review', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ message: 'Deleted' }))

        await prReviewApi.delete(1)

        expect(fetch).toHaveBeenCalledWith('/api/pr-reviews/1', expect.objectContaining({
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' }
        }))
      })
    })
  })

  describe('agentApi', () => {
    const mockAgent = {
      id: 'agent-1',
      name: 'Test Agent',
      backend_type: 'claude' as const,
      enabled: 1,
      creation_status: 'completed' as const
    }

    describe('list', () => {
      it('should list agents', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ agents: [mockAgent] }))

        const result = await agentApi.list()

        expect(fetch).toHaveBeenCalledWith('/admin/agents', expect.any(Object))
        expect(result.agents).toHaveLength(1)
      })
    })

    describe('get', () => {
      it('should get a single agent', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse(mockAgent))

        const result = await agentApi.get('agent-1')

        expect(fetch).toHaveBeenCalledWith('/admin/agents/agent-1', expect.any(Object))
        expect(result.name).toBe('Test Agent')
      })
    })

    describe('create', () => {
      it('should create an agent', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({ message: 'Created', agent_id: 'new-agent', name: 'New' }))

        const data = { name: 'New Agent' }
        const result = await agentApi.create(data)

        expect(fetch).toHaveBeenCalledWith('/admin/agents', expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data)
        }))
        expect(result.agent_id).toBe('new-agent')
      })
    })

    describe('run', () => {
      it('should run an agent', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(mockResponse({
          message: 'Started',
          agent_id: 'agent-1',
          execution_id: 'exec-1',
          status: 'running'
        }))

        const result = await agentApi.run('agent-1', 'Test message')

        expect(fetch).toHaveBeenCalledWith('/admin/agents/agent-1/run', expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: 'Test message' })
        }))
        expect(result.execution_id).toBe('exec-1')
      })
    })
  })

  describe('error handling', () => {
    it('should throw ApiError with error message from response', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: () => Promise.resolve({ error: 'Bad request' })
      } as Response)

      try {
        await triggerApi.list()
        expect.fail('Should have thrown')
      } catch (error) {
        expect(error).toBeInstanceOf(ApiError)
        expect((error as ApiError).status).toBe(400)
        expect((error as ApiError).message).toBe('Bad request')
      }
    })

    it('should handle empty response body', async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        status: 204,
        text: () => Promise.resolve('')
      } as Response)

      const result = await triggerApi.delete('bot-1')

      expect(result).toBeNull()
    })
  })
})
