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
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/ca1773130n/Agented/main/install.sh | bash
#   ./install.sh                # install / upgrade in the current directory
#   ./install.sh --dry-run      # print the commands without executing
#
# Environment:
#   GHCR_TAG      image tag to pull        (default: latest)
#   INSTALL_DIR   where to write compose   (default: current directory)
#
set -euo pipefail

IMAGE_REPO="ghcr.io/ca1773130n/agented"
GHCR_TAG="${GHCR_TAG:-latest}"
IMAGE="${IMAGE_REPO}:${GHCR_TAG}"
INSTALL_DIR="${INSTALL_DIR:-$(pwd)}"
COMPOSE_URL="https://raw.githubusercontent.com/ca1773130n/Agented/main/docker-compose.yml"

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h | --help)
      sed -n '2,20p' "$0"
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

# Ensure a docker-compose.yml is present (idempotent: never clobber an
# existing one — an operator may have customized it).
COMPOSE_FILE="${INSTALL_DIR}/docker-compose.yml"
if [ -f "$COMPOSE_FILE" ]; then
  echo "Using existing ${COMPOSE_FILE}"
else
  echo "Fetching docker-compose.yml -> ${COMPOSE_FILE}"
  run curl -fsSL "$COMPOSE_URL" -o "$COMPOSE_FILE"
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
