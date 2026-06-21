"""Source-adapter layer (phase 25): per-kind competitor fetchers + registry.

Importing this package is the single trigger that registers every adapter:
each adapter module (``github_repo``, and the phase-25 leaves) calls
``registry.register(...)`` at import time, so the side-effect imports below make
``registry.active_kinds()`` complete after one ``import app.services.source_adapters``.
The dispatcher (``CompetitorPollService.poll_due_sources``) imports the package
for exactly this reason — it never has to know the concrete adapter modules.

Public contract lives in ``base`` (``FetchResult`` / ``SourceAdapter`` /
``AdapterBase``) and ``registry`` (``register`` / ``get_adapter`` /
``active_kinds``); both are safe to import without the adapters (no cycle).
"""

from __future__ import annotations

# Side-effect imports: importing each adapter module runs its bottom-line
# ``register(...)`` so the kind is live. Add phase-25 leaf adapters here as they
# land (arxiv, job_board, ...); github_repo is the first.
from app.services.source_adapters import (
    arxiv,  # noqa: F401,E402  (register-on-import)
    base,
    github_repo,  # noqa: F401,E402  (register-on-import)
    job_board,  # noqa: F401,E402  (register-on-import)
    registry,
)

__all__ = ["base", "registry"]
