"""Phase-25 i18n key-parity guard (25-05).

A backend-side guard so a missing locale key fails CI even if the frontend suite
doesn't cover it: the new Phase-25 namespaces (share/attach, co-drive, fork,
sso/oidc) must have IDENTICAL recursive key sets across en/ko/ja/zh.
"""

import json
from pathlib import Path

import pytest

_LOCALES_DIR = Path(__file__).resolve().parents[2] / "frontend" / "src" / "locales"
_LOCALES = ("en", "ko", "ja", "zh")
_PHASE25_NAMESPACES = ("sharedSession", "coDrive", "fork", "sso")


def _keyset(obj, prefix=""):
    keys = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            keys.add(prefix + key)
            keys |= _keyset(value, prefix + key + ".")
    return keys


def _load(locale):
    with open(_LOCALES_DIR / f"{locale}.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("namespace", _PHASE25_NAMESPACES)
def test_phase25_namespace_key_parity(namespace):
    catalogs = {loc: _load(loc) for loc in _LOCALES}
    for loc in _LOCALES:
        assert namespace in catalogs[loc], f"{loc}.json missing namespace '{namespace}'"
    reference = _keyset(catalogs["en"][namespace])
    assert reference, f"namespace '{namespace}' is empty in en.json"
    for loc in _LOCALES:
        assert _keyset(catalogs[loc][namespace]) == reference, (
            f"{loc}.json key set for '{namespace}' differs from en.json"
        )
