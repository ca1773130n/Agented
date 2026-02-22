"""Audit history service."""

import csv
import datetime
import json
import logging
import os
import re
from http import HTTPStatus
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

from app.config import PROJECT_ROOT

from ..database import get_all_triggers, list_paths_for_trigger

AUDIT_REPORTS_DIR = os.path.join(PROJECT_ROOT, ".claude/skills/weekly-security-audit/reports")
AUDIT_INDEX_FILE = os.path.join(AUDIT_REPORTS_DIR, "audit_index.json")


class AuditService:
    """Service for audit history operations."""

    @staticmethod
    def _get_fix_command(finding: Dict) -> str:
        """Generate fix command based on ecosystem and package."""
        ecosystem = finding.get("ecosystem", "pip").lower()
        package = finding.get("package", "")
        vulnerable_version = finding.get("vulnerable_version", "")

        # Extract minimum safe version from vulnerable version spec
        safe_version = ""
        if vulnerable_version:
            match = re.match(r"<\s*([\d.]+)", vulnerable_version)
            if match:
                safe_version = match.group(1)

        if ecosystem in ("pip", "python"):
            if safe_version:
                return f"pip install '{package}>={safe_version}'"
            return f"pip install --upgrade {package}"
        elif ecosystem in ("npm", "yarn", "pnpm"):
            if safe_version:
                return f"npm install {package}@^{safe_version}"
            return f"npm update {package}"
        else:
            if safe_version:
                return f"Update {package} to version >= {safe_version}"
            return f"Update {package} to the latest version"

    @staticmethod
    def _add_resolution_guidance(findings: List[Dict]) -> List[Dict]:
        """Add resolution guidance to each finding."""
        enhanced_findings = []
        for finding in findings:
            enhanced = dict(finding)
            enhanced["fix_command"] = AuditService._get_fix_command(finding)

            # Add CVE link if available
            cve = finding.get("cve", "")
            if cve and cve.startswith("CVE-"):
                enhanced["cve_link"] = f"https://nvd.nist.gov/vuln/detail/{cve}"

            # Extract safe version from vulnerable version
            vulnerable_version = finding.get("vulnerable_version", "")
            if vulnerable_version:
                match = re.match(r"<\s*([\d.]+)", vulnerable_version)
                if match:
                    enhanced["recommended_version"] = f">= {match.group(1)}"

            enhanced_findings.append(enhanced)
        return enhanced_findings

    @staticmethod
    def _load_audit_index() -> List[Dict]:
        """Load audit index from project_audit_history.csv (source of truth)."""
        return AuditService._rebuild_audit_index_from_csv()

    @staticmethod
    def _save_audit_index(audits: List[Dict]) -> bool:
        """Save audit index to JSON file."""
        try:
            os.makedirs(AUDIT_REPORTS_DIR, exist_ok=True)
            with open(AUDIT_INDEX_FILE, "w", encoding="utf-8") as f:
                json.dump({"audits": audits}, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.warning("Audit index save error: %s", e)
            return False

    @staticmethod
    def _rebuild_audit_index_from_csv() -> List[Dict]:
        """Rebuild audit index from project_audit_history.csv."""
        project_history_file = os.path.join(AUDIT_REPORTS_DIR, "project_audit_history.csv")
        audits = []

        if not os.path.exists(project_history_file):
            return AuditService._migrate_old_audit_history()

        try:
            with open(project_history_file, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    audit_date = row.get("audit_date", "")
                    audit_week = row.get("audit_week", "")
                    project_path = row.get("project_path", ".")
                    project_name = (
                        AuditService._clean_project_name(row.get("project_name", ""), project_path)
                        or "Project"
                    )

                    # Try to load detailed findings from report file
                    findings = []
                    report_file = os.path.join(
                        AUDIT_REPORTS_DIR, f"security_report_{audit_week}.json"
                    )
                    if os.path.exists(report_file):
                        try:
                            with open(report_file, "r", encoding="utf-8") as rf:
                                report = json.load(rf)
                                all_findings = report.get("findings", [])
                                findings = [
                                    f for f in all_findings if f.get("project_path") == project_path
                                ]
                        except Exception as e:
                            logger.debug("Audit report parse: %s", e)

                    # Generate audit_id from project path and date
                    timestamp = (
                        audit_date.replace(":", "").replace("-", "").replace("T", "_").split(".")[0]
                    )
                    safe_path = (
                        project_path.replace("/", "_").replace("\\", "_").strip("_") or "project"
                    )
                    audit_id = f"{safe_path}_{timestamp}"

                    audit = {
                        "audit_id": audit_id,
                        "project_path": project_path,
                        "project_name": project_name,
                        "audit_date": audit_date,
                        "audit_week": audit_week,
                        "trigger_id": row.get("trigger_id", "bot-security"),
                        "trigger_name": row.get("trigger_name", "Weekly Security Audit"),
                        "total_findings": int(row.get("findings_count", 0)),
                        "critical": int(row.get("critical", 0)),
                        "high": int(row.get("high", 0)),
                        "medium": int(row.get("medium", 0)),
                        "low": int(row.get("low", 0)),
                        "status": row.get("status", "unknown"),
                        "findings": AuditService._add_resolution_guidance(findings),
                    }
                    audits.append(audit)

            AuditService._save_audit_index(audits)
        except Exception as e:
            print(f"Error rebuilding audit index: {e}")

        return audits

    @staticmethod
    def _migrate_old_audit_history() -> List[Dict]:
        """Migrate old CSV-based audit history to new per-project index."""
        history_file = os.path.join(AUDIT_REPORTS_DIR, "audit_history.csv")
        audits = []

        if os.path.exists(history_file):
            try:
                with open(history_file, "r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        audit_date = row.get("audit_date", "")
                        audit_week = row.get("audit_week", "")

                        report_file = os.path.join(
                            AUDIT_REPORTS_DIR, f"security_report_{audit_week}.json"
                        )

                        if os.path.exists(report_file):
                            try:
                                with open(report_file, "r", encoding="utf-8") as rf:
                                    report = json.load(rf)
                                    all_findings = report.get("findings", [])

                                    for project in report.get("projects_scanned", []):
                                        project_path = project.get("path", ".")
                                        project_name = (
                                            AuditService._clean_project_name(
                                                project.get("name", ""), project_path
                                            )
                                            or "Project"
                                        )

                                        project_findings = [
                                            f
                                            for f in all_findings
                                            if f.get("project_path") == project_path
                                        ]

                                        critical = sum(
                                            1
                                            for f in project_findings
                                            if f.get("severity") == "critical"
                                        )
                                        high = sum(
                                            1
                                            for f in project_findings
                                            if f.get("severity") == "high"
                                        )
                                        medium = sum(
                                            1
                                            for f in project_findings
                                            if f.get("severity") == "medium"
                                        )
                                        low = sum(
                                            1
                                            for f in project_findings
                                            if f.get("severity") == "low"
                                        )

                                        timestamp = (
                                            audit_date.replace(":", "")
                                            .replace("-", "")
                                            .replace("T", "_")
                                            .split(".")[0]
                                        )
                                        safe_path = (
                                            project_path.replace("/", "_")
                                            .replace("\\", "_")
                                            .strip("_")
                                            or "project"
                                        )
                                        audit_id = f"{safe_path}_{timestamp}"

                                        audit = {
                                            "audit_id": audit_id,
                                            "project_path": project_path,
                                            "project_name": project_name,
                                            "audit_date": audit_date,
                                            "audit_week": audit_week,
                                            "trigger_id": "bot-security",
                                            "trigger_name": "Weekly Security Audit",
                                            "total_findings": len(project_findings),
                                            "critical": critical,
                                            "high": high,
                                            "medium": medium,
                                            "low": low,
                                            "status": (
                                                "fail" if critical > 0 or high > 0 else "pass"
                                            ),
                                            "findings": AuditService._add_resolution_guidance(
                                                project_findings
                                            ),
                                        }
                                        audits.append(audit)
                            except Exception as e:
                                logger.debug("Audit report parse: %s", e)

                AuditService._save_audit_index(audits)
            except Exception as e:
                logger.warning("Audit history migration error: %s", e)

        return audits

    @staticmethod
    def get_history(
        limit: int = None, project_path: str = None, trigger_id: str = None
    ) -> Tuple[dict, HTTPStatus]:
        """Get audit history with optional filters."""
        audits = AuditService._load_audit_index()

        if trigger_id:
            audits = [a for a in audits if a.get("trigger_id") == trigger_id]

        if project_path:
            audits = [a for a in audits if a.get("project_path") == project_path]

        audits.sort(key=lambda x: x.get("audit_date", ""), reverse=True)

        if limit:
            audits = audits[:limit]

        # Return summary without full findings for list view
        summary_audits = []
        for audit in audits:
            summary = {k: v for k, v in audit.items() if k != "findings"}
            summary["findings_count"] = len(audit.get("findings", []))
            summary_audits.append(summary)

        return {"audits": summary_audits}, HTTPStatus.OK

    @staticmethod
    def get_stats(project_path: str = None, trigger_id: str = None) -> Tuple[dict, HTTPStatus]:
        """Get aggregate statistics from audit history."""
        audits = AuditService._load_audit_index()

        if trigger_id:
            audits = [a for a in audits if a.get("trigger_id") == trigger_id]

        if project_path:
            audits = [a for a in audits if a.get("project_path") == project_path]

        if not audits:
            return {
                "historical": {
                    "total_audits": 0,
                    "total_findings": 0,
                    "severity_totals": {"critical": 0, "high": 0, "medium": 0, "low": 0},
                },
                "current": {
                    "total_findings": 0,
                    "severity_totals": {"critical": 0, "high": 0, "medium": 0, "low": 0},
                    "status": "unknown",
                },
                "projects": [],
            }, HTTPStatus.OK

        # Historical stats
        total_audits = len(audits)
        total_findings = sum(a.get("total_findings", 0) for a in audits)

        historical_severity = {
            "critical": sum(a.get("critical", 0) for a in audits),
            "high": sum(a.get("high", 0) for a in audits),
            "medium": sum(a.get("medium", 0) for a in audits),
            "low": sum(a.get("low", 0) for a in audits),
        }

        # Current stats (latest audit per project)
        latest_by_project = {}
        for audit in audits:
            proj = audit.get("project_path", "")
            if proj not in latest_by_project or audit.get("audit_date", "") > latest_by_project[
                proj
            ].get("audit_date", ""):
                latest_by_project[proj] = audit

        latest_audits = list(latest_by_project.values())
        current_findings = sum(a.get("total_findings", 0) for a in latest_audits)
        current_pass = (
            all(a.get("status") == "pass" for a in latest_audits) if latest_audits else True
        )

        current_severity = {
            "critical": sum(a.get("critical", 0) for a in latest_audits),
            "high": sum(a.get("high", 0) for a in latest_audits),
            "medium": sum(a.get("medium", 0) for a in latest_audits),
            "low": sum(a.get("low", 0) for a in latest_audits),
        }

        # Get unique projects
        audited_projects = set(a.get("project_path", "") for a in audits if a.get("project_path"))

        # Also get registered project paths from all triggers
        all_triggers = get_all_triggers()
        registered_projects = set()
        for trigger_item in all_triggers:
            paths = list_paths_for_trigger(trigger_item["id"])
            for path_info in paths:
                path = path_info.get("local_project_path", "")
                if path:
                    registered_projects.add(path)

        all_projects = audited_projects | registered_projects

        return {
            "historical": {
                "total_audits": total_audits,
                "total_findings": total_findings,
                "severity_totals": historical_severity,
            },
            "current": {
                "total_findings": current_findings,
                "severity_totals": current_severity,
                "status": "pass" if current_pass else "fail",
            },
            "projects": list(all_projects),
        }, HTTPStatus.OK

    @staticmethod
    def _normalize_project_identity(path: str, github_url: str = None) -> str:
        """Create a normalized identity for deduplication.

        For GitHub repos: returns 'github:owner/repo'
        For local paths: returns the path itself
        For temp clone dirs: extracts owner/repo from path pattern
        """
        # If we have a GitHub URL, use it as canonical identity
        if github_url:
            # Extract owner/repo from URL like https://github.com/owner/repo
            # Supports various GitHub domains (github.com, github.example.com, etc.)
            match = re.search(r"github[^/]*/([^/]+)/([^/.\s]+)", github_url)
            if match:
                return f"github:{match.group(1)}/{match.group(2)}"

        # Check if path is a github:// placeholder
        if path.startswith("github://"):
            inner = path[9:]  # Remove 'github://' prefix
            # Handle 'github://https://github.com/owner/repo' format (nested URL)
            if inner.startswith("https://") or inner.startswith("http://"):
                match = re.search(r"github[^/]*/([^/]+)/([^/.\s]+)", inner)
                if match:
                    return f"github:{match.group(1)}/{match.group(2)}"
            # Handle 'github://owner/repo' format
            return f"github:{inner}"

        # Check if path looks like a temp clone directory (hive_clone_owner_repo_xxx)
        # Pattern: any_prefix/hive_clone_OWNER_REPO_randomsuffix(es) (with optional trailing slash)
        match = re.search(r"hive_clone_([^_]+)_(.+?)(?:_[a-z0-9]+)+/?$", path)
        if match:
            return f"github:{match.group(1)}/{match.group(2)}"

        # For local paths, use as-is
        return path

    @staticmethod
    def _extract_project_name(path: str, github_url: str = None) -> str:
        """Extract a clean project name.

        Prefers GitHub repo name over temp directory names.
        Handles hive_clone_* patterns in both paths and names.
        """
        # If we have a GitHub URL, extract repo name
        # Supports various GitHub domains (github.com, github.example.com, etc.)
        if github_url:
            match = re.search(r"github[^/]*/([^/]+)/([^/.\s]+)", github_url)
            if match:
                return match.group(2)

        # Check if path is a github:// placeholder
        if path.startswith("github://"):
            inner = path[9:]  # Remove 'github://' prefix
            # Handle 'github://https://github.com/owner/repo' format (nested URL)
            if inner.startswith("https://") or inner.startswith("http://"):
                match = re.search(r"github[^/]*/([^/]+)/([^/.\s]+)", inner)
                if match:
                    return match.group(2)
            # Handle 'github://owner/repo' format
            parts = inner.split("/")
            if len(parts) >= 2:
                return parts[1]
            return inner

        # Check if path or name matches hive_clone pattern
        # Can be a full path or just a name like 'hive_clone_owner_repo_xxx'
        match = re.search(r"hive_clone_([^_]+)_(.+?)(?:_[a-z0-9]+)+/?$", path)
        if match:
            return match.group(2)

        # Fall back to basename
        return os.path.basename(path.rstrip("/")) or path

    @staticmethod
    def _clean_project_name(name: str, path: str = None, github_url: str = None) -> str:
        """Clean a project name, extracting clean name from hive_clone patterns.

        Always checks if name contains hive_clone pattern and cleans it.
        Falls back to _extract_project_name if name is empty.
        """
        if not name:
            return AuditService._extract_project_name(path or "", github_url)

        # Check if name itself is a hive_clone pattern
        match = re.search(r"hive_clone_([^_]+)_(.+?)(?:_[a-z0-9]+)+$", name)
        if match:
            return match.group(2)

        return name

    @staticmethod
    def get_projects() -> Tuple[dict, HTTPStatus]:
        """Get list of all unique project paths with audit info."""
        audits = AuditService._load_audit_index()

        all_triggers = get_all_triggers()
        projects = {}  # Keyed by normalized identity

        # First, process registered trigger paths
        for trigger_item in all_triggers:
            paths = list_paths_for_trigger(trigger_item["id"])
            for path_info in paths:
                path = path_info.get("local_project_path", "")
                github_url = path_info.get("github_repo_url", "")

                if not path:
                    continue

                identity = AuditService._normalize_project_identity(path, github_url)
                project_name = AuditService._extract_project_name(path, github_url)

                if identity not in projects:
                    projects[identity] = {
                        "project_path": path,
                        "project_name": project_name,
                        "project_type": "github" if identity.startswith("github:") else "local",
                        "audit_count": 0,
                        "last_audit": "",
                        "last_status": "not_scanned",
                        "registered_by_triggers": [],
                        "_github_url": github_url,  # Track for audit matching
                    }
                projects[identity]["registered_by_triggers"].append(trigger_item["name"])

        # Then, process audit history - matching to registered projects where possible
        for audit in audits:
            path = audit.get("project_path", "")
            if not path:
                continue

            # Try to match audit to a registered project
            audit_identity = AuditService._normalize_project_identity(path)

            if audit_identity not in projects:
                # Audit for unregistered project (possibly deleted)
                project_name = audit.get("project_name") or AuditService._extract_project_name(path)
                projects[audit_identity] = {
                    "project_path": path,
                    "project_name": project_name,
                    "project_type": "github" if audit_identity.startswith("github:") else "local",
                    "audit_count": 0,
                    "last_audit": "",
                    "last_status": "",
                    "registered_by_triggers": [],
                }

            projects[audit_identity]["audit_count"] += 1
            if audit.get("audit_date", "") > projects[audit_identity]["last_audit"]:
                projects[audit_identity]["last_audit"] = audit.get("audit_date", "")
                projects[audit_identity]["last_status"] = audit.get("status", "")
                # Only update name if audit has one and current is from temp path
                if audit.get("project_name"):
                    projects[audit_identity]["project_name"] = audit.get("project_name")

        # Clean up internal fields before returning
        result = []
        for proj in projects.values():
            proj.pop("_github_url", None)
            result.append(proj)

        return {"projects": result}, HTTPStatus.OK

    @staticmethod
    def get_detail(audit_id: str) -> Tuple[dict, HTTPStatus]:
        """Get detailed audit report by audit_id."""
        audits = AuditService._load_audit_index()

        for audit in audits:
            if audit.get("audit_id") == audit_id:
                return audit, HTTPStatus.OK

        return {"error": f"Audit not found: {audit_id}"}, HTTPStatus.NOT_FOUND

    @staticmethod
    def get_weekly_report(audit_week: str) -> Tuple[dict, HTTPStatus]:
        """Get detailed report for a specific audit week."""
        report_file = os.path.join(AUDIT_REPORTS_DIR, f"security_report_{audit_week}.json")

        if not os.path.exists(report_file):
            return {"error": f"Report not found for {audit_week}"}, HTTPStatus.NOT_FOUND

        try:
            with open(report_file, "r", encoding="utf-8") as f:
                report = json.load(f)

            if "findings" in report:
                report["findings"] = AuditService._add_resolution_guidance(report["findings"])

            return report, HTTPStatus.OK

        except Exception as e:
            return {"error": f"Failed to read report: {str(e)}"}, HTTPStatus.INTERNAL_SERVER_ERROR

    @staticmethod
    def add_audit(data: dict) -> Tuple[dict, HTTPStatus]:
        """Add a new audit result."""
        project_path = data.get("project_path")
        if not project_path:
            return {"error": "project_path required"}, HTTPStatus.BAD_REQUEST

        audit_date = data.get("audit_date", datetime.datetime.now().isoformat())
        timestamp = audit_date.replace(":", "").replace("-", "").replace("T", "_").split(".")[0]
        safe_path = project_path.replace("/", "_").replace("\\", "_").strip("_") or "project"
        audit_id = f"{safe_path}_{timestamp}"

        findings = data.get("findings", [])
        enhanced_findings = AuditService._add_resolution_guidance(findings)

        critical = sum(1 for f in findings if f.get("severity") == "critical")
        high = sum(1 for f in findings if f.get("severity") == "high")
        medium = sum(1 for f in findings if f.get("severity") == "medium")
        low = sum(1 for f in findings if f.get("severity") == "low")

        audit = {
            "audit_id": audit_id,
            "project_path": project_path,
            "project_name": AuditService._clean_project_name(
                data.get("project_name", ""), project_path
            ),
            "audit_date": audit_date,
            "audit_week": data.get("audit_week", ""),
            "group_id": data.get("group_id"),
            "trigger_id": data.get("trigger_id"),
            "trigger_name": data.get("trigger_name"),
            "trigger_content": data.get("trigger_content"),
            "total_findings": len(findings),
            "critical": critical,
            "high": high,
            "medium": medium,
            "low": low,
            "status": "fail" if critical > 0 or high > 0 else "pass",
            "findings": enhanced_findings,
        }

        audits = AuditService._load_audit_index()
        audits.append(audit)

        if AuditService._save_audit_index(audits):
            return {"message": "Audit added", "audit_id": audit_id}, HTTPStatus.CREATED
        else:
            return {"error": "Failed to save audit"}, HTTPStatus.INTERNAL_SERVER_ERROR
