"""The sidecar's LazyFlaskKeyAuth must honor a just-minted admin key without
waiting out its 5s cache TTL — and it must read keys through the shared,
DATABASE_URL-aware DB layer so the same behavior holds on SQLite and Postgres.

Onboarding creates the admin key on the welcome page and *immediately* drives
the backends step, which calls the sidecar (`/api/v1/*`). If the sidecar's
in-memory key cache (primed empty at boot, before any key existed) only
refreshes every 5s, those first calls 401 — surfacing as "cannot find AI
backend" in the UI. The fix: on a cache MISS, force one throttled DB re-read
before rejecting, so a new key is accepted on the very next request.

`scripts/run_ai_accounts.py` builds the sidecar app at import time, so we load
just the class via AST extraction rather than importing the module. The
extracted class reads keys via ``app.db.rbac.get_authorized_api_keys`` (a
runtime import inside ``_read_keys_from_db``), which follows
``config.DATABASE_URL`` — so seeding through ``get_connection`` and driving the
class exercises the real read path on whichever backend ``isolated_db`` selects.
"""

import ast
import asyncio
import sqlite3
import sys
import types
from pathlib import Path

from app.db.connection import get_connection
from app.db.ids import _get_unique_role_id

_SRC = Path(__file__).resolve().parents[1] / "scripts" / "run_ai_accounts.py"


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


def _seed_keys(keys):
    """Insert admin ``user_roles`` rows through the shared DATABASE_URL-aware
    connection (the same path the sidecar now reads). Clears first so each test
    starts from a known set on either backend."""
    with get_connection() as conn:
        conn.execute("DELETE FROM user_roles")
        for k in keys:
            rid = _get_unique_role_id(conn)
            conn.execute(
                "INSERT INTO user_roles (id, api_key, label, role) VALUES (?, ?, ?, 'admin')",
                (rid, k, k),
            )
        conn.commit()


def _add_key(k):
    with get_connection() as conn:
        rid = _get_unique_role_id(conn)
        conn.execute(
            "INSERT INTO user_roles (id, api_key, label, role) VALUES (?, ?, ?, 'admin')",
            (rid, k, k),
        )
        conn.commit()


def test_new_key_honored_on_cache_miss(isolated_db):
    Lazy = _load_lazy_auth_class()
    _seed_keys(["OLDKEY"])
    auth = Lazy(isolated_db)

    # Prime the cache with the current key set {OLDKEY} (a HIT).
    assert asyncio.run(auth.authenticate(_Req("OLDKEY"))) is not None

    # A new admin key lands in the DB *after* the cache was primed — exactly the
    # onboarding race. The cached set still holds only {OLDKEY}.
    _add_key("NEWKEY")

    # Without force-refresh-on-miss this is None until the 5s TTL lapses.
    assert asyncio.run(auth.authenticate(_Req("NEWKEY"))) is not None


def test_unknown_key_still_rejected(isolated_db):
    Lazy = _load_lazy_auth_class()
    _seed_keys(["OLDKEY"])
    auth = Lazy(isolated_db)
    assert asyncio.run(auth.authenticate(_Req("BOGUS"))) is None


def test_missing_authorization_header_rejected(isolated_db):
    Lazy = _load_lazy_auth_class()
    _seed_keys(["OLDKEY"])
    auth = Lazy(isolated_db)

    class _NoAuth:
        headers: dict = {}

    assert asyncio.run(auth.authenticate(_NoAuth())) is None
