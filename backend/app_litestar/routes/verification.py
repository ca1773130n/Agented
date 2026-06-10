"""Litestar routes for verification records (Harness-1 Phase 2, P5)."""

from __future__ import annotations

from typing import Any, Optional

from litestar import Router, get, post
from msgspec import Struct

from app.db import verification_records
from app.services.verification_service import VerificationService


class VerificationCreate(Struct):
    claim: str
    status: str = "pending"
    evidence_ref: Optional[str] = None


@get("/api/executions/{execution_id:str}/verifications", sync_to_thread=True)
def list_verifications(execution_id: str) -> list[dict[str, Any]]:
    return verification_records.list_verifications(execution_id)


@post("/api/executions/{execution_id:str}/verifications", status_code=201, sync_to_thread=True)
def create_verification(execution_id: str, data: VerificationCreate) -> dict[str, Any]:
    rid = VerificationService.record(
        execution_id, data.claim, status=data.status, evidence_ref=data.evidence_ref
    )
    return {"id": rid, "execution_id": execution_id, "claim": data.claim, "status": data.status}


verification_router = Router(
    path="/",
    route_handlers=[list_verifications, create_verification],
)
