"""Provider usage client — calls real provider APIs for authoritative rate limit data.

Supports Claude (Anthropic), Codex (OpenAI), and Gemini (Google) providers.
Reads OAuth tokens from the same locations as claude-dashboard and each CLI tool.
"""

import hashlib
import json
import logging
import os
import platform
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default timeout for HTTP requests (seconds)
_HTTP_TIMEOUT = 15

# Gemini CLI well-known OAuth credentials (public, embedded in the open-source CLI).
# See: https://github.com/anthropics/gemini-cli → code_assist/oauth2.js
_GEMINI_CLI_CLIENT_ID = "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com"
_GEMINI_CLI_CLIENT_SECRET = "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"


class CredentialResolver:
    """Resolves OAuth tokens for each provider from local credential stores."""

    @staticmethod
    def get_claude_token(account: dict) -> Optional[str]:
        """Read Claude OAuth token.

        Priority (account-specific first):
        1. macOS Keychain with config-path hash suffix (non-default accounts)
        2. config_path / .credentials.json (if account has config_path)
        3. macOS Keychain entry 'Claude Code-credentials' (default account)
        4. ~/.claude/.credentials.json (default account)

        Claude Code stores Keychain credentials under:
        - Default:     'Claude Code-credentials'
        - Non-default: 'Claude Code-credentials-{sha256(config_path)[:8]}'
        """
        config_path = account.get("config_path")
        default_config = str(Path.home() / ".claude")
        is_default_account = not config_path or os.path.expanduser(config_path) == default_config

        # For non-default accounts, try their specific Keychain entry first, then file
        if config_path and not is_default_account:
            expanded = os.path.expanduser(config_path)
            if platform.system() == "Darwin":
                suffix = hashlib.sha256(expanded.encode()).hexdigest()[:8]
                service = f"Claude Code-credentials-{suffix}"
                token = _read_keychain(service, "claudeAiOauth.accessToken")
                if token:
                    return token

            cred_path = Path(expanded) / ".credentials.json"
            token = _read_json_field(cred_path, ["claudeAiOauth", "accessToken"])
            if token:
                return token
            return None

        # For default account: try Keychain first, then file
        if platform.system() == "Darwin":
            token = _read_keychain("Claude Code-credentials", "claudeAiOauth.accessToken")
            if token:
                return token

        # File-based fallback for default account
        paths_to_try = []
        if config_path:
            paths_to_try.append(Path(os.path.expanduser(config_path)) / ".credentials.json")
        paths_to_try.append(Path.home() / ".claude" / ".credentials.json")

        for cred_path in paths_to_try:
            token = _read_json_field(cred_path, ["claudeAiOauth", "accessToken"])
            if token:
                return token

        return None

    @staticmethod
    def get_token_fingerprint(account: dict, backend_type: str) -> Optional[str]:
        """Return a short hash fingerprint of the resolved token for deduplication.

        Accounts sharing the same credential will produce the same fingerprint.
        """
        token = None
        if backend_type == "claude":
            token = CredentialResolver.get_claude_token(account)
        elif backend_type == "codex":
            token, _ = CredentialResolver.get_codex_token(account)
        elif backend_type == "gemini":
            token = CredentialResolver.get_gemini_token(account)
        if not token:
            return None
        return hashlib.sha256(token.encode()).hexdigest()[:12]

    @staticmethod
    def get_codex_token(account: dict) -> tuple[Optional[str], Optional[str]]:
        """Read Codex OAuth token and account_id.

        Priority:
        1. Account config_path / auth.json (if config_path set)
        2. ~/.codex/auth.json (default)
        Returns: (access_token, account_id) tuple
        """
        config_path = account.get("config_path")
        if config_path:
            custom_auth = Path(os.path.expanduser(config_path)) / "auth.json"
            token = _read_json_field(custom_auth, ["tokens", "access_token"])
            if token:
                acct_id = _read_json_field(custom_auth, ["tokens", "account_id"])
                return token, acct_id

        auth_path = Path.home() / ".codex" / "auth.json"
        access_token = _read_json_field(auth_path, ["tokens", "access_token"])
        account_id = _read_json_field(auth_path, ["tokens", "account_id"])
        return access_token, account_id

    @staticmethod
    def get_gemini_token(account: dict) -> Optional[str]:
        """Read Gemini OAuth token.

        Priority:
        1. Account config_path / oauth_creds.json (if config_path set)
        2. macOS Keychain entry 'gemini-cli-oauth'
        3. ~/.gemini/oauth_creds.json
        If token is expired, attempts refresh via Google OAuth.
        Falls back to well-known Gemini CLI OAuth credentials when
        client_id/client_secret are missing from the creds file.
        """
        cred_data = None
        config_path = account.get("config_path")

        # Try account-specific config_path first
        if config_path:
            custom_cred_path = Path(os.path.expanduser(config_path)) / "oauth_creds.json"
            cred_data = _read_json_file(custom_cred_path)

        # Try macOS Keychain
        if not cred_data and platform.system() == "Darwin":
            raw = _read_keychain_raw("gemini-cli-oauth")
            if raw:
                try:
                    cred_data = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    pass

        # File-based fallback (default location)
        if not cred_data:
            cred_path = Path.home() / ".gemini" / "oauth_creds.json"
            cred_data = _read_json_file(cred_path)

        if not cred_data:
            return None

        access_token = cred_data.get("access_token")
        refresh_token = cred_data.get("refresh_token")
        client_id = cred_data.get("client_id") or _GEMINI_CLI_CLIENT_ID
        client_secret = cred_data.get("client_secret") or _GEMINI_CLI_CLIENT_SECRET

        # Resolve expiry — Gemini CLI uses "expiry_date" (ms timestamp),
        # while other formats use "expiry" or "token_expiry" (ISO string).
        is_expired = False
        expiry = cred_data.get("expiry") or cred_data.get("token_expiry")
        expiry_date = cred_data.get("expiry_date")
        if expiry_date:
            try:
                exp_dt = datetime.fromtimestamp(int(expiry_date) / 1000, tz=timezone.utc)
                is_expired = exp_dt < datetime.now(timezone.utc)
            except (ValueError, TypeError, OSError):
                pass
        elif expiry:
            try:
                exp_dt = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
                is_expired = exp_dt < datetime.now(timezone.utc)
            except (ValueError, TypeError):
                pass

        # Refresh if expired
        if is_expired and refresh_token:
            refreshed = _refresh_google_token(refresh_token, client_id, client_secret)
            if refreshed:
                return refreshed

        return access_token


