"""Microsoft Teams integration adapter via Incoming Webhooks.

Sends Adaptive Card messages to a Teams channel via webhook URL POST.
"""

import logging
from typing import Optional, Tuple

import httpx

from . import IntegrationAdapter, register_adapter

logger = logging.getLogger(__name__)


class TeamsAdapter(IntegrationAdapter):
    """Teams integration via Incoming Webhook URL."""

    def __init__(self, webhook_url: str = "", **kwargs):
        self.webhook_url = webhook_url

    def send_notification(
        self, channel: str, message: str, metadata: Optional[dict] = None
    ) -> bool:
        """POST a MessageCard JSON to the Teams webhook URL.

        The `channel` parameter is ignored since the webhook URL is pre-configured
        for a specific channel.
        """
        if not self.webhook_url:
            logger.error("Teams adapter: no webhook URL configured")
            return False

        metadata = metadata or {}
        status = metadata.get("status", "completed")
        bot_name = metadata.get("bot_name", "Agented")
        duration = metadata.get("duration", "N/A")
        color = "00FF00" if status == "success" else "FF0000"

        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": color,
            "summary": f"{bot_name} Execution {status.title()}",
            "sections": [
                {
                    "activityTitle": f"{bot_name} Execution {status.title()}",
                    "facts": [
                        {"name": "Status", "value": status},
                        {"name": "Duration", "value": str(duration)},
                    ],
                    "text": message[:3000] if message else "",
                    "markdown": True,
                }
            ],
        }

        try:
            response = httpx.post(
                self.webhook_url,
                json=card,
                timeout=10.0,
            )
            if response.status_code == 200:
                return True
            logger.error("Teams webhook error: %s %s", response.status_code, response.text[:200])
            return False
        except httpx.TimeoutException:
            logger.error("Teams webhook timeout after 10s")
            return False
        except Exception as e:
            logger.error("Teams send error: %s", e)
            return False

    def create_ticket(self, project_key: str, finding: dict) -> Optional[str]:
        """Teams does not create tickets. Returns None."""
        return None

    def validate_config(self, config: dict) -> Tuple[bool, Optional[str]]:
        """Validate Teams configuration. Checks webhook_url is non-empty and HTTPS."""
        url = config.get("webhook_url") or self.webhook_url
        if not url:
            return False, "Teams webhook URL is required"
        if not url.startswith("https://"):
            return False, "Teams webhook URL must use HTTPS"
        return True, None


register_adapter("teams", TeamsAdapter)
