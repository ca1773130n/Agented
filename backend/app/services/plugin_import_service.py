"""Plugin import service — backward-compatible facade.

Delegates to:
  - plugin_parser_service: directory scanning, manifest parsing, content extraction
  - plugin_persistence_service: save parsed plugin data to database
"""
import logging

from .plugin_parser_service import PluginParserService  # noqa: F401
from .plugin_persistence_service import PluginPersistenceService  # noqa: F401

logger = logging.getLogger(__name__)


class ImportService(PluginParserService, PluginPersistenceService):
    """Facade combining parser + persistence for backward compatibility."""

    pass
