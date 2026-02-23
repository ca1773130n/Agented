"""Centralized path constants for Agented backend."""

import os

# PROJECT_ROOT is the agented/ directory (parent of backend/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Default database path is in backend/ folder to avoid creating in project root
_DEFAULT_DB_PATH = os.path.join(PROJECT_ROOT, "backend", "agented.db")
DB_PATH = os.environ.get("AGENTED_DB_PATH", _DEFAULT_DB_PATH)
SYMLINK_DIR = os.path.join(PROJECT_ROOT, "project_links")
