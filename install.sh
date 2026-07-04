#!/usr/bin/env bash
#
# Agented single-command installer.
#
# Pulls the prebuilt container image from GHCR and brings up the
# docker-compose stack (backend :20000 + ai-accounts sidecar :20001).
# The IMAGE is the distribution unit — no source clone, no local Python /
# Node toolchain, no build. Re-running is an idempotent no-op upgrade
# (pull newer image + `up -d` reconciles).
#
# SUPPLY-CHAIN SAFETY
#   The safest install path is clone-and-inspect: read the source, THEN run it.
#       git clone https://github.com/ca1773130n/Agented && cd Agented
#       bash scripts/setup.sh          # dev
#       ./install.sh                   # or: prebuilt-image deploy
#
#   When this script fetches docker-compose.yml over the network it does so
#   from a PINNED, immutable release tag and verifies the download against a
#   SHA-256 checksum embedded in this script (see COMPOSE_SHA256 below). A
#   mismatch aborts — a compromised repo/CDN cannot swap the compose file for
#   a malicious one without also breaking the checksum baked into the copy of
#   install.sh you are running.
#
#   Fetching from a MUTABLE ref (e.g. `main`) is refused unless you explicitly
#   opt in with AGENTED_INSTALL_UNVERIFIED=1, which prints a security warning
#   and skips checksum verification. Do this only when you understand the risk.
#
# Usage:
#   # Preferred: clone and inspect first
#   git clone https://github.com/ca1773130n/Agented && cd Agented && ./install.sh
#
#   # Convenience (less safe): pipe a PINNED tag through bash
#   curl -fsSL https://raw.githubusercontent.com/ca1773130n/Agented/v0.8.0/install.sh | bash
#
#   ./install.sh                # install / upgrade in the current directory
#   ./install.sh --dry-run      # print the commands without executing
#
# Environment:
#   GHCR_TAG              image tag to pull            (default: latest)
#   INSTALL_DIR          where to write compose       (default: current directory)
#   AGENTED_INSTALL_REF  git ref to fetch compose from (default: pinned tag below)
#   AGENTED_INSTALL_UNVERIFIED  set to 1 to fetch from a mutable ref WITHOUT
#                        checksum verification (prints a security warning)
#
set -euo pipefail

IMAGE_REPO="ghcr.io/ca1773130n/agented"
GHCR_TAG="${GHCR_TAG:-latest}"
IMAGE="${IMAGE_REPO}:${GHCR_TAG}"
INSTALL_DIR="${INSTALL_DIR:-$(pwd)}"

# Immutable release tag the network fetch is pinned to by default. Bumped per
# release alongside COMPOSE_SHA256. Override with AGENTED_INSTALL_REF only if
# you know the checksum still matches (or use the unverified opt-in).
PINNED_REF="v0.8.0"
INSTALL_REF="${AGENTED_INSTALL_REF:-$PINNED_REF}"

# SHA-256 of docker-compose.yml at PINNED_REF. Regenerate on every release:
#   shasum -a 256 docker-compose.yml
COMPOSE_SHA256="bc3d5e67b9a75d412a98146c795c45560fcd5237a908eb6060b70fdc89d46d43"

# Opt-in escape hatch for fetching from a mutable ref (no checksum check).
UNVERIFIED="${AGENTED_INSTALL_UNVERIFIED:-0}"

RAW_BASE="https://raw.githubusercontent.com/ca1773130n/Agented"
COMPOSE_URL="${RAW_BASE}/${INSTALL_REF}/docker-compose.yml"

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h | --help)
      sed -n '2,45p' "$0"
      exit 0
      ;;
    *)
      echo "install.sh: unknown argument: $arg" >&2
      echo "run './install.sh --help' for usage" >&2
      exit 2
      ;;
  esac
done

# run CMD... — execute, or just print when --dry-run.
run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '+ %s\n' "$*"
  else
    "$@"
  fi
}

# sha256_of FILE — print the file's SHA-256 (bare hex), using whichever tool
# is available. Empty output means no hasher was found.
sha256_of() {
  if command -v sha256sum > /dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum > /dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    echo ""
  fi
}

