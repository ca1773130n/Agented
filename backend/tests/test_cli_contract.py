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


def _shape(path: str) -> str:
    """Reduce a path to its SHAPE: literals kept, any placeholder becomes `*`.

    Compare shapes, not names. The CLI derives a param name from the frontend's
    JavaScript variable (`:projectId`) while Litestar declares the Python one
    (`{project_id:str}`), and the types vary (`:int`, `:uuid`). Those names are
    both correct and will never match textually — what must match is the position
    and count of the placeholders.
    """
    out = []
    for seg in path.split("/"):
        out.append("*" if seg.startswith(":") or seg.startswith("{") else seg)
    return "/".join(out)


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
            table.add((method.upper(), _shape(path)))
    assert table, "the app exposed no routes — create_app() changed shape"
    return table


def test_every_cli_alias_resolves_to_a_real_route(route_table):
    """The load-bearing assertion: every shortcut the CLI advertises exists."""
    missing = []
    for method, cli_path in _declared_aliases():
        if (method, _shape(cli_path)) not in route_table:
            missing.append(f"{method} {cli_path}")
    assert not missing, "cli/aliases.ts references routes that do not exist:\n  " + "\n  ".join(missing)


GENERATED_TS = ALIASES_TS.parent / "aliases.generated.ts"

# Calls the FRONTEND makes that no backend route serves.
#
# These are not CLI bugs. The generated commands mirror the web client exactly,
# so where the client calls a route the server does not expose, the CLI inherits
# it — and surfacing that is a feature of deriving one from the other. Each was
# checked against the live router:
#
#   POST   …/viewers                     server has POST …/viewers/join
#   DELETE …/viewers/{viewerId}          server has POST …/viewers/leave
#   POST   …/viewers/{viewerId}/heartbeat server has POST …/viewers/heartbeat
#                                        (no viewer segment)
#   GET    /admin/workflows/*/versions/*  server has …/versions/latest, a LITERAL
#                                        segment — any other version 404s
#
# So the collaborative-viewer calls and the versioned-workflow fetch are dead or
# broken in the browser too. Listed rather than silenced: this test must fail on
# MY bugs without blocking on somebody else's, and an entry disappearing from
# here means the app was fixed, which is worth noticing.
FRONTEND_BACKEND_MISMATCHES = {
    "POST /admin/executions/*/viewers",
    "DELETE /admin/executions/*/viewers/*",
    "POST /admin/executions/*/viewers/*/heartbeat",
    "GET /admin/workflows/*/versions/*",
}

_GEN_ENTRY = re.compile(
    r'method:\s*"(?P<method>[A-Z]+)",\s*path:\s*"(?P<path>[^"]+)"',
)


def _generated_aliases() -> list[tuple[str, str]]:
    if not GENERATED_TS.is_file():
        pytest.skip(f"generated table not present at {GENERATED_TS}")
    found = [(m.group("method"), m.group("path")) for m in _GEN_ENTRY.finditer(GENERATED_TS.read_text())]
    assert found, "parsed zero generated aliases — the regex and the generator have drifted apart"
    return found


def test_every_generated_alias_resolves_to_a_real_route(route_table):
    """The 750+ GENERATED commands must hit real routes too.

    This is the assertion that actually protects users. The CLI's own coverage
    test compares the generated table against the frontend using the SAME
    normalisation the generator used — so a normalisation bug agrees with itself
    and passes. Only the server's real route table is an independent oracle.

    It caught two shipped classes of wrong command:
      * `${encodeURIComponent(id)}` collapsing a path to its prefix, which turned
        `ag team-leader-chat open-session` into POST /admin/projects — a MUTATING
        call to the wrong endpoint, which would have created a project;
      * query suffixes becoming path segments (`/admin/system/errors:query`),
        which 404.
    A missing command is an inconvenience; a command that silently hits the wrong
    endpoint is a bug the user cannot see.
    """
    missing = []
    for method, cli_path in _generated_aliases():
        if (method, _shape(cli_path)) not in route_table:
            missing.append(f"{method} {_shape(cli_path)}")

    # The sidecar (:20001) publishes no OpenAPI and is not part of this app's
    # route table, so its paths cannot be checked here.
    missing = [m for m in missing if "/api/v1/" not in m]
    missing = [m for m in missing if m not in FRONTEND_BACKEND_MISMATCHES]

    assert not missing, (
        f"{len(missing)} generated command(s) do not resolve to a real route.\n"
        "Fix cli/scripts/gen-aliases.mjs and re-run `just cli-gen`:\n  "
        + "\n  ".join(sorted(missing)[:30])
    )


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
