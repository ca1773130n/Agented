"""Encrypted secrets vault service using Fernet symmetric encryption.

Uses MultiFernet for key rotation support. The encryption key is read from the
AGENTED_VAULT_KEYS environment variable (comma-separated Fernet keys). The first
key is the primary (used for new encryptions); additional keys are used for
decrypting secrets encrypted with older keys.

NEVER stores the encryption key in the database.
NEVER logs plaintext secret values.
"""

import logging
import os
from typing import Optional

from cryptography.fernet import Fernet, MultiFernet

from app.db import secrets as db_secrets
from app.services.audit_log_service import AuditLogService

logger = logging.getLogger(__name__)


class SecretVaultService:
    """Fernet-based encrypted secrets vault with audit logging on every access."""

    _fernet: Optional[MultiFernet] = None

    @classmethod
    def _get_fernet(cls) -> MultiFernet:
        """Lazily initialize and return the MultiFernet instance.

        Reads AGENTED_VAULT_KEYS env var (comma-separated Fernet keys).
        First key is the primary for new encryptions.
        """
        if cls._fernet is not None:
            return cls._fernet

        keys_str = os.environ.get("AGENTED_VAULT_KEYS")
        if not keys_str:
            raise RuntimeError(
                "AGENTED_VAULT_KEYS not configured. "
                "Generate a key with: python -c "
                '"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            )

        fernet_keys = [
            Fernet(k.strip().encode() if isinstance(k.strip(), str) else k.strip())
            for k in keys_str.split(",")
            if k.strip()
        ]
        if not fernet_keys:
            raise RuntimeError("AGENTED_VAULT_KEYS contains no valid keys")

        cls._fernet = MultiFernet(fernet_keys)
        return cls._fernet

    @classmethod
    def reset(cls) -> None:
        """Reset the cached Fernet instance (useful for testing key rotation)."""
        cls._fernet = None

    @classmethod
    def is_configured(cls) -> bool:
        """Check if the vault encryption keys are configured."""
        return bool(os.environ.get("AGENTED_VAULT_KEYS"))

    @classmethod
    def encrypt(cls, plaintext: str) -> str:
        """Encrypt a plaintext string. Returns base64-encoded ciphertext."""
        fernet = cls._get_fernet()
        return fernet.encrypt(plaintext.encode()).decode()

    @classmethod
    def decrypt(cls, ciphertext: str, purpose: str = "", accessor: str = "") -> str:
        """Decrypt a ciphertext string. Audit-logs the access.

        Args:
            ciphertext: Base64-encoded Fernet ciphertext.
            purpose: Description of why the secret is being accessed (for audit).
            accessor: Identity of who/what is accessing the secret.

        Returns:
            The decrypted plaintext string.
        """
        AuditLogService.log(
            action="secret.access",
            entity_type="secret",
            entity_id=purpose,
            outcome="accessed",
            details={"accessor": accessor},
        )
        fernet = cls._get_fernet()
        return fernet.decrypt(ciphertext.encode()).decode()

    @classmethod
    def create_secret(
        cls,
        name: str,
        value: str,
        description: str = "",
        scope: str = "global",
        created_by: str = "system",
    ) -> str:
        """Create a new secret. Encrypts the value before storage.

        Returns the secret ID.
        """
        encrypted = cls.encrypt(value)
        secret_id = db_secrets.create_secret(
            name=name,
            encrypted_value=encrypted,
            description=description,
            scope=scope,
            created_by=created_by,
        )
        AuditLogService.log(
            action="secret.create",
            entity_type="secret",
            entity_id=secret_id,
            outcome="created",
            details={"name": name, "scope": scope, "created_by": created_by},
        )
        return secret_id

    @classmethod
    def update_secret(
        cls,
        secret_id: str,
        value: Optional[str] = None,
        description: Optional[str] = None,
        actor: str = "system",
    ) -> bool:
        """Update a secret's value and/or description with audit trail.

        Uses AuditLogService.log_field_changes() for metadata diffs.
        """
        existing = db_secrets.get_secret(secret_id)
        if not existing:
            return False

        old_metadata = {
            "description": existing.get("description", ""),
            "scope": existing.get("scope", "global"),
        }

        encrypted_value = None
        if value is not None:
            encrypted_value = cls.encrypt(value)

        new_description = description if description is not None else None

        updated = db_secrets.update_secret(
            secret_id=secret_id,
            encrypted_value=encrypted_value,
            description=new_description,
        )
        if not updated:
            return False

        # Audit log field changes for description
        new_metadata = {
            "description": new_description
            if new_description is not None
            else old_metadata["description"],
            "scope": existing.get("scope", "global"),
        }
        AuditLogService.log_field_changes(
            action="secret.update",
            entity_type="secret",
            entity_id=secret_id,
            old_entity=old_metadata,
            new_entity=new_metadata,
        )

        # Separate audit entry for value rotation (without logging the value itself)
        if value is not None:
            AuditLogService.log(
                action="secret.value_rotated",
                entity_type="secret",
                entity_id=secret_id,
                outcome="rotated",
                details={"actor": actor},
            )

        return True

    @classmethod
    def delete_secret(cls, secret_id: str, actor: str = "system") -> bool:
        """Delete a secret with audit trail.

        Uses AuditLogService.log_field_changes() to record the before state.
        """
        existing = db_secrets.get_secret(secret_id)
        if not existing:
            return False

        old_metadata = {
            "name": existing.get("name", ""),
            "description": existing.get("description", ""),
            "scope": existing.get("scope", "global"),
            "created_by": existing.get("created_by", "system"),
        }

        deleted = db_secrets.delete_secret(secret_id)
        if not deleted:
            return False

        AuditLogService.log_field_changes(
            action="secret.delete",
            entity_type="secret",
            entity_id=secret_id,
            old_entity=old_metadata,
            new_entity={},
        )
        return True

    @classmethod
    def get_secret_value(cls, secret_id_or_name: str, accessor: str = "system") -> Optional[str]:
        """Decrypt and return a secret's value by ID or name.

        Updates last_accessed_at and audit-logs the access.
        """
        secret = db_secrets.get_secret(secret_id_or_name)
        if not secret:
            secret = db_secrets.get_secret_by_name(secret_id_or_name)
        if not secret:
            return None

        plaintext = cls.decrypt(
            secret["encrypted_value"],
            purpose=secret["id"],
            accessor=accessor,
        )
        db_secrets.update_last_accessed(secret["id"])
        return plaintext

    @classmethod
    def get_secrets_for_execution(cls, scope: str = "global") -> dict:
        """Get all secrets for a scope as env vars for subprocess injection.

        Returns a dict of {"AGENTED_SECRET_{NAME}": plaintext} entries.
        """
        secrets_list = db_secrets.list_secrets(scope=scope)
        result = {}
        for secret_meta in secrets_list:
            secret = db_secrets.get_secret(secret_meta["id"])
            if not secret:
                continue
            try:
                plaintext = cls.decrypt(
                    secret["encrypted_value"],
                    purpose=secret["id"],
                    accessor="execution_service",
                )
                env_name = f"AGENTED_SECRET_{secret_meta['name'].upper()}"
                result[env_name] = plaintext
            except Exception as e:
                logger.warning(
                    "Failed to decrypt secret '%s' for execution: %s", secret_meta["name"], e
                )
        return result

    @classmethod
    def rotate_key(cls, new_key: str) -> int:
        """Re-encrypt all secrets with a new primary key.

        The new key should be added as the first key in AGENTED_VAULT_KEYS.
        This method decrypts each secret with the current MultiFernet and
        re-encrypts with the (now-rotated) MultiFernet.

        Returns the number of secrets re-encrypted.
        """
        cls.reset()  # Force reload of keys
        secrets_list = db_secrets.list_secrets()
        count = 0
        for secret_meta in secrets_list:
            secret = db_secrets.get_secret(secret_meta["id"])
            if not secret:
                continue
            try:
                fernet = cls._get_fernet()
                # Rotate uses MultiFernet.rotate() which re-encrypts with the primary key
                new_ciphertext = fernet.rotate(secret["encrypted_value"].encode()).decode()
                db_secrets.update_secret(secret_meta["id"], encrypted_value=new_ciphertext)
                count += 1
            except Exception as e:
                logger.error(
                    "Failed to rotate secret '%s': %s", secret_meta["name"], e, exc_info=True
                )
        AuditLogService.log(
            action="secret.key_rotation",
            entity_type="vault",
            entity_id="vault",
            outcome="rotated",
            details={"secrets_rotated": count},
        )
        return count
