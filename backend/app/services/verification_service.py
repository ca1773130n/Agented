"""Write facade for verification records (Harness-1 Phase 2, P5).

The deliverable is the write API. Auto-wiring a specific bot
(bot-security / bot-pr-review) to populate records is a later integration.
"""

from __future__ import annotations

from typing import Optional

from ..db import verification_records


class VerificationService:
    @staticmethod
    def record(
        execution_id: str,
        claim: str,
        status: str = "pending",
        evidence_ref: Optional[str] = None,
    ) -> int:
        """Record a verification claim against an execution. Returns row id."""
        return verification_records.record_verification(
            execution_id, claim, status=status, evidence_ref=evidence_ref
        )
