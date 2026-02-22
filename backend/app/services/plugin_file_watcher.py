"""Plugin file watcher — watchdog-based file change detection with debouncing."""

import logging
import threading
from datetime import datetime, timezone
from typing import Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .sync_persistence_service import SyncService

log = logging.getLogger(__name__)


class PluginFileWatcher(FileSystemEventHandler):
    """Watches a plugin directory for file changes and syncs them back to DB.

    Uses debouncing (DEBOUNCE_SECONDS) to batch rapid file events from editors
    that do save-write-rename patterns. Events are accumulated in _pending and
    processed after the debounce window expires.
    """

    DEBOUNCE_SECONDS = 2.0

    def __init__(self, plugin_id: str, plugin_dir: str):
        super().__init__()
        self.plugin_id = plugin_id
        self.plugin_dir = plugin_dir
        self._pending: dict[str, float] = {}
        self._lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None
        self._observer: Optional[Observer] = None

    def on_modified(self, event):
        """Handle file modification events. Ignores directories."""
        if event.is_directory:
            return
        with self._lock:
            self._pending[event.src_path] = datetime.now(timezone.utc).timestamp()
        self._schedule_process()

    def on_created(self, event):
        """Handle file creation events. New files should also be synced."""
        if event.is_directory:
            return
        with self._lock:
            self._pending[event.src_path] = datetime.now(timezone.utc).timestamp()
        self._schedule_process()

    def _schedule_process(self):
        """Cancel existing timer and schedule a new debounced processing run."""
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(self.DEBOUNCE_SECONDS, self._process_pending)
        self._timer.daemon = True
        self._timer.start()

    def _process_pending(self):
        """Process all pending file changes after debounce window."""
        with self._lock:
            paths = dict(self._pending)
            self._pending.clear()

        for file_path in paths:
            # Skip files that SyncService is currently writing (loop prevention)
            if file_path in SyncService._syncing_paths:
                log.debug("Skipping sync-loop path: %s", file_path)
                continue
            try:
                SyncService.sync_file_to_db(file_path, self.plugin_id, self.plugin_dir)
            except Exception:
                log.exception("Error syncing file to DB: %s", file_path)

    def start(self):
        """Start watching the plugin directory for file changes."""
        self._observer = Observer()
        self._observer.schedule(self, self.plugin_dir, recursive=True)
        self._observer.daemon = True
        self._observer.start()
        log.info("File watcher started for plugin %s at %s", self.plugin_id, self.plugin_dir)

    def stop(self):
        """Stop watching and clean up resources."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        log.info("File watcher stopped for plugin %s", self.plugin_id)
