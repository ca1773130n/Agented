"""Session usage collector — backward-compatible facade.

Delegates to:
  - session_cost_service: pricing data and cost computation
  - session_collection_service: session file discovery, parsing, DB recording
"""

from .session_collection_service import (
    _SETTINGS_KEY,  # noqa: F401
    SessionCollectionService,  # noqa: F401
)
from .session_cost_service import _PRICING, _compute_cost, _resolve_model_pricing  # noqa: F401


class SessionUsageCollector(SessionCollectionService):
    """Facade for backward compatibility."""

    pass
