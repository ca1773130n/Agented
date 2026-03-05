"""JIRA integration adapter using the jira library.

Creates issues with severity-to-priority mapping for automated ticket creation
from security findings and other bot outputs.
"""

import logging
from typing import Optional, Tuple

from . import IntegrationAdapter, register_adapter

logger = logging.getLogger(__name__)

# Severity to JIRA priority mapping
SEVERITY_TO_PRIORITY = {
    "critical": "Highest",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
    "info": "Lowest",
}


class JiraAdapter(IntegrationAdapter):
    """JIRA integration via the jira Python library."""

    def __init__(
        self, server: str = "", email: str = "", api_token: str = "", **kwargs
    ):
        self.server = server
        self.email = email
        self.api_token = api_token
        self._client = None

    def _get_client(self):
        """Lazy-initialize the JIRA client."""
        if self._client is None:
            from jira import JIRA

            self._client = JIRA(
                server=self.server,
                basic_auth=(self.email, self.api_token),
            )
        return self._client

    def send_notification(
        self, channel: str, message: str, metadata: Optional[dict] = None
    ) -> bool:
        """JIRA does not support notifications. Returns False."""
        return False

    def create_ticket(self, project_key: str, finding: dict) -> Optional[str]:
        """Create a JIRA issue from a finding.

        Args:
            project_key: JIRA project key (e.g., "SEC", "OPS").
            finding: Dict with keys: title, description, severity, source.

        Returns:
            Issue key (e.g., "SEC-123") or None on failure.
        """
        if not self.server or not self.email or not self.api_token:
            logger.error("JIRA adapter: missing server, email, or api_token")
            return None

        severity = finding.get("severity", "medium").lower()
        priority = SEVERITY_TO_PRIORITY.get(severity, "Medium")
        title = finding.get("title", "Agented Finding")
        description = finding.get("description", "")
        source = finding.get("source", "agented")

        issue_dict = {
            "project": {"key": project_key},
            "summary": title,
            "description": description,
            "issuetype": {"name": "Bug"},
            "priority": {"name": priority},
            "labels": ["agented", "automated"],
        }

        try:
            client = self._get_client()
            issue = client.create_issue(fields=issue_dict)
            logger.info("Created JIRA issue %s for finding: %s", issue.key, title)
            return issue.key
        except Exception as e:
            logger.error("JIRA create_issue error: %s", e)
            return None

    def validate_config(self, config: dict) -> Tuple[bool, Optional[str]]:
        """Validate JIRA configuration. Checks server, email, api_token are non-empty."""
        server = config.get("server") or self.server
        email = config.get("email") or self.email
        api_token = config.get("api_token") or self.api_token
        if not server:
            return False, "JIRA server URL is required"
        if not email:
            return False, "JIRA email is required"
        if not api_token:
            return False, "JIRA API token is required"
        return True, None


register_adapter("jira", JiraAdapter)
