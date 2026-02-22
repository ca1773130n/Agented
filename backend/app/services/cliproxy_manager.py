"""CLIProxyAPI lifecycle manager.

Manages a SINGLE global CLIProxyAPI process that serves all Claude Code
accounts through OAuth credentials stored in ~/.cli-proxy-api/.

CLIProxyAPI reads credential files (claude-{email}.json) from its auth-dir
and exposes an OpenAI-compatible /v1/chat/completions endpoint. New accounts
are added via ``cliproxyapi --claude-login`` which opens a browser for OAuth.
"""

import atexit
import hashlib
import json
import logging
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import httpx
import yaml

logger = logging.getLogger(__name__)

# Global CLIProxyAPI config location
_GLOBAL_CONFIG = Path.home() / ".cli-proxy-api" / "config.yaml"
_GLOBAL_AUTH_DIR = Path.home() / ".cli-proxy-api"


class CLIProxyManager:
    """Singleton manager for a single global CLIProxyAPI instance."""

    _process: Optional[subprocess.Popen] = None
    _port: int = 8317
    _api_key: str = "not-needed"
    _config_loaded: bool = False
    _lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @classmethod
    def kill_orphans(cls) -> None:
        """Kill all existing cliproxyapi processes (cleanup from prior runs)."""
        try:
            subprocess.run(["pkill", "-f", "cliproxyapi"], capture_output=True, timeout=5)
            time.sleep(0.5)
        except Exception as e:
            logger.debug("Process cleanup: %s", e)

    @classmethod
    def start(cls) -> bool:
        """Start the global CLIProxyAPI using ~/.cli-proxy-api/config.yaml.

        Returns True if the proxy is running and healthy.
        """
        with cls._lock:
            if cls._process is not None:
                return cls.is_healthy()

        # Read config
        conf = cls._read_config()
        if conf is None:
            cls._write_default_config()
            conf = cls._read_config()
            if conf is None:
                logger.warning("Failed to create CLIProxyAPI config")
                return False

        cls._port = conf.get("port", 8317)
        keys = conf.get("api-keys", [])
        cls._api_key = keys[0] if keys else "not-needed"
        cls._config_loaded = True

        # Check if already running on this port
        if cls._check_port_healthy():
            logger.info("CLIProxyAPI already running on port %d", cls._port)
            return True

        # Start the process
        config_path = str(_GLOBAL_CONFIG)
        cmd = ["cliproxyapi", "--config", config_path]
        logger.info("Starting CLIProxyAPI on port %d", cls._port)

        try:
            with cls._lock:
                cls._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )

            # Wait for readiness
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if cls._check_port_healthy():
                    logger.info("CLIProxyAPI ready on port %d", cls._port)
                    return True
                time.sleep(0.5)

            logger.warning("CLIProxyAPI did not become ready within 10s")
            return False

        except FileNotFoundError:
            logger.warning("cliproxyapi binary not found")
            return False
        except Exception as exc:
            logger.warning("Failed to start CLIProxyAPI: %s", exc)
            return False

    @classmethod
    def stop(cls) -> None:
        """Stop the managed CLIProxyAPI process."""
        with cls._lock:
            proc = cls._process
            cls._process = None

        if proc is None:
            return

        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGTERM)
            proc.wait(timeout=5)
            logger.info("Stopped CLIProxyAPI (pid=%d)", proc.pid)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        except Exception as exc:
            logger.error("Error stopping CLIProxyAPI: %s", exc)

    # ------------------------------------------------------------------
    # Health & URL
    # ------------------------------------------------------------------

    @classmethod
    def is_healthy(cls) -> bool:
        """Return True if the proxy responds to GET /v1/models."""
        return cls._check_port_healthy()

    @classmethod
    def get_base_url(cls) -> Optional[str]:
        """Return the base URL if the proxy is healthy, else None."""
        if cls._check_port_healthy():
            return f"http://127.0.0.1:{cls._port}/v1"
        return None

    @classmethod
    def get_url_and_key(cls) -> Optional[Tuple[str, str]]:
        """Return (base_url, api_key) if proxy is healthy, else None."""
        if cls._check_port_healthy():
            return f"http://127.0.0.1:{cls._port}/v1", cls._api_key
        return None

    # ------------------------------------------------------------------
    # Account management
    # ------------------------------------------------------------------

    @classmethod
    def list_accounts(cls) -> List[dict]:
        """List all Claude Code credential files from auth-dir."""
        accounts = []
        for path in _GLOBAL_AUTH_DIR.glob("claude-*.json"):
            try:
                import json

                data = json.loads(path.read_text())
                accounts.append(
                    {
                        "email": data.get("email", ""),
                        "type": data.get("type", "claude"),
                        "disabled": data.get("disabled", False),
                        "expired": data.get("expired", ""),
                        "last_refresh": data.get("last_refresh", ""),
                        "file": path.name,
                    }
                )
            except Exception as e:
                logger.debug("Account file parse: %s", e)
                continue
        return accounts

    @classmethod
    def start_login(cls) -> subprocess.Popen:
        """Start ``cliproxyapi --claude-login`` for interactive OAuth.

        Returns the Popen handle so the caller can stream stdout/stderr.
        The login process opens a browser; after OAuth completes, a new
        credential file appears in ~/.cli-proxy-api/.
        """
        config_path = str(_GLOBAL_CONFIG)
        return subprocess.Popen(
            ["cliproxyapi", "--config", config_path, "--claude-login"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    # ------------------------------------------------------------------
    # Install
    # ------------------------------------------------------------------

    @classmethod
    def install_if_needed(cls) -> bool:
        """Install cliproxyapi via Homebrew if not on PATH."""
        if shutil.which("cliproxyapi"):
            return True
        logger.info("cliproxyapi not found, attempting install via brew...")
        try:
            result = subprocess.run(
                ["brew", "install", "cliproxyapi"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0 and shutil.which("cliproxyapi"):
                logger.info("cliproxyapi installed successfully")
                return True
            logger.warning("cliproxyapi install failed: %s", result.stderr[:200])
        except Exception as exc:
            logger.warning("cliproxyapi install error: %s", exc)
        return False

    # ------------------------------------------------------------------
    # Legacy compatibility (used by super_agents.py, sketch_routing_service)
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls, account_id: int) -> Optional[object]:
        """Legacy: return a proxy-like object if the global proxy is healthy."""
        if cls._check_port_healthy():
            return cls  # Return the class itself as it has base_url
        return None

    @classmethod
    def is_proxy_enabled(cls, account_id: int) -> bool:
        """Return True if CLIProxyAPI is running and healthy."""
        return cls._check_port_healthy()

    @classmethod
    def list_instances(cls) -> Dict[int, dict]:
        """Legacy: return status for the global instance."""
        return {
            0: {
                "port": cls._port,
                "backend_type": "claude",
                "healthy": cls._check_port_healthy(),
            }
        }

    # ------------------------------------------------------------------
    # Token refresh
    # ------------------------------------------------------------------

    @classmethod
    def refresh_expired_tokens(cls, timeout_per_account: int = 60) -> dict:
        """Refresh all expired OAuth tokens using Playwright browser automation.

        Uses Chrome profiles' cookies to authenticate the OAuth flow.  Each
        Chrome profile may be logged into a different claude.ai account, so the
        method tries each profile and checks which credential files are updated.

        Returns dict with 'refreshed', 'skipped', and 'failed' lists.
        """
        result = {"refreshed": [], "skipped": [], "failed": []}
        accounts = cls.list_accounts()

        if not accounts:
            logger.info("No CLIProxyAPI accounts found, skipping token refresh")
            return result

        now = datetime.now(timezone.utc)
        expired_emails = set()

        for acct in accounts:
            email = acct.get("email", "unknown")

            if acct.get("disabled", False):
                result["skipped"].append(email)
                logger.debug("Skipping disabled account: %s", email)
                continue

            expired_str = acct.get("expired", "")
            if not expired_str:
                result["skipped"].append(email)
                logger.debug("Skipping account with no expiry: %s", email)
                continue

            try:
                expired_dt = datetime.fromisoformat(expired_str.replace("Z", "+00:00"))
                if expired_dt.tzinfo is None:
                    expired_dt = expired_dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                result["skipped"].append(email)
                logger.debug("Skipping account with unparseable expiry: %s", email)
                continue

            if expired_dt > now:
                result["skipped"].append(email)
                logger.debug("Token still valid for %s (expires %s)", email, expired_str)
                continue

            logger.info("Token expired for %s (expired %s)", email, expired_str)
            expired_emails.add(email)

        if not expired_emails:
            return result

        # Snapshot credential file timestamps before refresh attempts
        pre_snapshots = cls._snapshot_cred_expiries()

        # Find all Chrome profiles with claude.ai session cookies
        chrome_profiles = cls._find_chrome_profiles_with_session()

        if not chrome_profiles:
            logger.warning("No Chrome profiles with claude.ai sessions found")
            result["failed"].extend(expired_emails)
            return result

        # Try each Chrome profile until all expired accounts are refreshed
        for profile_path in chrome_profiles:
            if not expired_emails:
                break

            try:
                cls._run_oauth_flow(profile_path, timeout_per_account)
            except Exception as exc:
                logger.debug("OAuth flow failed with profile '%s': %s", profile_path.name, exc)
                continue

            # Check which credential files were updated
            post_snapshots = cls._snapshot_cred_expiries()
            for email in list(expired_emails):
                new_expiry = post_snapshots.get(email)
                old_expiry = pre_snapshots.get(email)
                if new_expiry and new_expiry != old_expiry:
                    try:
                        new_dt = datetime.fromisoformat(new_expiry.replace("Z", "+00:00"))
                        if new_dt.tzinfo is None:
                            new_dt = new_dt.replace(tzinfo=timezone.utc)
                        if new_dt > datetime.now(timezone.utc):
                            result["refreshed"].append(email)
                            expired_emails.discard(email)
                            logger.info("Successfully refreshed token for %s", email)
                    except (ValueError, TypeError):
                        pass

            # Also check for newly created credential files
            for email_key, new_expiry in post_snapshots.items():
                if email_key not in pre_snapshots and email_key in expired_emails:
                    result["refreshed"].append(email_key)
                    expired_emails.discard(email_key)

            pre_snapshots = post_snapshots

        # Any remaining expired accounts are failures
        for email in expired_emails:
            result["failed"].append(email)
            logger.warning("Failed to refresh token for %s", email)

        return result

    @classmethod
    def _snapshot_cred_expiries(cls) -> Dict[str, str]:
        """Return {email: expired_str} for all credential files."""
        snapshots = {}
        for path in _GLOBAL_AUTH_DIR.glob("claude-*.json"):
            try:
                data = json.loads(path.read_text())
                email = data.get("email", "")
                if email:
                    snapshots[email] = data.get("expired", "")
            except Exception as e:
                logger.debug("Credential file parse: %s", e)
                continue
        return snapshots

    @classmethod
    def _find_chrome_profiles_with_session(cls) -> List[Path]:
        """Find all Chrome profiles that have a claude.ai sessionKey cookie."""
        chrome_dir = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
        if not chrome_dir.is_dir():
            return []

        profiles = []
        candidates = ["Default"] + [f"Profile {i}" for i in range(1, 20)]
        for name in candidates:
            cookies_db = chrome_dir / name / "Cookies"
            if not cookies_db.exists():
                continue
            # Quick check: does this profile have a claude.ai sessionKey?
            try:
                import tempfile

                tmp = Path(tempfile.mktemp(suffix=".db"))
                shutil.copy2(str(cookies_db), str(tmp))
                conn = sqlite3.connect(str(tmp))
                row = conn.execute(
                    "SELECT 1 FROM cookies WHERE host_key LIKE '%claude.ai%' "
                    "AND name = 'sessionKey' LIMIT 1"
                ).fetchone()
                conn.close()
                tmp.unlink(missing_ok=True)
                if row:
                    profiles.append(chrome_dir / name)
            except Exception as e:
                logger.debug("Chrome profile check: %s", e)
                continue
        return profiles

    @classmethod
    def _run_oauth_flow(cls, chrome_profile: Path, timeout: int = 60) -> bool:
        """Run a single cliproxyapi OAuth flow using cookies from a Chrome profile.

        Spawns ``cliproxyapi --claude-login --no-browser``, captures the OAuth URL,
        and completes the flow with Playwright using the given Chrome profile's cookies.
        """
        config_path = str(_GLOBAL_CONFIG)
        cmd = ["cliproxyapi", "--config", config_path, "--claude-login", "--no-browser"]

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        except FileNotFoundError:
            logger.warning("cliproxyapi binary not found")
            return False

        # Read stdout lines until we find the OAuth URL (15s deadline)
        oauth_url = None
        deadline = time.monotonic() + 15

        try:
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    break
                line = proc.stdout.readline()
                if not line:
                    time.sleep(0.1)
                    continue

                url_match = re.search(r"(https?://\S+)", line)
                if url_match:
                    candidate = url_match.group(1)
                    if (
                        "claude.ai" in candidate
                        or "anthropic" in candidate
                        or "oauth" in candidate.lower()
                    ):
                        oauth_url = candidate
                        break
        except Exception as exc:
            logger.warning("Error reading cliproxyapi stdout: %s", exc)

        if not oauth_url:
            logger.warning("No OAuth URL found in cliproxyapi output")
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception as e:
                logger.debug("Process cleanup: %s", e)
            return False

        # Parse callback port from redirect_uri
        try:
            parsed = urlparse(oauth_url)
            qs = parse_qs(parsed.query)
            redirect_uri = qs.get("redirect_uri", [""])[0]
            callback_port = urlparse(redirect_uri).port if redirect_uri else None
        except Exception as e:
            logger.debug("OAuth URL parse: %s", e)
            callback_port = None

        if not callback_port:
            logger.warning("Could not parse callback port from OAuth URL")
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception as e:
                logger.debug("Process cleanup: %s", e)
            return False

        # Run Playwright OAuth flow with this Chrome profile's cookies
        oauth_success = cls._run_playwright_oauth(
            oauth_url, callback_port, timeout, chrome_profile=chrome_profile
        )

        if not oauth_success:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception as e:
                logger.debug("Process cleanup: %s", e)
            return False

        # Wait for cliproxyapi to finish writing the token
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

        return True

    @classmethod
    def _extract_chrome_cookies(cls, profile_path: Path, domains: List[str]) -> List[dict]:
        """Decrypt cookies from a Chrome profile's Cookies SQLite database.

        On macOS, Chrome encrypts cookie values using AES-128-CBC with a key
        derived from the "Chrome Safe Storage" Keychain entry via PBKDF2.
        """
        cookies_db = profile_path / "Cookies"
        if not cookies_db.exists():
            return []

        # Get the encryption password from macOS Keychain
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-s", "Chrome Safe Storage", "-w"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.debug("Could not read Chrome Safe Storage from Keychain")
                return []
            chrome_pass = result.stdout.strip()
        except Exception as exc:
            logger.debug("Keychain access error: %s", exc)
            return []

        # Derive the decryption key (PBKDF2 with salt='saltysalt', 1003 iterations, 16-byte key)
        key = hashlib.pbkdf2_hmac("sha1", chrome_pass.encode(), b"saltysalt", 1003, dklen=16)

        # Copy database to temp file (Chrome may have it locked)
        import tempfile

        tmp_db = Path(tempfile.mktemp(suffix=".db"))
        try:
            shutil.copy2(str(cookies_db), str(tmp_db))
        except Exception as exc:
            logger.debug("Could not copy Chrome cookies DB: %s", exc)
            return []

        extracted = []
        try:
            conn = sqlite3.connect(str(tmp_db))
            # Build WHERE clause for domains
            domain_clauses = " OR ".join(f"host_key LIKE '%{d}%'" for d in domains)
            rows = conn.execute(
                f"SELECT host_key, name, encrypted_value, path, is_secure, "
                f"is_httponly, expires_utc, samesite FROM cookies "
                f"WHERE {domain_clauses}"
            ).fetchall()
            conn.close()

            for host, name, enc_val, path, secure, httponly, expires, samesite in rows:
                value = cls._decrypt_chrome_cookie(enc_val, key)
                if not value:
                    continue

                # Chrome stores expires_utc as microseconds since 1601-01-01
                # Convert to Unix epoch seconds
                if expires and expires > 0:
                    epoch_seconds = (expires / 1_000_000) - 11644473600
                else:
                    epoch_seconds = -1

                sameSite_map = {0: "None", 1: "Lax", 2: "Strict"}

                cookie = {
                    "name": name,
                    "value": value,
                    "domain": host,
                    "path": path or "/",
                    "secure": bool(secure),
                    "httpOnly": bool(httponly),
                    "sameSite": sameSite_map.get(samesite, "None"),
                }
                if epoch_seconds > 0:
                    cookie["expires"] = epoch_seconds

                extracted.append(cookie)
        except Exception as exc:
            logger.debug("Error reading Chrome cookies: %s", exc)
        finally:
            tmp_db.unlink(missing_ok=True)

        return extracted

    @staticmethod
    def _decrypt_chrome_cookie(encrypted_value: bytes, key: bytes) -> str:
        """Decrypt a single Chrome cookie value (macOS v10 encryption).

        Chrome on macOS encrypts cookies with AES-128-CBC using a key derived
        from the "Chrome Safe Storage" Keychain entry via PBKDF2.  The decrypted
        plaintext is prefixed with a 32-byte header that must be stripped.
        """
        if not encrypted_value:
            return ""

        # Unencrypted cookies (no prefix)
        if not encrypted_value[:3] == b"v10":
            try:
                return encrypted_value.decode("utf-8")
            except UnicodeDecodeError:
                return ""

        try:
            from cryptography.hazmat.primitives import padding as sym_padding
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        except ImportError:
            logger.debug("cryptography package not installed, cannot decrypt Chrome cookies")
            return ""

        # v10: AES-128-CBC, IV = 16 spaces
        iv = b" " * 16
        encrypted_data = encrypted_value[3:]  # Strip 'v10' prefix

        try:
            cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
            decryptor = cipher.decryptor()
            decrypted = decryptor.update(encrypted_data) + decryptor.finalize()

            # Remove PKCS7 padding
            unpadder = sym_padding.PKCS7(128).unpadder()
            decrypted = unpadder.update(decrypted) + unpadder.finalize()

            # Chrome prepends a 32-byte header to the plaintext; strip it
            if len(decrypted) > 32:
                decrypted = decrypted[32:]
            else:
                return ""

            return decrypted.decode("utf-8")
        except Exception as e:
            logger.debug("Cookie decryption: %s", e)
            return ""

    @classmethod
    def _run_playwright_oauth(
        cls,
        oauth_url: str,
        callback_port: int,
        timeout: int = 60,
        chrome_profile: Optional[Path] = None,
    ) -> bool:
        """Complete OAuth flow in a non-headless Chrome browser using Playwright.

        Decrypts cookies from the given Chrome profile and injects them into the
        Playwright context so the user is already authenticated on claude.ai.
        Uses ``channel='chrome'`` and ``headless=False`` to bypass Cloudflare.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning(
                "Playwright not installed. Install with: "
                "uv add playwright && uv run playwright install chromium"
            )
            return False

        # Extract cookies from Chrome profile
        chrome_cookies = []
        if chrome_profile:
            chrome_cookies = cls._extract_chrome_cookies(
                chrome_profile,
                domains=["claude.ai", "anthropic.com", "accounts.google.com"],
            )
            if chrome_cookies:
                logger.info(
                    "Extracted %d cookies from Chrome profile '%s'",
                    len(chrome_cookies),
                    chrome_profile.name,
                )

        browser_profile = _GLOBAL_AUTH_DIR / ".browser-profile"
        browser_profile.mkdir(parents=True, exist_ok=True)

        try:
            with sync_playwright() as p:
                # Use actual Chrome (not Chromium) in non-headless mode to
                # bypass Cloudflare bot detection on claude.ai.
                context = p.chromium.launch_persistent_context(
                    str(browser_profile),
                    headless=False,
                    channel="chrome",
                )

                # Inject decrypted Chrome cookies
                if chrome_cookies:
                    try:
                        context.add_cookies(chrome_cookies)
                        logger.debug(
                            "Injected %d cookies into Playwright context", len(chrome_cookies)
                        )
                    except Exception as exc:
                        logger.debug("Failed to inject some cookies: %s", exc)

                page = context.pages[0] if context.pages else context.new_page()

                page.goto(oauth_url, wait_until="domcontentloaded")

                # Wait for page to settle (Cloudflare, redirects)
                time.sleep(3)

                # Click "Authorize" button if present on the OAuth consent page
                try:
                    authorize_btn = page.get_by_role("button", name="Authorize")
                    if authorize_btn.is_visible(timeout=5000):
                        logger.info("Clicking 'Authorize' button on OAuth consent page")
                        authorize_btn.click()
                except Exception as e:
                    logger.debug("OAuth authorize button: %s", e)

                try:
                    page.wait_for_url(
                        f"**/localhost:{callback_port}/**",
                        timeout=timeout * 1000,
                    )
                    context.close()
                    return True
                except Exception as e:
                    # Check if stuck on login page
                    logger.warning("OAuth flow error: %s", e)
                    current_url = page.url
                    if "login" in current_url or "signin" in current_url:
                        logger.warning(
                            "OAuth redirected to login page — user must log in to claude.ai "
                            "manually first. Run: cliproxyapi --claude-login"
                        )
                    else:
                        logger.warning(
                            "OAuth flow timed out (page URL: %s). "
                            "Try manual login: cliproxyapi --claude-login",
                            current_url,
                        )
                    context.close()
                    return False
        except Exception as exc:
            logger.warning("Playwright browser error: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @classmethod
    def _ensure_config_loaded(cls) -> None:
        """Load port and api_key from config.yaml if not already loaded."""
        if cls._config_loaded:
            return
        conf = cls._read_config()
        if conf:
            cls._port = conf.get("port", 8317)
            keys = conf.get("api-keys", [])
            cls._api_key = keys[0] if keys else "not-needed"
            cls._config_loaded = True

    @classmethod
    def _check_port_healthy(cls) -> bool:
        """Ping the proxy at the configured port."""
        cls._ensure_config_loaded()
        try:
            resp = httpx.get(
                f"http://127.0.0.1:{cls._port}/v1/models",
                headers={"Authorization": f"Bearer {cls._api_key}"},
                timeout=2,
            )
            return resp.status_code == 200
        except Exception as e:
            logger.debug("Health check: %s", e)
            return False

    @classmethod
    def _read_config(cls) -> Optional[dict]:
        """Read ~/.cli-proxy-api/config.yaml."""
        if not _GLOBAL_CONFIG.exists():
            return None
        try:
            return yaml.safe_load(_GLOBAL_CONFIG.read_text())
        except Exception as e:
            logger.warning("Config read error: %s", e)
            return None

    @classmethod
    def _write_default_config(cls) -> None:
        """Create a default config.yaml if it doesn't exist."""
        _GLOBAL_AUTH_DIR.mkdir(parents=True, exist_ok=True)
        config = {
            "port": 8317,
            "auth-dir": str(_GLOBAL_AUTH_DIR),
            "api-keys": ["any-secret-key-here"],
        }
        _GLOBAL_CONFIG.write_text(yaml.dump(config, default_flow_style=False))
        logger.info("Created default CLIProxyAPI config at %s", _GLOBAL_CONFIG)


# Register shutdown hook
atexit.register(CLIProxyManager.stop)
