"""Resolve a GENERAL-chat backend from the operator's CONFIGURED accounts.

General-chat features (Sketch ideation, competitor-intel summarize/strategize)
must NOT hard-require a backend the operator hasn't added — routing to an
unconfigured kind falls back to a stale/expired on-disk cred and 401s with a
cryptic ``Google OAuth`` error. Pick the first backend the operator actually
configured, ordered by general-chat suitability, instead.
"""

import logging

logger = logging.getLogger(__name__)

# Antigravity (``gemini``) and Codex both handle open-ended / non-coding prompts;
# Claude Code (``claude``) refuses them, so it's last-resort (better than erroring).
GENERAL_CHAT_BACKEND_PRIORITY = (
    "gemini",
    "codex",
    "openrouter",
    "openai_compat",
    "opencode",
    "claude",
)


def resolve_general_chat_backend(default: str = "gemini", preferred: str | None = None) -> str:
    """Resolve a general-chat backend the operator has actually configured.

    ``preferred`` (e.g. an explicit config value) wins **iff it has configured
    accounts** — otherwise it's a stale default for a backend they never added, so
    fall through. Then the first CONFIGURED backend by general-chat priority;
    finally ``default`` if the lookup fails or the operator has added none.
    """
    try:
        from app.db.backends import get_backend_accounts

        if preferred and get_backend_accounts(f"backend-{preferred}"):
            return preferred
        for kind in GENERAL_CHAT_BACKEND_PRIORITY:
            if get_backend_accounts(f"backend-{kind}"):
                return kind
    except Exception:
        logger.debug("general-chat backend resolve failed; using %s", default, exc_info=True)
    return default
