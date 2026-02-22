"""Harness settings service — backward-compatible facade.

Delegates to:
  - harness_loader_service: load configs from GitHub repos
  - harness_deploy_service: deploy configs to GitHub
  - layer_detection_service: agent layer auto-detection
"""

from .harness_deploy_service import HarnessDeployService  # noqa: F401
from .harness_loader_service import HarnessLoaderService  # noqa: F401
from .layer_detection_service import LayerDetectionService  # noqa: F401


class HarnessService(HarnessLoaderService, HarnessDeployService, LayerDetectionService):
    """Facade combining all harness sub-services for backward compatibility."""

    pass
