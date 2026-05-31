"""Content fingerprint for forge primitives (Phase E propagation).

Two primitives of the same kind with identical *content* fields share a
fingerprint regardless of project / id / timestamps."""

from __future__ import annotations

import hashlib
import json

# Content fields per kind (mirrors the create/update payload shape).
_FP_KEYS = {
    "rule": ("rule_type", "description", "condition", "action", "enabled"),
    "hook": ("event", "description", "content", "enabled"),
    "command": ("description", "content", "arguments", "enabled"),
    "skill": ("description", "content"),
}


def fingerprint(kind: str, asset: dict) -> str:
    keys = _FP_KEYS.get(kind, ())
    payload = {k: asset.get(k) for k in keys}
    payload["__kind"] = kind
    payload["__name"] = asset.get("name") or asset.get("skill_name")
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
