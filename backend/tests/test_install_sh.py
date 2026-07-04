"""Guard tests for the top-level install.sh (Phase 26 supply-chain hardening).

These are STATIC assertions over the installer source — they never touch the
network. They exist to keep the RCE-hardening from silently regressing:

  * the default network fetch must be pinned to an immutable release tag
    (not the mutable `main` branch),
  * the fetched docker-compose.yml must be SHA-256 verified before use,
  * fetching from a mutable ref without verification must remain behind an
    explicit opt-in env var.

If a future edit points the default fetch back at `main`, or drops the
checksum step, one of these assertions fails.
"""

from pathlib import Path

import pytest

# backend/tests/ -> backend/ -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_INSTALL_SH = _REPO_ROOT / "install.sh"


@pytest.fixture(scope="module")
def install_src() -> str:
    if not _INSTALL_SH.is_file():
        pytest.skip(f"install.sh not found at {_INSTALL_SH}")
    return _INSTALL_SH.read_text(encoding="utf-8")


def test_default_fetch_ref_is_pinned_not_main(install_src: str):
    # The default ref the compose fetch resolves to is a pinned tag, never main.
    assert 'PINNED_REF="v' in install_src, "PINNED_REF must default to a vX.Y.Z tag"
    assert 'INSTALL_REF="${AGENTED_INSTALL_REF:-$PINNED_REF}"' in install_src
    # The URL is built from the (pinned) INSTALL_REF, not a hardcoded /main/.
    assert "/${INSTALL_REF}/docker-compose.yml" in install_src
    assert "/main/docker-compose.yml" not in install_src


def test_compose_is_checksum_verified(install_src: str):
    # A published SHA-256 exists and is compared against the download.
    assert "COMPOSE_SHA256=" in install_src
    assert 'if [ "$got" != "$COMPOSE_SHA256" ]; then' in install_src
    # Mismatch aborts and removes the bad file.
    assert "checksum MISMATCH" in install_src
    assert 'rm -f "$dest"' in install_src


def test_unverified_fetch_requires_explicit_optin(install_src: str):
    # The only path that skips verification is gated behind an env opt-in and
    # prints a security warning first.
    assert 'UNVERIFIED="${AGENTED_INSTALL_UNVERIFIED:-0}"' in install_src
    assert 'if [ "$UNVERIFIED" = "1" ]; then' in install_src
    assert "WITHOUT checksum verification" in install_src


def test_no_unconditional_remote_pipe_to_shell(install_src: str):
    # The installer itself must not curl|bash any remote script (that would
    # re-open the exec-unverified-remote-content hole from inside install.sh).
    # Ignore comment/usage lines — the `curl ... | bash` in the header docs is
    # illustrative, not an executed statement.
    code_lines = [ln for ln in install_src.splitlines() if not ln.lstrip().startswith("#")]
    code = "\n".join(code_lines).lower()
    assert "curl" in code  # it does fetch compose...
    assert "| bash" not in code and "| sh" not in code, (
        "install.sh must not pipe any fetched content straight into a shell"
    )
