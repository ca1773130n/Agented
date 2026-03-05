"""Centralized path and configuration constants for Agented backend.

This module is a pure constants module -- only stdlib imports (os, pathlib) allowed.
Do NOT import from app.services or app.db to avoid circular dependencies.
"""

import os

# --- Paths ---

# PROJECT_ROOT is the agented/ directory (parent of backend/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Default database path is in backend/ folder to avoid creating in project root
_DEFAULT_DB_PATH = os.path.join(PROJECT_ROOT, "backend", "agented.db")
DB_PATH = os.environ.get("AGENTED_DB_PATH", _DEFAULT_DB_PATH)
SYMLINK_DIR = os.path.join(PROJECT_ROOT, "project_links")

# --- Execution ---

EXECUTION_TIMEOUT_DEFAULT = 600  # 10 minutes
EXECUTION_TIMEOUT_MIN = 60  # 1 minute
EXECUTION_TIMEOUT_MAX = 3600  # 1 hour
MAX_RETRY_ATTEMPTS = 5
MAX_RETRY_DELAY = 3600  # 1 hour ceiling for exponential backoff
WEBHOOK_DEDUP_WINDOW = 10  # seconds

# --- SSE ---

SSE_REPLAY_LIMIT = int(os.environ.get("SSE_REPLAY_LIMIT", "500"))
SSE_KEEPALIVE_TIMEOUT = 30  # seconds
STALE_EXECUTION_THRESHOLD = int(os.environ.get("STALE_EXECUTION_THRESHOLD_SECS", "900"))

# --- Process management ---

THREAD_JOIN_TIMEOUT = 10  # seconds
SIGTERM_GRACE_SECONDS = 5
OUTPUT_RING_BUFFER_SIZE = 1000

# --- Budget ---

DEFAULT_5H_TOKEN_LIMIT = 300_000
DEFAULT_WEEKLY_TOKEN_LIMIT = 1_000_000

# --- GitHub ---

CLONE_TIMEOUT = 300  # 5 minutes
GIT_OP_TIMEOUT = 120  # 2 minutes
