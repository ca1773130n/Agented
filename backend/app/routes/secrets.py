"""Secrets vault API endpoints.

Provides CRUD operations for encrypted secrets. Secret values are NEVER returned
in list or detail responses -- use the POST /reveal endpoint to decrypt.
"""

from http import HTTPStatus

from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.models.common import error_response
from app.models.secret import SecretCreate, SecretUpdate

from ..services.secret_vault_service import SecretVaultService

tag = Tag(name="secrets", description="Encrypted secrets vault management")
secrets_bp = APIBlueprint("secrets", __name__, url_prefix="/admin/secrets", abp_tags=[tag])


class SecretPath(BaseModel):
    """Path parameter for secret ID."""

    secret_id: str = Field(..., description="Secret ID")


def _check_vault():
    """Return an error response if the vault is not configured, or None if OK."""
    if not SecretVaultService.is_configured():
        return {
            "error": "Secrets vault not configured",
            "detail": "Set AGENTED_VAULT_KEYS environment variable to enable the secrets vault.",
        }, HTTPStatus.SERVICE_UNAVAILABLE
    return None


@secrets_bp.get("/status")
def vault_status():
    """Get vault configuration status."""
    configured = SecretVaultService.is_configured()
    count = 0
    if configured:
        try:
            from app.db.secrets import count_secrets

            count = count_secrets()
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning("Failed to count secrets: %s", e)
    return {"configured": configured, "secret_count": count}, HTTPStatus.OK


@secrets_bp.post("/")
def create_secret(body: SecretCreate):
    """Create a new encrypted secret."""
    err = _check_vault()
    if err:
        return err

    try:
        secret_id = SecretVaultService.create_secret(
            name=body.name, value=body.value, description=body.description, scope=body.scope
        )
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            return error_response(
                "CONFLICT", f"Secret with name '{body.name}' already exists", HTTPStatus.CONFLICT
            )
        return error_response("INTERNAL_SERVER_ERROR", str(e), HTTPStatus.INTERNAL_SERVER_ERROR)

    from app.db.secrets import get_secret

    secret = get_secret(secret_id)
    return _secret_metadata(secret), HTTPStatus.CREATED


@secrets_bp.get("/")
def list_secrets():
    """List all secrets (metadata only, NEVER values)."""
    err = _check_vault()
    if err:
        return err

    from app.db.secrets import list_secrets as db_list_secrets

    secrets = db_list_secrets()
    return {"secrets": secrets}, HTTPStatus.OK


@secrets_bp.get("/<secret_id>")
def get_secret_detail(path: SecretPath):
    """Get secret metadata (NOT the decrypted value)."""
    err = _check_vault()
    if err:
        return err

    from app.db.secrets import get_secret

    secret = get_secret(path.secret_id)
    if not secret:
        return error_response("NOT_FOUND", "Secret not found", HTTPStatus.NOT_FOUND)

    return _secret_metadata(secret), HTTPStatus.OK


@secrets_bp.post("/<secret_id>/reveal")
def reveal_secret(path: SecretPath):
    """Decrypt and return a secret's value (audit-logged).

    Uses POST instead of GET to prevent browser/proxy caching of secrets.
    """
    err = _check_vault()
    if err:
        return err

    value = SecretVaultService.get_secret_value(path.secret_id, accessor="api")
    if value is None:
        return error_response("NOT_FOUND", "Secret not found", HTTPStatus.NOT_FOUND)

    from app.db.secrets import get_secret

    secret = get_secret(path.secret_id)
    return {
        "id": secret["id"],
        "name": secret["name"],
        "value": value,
    }, HTTPStatus.OK


@secrets_bp.put("/<secret_id>")
def update_secret(path: SecretPath, body: SecretUpdate):
    """Update a secret's value and/or description."""
    err = _check_vault()
    if err:
        return err

    if body.value is None and body.description is None:
        return error_response(
            "BAD_REQUEST",
            "At least one of value or description is required",
            HTTPStatus.BAD_REQUEST,
        )

    updated = SecretVaultService.update_secret(
        secret_id=path.secret_id, value=body.value, description=body.description
    )
    if not updated:
        return error_response("NOT_FOUND", "Secret not found", HTTPStatus.NOT_FOUND)

    from app.db.secrets import get_secret

    secret = get_secret(path.secret_id)
    return _secret_metadata(secret), HTTPStatus.OK


@secrets_bp.delete("/<secret_id>")
def delete_secret(path: SecretPath):
    """Delete a secret."""
    err = _check_vault()
    if err:
        return err

    deleted = SecretVaultService.delete_secret(path.secret_id)
    if not deleted:
        return error_response("NOT_FOUND", "Secret not found", HTTPStatus.NOT_FOUND)

    return {"message": "Secret deleted"}, HTTPStatus.OK


def _secret_metadata(secret: dict) -> dict:
    """Extract metadata from a secret dict, excluding encrypted_value."""
    return {
        "id": secret.get("id"),
        "name": secret.get("name"),
        "description": secret.get("description", ""),
        "scope": secret.get("scope", "global"),
        "created_by": secret.get("created_by", "system"),
        "created_at": secret.get("created_at"),
        "updated_at": secret.get("updated_at"),
        "last_accessed_at": secret.get("last_accessed_at"),
    }