class ProviderUsageClient:
    """Fetches real rate limit utilization from provider APIs."""

    @classmethod
    def fetch_usage(cls, account: dict, backend_type: str) -> list[dict]:
        """Dispatch to the correct provider fetcher.

        Returns a list of window dicts:
            {window_type, percentage, resets_at, tokens_used, tokens_limit}
        """
        if backend_type == "claude":
            return cls._fetch_claude(account)
        elif backend_type == "codex":
            return cls._fetch_codex(account)
        elif backend_type == "gemini":
            return cls._fetch_gemini(account)
        else:
            logger.debug(f"No provider API for backend_type={backend_type}")
            return []

    @classmethod
    def _fetch_claude(cls, account: dict) -> list[dict]:
        """Fetch Claude usage from Anthropic OAuth API.

        GET https://api.anthropic.com/api/oauth/usage
        Returns windows: five_hour, seven_day, seven_day_sonnet
        """
        token = CredentialResolver.get_claude_token(account)
        if not token:
            logger.warning(f"Claude: no OAuth token for account {account.get('id')}")
            return []

        url = "https://api.anthropic.com/api/oauth/usage"
        headers = {
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
        }

        data = _http_get(url, headers)
        if data is None:
            return []

        windows = []
        for key in ("five_hour", "seven_day", "seven_day_sonnet"):
            window = data.get(key)
            if not window:
                continue
            utilization = window.get("utilization", 0)
            resets_at = window.get("resets_at")
            windows.append(
                {
                    "window_type": key,
                    "percentage": round(float(utilization), 1),
                    "resets_at": resets_at,
                    "tokens_used": 0,
                    "tokens_limit": 0,
                }
            )
        return windows

    @classmethod
    def _fetch_codex(cls, account: dict) -> list[dict]:
        """Fetch Codex usage — tries PTY /status first (default account only), falls back to HTTP API.

        PTY method: Launch `codex` interactively, send `/status`, parse usage.
        HTTP fallback: GET https://chatgpt.com/backend-api/wham/usage
        """
        # Only try PTY for the default codex account — PTY always uses
        # the default ~/.codex config and would return wrong data for
        # non-default accounts.
        config_path = account.get("config_path")
        is_default = not config_path or os.path.expanduser(config_path) == str(
            Path.home() / ".codex"
        )
        if is_default:
            pty_result = cls._fetch_codex_via_pty()
            if pty_result:
                return pty_result

        # HTTP API (uses account-specific credentials)
        access_token, chatgpt_account_id = CredentialResolver.get_codex_token(account)
        if not access_token:
            logger.warning(f"Codex: no OAuth token for account {account.get('id')}")
            return []

        url = "https://chatgpt.com/backend-api/wham/usage"
        headers = {
            "Authorization": f"Bearer {access_token}",
        }
        if chatgpt_account_id:
            headers["ChatGPT-Account-Id"] = chatgpt_account_id

        data = _http_get(url, headers)
        if data is None:
            return []

        windows = []

        def _extract_windows(rate_limit_obj: dict, prefix: str = "") -> None:
            """Extract primary/secondary windows from a rate_limit object."""
            for key in ("primary_window", "secondary_window"):
                window = rate_limit_obj.get(key)
                if not window:
                    continue
                used_pct = window.get("used_percent", 0)
                reset_at = window.get("reset_at")
                resets_at_str = None
                if reset_at:
                    try:
                        resets_at_str = datetime.fromtimestamp(
                            float(reset_at), tz=timezone.utc
                        ).strftime("%Y-%m-%dT%H:%M:%SZ")
                    except (ValueError, TypeError, OSError):
                        pass
                window_type = f"{prefix}_{key}" if prefix else key
                windows.append(
                    {
                        "window_type": window_type,
                        "percentage": round(float(used_pct), 1),
                        "resets_at": resets_at_str,
                        "tokens_used": 0,
                        "tokens_limit": 0,
                    }
                )

        # Derive base model name from additional_rate_limits
        # e.g. "GPT-5.3-Codex-Spark" → base "GPT-5.3-Codex"
        additional = data.get("additional_rate_limits") or []
        base_model = "Codex"
        if additional:
            first_name = additional[0].get("limit_name", "")
            if first_name:
                parts = first_name.rsplit("-", 1)
                if len(parts) == 2:
                    base_model = parts[0]
        else:
            # No additional_rate_limits (e.g. Plus plan) — try models_cache.json
            base_model = _get_codex_model_name(config_path) or "Codex"

        # Main rate limit (base model)
        rate_limit = data.get("rate_limit") or {}
        _extract_windows(rate_limit, prefix=base_model)

        # Additional rate limits (model variants) — only if account plan matches API plan
        account_plan = (account.get("plan") or "").lower()
        api_plan = (data.get("plan_type") or "").lower()
        if not account_plan or account_plan == api_plan:
            for extra in additional:
                limit_name = extra.get("limit_name", "")
                rl = extra.get("rate_limit", {})
                if rl:
                    _extract_windows(rl, prefix=limit_name)

        return windows

    @classmethod
    def _fetch_codex_via_pty(cls) -> Optional[list[dict]]:
        """Fetch Codex usage by running `codex` in PTY and sending /status.

        Parses percentage usage and reset times from the /status output.
        Returns list of window dicts, or None if PTY method fails.
        """
        try:
            from .pty_service import PtyRunner

            output = PtyRunner.run_interactive(
                cmd_list=["codex"],
                input_lines=["/status"],
                timeout=15,
                ready_pattern=r"(>|codex|prompt)",
                settle_time=2.0,
            )
            if not output:
                return None

            windows = []
            # Parse percentage patterns like "Usage: 45%" or "45% used"
            pct_pattern = re.compile(
                r"(\w[\w\s]*?)(?:usage|window|limit)?[:\s]+(\d+(?:\.\d+)?)\s*%", re.IGNORECASE
            )
            for match in pct_pattern.finditer(output):
                label = match.group(1).strip().lower().replace(" ", "_")
                pct = float(match.group(2))
                window_type = label if label else "primary_window"
                windows.append(
                    {
                        "window_type": window_type,
                        "percentage": round(pct, 1),
                        "resets_at": None,
                        "tokens_used": 0,
                        "tokens_limit": 0,
                    }
                )

            # Parse reset times like "Resets at 2025-01-15T10:00:00Z" or "resets in 2h"
            reset_pattern = re.compile(
                r"reset[s]?\s+(?:at\s+)?(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?Z?)",
                re.IGNORECASE,
            )
            reset_match = reset_pattern.search(output)
            if reset_match and windows:
                reset_str = reset_match.group(1)
                if not reset_str.endswith("Z"):
                    reset_str += "Z"
                for w in windows:
                    if not w["resets_at"]:
                        w["resets_at"] = reset_str

            return windows if windows else None
        except Exception as e:
            logger.debug(f"Codex PTY /status failed: {e}")
            return None

    @classmethod
    def _fetch_gemini(cls, account: dict) -> list[dict]:
        """Fetch Gemini usage from Google Cloud Code API.

        POST https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuota
        Returns buckets with remainingFraction and resetTime.
        """
        token = CredentialResolver.get_gemini_token(account)
        if not token:
            logger.warning(f"Gemini: no OAuth token for account {account.get('id')}")
            return []

        url = "https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuota"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        body = json.dumps({"project": "cloud-code-assist"}).encode("utf-8")

        data = _http_post(url, headers, body)
        if data is None:
            return []

        buckets = data.get("buckets", [])

        # Determine the latest major version family among all non-skipped models
        # so we can filter out older generations (e.g. gemini-2.x when gemini-3.x exists).
        major_versions: list[int] = []
        for bucket in buckets:
            model_id = bucket.get("modelId", "")
            if model_id.endswith("_vertex") or "2.0" in model_id or "2.5-flash" in model_id:
                continue
            # Extract major version: "gemini-3-pro-preview" -> 3, "gemini-2.5-pro" -> 2
            m = re.match(r"gemini-(\d+)", model_id)
            if m:
                major_versions.append(int(m.group(1)))

        latest_major = max(major_versions) if major_versions else 0

        windows = []
        for bucket in buckets:
            model_id = bucket.get("modelId", "gemini")
            # Skip Vertex AI duplicates, deprecated models, and flash variants
            if model_id.endswith("_vertex") or "2.0" in model_id or "2.5-flash" in model_id:
                continue

            # Skip models from older major version families
            m = re.match(r"gemini-(\d+)", model_id)
            if m and int(m.group(1)) < latest_major:
                logger.debug(
                    f"Gemini: skipping {model_id} (older major version than {latest_major})"
                )
                continue

            remaining = bucket.get("remainingFraction", 1.0)
            reset_time = bucket.get("resetTime")
            usage_pct = round((1.0 - float(remaining)) * 100, 1)

            resets_at_str = None
            if reset_time:
                try:
                    resets_at_str = reset_time if "T" in str(reset_time) else None
                except (ValueError, TypeError):
                    pass

            windows.append(
                {
                    "window_type": model_id,
                    "percentage": usage_pct,
                    "resets_at": resets_at_str,
                    "tokens_used": 0,
                    "tokens_limit": 0,
                }
            )
        return windows


