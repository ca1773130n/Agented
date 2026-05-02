# Security runbook

## Secrets that should NEVER live in the repo

| Secret | Where it actually belongs |
|--------|---------------------------|
| GitHub Personal Access Token | macOS Keychain / libsecret / pass-store, exported into `$GITHUB_TOKEN` at shell startup |
| Anthropic API key (`sk-ant-…`) | Backend `.env` file (gitignored) or per-account row in `agented.db` (encrypted via `EnvKeyVault`) |
| Sidecar admin key (`AI_ACCOUNTS_API_KEY`) | Backend `.env` file or reused from `agented.db` `user_roles` table |
| Vault key (`AI_ACCOUNTS_VAULT_KEY`) | Backend `.env` file. **Required in production** — sidecar refuses to start without it (Wave 3) |

## Moving a GitHub PAT into the macOS Keychain

If you currently have a PAT in `~/.claude-personal1/settings.json` or any
similar plaintext config file, evict it now.

```bash
# 1. Move it into the keychain (replace with your actual PAT).
scripts/install-github-pat-keychain.sh ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAA

# 2. Add this line to ~/.zshrc so the token is exposed at shell startup.
export GITHUB_TOKEN="$(security find-generic-password -a "$USER" -s 'agented-github-pat' -w 2>/dev/null)"

# 3. Restart your shell. Verify:
gh auth status

# 4. Once verified, scrub the PAT from the original config file.
```

## Rotating

| Secret | How |
|--------|-----|
| GitHub PAT | re-run `scripts/install-github-pat-keychain.sh <new-pat>` (it overwrites) |
| Sidecar admin key | UI: Settings → RBAC → row → **Rotate**, or `POST /admin/rbac/roles/{role_id}/rotate` (Wave 8) |
| Anthropic / OpenAI per-account key | Account wizard re-login on the relevant backend |
| Vault key | Out of scope for online rotation — re-encrypt the secrets table; stop the sidecar before doing it |

## Logging

`SensitiveDataFilter` (Wave 7) is attached to both the stderr and rotating
file handlers. It redacts the following patterns from log records before
they hit disk:

- `Authorization: Bearer <token>`
- `X-API-Key: <token>`
- `sk-{ant,proj,live,test}-…` (Anthropic / OpenAI key shapes)
- `token=`, `password=`, `api_key=`, `secret=` query/form values

If you're adding new auth-shaped secrets, extend `_REDACTION_PATTERNS` in
`backend/app/logging_config.py` and add a unit test in
`backend/tests/test_logging_redaction.py`.

## SSRF guard (Wave 3)

The CLIProxyAPI manager rejects callback URLs whose path contains `..`
segments (literal or `%2e%2e`-encoded). Any new URL-accepting endpoint
must use the same guard — see `_assert_path_safe` in
`ai-accounts/packages/core/src/ai_accounts_core/cliproxy/manager.py`.
