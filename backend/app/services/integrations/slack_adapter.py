"""Slack integration adapter using slack-sdk WebClient.

Sends notifications via chat.postMessage with Block Kit formatting.
Includes HMAC-SHA256 signature verification for inbound slash commands.
"""

import hashlib
import hmac
import logging
import time
from typing import Optional, Tuple

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from . import IntegrationAdapter, register_adapter

logger = logging.getLogger(__name__)


class SlackAdapter(IntegrationAdapter):
    """Slack integration via slack-sdk WebClient."""

    def __init__(self, token: str = "", **kwargs):
        self.token = token
        self._client = WebClient(token=token) if token else None

    def send_notification(
        self, channel: str, message: str, metadata: Optional[dict] = None
    ) -> bool:
        """Send a Block Kit formatted notification to a Slack channel."""
        if not self._client:
            logger.error("Slack adapter: no token configured")
            return False

        metadata = metadata or {}
        status = metadata.get("status", "completed")
        bot_name = metadata.get("bot_name", "Agented")
        duration = metadata.get("duration", "N/A")
        emoji = ":white_check_mark:" if status == "success" else ":x:"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{bot_name} Execution {status.title()}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Status:* {emoji} {status}"},
                    {"type": "mrkdwn", "text": f"*Duration:* {duration}"},
                ],
            },
        ]

        if message:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": message[:3000]},
                }
            )

        try:
            self._client.chat_postMessage(
                channel=channel,
                text=message[:500],
                blocks=blocks,
            )
            return True
        except SlackApiError as e:
            logger.error("Slack API error: %s", e.response.get("error", str(e)))
            return False
        except Exception as e:
            logger.error("Slack send error: %s", e)
            return False

    def create_ticket(self, project_key: str, finding: dict) -> Optional[str]:
        """Slack does not create tickets. Returns None."""
        return None

    def validate_config(self, config: dict) -> Tuple[bool, Optional[str]]:
        """Validate Slack configuration. Checks token is non-empty."""
        token = config.get("token") or self.token
        if not token:
            return False, "Slack token is required"
        return True, None

    @classmethod
    def verify_slack_signature(
        cls,
        signing_secret: str,
        timestamp: str,
        body: str,
        signature: str,
    ) -> bool:
        """Verify Slack request signature using HMAC-SHA256.

        Per https://api.slack.com/authentication/verifying-requests-from-slack:
        1. Check timestamp is within 5 minutes (replay protection)
        2. Compute HMAC-SHA256 of 'v0:{timestamp}:{body}'
        3. Compare with constant-time comparison

        Args:
            signing_secret: Slack app signing secret.
            timestamp: X-Slack-Request-Timestamp header value.
            body: Raw request body as string.
            signature: X-Slack-Signature header value.

        Returns:
            True if signature is valid.
        """
        try:
            ts = int(timestamp)
        except (ValueError, TypeError):
            return False

        # Replay protection: reject requests older than 5 minutes
        if abs(time.time() - ts) > 300:
            return False

        sig_basestring = f"v0:{timestamp}:{body}"
        computed = (
            "v0="
            + hmac.new(
                signing_secret.encode(),
                sig_basestring.encode(),
                hashlib.sha256,
            ).hexdigest()
        )

        return hmac.compare_digest(computed, signature)


register_adapter("slack", SlackAdapter)
