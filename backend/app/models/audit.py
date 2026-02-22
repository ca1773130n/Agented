"""Audit-related Pydantic models."""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class SeverityLevel(str, Enum):
    """Vulnerability severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AuditStatus(str, Enum):
    """Audit status values."""

    PASS = "pass"
    FAIL = "fail"


class Ecosystem(str, Enum):
    """Package manager ecosystems."""

    PIP = "pip"
    NPM = "npm"
    YARN = "yarn"
    PNPM = "pnpm"


class Finding(BaseModel):
    """Individual security vulnerability finding."""

    package: str
    current_version: str
    vulnerable_version: str
    severity: SeverityLevel
    cve: Optional[str] = None
    ecosystem: str
    project_path: str
    fix_command: Optional[str] = None
    cve_link: Optional[str] = None
    recommended_version: Optional[str] = None


class AuditRecord(BaseModel):
    """Security audit execution result."""

    audit_id: str
    project_path: str
    project_name: str
    audit_date: str
    audit_week: str
    total_findings: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    status: str
    findings: List[Finding] = []


class AuditHistoryResponse(BaseModel):
    """Response for audit history list."""

    audits: List[AuditRecord]


class SeverityTotals(BaseModel):
    """Severity count totals."""

    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


class HistoricalStats(BaseModel):
    """Historical audit statistics."""

    total_audits: int = 0
    total_findings: int = 0
    severity_totals: SeverityTotals = SeverityTotals()


class CurrentStats(BaseModel):
    """Current audit state statistics."""

    total_findings: int = 0
    severity_totals: SeverityTotals = SeverityTotals()
    status: str = "unknown"


class AuditStatsResponse(BaseModel):
    """Response for audit statistics."""

    historical: HistoricalStats
    current: CurrentStats
    projects: List[str]


class ProjectInfo(BaseModel):
    """Project information with audit history."""

    project_path: str
    project_name: str
    audit_count: int = 0
    last_audit: str = ""
    last_status: str = ""
    registered_by_triggers: List[str] = []


class AuditProjectsResponse(BaseModel):
    """Response for listing audited projects."""

    projects: List[ProjectInfo]
