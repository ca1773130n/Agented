"""Secrets vault API endpoints.

Provides CRUD operations for encrypted secrets. Secret values are NEVER returned
in list or detail responses -- use the POST /reveal endpoint to decrypt.
"""

from http import HTTPStatus

from flask import request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

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
        except Exception:
            pass
    return {"configured": configured, "secret_count": count}, HTTPStatus.OK


@secrets_bp.post("/")
def create_secret():
    """Create a new encrypted secret."""
    err = _check_vault()
    if err:
        return err

    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    name = data.get("name")
    value = data.get("value")
    if not name or not value:
        return {"error": "name and value are required"}, HTTPStatus.BAD_REQUEST

    description = data.get("description", "")
    scope = data.get("scope", "global")

    try:
        secret_id = SecretVaultService.create_secret(
            name=name, value=value, description=description, scope=scope
        )
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            return {"error": f"Secret with name '{name}' already exists"}, HTTPStatus.CONFLICT
        return {"error": str(e)}, HTTPStatus.INTERNAL_SERVER_ERROR

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
        return {"error": "Secret not found"}, HTTPStatus.NOT_FOUND

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
        return {"error": "Secret not found"}, HTTPStatus.NOT_FOUND

    from app.db.secrets import get_secret
    secret = get_secret(path.secret_id)
    return {
        "id": secret["id"],
        "name": secret["name"],
        "value": value,
    }, HTTPStatus.OK


@secrets_bp.put("/<secret_id>")
def update_secret(path: SecretPath):
    """Update a secret's value and/or description."""
    err = _check_vault()
    if err:
        return err

    data = request.get_json()
    if not data:
        return {"error": "JSON body required"}, HTTPStatus.BAD_REQUEST

    value = data.get("value")
    description = data.get("description")

    if value is None and description is None:
        return {"error": "At least one of value or description is required"}, HTTPStatus.BAD_REQUEST

    updated = SecretVaultService.update_secret(
        secret_id=path.secret_id, value=value, description=description
    )
    if not updated:
        return {"error": "Secret not found"}, HTTPStatus.NOT_FOUND

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
        return {"error": "Secret not found"}, HTTPStatus.NOT_FOUND

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
