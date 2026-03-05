"""Integration adapter framework.

Defines the IntegrationAdapter base class and adapter registry following
the Adapter pattern (Gamma et al. 1994). Each integration type (Slack, Teams,
JIRA, Linear) implements this interface and self-registers at import time.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple


class IntegrationAdapter(ABC):
    """Base class for all integration adapters."""

    @abstractmethod
    def send_notification(
        self, channel: str, message: str, metadata: Optional[dict] = None
    ) -> bool:
        """Send a notification message. Returns True on success."""
        ...

    @abstractmethod
    def create_ticket(
        self, project_key: str, finding: dict
    ) -> Optional[str]:
        """Create a ticket/issue from a finding. Returns ticket ID/URL or None."""
        ...

    @abstractmethod
    def validate_config(self, config: dict) -> Tuple[bool, Optional[str]]:
        """Validate adapter configuration. Returns (is_valid, error_message)."""
        ...


ADAPTER_REGISTRY: Dict[str, type] = {}


def register_adapter(adapter_type: str, adapter_class: type):
    """Register an adapter class for a given integration type."""
    ADAPTER_REGISTRY[adapter_type] = adapter_class


def get_adapter(adapter_type: str, **kwargs) -> Optional[IntegrationAdapter]:
    """Instantiate and return an adapter for the given type."""
    cls = ADAPTER_REGISTRY.get(adapter_type)
    if cls:
        return cls(**kwargs)
    return None


# Import adapters to trigger self-registration
from . import jira_adapter  # noqa: F401, E402
from . import linear_adapter  # noqa: F401, E402
from . import slack_adapter  # noqa: F401, E402
from . import teams_adapter  # noqa: F401, E402
