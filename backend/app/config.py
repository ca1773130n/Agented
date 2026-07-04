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

# Postgres opt-in (REQ-38). Empty string = SQLite (the zero-config default):
# with DATABASE_URL unset the sqlite3 path is byte-for-byte unchanged. When it
# starts with postgres://|postgresql:// the DB layer selects psycopg 3 instead.
DATABASE_URL = os.environ.get("DATABASE_URL", "")

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

# --- Autoresearch kernel ---

AUTORESEARCH_KERNEL_ENABLED = os.environ.get("AUTORESEARCH_KERNEL_ENABLED", "0") == "1"

# --- LLM key isolation (REQ-41) ---
#
# AGENTED_SERVER_NO_LLM_KEYS: when set truthy, the server refuses to read raw
# LLM *inference* keys (e.g. ANTHROPIC_API_KEY) from its OWN process
# environment. Credentials must instead flow in per-request via explicit
# ``api_key`` arguments sourced from the ai-accounts sidecar. This isolates a
# shared or "poison" server-wide key from silently backing every user's
# inference. Default (unset) = read env keys as before, byte-for-byte
# unchanged. The flag is read dynamically (not cached at import) so operators
# and tests can toggle it at runtime.

_TRUTHY_FLAG_VALUES = {"1", "true", "yes", "on"}

# Env var names that carry raw LLM *inference* credentials. When the isolation
# flag is on, these are stripped from any subprocess environment that would
# otherwise be inherited from the server's own os.environ — so a key baked into
# the deploy cannot back user inference via a harness/CLI child. Per-request
# credentials layered on top by callers (sourced from the ai-accounts sidecar)
# are unaffected. Sidecar/self-auth and sandbox-provider keys (AI_ACCOUNTS_API_KEY,
# AGENTED_API_KEY, E2B_API_KEY) are intentionally NOT here — they are not
# inference keys and are legitimately read from the server env.
LLM_INFERENCE_KEY_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "OPENROUTER_API_KEY",
    "MISTRAL_API_KEY",
    "GROQ_API_KEY",
    "DEEPSEEK_API_KEY",
    "XAI_API_KEY",
    "COHERE_API_KEY",
    "PERPLEXITY_API_KEY",
)


def server_no_llm_keys() -> bool:
    """Return True when the server must ignore raw LLM keys from its own env."""
    return os.environ.get("AGENTED_SERVER_NO_LLM_KEYS", "").strip().lower() in _TRUTHY_FLAG_VALUES


def subprocess_env(base: dict | None = None) -> dict | None:
    """Environment dict for a harness/CLI subprocess, honoring key isolation.

    This is the 4th-leak guard (REQ-41): the three ``env_llm_key`` sites only
    cover the in-process paths, but a subprocess that inherits the full
    ``os.environ`` re-exposes a server-baked ``ANTHROPIC_API_KEY`` to the child.

    - Flag OFF → return ``base`` unchanged (default ``None`` ⇒ the child
      inherits ``os.environ`` exactly as before, byte-for-byte).
    - Flag ON → a concrete copy of ``base`` (or ``os.environ`` when ``base`` is
      ``None``) with every :data:`LLM_INFERENCE_KEY_ENV_VARS` entry removed, so
      no server-process inference key reaches the subprocess.
    """
    if not server_no_llm_keys():
        return base
    source = base if base is not None else os.environ
    return {k: v for k, v in source.items() if k not in LLM_INFERENCE_KEY_ENV_VARS}


def scrub_env_inplace(environ) -> None:
    """Pop LLM inference keys from a mutable ``environ`` mapping in place.

    The pipe path can swap to an explicit scrubbed ``env`` dict via
    :func:`subprocess_env`, but the fork/exec (PTY) path has no such hook — the
    forked child inherits the parent's ``os.environ`` directly and there is no
    ``env=`` argument to interpose. Call this in the child *after* fork and
    *before* ``execvp`` to strip every :data:`LLM_INFERENCE_KEY_ENV_VARS` entry
    the child inherited, so a server-baked ``ANTHROPIC_API_KEY`` cannot reach it.

    No-op when ``AGENTED_SERVER_NO_LLM_KEYS`` is unset — the mapping is left
    byte-for-byte unchanged (default behavior).
    """
    if not server_no_llm_keys():
        return
    for name in LLM_INFERENCE_KEY_ENV_VARS:
        environ.pop(name, None)


def env_llm_key(name: str, default: str = "") -> str:
    """Read an LLM inference key from the environment, honoring the isolation flag.

    When AGENTED_SERVER_NO_LLM_KEYS is set, the server-side environment fallback
    is suppressed and ``default`` is returned instead — so a key baked into the
    server process cannot back user inference. Explicit ``api_key`` arguments
    passed by callers are unaffected; they never route through here.
    """
    if server_no_llm_keys():
        return default
    return os.environ.get(name, default)
