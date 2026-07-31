"""Contract between the `ag` CLI's curated aliases and the real route table.

`cli/aliases.ts` is the ONE file in the CLI that can go stale: everything else is
endpoint-agnostic (`ag api` reaches any path, `ag find` reads the live schema).
So the alias table is pinned here — a route rename fails `uv run pytest` instead
of failing in an operator's terminal with a 404.

This runs entirely offline: no gunicorn, no port, no network. It builds the
Litestar app in-process and asks its router.
"""

import re
from pathlib import Path

import pytest

ALIASES_TS = Path(__file__).resolve().parent.parent.parent / "cli" / "aliases.ts"

# `method: 'GET',` … `path: '/admin/products/:product_id',` inside one object literal.
_ENTRY = re.compile(
    r"method:\s*'(?P<method>[A-Z]+)',\s*\n\s*path:\s*'(?P<path>[^']+)'",
    re.MULTILINE,
)


def _declared_aliases() -> list[tuple[str, str]]:
    if not ALIASES_TS.is_file():
        pytest.skip(f"CLI not present at {ALIASES_TS}")
    text = ALIASES_TS.read_text()
    found = [(m.group("method"), m.group("path")) for m in _ENTRY.finditer(text)]
    assert found, "parsed zero aliases — the regex and aliases.ts have drifted apart"
    return found


def _cli_path_to_litestar(path: str) -> str:
    """`/admin/products/:product_id` -> `/admin/products/{product_id:str}`.

    The CLI uses `:name` because it is a shell tool and `{}` would need quoting
    in every example; Litestar declares `{name:type}`.
    """
    return re.sub(r":([a-zA-Z_]+)", r"{\1:str}", path)


@pytest.fixture(scope="module")
def route_table():
    """Every (method, path) the app actually serves. Built in-process."""
    import os

    os.environ.setdefault("AGENTED_LITESTAR_SKIP_STARTUP", "1")
    from app_litestar.main import create_app

    app = create_app()
    table: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        if not path:
            continue
        for method in getattr(route, "methods", None) or []:
            table.add((method.upper(), path))
    assert table, "the app exposed no routes — create_app() changed shape"
    return table


def test_every_cli_alias_resolves_to_a_real_route(route_table):
    """The load-bearing assertion: every shortcut the CLI advertises exists."""
    missing = []
    for method, cli_path in _declared_aliases():
        want = (method, _cli_path_to_litestar(cli_path))
        if want not in route_table:
            missing.append(f"{method} {cli_path}  (looked for {want[1]})")
    assert not missing, "cli/aliases.ts references routes that do not exist:\n  " + "\n  ".join(missing)


def test_alias_table_is_not_silently_empty():
    """Guards the regex itself: if aliases.ts is reformatted so the parser stops
    matching, the test above would pass vacuously and stop protecting anything."""
    assert len(_declared_aliases()) >= 15


def test_auth_exempt_prefixes_match_what_the_cli_assumes(route_table):
    """`ag ping` and `ag find` work before a key exists because /health and
    /schema bypass auth. The CLI hard-codes that list in lib/transport.ts
    (`needsAuth`); if the backend's list changes, the CLI would start sending an
    unnecessary key — or worse, omit a required one."""
    from app_litestar.middleware import _AUTH_BYPASS_PREFIXES

    for required in ("/health", "/schema"):
        assert required in _AUTH_BYPASS_PREFIXES, (
            f"{required} is no longer auth-exempt; cli/lib/transport.ts needsAuth() must be updated"
        )
