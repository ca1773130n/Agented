"""Linear integration adapter using GraphQL API via httpx.

Creates issues via the Linear GraphQL mutation API. Uses raw httpx instead of
a Python SDK as recommended in 11-RESEARCH.md.
"""

import logging
from typing import Optional, Tuple

import httpx

from . import IntegrationAdapter, register_adapter

logger = logging.getLogger(__name__)

LINEAR_API_URL = "https://api.linear.app/graphql"

# Severity to Linear priority mapping (1=Urgent, 2=High, 3=Medium, 4=Low, 0=None)
SEVERITY_TO_PRIORITY = {
    "critical": 1,
    "high": 2,
    "medium": 3,
    "low": 4,
    "info": 0,
}

CREATE_ISSUE_MUTATION = """
mutation IssueCreate($teamId: String!, $title: String!, $description: String, $priority: Int) {
  issueCreate(input: {
    teamId: $teamId,
    title: $title,
    description: $description,
    priority: $priority
  }) {
    success
    issue {
      id
      identifier
      url
    }
  }
}
"""


class LinearAdapter(IntegrationAdapter):
    """Linear integration via GraphQL mutations."""

    def __init__(self, api_key: str = "", **kwargs):
        self.api_key = api_key

    def send_notification(
        self, channel: str, message: str, metadata: Optional[dict] = None
    ) -> bool:
        """Linear does not support notifications. Returns False."""
        return False

    def create_ticket(self, project_key: str, finding: dict) -> Optional[str]:
        """Create a Linear issue from a finding.

        Args:
            project_key: Linear team ID.
            finding: Dict with keys: title, description, severity.

        Returns:
            Issue identifier (e.g., "ENG-123") or None on failure.
        """
        if not self.api_key:
            logger.error("Linear adapter: no API key configured")
            return None

        severity = finding.get("severity", "medium").lower()
        priority = SEVERITY_TO_PRIORITY.get(severity, 3)
        title = finding.get("title", "Agented Finding")
        description = finding.get("description", "")

        variables = {
            "teamId": project_key,
            "title": title,
            "description": description,
            "priority": priority,
        }

        try:
            response = httpx.post(
                LINEAR_API_URL,
                json={"query": CREATE_ISSUE_MUTATION, "variables": variables},
                headers={
                    "Authorization": self.api_key,
                    "Content-Type": "application/json",
                },
                timeout=10.0,
            )

            if response.status_code != 200:
                logger.error("Linear API error: %s %s", response.status_code, response.text[:200])
                return None

            data = response.json()
            issue_data = data.get("data", {}).get("issueCreate", {})
            if issue_data.get("success"):
                identifier = issue_data.get("issue", {}).get("identifier", "")
                logger.info("Created Linear issue %s for: %s", identifier, title)
                return identifier
            else:
                errors = data.get("errors", [])
                logger.error("Linear issueCreate failed: %s", errors)
                return None
        except httpx.TimeoutException:
            logger.error("Linear API timeout after 10s")
            return None
        except Exception as e:
            logger.error("Linear create_ticket error: %s", e)
            return None

    def validate_config(self, config: dict) -> Tuple[bool, Optional[str]]:
        """Validate Linear configuration. Checks api_key is non-empty."""
        api_key = config.get("api_key") or self.api_key
        if not api_key:
            return False, "Linear API key is required"
        return True, None


register_adapter("linear", LinearAdapter)
