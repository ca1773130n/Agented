"""The sidecar's LazyFlaskKeyAuth must honor a just-minted admin key without
waiting out its 5s cache TTL.

Onboarding creates the admin key on the welcome page and *immediately* drives
the backends step, which calls the sidecar (`/api/v1/*`). If the sidecar's
in-memory key cache (primed empty at boot, before any key existed) only
refreshes every 5s, those first calls 401 — surfacing as "cannot find AI
backend" in the UI. The fix: on a cache MISS, force one throttled DB re-read
before rejecting, so a new key is accepted on the very next request.

`scripts/run_ai_accounts.py` builds the sidecar app at import time, so we load
just the class via AST extraction rather than importing the module.
"""

import ast
import asyncio
import sqlite3
import sys
import types
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "scripts" / "run_ai_accounts.py"


@pytest.fixture(autouse=True)
def _skip_pg(skip_on_pg):
    """SQLite-specific: the sidecar lazy-auth reads keys from a SQLite DB file — skip on PG."""


def _load_lazy_auth_class():
    tree = ast.parse(_SRC.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "LazyFlaskKeyAuth")
    # Stub the `ai_accounts_core.domain.principal.Principal` import the class
    # does inside __init__ so we don't pull in the whole sidecar package.
    for name in ("ai_accounts_core", "ai_accounts_core.domain"):
        sys.modules.setdefault(name, types.ModuleType(name))
    principal_mod = types.ModuleType("ai_accounts_core.domain.principal")

    class Principal:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    principal_mod.Principal = Principal
    sys.modules["ai_accounts_core.domain.principal"] = principal_mod

    module = ast.Module(body=[cls], type_ignores=[])
    ast.fix_missing_locations(module)
    ns: dict = {"os": __import__("os"), "sqlite3": sqlite3}
    exec(compile(module, str(_SRC), "exec"), ns)
    return ns["LazyFlaskKeyAuth"]


class _Req:
    def __init__(self, token: str):
        self.headers = {"authorization": f"bearer {token}"}


def _make_db(tmp_path, keys):
    db = tmp_path / "agented.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE user_roles (id TEXT, api_key TEXT, label TEXT, role TEXT)")
    conn.executemany(
        "INSERT INTO user_roles VALUES (?, ?, 'l', 'admin')",
        [(f"r{i}", k) for i, k in enumerate(keys)],
    )
    conn.commit()
    conn.close()
    return str(db)


def test_new_key_honored_on_cache_miss(tmp_path):
    Lazy = _load_lazy_auth_class()
    db = _make_db(tmp_path, ["OLDKEY"])
    auth = Lazy(db)

    # Prime the cache with the current key set {OLDKEY} (a HIT).
    assert asyncio.run(auth.authenticate(_Req("OLDKEY"))) is not None

    # A new admin key lands in the DB *after* the cache was primed — exactly the
    # onboarding race. The cached set still holds only {OLDKEY}.
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO user_roles VALUES ('r9', 'NEWKEY', 'l', 'admin')")
    conn.commit()
    conn.close()

    # Without force-refresh-on-miss this is None until the 5s TTL lapses.
    assert asyncio.run(auth.authenticate(_Req("NEWKEY"))) is not None


def test_unknown_key_still_rejected(tmp_path):
    Lazy = _load_lazy_auth_class()
    db = _make_db(tmp_path, ["OLDKEY"])
    auth = Lazy(db)
    assert asyncio.run(auth.authenticate(_Req("BOGUS"))) is None


def test_missing_authorization_header_rejected(tmp_path):
    Lazy = _load_lazy_auth_class()
    auth = Lazy(_make_db(tmp_path, ["OLDKEY"]))

    class _NoAuth:
        headers: dict = {}

    assert asyncio.run(auth.authenticate(_NoAuth())) is None
