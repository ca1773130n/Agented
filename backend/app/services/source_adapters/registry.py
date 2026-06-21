"""Kind -> adapter registry (phase 25).

A flat module-level map from ``competitor_source.kind`` to the ``SourceAdapter``
that polls it. Adapters self-register at import time
(``registry.register(GitHubRepoAdapter())`` at the bottom of ``github_repo``),
and the dispatcher (``CompetitorPollService``) imports the ``source_adapters``
subpackage so every adapter module runs and registers before the first poll.

Registration is lazy by design — the registry module must NOT import the adapter
modules itself (an adapter imports ``base``, which would create a cycle if the
registry pulled the adapters back in). This mirrors P1's in-function
``from app.services.signal_summarizer_service import ...`` pattern at
``github_monitor_service.py:319``: the importer (the dispatcher) is what triggers
registration, not the registry.
"""

from __future__ import annotations

from app.services.source_adapters.base import SourceAdapter

# kind -> adapter. Populated at import time by each adapter module's bottom-line
# ``register(...)`` call (e.g. ``github_repo`` registers ``github_repo``).
_ADAPTERS: dict[str, SourceAdapter] = {}


def register(adapter: SourceAdapter) -> None:
    """Register ``adapter`` under its ``kind`` (last registration wins).

    Called once per adapter module at import time. Idempotent for re-imports —
    re-registering the same kind simply replaces the entry.
    """
    _ADAPTERS[adapter.kind] = adapter


def get_adapter(kind: str) -> SourceAdapter | None:
    """Return the adapter for ``kind``, or ``None`` if no adapter handles it.

    ``None`` is the dispatcher's signal to skip-and-log a source whose ``kind``
    has no registered fetcher (a kind added to a row but not yet wired).
    """
    return _ADAPTERS.get(kind)


def active_kinds() -> list[str]:
    """Return the sorted list of registered kinds (the kinds the poller serves)."""
    return sorted(_ADAPTERS)
