"""Plugin import service — backward-compatible facade.

Delegates to:
  - plugin_parser_service: directory scanning, manifest parsing, content extraction
  - plugin_persistence_service: save parsed plugin data to database
"""

from .plugin_parser_service import PluginParserService  # noqa: F401
from .plugin_persistence_service import PluginPersistenceService  # noqa: F401


class ImportService(PluginParserService, PluginPersistenceService):
    """Facade combining parser + persistence for backward compatibility."""

    pass
