#!/usr/bin/env bash
# Move a GitHub Personal Access Token from a plaintext settings file into the
# macOS login keychain. After running this script, source the printed shell
# snippet (or add it to ~/.zshrc) to expose the token as $GITHUB_TOKEN at
# runtime without storing it on disk in plaintext.
#
# Usage:
#   scripts/install-github-pat-keychain.sh ghp_yourTokenHere
#
# To read it back later:
#   security find-generic-password -a "$USER" -s "agented-github-pat" -w
#
# To remove it:
#   security delete-generic-password -a "$USER" -s "agented-github-pat"

set -euo pipefail

SERVICE="agented-github-pat"

if [[ "${1:-}" == "" ]]; then
  echo "usage: $0 <github-pat>" >&2
  echo "example: $0 ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" >&2
  exit 64
fi

if [[ "$(uname)" != "Darwin" ]]; then
  echo "This helper targets macOS Keychain. On Linux, use \`secret-tool\`" >&2
  echo "(libsecret) or pass-store. Skipping." >&2
  exit 1
fi

PAT="$1"

# Overwrite if it already exists (-U), no interactive prompt.
security add-generic-password \
  -a "$USER" \
  -s "$SERVICE" \
  -w "$PAT" \
  -U \
  -T /usr/bin/security

cat <<'EOF'

✓ Stored in macOS login keychain (service: agented-github-pat).

Add this to your ~/.zshrc (or ~/.bashrc) so the token is exposed as
$GITHUB_TOKEN to gh / git / scripts that need it:

  export GITHUB_TOKEN="$(security find-generic-password -a "$USER" -s 'agented-github-pat' -w 2>/dev/null)"

Then reopen your shell. Verify with:

  gh auth status

To rotate later: re-run this script with the new PAT.
To remove:
  security delete-generic-password -a "$USER" -s "agented-github-pat"
EOF
