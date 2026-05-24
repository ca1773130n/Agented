"""Retention policy service — validation + CRUD facade.

PR-R (wave 83): this is the *real* data-retention feature, replacing the
501 stubs at ``/admin/retention`` shipped in PR-J3b.

Scope of this PR:

* Persist retention policies (CRUD).
* Validate categories + retention windows.
* Provide ``enqueue_cleanup`` which *acknowledges* a cleanup request but
  does **not** perform destructive deletes against any other table. The
  actual enforcement worker is a follow-up PR — the goal here is to give
  the frontend a stable contract so operators can author policies today
  and have them take effect when the worker ships.
"""

from __future__ import annotations

import logging
from typing import Any

from litestar.exceptions import ClientException

from app.db import retention_policies as policies_db

logger = logging.getLogger(__name__)


# Categories the operator console knows how to render. Keep this list in
# lockstep with ``DataCategory`` in
# ``frontend/src/views/DataRetentionPoliciesPage.vue``.
KNOWN_CATEGORIES: frozenset[str] = frozenset(
    {
        "execution_logs",
        "execution_outputs",
        "bot_memory",
        "audit_logs",
        "token_metrics",
    }
)


class RetentionService:
    """Static facade around ``app.db.retention_policies`` with validation."""

    @staticmethod
    def list_policies() -> list[dict[str, Any]]:
        """Return all persisted retention policies (newest first)."""
        return policies_db.list_policies()

    @staticmethod
    def get_policy(policy_id: str) -> dict[str, Any] | None:
        """Return a single policy by id, or ``None`` if missing."""
        return policies_db.get_policy(policy_id)

    @staticmethod
    def create_policy(payload: dict[str, Any]) -> dict[str, Any]:
        """Validate ``payload`` and insert a new retention policy.

        Required: ``category`` (must be in :data:`KNOWN_CATEGORIES`).
        Optional: ``scope``, ``scope_name``, ``retention_days`` (>=1),
        ``delete_on_expiry``, ``archive_on_expiry``, ``estimated_size_gb``.

        Raises :class:`ClientException` on validation failure.
        Returns the freshly-inserted policy row (as a dict).
        """
        if not isinstance(payload, dict):  # defensive — Litestar gives dict already
            raise ClientException(detail="JSON object body required")

        category = payload.get("category")
        if not category or not isinstance(category, str):
            raise ClientException(detail="category is required")
        if category not in KNOWN_CATEGORIES:
            raise ClientException(
                detail=(
                    f"Unknown category {category!r}. Expected one of: {sorted(KNOWN_CATEGORIES)}"
                )
            )

        retention_days = payload.get("retention_days", 90)
        try:
            retention_days_int = int(retention_days)
        except (TypeError, ValueError) as exc:
            raise ClientException(detail="retention_days must be an integer") from exc
        if retention_days_int < 1:
            raise ClientException(detail="retention_days must be >= 1")

        scope = payload.get("scope") or "global"
        scope_name = payload.get("scope_name") or "All"
        delete_on_expiry = bool(payload.get("delete_on_expiry", True))
        archive_on_expiry = bool(payload.get("archive_on_expiry", False))

        estimated_size_gb_raw = payload.get("estimated_size_gb", 0)
        try:
            estimated_size_gb = float(estimated_size_gb_raw)
        except (TypeError, ValueError) as exc:
            raise ClientException(detail="estimated_size_gb must be numeric") from exc

        policy_id = policies_db.create_policy(
            category=category,
            scope=str(scope),
            scope_name=str(scope_name),
            retention_days=retention_days_int,
            delete_on_expiry=delete_on_expiry,
            archive_on_expiry=archive_on_expiry,
            estimated_size_gb=estimated_size_gb,
        )
        created = policies_db.get_policy(policy_id)
        # ``get_policy`` is None only if a concurrent delete raced us, which is
        # exotic enough to surface as a server error rather than swallow.
        if created is None:  # pragma: no cover — defensive
            raise RuntimeError(f"Policy {policy_id} vanished after insert")
        return created

    @staticmethod
    def set_enabled(policy_id: str, enabled: bool) -> bool:
        """Toggle the enabled flag. Returns True if the row existed."""
        return policies_db.set_enabled(policy_id, bool(enabled))

    @staticmethod
    def delete_policy(policy_id: str) -> bool:
        """Delete a retention policy. Returns True if the row existed."""
        return policies_db.delete_policy(policy_id)

    @staticmethod
    def enqueue_cleanup() -> dict[str, Any]:
        """Acknowledge a cleanup request without performing any deletes.

        Returns a message describing what *would* happen and the number
        of currently-active policies. Destructive enforcement is the
        scope of the follow-up PR; this handler is a no-op against
        every table other than ``retention_policies`` itself (which is
        likewise untouched).
        """
        active = policies_db.count_policies(enabled_only=True)
        message = (
            f"Cleanup queued — destructive enforcement ships in a follow-up. "
            f"{active} {'policy' if active == 1 else 'policies'} currently active."
        )
        logger.info(
            "retention_service.enqueue_cleanup invoked — no-op (active=%d). "
            "Destructive enforcement is deferred to the next PR.",
            active,
        )
        return {"message": message, "active_policies": active}
