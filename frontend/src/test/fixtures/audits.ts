import type { AuditRecord, Finding, AuditStats } from '../../services/api'

export const mockFinding: Finding = {
  package: 'lodash',
  current_version: '4.17.20',
  installed_version: '4.17.20',
  vulnerable_version: '<4.17.21',
  severity: 'high',
  cve: 'CVE-2021-23337',
  ecosystem: 'npm',
  project_path: '/path/to/project1',
  fix_command: 'npm install lodash@4.17.21',
  cve_link: 'https://nvd.nist.gov/vuln/detail/CVE-2021-23337',
  recommended_version: '4.17.21',
  description: 'Command injection vulnerability in lodash'
}

export const mockFindings: Finding[] = [
  mockFinding,
  {
    package: 'axios',
    current_version: '0.21.0',
    vulnerable_version: '<0.21.1',
    severity: 'critical',
    cve: 'CVE-2021-3749',
    ecosystem: 'npm',
    project_path: '/path/to/project1',
    recommended_version: '0.21.1',
    description: 'ReDoS vulnerability'
  },
  {
    package: 'express',
    current_version: '4.17.0',
    vulnerable_version: '<4.17.3',
    severity: 'medium',
    ecosystem: 'npm',
    project_path: '/path/to/project2'
  },
  {
    package: 'moment',
    current_version: '2.29.0',
    vulnerable_version: '<2.29.2',
    severity: 'low',
    ecosystem: 'npm',
    project_path: '/path/to/project1'
  }
]

export const mockAuditRecord: AuditRecord = {
  audit_id: 'audit-1',
  project_path: '/path/to/project1',
  project_name: 'project1',
  audit_date: '2024-01-15T10:00:00Z',
  audit_week: '2024-W03',
  group_id: '1',
  trigger_id: 'bot-1',
  trigger_name: 'Test Bot',
  total_findings: 4,
  critical: 1,
  high: 1,
  medium: 1,
  low: 1,
  status: 'fail',
  findings: mockFindings,
  findings_count: 4
}

export const mockAuditRecords: AuditRecord[] = [
  mockAuditRecord,
  {
    audit_id: 'audit-2',
    project_path: '/path/to/project2',
    project_name: 'project2',
    audit_date: '2024-01-16T10:00:00Z',
    audit_week: '2024-W03',
    group_id: '1',
    trigger_id: 'bot-1',
    trigger_name: 'Test Bot',
    total_findings: 0,
    critical: 0,
    high: 0,
    medium: 0,
    low: 0,
    status: 'pass'
  },
  {
    audit_id: 'audit-3',
    project_path: '/path/to/project1',
    project_name: 'project1',
    audit_date: '2024-01-14T10:00:00Z',
    audit_week: '2024-W03',
    group_id: '2',
    trigger_id: 'bot-2',
    trigger_name: 'Security Scanner',
    total_findings: 2,
    critical: 0,
    high: 1,
    medium: 1,
    low: 0,
    status: 'fail'
  }
]

export const mockAuditStats: AuditStats = {
  historical: {
    total_audits: 10,
    total_findings: 25,
    severity_totals: {
      critical: 3,
      high: 8,
      medium: 10,
      low: 4
    }
  },
  current: {
    total_findings: 4,
    severity_totals: {
      critical: 1,
      high: 1,
      medium: 1,
      low: 1
    },
    status: 'fail'
  },
  projects: ['/path/to/project1', '/path/to/project2']
}
