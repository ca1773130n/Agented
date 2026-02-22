"""Skills management service — backward-compatible facade.

Delegates to:
  - skill_discovery_service: project/global/plugin skill discovery
  - skill_testing_service: test execution + SSE streaming
  - skill_harness_service: user skills CRUD, harness integration, agent export
  - skill_marketplace_service: marketplace load and deploy operations
"""

from .skill_discovery_service import SkillDiscoveryService, get_playground_working_dir  # noqa: F401
from .skill_harness_service import SkillHarnessService  # noqa: F401
from .skill_testing_service import SkillTestingService  # noqa: F401


class SkillsService(SkillDiscoveryService, SkillTestingService, SkillHarnessService):
    """Facade combining all skill sub-services for backward compatibility."""

    pass
