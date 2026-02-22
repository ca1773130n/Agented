"""Plugin sync service — backward-compatible facade.

Delegates to:
  - plugin_file_watcher: watchdog file watching + debouncing
  - sync_persistence_service: DB-to-disk and disk-to-DB sync logic
"""

from .plugin_file_watcher import PluginFileWatcher  # noqa: F401
from .sync_persistence_service import SyncService  # noqa: F401