# fetch_and_verify_compose DEST — download docker-compose.yml to DEST and, in
# the pinned/verified mode, abort unless its SHA-256 matches COMPOSE_SHA256.
fetch_and_verify_compose() {
  local dest="$1"
  if [ "$UNVERIFIED" = "1" ]; then
    echo "!! AGENTED_INSTALL_UNVERIFIED=1 — fetching docker-compose.yml from" >&2
    echo "!! '${INSTALL_REF}' WITHOUT checksum verification. This trusts the" >&2
    echo "!! remote content to execute on your host. Prefer clone-and-inspect" >&2
    echo "!! or a pinned release tag. Continuing in 3s..." >&2
    run sleep 3
    echo "Fetching (unverified) docker-compose.yml -> ${dest}"
    run curl -fsSL "$COMPOSE_URL" -o "$dest"
    return
  fi

  echo "Fetching docker-compose.yml (ref ${INSTALL_REF}) -> ${dest}"
  run curl -fsSL "$COMPOSE_URL" -o "$dest"

  if [ "$DRY_RUN" -eq 1 ]; then
    printf '+ verify sha256(%s) == %s\n' "$dest" "$COMPOSE_SHA256"
    return
  fi

  local got
  got="$(sha256_of "$dest")"
  if [ -z "$got" ]; then
    rm -f "$dest"
    echo "install.sh: no sha256 tool (sha256sum/shasum) to verify the download." >&2
    echo "install.sh: refusing to run an unverified compose file. Install one," >&2
    echo "install.sh: or use clone-and-inspect, or set AGENTED_INSTALL_UNVERIFIED=1." >&2
    exit 1
  fi
  if [ "$got" != "$COMPOSE_SHA256" ]; then
    rm -f "$dest"
    echo "install.sh: docker-compose.yml checksum MISMATCH — aborting." >&2
    echo "install.sh:   expected ${COMPOSE_SHA256}" >&2
    echo "install.sh:   got      ${got}" >&2
    echo "install.sh: the remote file does not match the pinned release. This" >&2
    echo "install.sh: could be tampering, or a stale PINNED_REF/COMPOSE_SHA256." >&2
    exit 1
  fi
  echo "docker-compose.yml checksum OK (${COMPOSE_SHA256})"
}

# In --dry-run we skip the hard prerequisite check so the command plan is
# printable on any machine (CI, docs generation).
if [ "$DRY_RUN" -eq 0 ]; then
  if ! command -v docker > /dev/null 2>&1; then
    echo "install.sh: docker is required but not found on PATH" >&2
    exit 1
  fi
  if ! docker compose version > /dev/null 2>&1; then
    echo "install.sh: 'docker compose' (v2) is required but not available" >&2
    exit 1
  fi
fi

echo "Agented installer — image ${IMAGE}, dir ${INSTALL_DIR}"

run mkdir -p "$INSTALL_DIR"

# Prefer a docker-compose.yml already sitting next to this script (the
# clone-and-inspect path: the user has already seen the file). Otherwise
# fetch-and-verify one from the pinned release. Never clobber an operator's
# existing customized compose file.
COMPOSE_FILE="${INSTALL_DIR}/docker-compose.yml"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_COMPOSE="${SCRIPT_DIR}/docker-compose.yml"
if [ -f "$COMPOSE_FILE" ]; then
  echo "Using existing ${COMPOSE_FILE}"
elif [ -f "$LOCAL_COMPOSE" ] && [ "$LOCAL_COMPOSE" != "$COMPOSE_FILE" ]; then
  echo "Using bundled ${LOCAL_COMPOSE} (clone-and-inspect) -> ${COMPOSE_FILE}"
  run cp "$LOCAL_COMPOSE" "$COMPOSE_FILE"
else
  fetch_and_verify_compose "$COMPOSE_FILE"
fi

# Ensure a .env exists so compose's `env_file` directive is satisfied.
ENV_FILE="${INSTALL_DIR}/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "Creating empty ${ENV_FILE} (add secrets here — see docs/deploy/SECRETS.md)"
  run touch "$ENV_FILE"
fi

# Pull the image + reconcile the stack. `pull` then `up -d` is the same
# operation as `just self-update`, so first install and upgrade share a path.
run env GHCR_TAG="$GHCR_TAG" docker compose -f "$COMPOSE_FILE" pull
run env GHCR_TAG="$GHCR_TAG" docker compose -f "$COMPOSE_FILE" up -d

echo "Done. Console: http://localhost:3000  ·  API: http://localhost:20000/schema"
echo "Update anytime with: just self-update  (or re-run this script)"