# =============================================================================
# Helper functions (module-private)
# =============================================================================


def _get_codex_model_name(config_path: Optional[str]) -> Optional[str]:
    """Read the default model name from Codex's models_cache.json.

    Returns a display name like 'GPT-5.3-Codex' or None.
    """
    dirs_to_try = []
    if config_path:
        dirs_to_try.append(Path(os.path.expanduser(config_path)))
    dirs_to_try.append(Path.home() / ".codex")

    for d in dirs_to_try:
        cache_path = d / "models_cache.json"
        data = _read_json_file(cache_path)
        if data and data.get("models"):
            slug = data["models"][0].get("slug") or data["models"][0].get("display_name")
            if slug:
                # "gpt-5.3-codex" → "GPT-5.3-Codex"
                return slug.upper().replace("CODEX", "Codex")
    return None


def _http_get(url: str, headers: dict) -> Optional[dict]:
    """Perform an HTTP GET and return parsed JSON, or None on failure."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            if resp.status != 200:
                logger.error(f"HTTP GET {url} returned {resp.status}")
                return None
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        logger.error(f"HTTP GET {url} failed: {e.code} {e.reason}")
        return None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        logger.error(f"HTTP GET {url} network error: {e}")
        return None
    except json.JSONDecodeError:
        logger.error(f"HTTP GET {url} returned invalid JSON")
        return None


def _http_post(url: str, headers: dict, body: bytes) -> Optional[dict]:
    """Perform an HTTP POST and return parsed JSON, or None on failure."""
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            if resp.status not in (200, 201):
                logger.error(f"HTTP POST {url} returned {resp.status}")
                return None
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        logger.error(f"HTTP POST {url} failed: {e.code} {e.reason}")
        return None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        logger.error(f"HTTP POST {url} network error: {e}")
        return None
    except json.JSONDecodeError:
        logger.error(f"HTTP POST {url} returned invalid JSON")
        return None


def _read_keychain(service: str, json_field_path: str) -> Optional[str]:
    """Read a JSON value from macOS Keychain.

    Runs: security find-generic-password -s <service> -w
    Then parses the JSON output and extracts the field at json_field_path (dot-separated).
    """
    raw = _read_keychain_raw(service)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        parts = json_field_path.split(".")
        for part in parts:
            data = data[part]
        return str(data) if data else None
    except (json.JSONDecodeError, KeyError, TypeError, IndexError):
        return None


def _read_keychain_raw(service: str) -> Optional[str]:
    """Read raw password string from macOS Keychain."""
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-w"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _read_json_file(path: Path) -> Optional[dict]:
    """Read and parse a JSON file. Returns None if not found or invalid."""
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, PermissionError):
        pass
    return None


def _read_json_field(path: Path, field_path: list[str]) -> Optional[str]:
    """Read a nested field from a JSON file. Returns None if not found."""
    data = _read_json_file(path)
    if not data:
        return None
    try:
        for key in field_path:
            data = data[key]
        return str(data) if data else None
    except (KeyError, TypeError, IndexError):
        return None


def _refresh_google_token(refresh_token: str, client_id: str, client_secret: str) -> Optional[str]:
    """Refresh a Google OAuth access token. Returns new access_token or None."""
    url = "https://oauth2.googleapis.com/token"
    body = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode("utf-8")
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    data = _http_post(url, headers, body)
    if data and data.get("access_token"):
        return data["access_token"]
    return None
