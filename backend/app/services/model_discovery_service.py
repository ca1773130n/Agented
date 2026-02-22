"""Model discovery service — detects available models via PTY, local files, and APIs.

Discovery strategy per backend:
  - Claude:   local stats-cache.json (PTY fails inside nested Claude sessions)
  - Codex:    PTY `/model` command (returns curated list), local files as fallback
  - OpenCode: CLI `opencode models` command, local config files as fallback
  - Gemini:   Google Cloud Code quota API (returns per-model buckets)

Never uses hardcoded model lists.
"""

import json
import logging
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CACHE_KEY = "model_discovery_cache"
_CACHE_MAX_AGE_DAYS = 7
# Bump this version whenever normalization logic changes to invalidate stale caches
_CACHE_SCHEMA_VERSION = 14


class ModelDiscoveryService:
    """Discovers model lists from local CLI config/cache files with DB-backed weekly cache."""

    @classmethod
    def _discover_raw(cls, backend_type: str) -> list[str]:
        """Discover raw model IDs (before normalization) for a backend."""
        if backend_type == "claude":
            models = cls._discover_claude_models_local()
            if not models:
                models = cls._discover_claude_models_pty()
            # Merge additional sources — local/PTY only shows models you've used.
            # CLIProxyAPI and OpenCode CLI list all available anthropic models.
            for extra in [
                cls._discover_models_via_cliproxy("anthropic"),
                cls._discover_anthropic_models_via_opencode(),
            ]:
                if extra:
                    existing = set(models or [])
                    for m in extra:
                        if m not in existing:
                            (models := models or []).append(m)
                            existing.add(m)
            return models or []
        elif backend_type == "codex":
            models = cls._discover_codex_models_pty()
            if not models:
                models = cls._discover_codex_models_local()
            if not models:
                models = cls._discover_models_via_cliproxy("openai")
            return models or []
        elif backend_type == "opencode":
            models = cls._discover_opencode_models_cli()
            if not models:
                models = cls._discover_opencode_models_local()
            return models or []
        elif backend_type == "gemini":
            models = cls._discover_gemini_models_api()
            if not models:
                models = cls._discover_gemini_models_local()
            if not models:
                models = cls._discover_models_via_cliproxy("google")
            return models or []
        return []

    # Providers whose models are accessible through other backends (Claude, Codex, Gemini).
    # When selecting a default model for the "opencode" backend, skip these so the
    # default is an OpenCode-native model, not a duplicate of another backend.
    _PROXY_PROVIDERS = {"anthropic", "openai", "google"}

    @classmethod
    def get_default_model_id(cls, backend_type: str) -> Optional[str]:
        """Get the first raw (unnormalized) model ID for a backend.

        Used for API calls where the actual model ID is needed
        (e.g. CLIProxyAPI routing by model name prefix).

        For the OpenCode backend, filters out models from providers already
        served by other backends (anthropic, openai, google) so the default
        is an OpenCode-native model.
        """
        raw = cls._discover_raw(backend_type)
        if not raw:
            return None

        if backend_type == "opencode":
            # Prefer native models (not anthropic/openai/google which are served by other backends)
            native = [
                m
                for m in raw
                if "/" not in m or m.split("/", 1)[0].lower() not in cls._PROXY_PROVIDERS
            ]
            if not native:
                return raw[0]
            # Among native models, prefer free-tier models (e.g. glm-4.7-free)
            free = [m for m in native if "free" in m.lower()]
            return free[0] if free else native[0]

        return raw[0]

    @classmethod
    def discover_models(cls, backend_type: str) -> list[str]:
        """Discover models for a backend type.

        1. Check DB cache — if fresh (< 7 days), return cached list
        2. Claude: local files first (PTY fails inside nested sessions)
           Codex: PTY `/model` first (returns curated list), local files as fallback
        3. Normalize and cache results
        4. Return empty list if nothing found (no hardcoded fallbacks)
        """
        cached = cls._get_cached_models(backend_type)
        if cached is not None:
            return cached

        models = cls._discover_raw(backend_type)
        from_pty = False  # PTY state tracking for normalization
        if backend_type == "codex" and models:
            # Check if models came from PTY (discover_raw tries PTY first)
            pty_models = cls._discover_codex_models_pty()
            from_pty = pty_models is not None and len(pty_models) > 0

        if models:
            models = cls._normalize_models(backend_type, models, from_pty=from_pty)
        else:
            models = []

        if models:
            cls._set_cached_models(backend_type, models)
        return models

    # ----- Local file discovery (preferred) -----

    @classmethod
    def _get_claude_config_dirs(cls) -> list[Path]:
        """Get all Claude config directories: default paths + account-specific config_paths."""
        dirs = [Path.home() / ".claude", Path.home() / ".config" / "claude"]
        try:
            from ..db.backends import get_backend_accounts

            accounts = get_backend_accounts("backend-claude")
            for acct in accounts:
                config_path = acct.get("config_path", "")
                if config_path:
                    expanded = Path(os.path.expanduser(config_path))
                    if expanded not in dirs:
                        dirs.append(expanded)
        except Exception as e:
            logger.debug(f"Failed to load Claude account config paths: {e}")
        return dirs

    @classmethod
    def _discover_claude_models_local(cls) -> Optional[list[str]]:
        """Discover Claude models from stats-cache.json modelUsage keys.

        Checks default dirs (~/.claude, ~/.config/claude) and all account-specific
        config_path directories from the database.
        """
        all_models = set()

        for base in cls._get_claude_config_dirs():
            stats_file = base / "stats-cache.json"
            if not stats_file.exists():
                continue
            try:
                data = json.loads(stats_file.read_text())
                model_usage = data.get("modelUsage", {})
                if not model_usage:
                    continue
                # Keys are raw model IDs like "claude-opus-4-6-20250514"
                all_models.update(model_usage.keys())
                logger.info(f"Claude models from {stats_file}: {list(model_usage.keys())}")
            except (json.JSONDecodeError, OSError) as e:
                logger.debug(f"Failed to read {stats_file}: {e}")

        if all_models:
            return list(all_models)

        # Also try reading model IDs from session history
        for base in cls._get_claude_config_dirs():
            history_file = base / "history.jsonl"
            if not history_file.exists():
                continue
            try:
                models = cls._extract_models_from_claude_history(history_file)
                if models:
                    logger.info(f"Claude models from {history_file}: {models}")
                    all_models.update(models)
            except (OSError, IOError) as e:
                logger.debug(f"Failed to read {history_file}: {e}")

        return list(all_models) if all_models else None

    @classmethod
    def _extract_models_from_claude_history(cls, history_path: Path) -> Optional[list[str]]:
        """Extract unique model IDs from Claude's history.jsonl."""
        models = set()
        id_pattern = re.compile(r"claude-(?:opus|sonnet|haiku)-[\d][\w.-]*")
        try:
            with open(history_path, "r", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    for match in id_pattern.finditer(line):
                        models.add(match.group(0))
        except (OSError, IOError):
            pass
        return list(models) if models else None

    @classmethod
    def _get_codex_config_dirs(cls) -> list[Path]:
        """Get all Codex config directories: default path + account-specific config_paths."""
        dirs = [Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))]
        try:
            from ..db.backends import get_backend_accounts

            accounts = get_backend_accounts("backend-codex")
            for acct in accounts:
                config_path = acct.get("config_path", "")
                if config_path:
                    expanded = Path(os.path.expanduser(config_path))
                    if expanded not in dirs:
                        dirs.append(expanded)
        except Exception as e:
            logger.debug(f"Failed to load Codex account config paths: {e}")
        return dirs

    @classmethod
    def _get_gemini_config_dirs(cls) -> list[Path]:
        """Get all Gemini config directories: default path + account-specific config_paths."""
        dirs = [Path(os.environ.get("GEMINI_CLI_HOME", str(Path.home() / ".gemini")))]
        try:
            from ..db.backends import get_backend_accounts

            accounts = get_backend_accounts("backend-gemini")
            for acct in accounts:
                config_path = acct.get("config_path", "")
                if config_path:
                    expanded = Path(os.path.expanduser(config_path))
                    if expanded not in dirs:
                        dirs.append(expanded)
        except Exception as e:
            logger.debug(f"Failed to load Gemini account config paths: {e}")
        return dirs

    @classmethod
    def _discover_codex_models_local(cls) -> Optional[list[str]]:
        """Discover Codex models from models_cache.json.

        Checks default path and all account-specific config_path directories.
        Only includes models with visibility='list' (matching what `/model` shows).
        """
        all_models: list[str] = []
        seen: set[str] = set()

        for codex_home in cls._get_codex_config_dirs():
            cache_file = codex_home / "models_cache.json"
            if not cache_file.exists():
                continue
            try:
                data = json.loads(cache_file.read_text())
                entries = []
                if isinstance(data, list):
                    entries = data
                elif isinstance(data, dict):
                    entries = data.get("models", [])

                for entry in entries:
                    slug = None
                    if isinstance(entry, dict) and "slug" in entry:
                        if entry.get("visibility") == "list":
                            slug = entry["slug"]
                    elif isinstance(entry, str):
                        slug = entry
                    if slug and slug not in seen:
                        seen.add(slug)
                        all_models.append(slug)
                if all_models:
                    logger.info(f"Codex models from {cache_file}: {all_models}")
            except (json.JSONDecodeError, OSError) as e:
                logger.debug(f"Failed to read {cache_file}: {e}")

        if all_models:
            return all_models

        # Secondary: read default model from config.toml in any config dir
        for codex_home in cls._get_codex_config_dirs():
            config_file = codex_home / "config.toml"
            if config_file.exists():
                try:
                    content = config_file.read_text()
                    match = re.search(r'^model\s*=\s*"([^"]+)"', content, re.MULTILINE)
                    if match:
                        logger.info(f"Codex model from config.toml: {match.group(1)}")
                        return [match.group(1)]
                except OSError as e:
                    logger.debug(f"Failed to read {config_file}: {e}")

        return None

    # ----- Gemini API discovery -----

    @classmethod
    def _discover_gemini_models_api(cls) -> Optional[list[str]]:
        """Discover Gemini models via the quota API using the first available account."""
        try:
            from ..database import get_all_accounts_with_health
            from .provider_usage_client import ProviderUsageClient

            accounts = get_all_accounts_with_health("gemini")
            for account in accounts:
                windows = ProviderUsageClient.fetch_usage(account, "gemini")
                if windows:
                    models = [w["window_type"] for w in windows]
                    logger.info(f"Gemini models from quota API: {models}")
                    return models
        except Exception as e:
            logger.warning(f"Gemini model discovery via API failed: {e}")
        return None

    @classmethod
    def _discover_gemini_models_local(cls) -> Optional[list[str]]:
        """Discover Gemini models from local session files and settings.

        Checks account-specific config directories for any model references
        in session chat logs or settings.
        """
        all_models = set()

        for gemini_home in cls._get_gemini_config_dirs():
            # Check settings.json for model field
            for settings_path in [
                gemini_home / "settings.json",
                gemini_home / ".gemini" / "settings.json",
            ]:
                if settings_path.exists():
                    try:
                        data = json.loads(settings_path.read_text())
                        model = data.get("model") or data.get("defaultModel")
                        if model:
                            all_models.add(model)
                    except (json.JSONDecodeError, OSError):
                        pass

            # Check state.json for last-used model
            for state_path in [gemini_home / "state.json", gemini_home / ".gemini" / "state.json"]:
                if state_path.exists():
                    try:
                        data = json.loads(state_path.read_text())
                        model = data.get("model") or data.get("lastModel")
                        if model:
                            all_models.add(model)
                    except (json.JSONDecodeError, OSError):
                        pass

        if all_models:
            logger.info(f"Gemini models from local files: {list(all_models)}")
            return list(all_models)
        return None

    # ----- CLIProxyAPI discovery (fallback) -----

    @classmethod
    def _discover_models_via_cliproxy(cls, owned_by: str) -> Optional[list[str]]:
        """Discover models from a running CLIProxyAPI instance filtered by owned_by.

        Args:
            owned_by: Filter models by owner (e.g. "google", "openai", "anthropic").
        """
        try:
            from .conversation_streaming import _find_cliproxy

            result = _find_cliproxy()
            if not result:
                return None
            base_url, api_key = result

            import httpx

            resp = httpx.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=5,
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            models = sorted(
                [m["id"] for m in data.get("data", []) if m.get("owned_by") == owned_by],
                reverse=True,
            )
            if models:
                logger.info("Models from CLIProxyAPI (owned_by=%s): %s", owned_by, models)
                return models
        except Exception as e:
            logger.debug("CLIProxyAPI model discovery failed: %s", e)
        return None

    # ----- OpenCode discovery -----

    @classmethod
    def _discover_opencode_models_local(cls) -> Optional[list[str]]:
        """Discover OpenCode models from local config files.

        Checks ~/.opencode/config.json for model settings and
        ~/.opencode/ for any model-related cache files.
        """
        opencode_home = Path(os.environ.get("OPENCODE_HOME", str(Path.home() / ".opencode")))

        # Check config.json for model field
        config_file = opencode_home / "config.json"
        if config_file.exists():
            try:
                data = json.loads(config_file.read_text())
                models = []
                # Model field could be a string or list
                if isinstance(data.get("model"), str):
                    models.append(data["model"])
                if isinstance(data.get("models"), list):
                    models.extend(data["models"])
                # Check for provider-specific model configs
                for key in ("default_model", "selectedModel", "active_model"):
                    if isinstance(data.get(key), str) and data[key]:
                        if data[key] not in models:
                            models.append(data[key])
                if models:
                    logger.info(f"OpenCode models from config.json: {models}")
                    return models
            except (json.JSONDecodeError, OSError) as e:
                logger.debug(f"Failed to read {config_file}: {e}")

        # Check config.toml
        config_toml = opencode_home / "config.toml"
        if config_toml.exists():
            try:
                content = config_toml.read_text()
                match = re.search(r'^model\s*=\s*"([^"]+)"', content, re.MULTILINE)
                if match:
                    logger.info(f"OpenCode model from config.toml: {match.group(1)}")
                    return [match.group(1)]
            except OSError as e:
                logger.debug(f"Failed to read {config_toml}: {e}")

        # Check models_cache.json
        cache_file = opencode_home / "models_cache.json"
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text())
                entries = data if isinstance(data, list) else data.get("models", [])
                models = []
                for entry in entries:
                    if isinstance(entry, dict) and "slug" in entry:
                        models.append(entry["slug"])
                    elif isinstance(entry, dict) and "id" in entry:
                        models.append(entry["id"])
                    elif isinstance(entry, str):
                        models.append(entry)
                if models:
                    logger.info(f"OpenCode models from models_cache.json: {models}")
                    return models
            except (json.JSONDecodeError, OSError) as e:
                logger.debug(f"Failed to read {cache_file}: {e}")

        return None

    @classmethod
    def _discover_opencode_models_cli(cls) -> Optional[list[str]]:
        """Discover OpenCode models via `opencode models` CLI command.

        This non-interactive command outputs one model per line in
        provider/model-id format (e.g. "anthropic/claude-opus-4-6").
        """
        try:
            result = subprocess.run(
                ["opencode", "models"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return None

            models = [
                line.strip()
                for line in result.stdout.strip().splitlines()
                if line.strip() and "/" in line.strip()
            ]
            if models:
                logger.info(f"OpenCode models from CLI: {len(models)} models found")
                return models
        except FileNotFoundError:
            logger.debug("opencode not found in PATH")
        except subprocess.TimeoutExpired:
            logger.warning("opencode models command timed out")
        except Exception as e:
            logger.warning(f"OpenCode model discovery via CLI failed: {e}")
        return None

    @classmethod
    def _discover_anthropic_models_via_opencode(cls) -> Optional[list[str]]:
        """Extract anthropic/* models from OpenCode CLI output.

        OpenCode's ``opencode models`` lists models from all providers.
        We filter for ``anthropic/`` prefix and strip it to get raw Claude IDs
        (e.g. ``anthropic/claude-sonnet-4-6`` -> ``claude-sonnet-4-6``).
        """
        raw = cls._discover_opencode_models_cli()
        if not raw:
            return None
        models = []
        for m in raw:
            if m.startswith("anthropic/"):
                models.append(m.split("/", 1)[1])
        return models if models else None

    # ----- PTY discovery (fallback) -----

    @classmethod
    def _discover_claude_models_pty(cls) -> Optional[list[str]]:
        """Discover Claude models via interactive PTY session."""
        try:
            from .pty_service import PtyRunner

            output = PtyRunner.run_interactive(
                cmd_list=["claude"],
                input_lines=["/model"],
                timeout=15,
                ready_pattern=r"(>|claude|prompt)",
                settle_time=2.0,
            )
            if not output:
                return None

            models = set()
            id_pattern = re.compile(r"claude-(?:opus|sonnet|haiku)-[\d][\w.-]*")
            for match in id_pattern.finditer(output):
                models.add(match.group(0))

            if models:
                return sorted(models)
        except Exception as e:
            logger.warning(f"Claude model discovery via PTY failed: {e}")
        return None

    @classmethod
    def _discover_codex_models_pty(cls) -> Optional[list[str]]:
        """Discover Codex models via interactive PTY `/model` command.

        The `/model` command outputs a numbered list like:
            › 1. gpt-5.3-codex (current)  Latest frontier agentic coding model.
              2. gpt-5.3-codex-spark      Ultra-fast coding model.
              3. gpt-5.2-codex            Frontier agentic coding model.
        We parse model IDs from each numbered line, preserving display order.
        """
        try:
            from .pty_service import PtyRunner

            output = PtyRunner.run_interactive(
                cmd_list=["codex"],
                input_lines=["/model"],
                timeout=15,
                ready_pattern=r"(>|codex|prompt|\$)",
                settle_time=2.0,
            )
            if not output:
                return None

            models = cls._parse_codex_model_list(output)
            if models:
                logger.info(f"Codex models from PTY /model: {models}")
                return models

            # Fallback: extract any model IDs from the raw output
            raw = cls._parse_codex_model_ids(output)
            if raw:
                return sorted(raw)
        except Exception as e:
            logger.warning(f"Codex model discovery via PTY failed: {e}")
        return None

    @classmethod
    def _parse_codex_model_list(cls, output: str) -> Optional[list[str]]:
        """Parse the numbered model list from Codex `/model` output.

        Matches lines like:
            1. gpt-5.3-codex (current)  Description text
            2. gpt-5.3-codex-spark      Description text
        Returns model IDs in display order.
        """
        # Match: any leading chars (including › unicode), digit+dot, model-id, optional "(current)"
        line_re = re.compile(r"\d+\.\s+([\w][\w.-]+?)(?:\s+\(current\))?\s{2,}", re.MULTILINE)
        models = []
        seen = set()
        for match in line_re.finditer(output):
            model_id = match.group(1)
            if model_id not in seen:
                seen.add(model_id)
                models.append(model_id)
        return models if models else None

    # ----- Normalization -----

    @classmethod
    def _normalize_models(
        cls, backend_type: str, raw_models: list[str], *, from_pty: bool = False
    ) -> list[str]:
        """Normalize and filter discovered models based on backend type.

        Claude: group by family, keep latest version per family -> friendly names.
        Codex (PTY): just drop non-codex entries — the CLI already curates the list.
        Codex (local files): filter to codex-only AND deduplicate by version.
        OpenCode: group by provider — normalize each provider's models.
        """
        if backend_type == "claude":
            return cls._group_claude_models(raw_models)
        if backend_type == "codex":
            # Both PTY /model and models_cache.json are maintained by the CLI — return as-is
            return raw_models
        if backend_type == "opencode":
            return cls._normalize_opencode_models(raw_models)
        return raw_models

    @classmethod
    def _normalize_opencode_models(cls, raw_models: list[str]) -> list[str]:
        """Normalize OpenCode models — keep only free native models, strip provider prefix.

        OpenCode lists models from all providers (anthropic, openai, google, zhipu, etc.)
        but providers already served by other backends (anthropic, openai, google) are
        filtered out. Among the remaining native models, only free-tier models
        (containing "free" in the name) are kept for display.
        """
        native = []
        for model in raw_models:
            if "/" in model:
                provider, model_id = model.split("/", 1)
                if provider.lower() not in cls._PROXY_PROVIDERS:
                    native.append(model_id)
            else:
                native.append(model)
        # Only show free-tier models for opencode
        free = [m for m in native if "free" in m.lower()]
        return free if free else native

    @classmethod
    def _group_claude_models(cls, models: list[str]) -> list[str]:
        """Group raw Claude model IDs and keep only the latest version per family.

        e.g. ["claude-opus-4-6-20250514", "claude-sonnet-4-5-20250514"]
        -> ["Opus 4.6", "Sonnet 4.5"]

        Model IDs have the form: claude-{family}-{v1}[-{v2}...]-{YYYYMMDD}
        The trailing date (8+ digits) must be stripped before parsing the version.
        Only the highest version per family (opus/sonnet/haiku) is retained.
        """
        # Capture family + everything after it as raw version+date
        pattern = re.compile(r"claude-(opus|sonnet|haiku)-([\d][\d.-]*)")
        # Date suffix: dash followed by 8+ digits (YYYYMMDD or longer)
        date_suffix = re.compile(r"-\d{8,}.*$")
        family_order = {"opus": 0, "sonnet": 1, "haiku": 2}
        # Track best version per family: family -> (version_tuple, friendly_name)
        best: dict[str, tuple[tuple[int, ...], str]] = {}

        for model_id in models:
            match = pattern.search(model_id)
            if match:
                family = match.group(1)
                raw = match.group(2)
                # Strip date suffix: "4-6-20250514" -> "4-6", "4-20250514" -> "4"
                version_str = date_suffix.sub("", raw).replace("-", ".")
                if not version_str:
                    continue
                # Parse version as tuple of ints for comparison: "4.6" -> (4, 6)
                try:
                    version_parts = tuple(int(p) for p in version_str.split("."))
                except ValueError:
                    continue
                friendly = f"{family.capitalize()} {version_str}"

                if family not in best or version_parts > best[family][0]:
                    best[family] = (version_parts, friendly)

        if not best:
            return models  # Return originals if nothing matched

        # Sort by family order: Opus > Sonnet > Haiku
        return [best[f][1] for f in sorted(best.keys(), key=lambda f: family_order.get(f, 9))]

    @classmethod
    def _filter_codex_models(cls, models: list[str]) -> list[str]:
        """Keep only models containing 'codex', and only the latest version per variant.

        e.g. [gpt-5-codex, gpt-5.1-codex, gpt-5.2-codex, gpt-5.3-codex, gpt-5.3-codex-spark]
        -> [gpt-5.3-codex, gpt-5.3-codex-spark]

        Groups by variant suffix (codex, codex-spark, codex-mini, codex-max)
        and keeps only the highest gpt-X.Y version in each group.
        """
        codex_only = [m for m in models if "codex" in m.lower()]
        if not codex_only:
            return models

        # Pattern: gpt-{major}[.{minor}]-codex[-{variant}]
        version_re = re.compile(r"^gpt-(\d+)(?:\.(\d+))?-codex(-\w+)?$", re.IGNORECASE)
        # best per variant: variant_suffix -> (version_tuple, model_id)
        best: dict[str, tuple[tuple[int, ...], str]] = {}

        non_gpt = []  # codex models that don't match gpt-X pattern (e.g. codex-mini-latest)
        for m in codex_only:
            match = version_re.match(m)
            if not match:
                non_gpt.append(m)
                continue
            major = int(match.group(1))
            minor = int(match.group(2)) if match.group(2) else 0
            variant = match.group(3) or ""  # e.g. "", "-spark", "-mini", "-max"
            version = (major, minor)
            if variant not in best or version > best[variant][0]:
                best[variant] = (version, m)

        result = [best[v][1] for v in sorted(best.keys())]
        result.extend(sorted(non_gpt))
        return result if result else codex_only

    @classmethod
    def _parse_codex_model_ids(cls, output: str) -> set[str]:
        """Extract Codex model IDs from CLI output text."""
        models = set()
        patterns = [
            re.compile(r"\b(gpt-5(?:\.\d+)?-codex(?:-\w+)?)\b"),
            re.compile(r"\b(codex-mini(?:-[\w.-]+)?)\b"),
            re.compile(r"\b(gpt-5(?:\.\d+)?(?!-codex))\b"),
        ]
        for pattern in patterns:
            for match in pattern.finditer(output):
                model_id = match.group(1)
                if len(model_id) < 40:
                    models.add(model_id)
        return models

    # ----- DB Cache -----

    @classmethod
    def clear_cache(cls):
        """Delete all cached model lists from DB. Called on server startup."""
        try:
            from ..database import get_connection

            with get_connection() as conn:
                conn.execute("DELETE FROM settings WHERE key = ?", (_CACHE_KEY,))
                conn.commit()
                logger.info("Model discovery cache cleared")
        except Exception as e:
            logger.debug(f"Model discovery cache clear failed: {e}")

    @classmethod
    def _get_cached_models(cls, backend_type: str) -> Optional[list[str]]:
        """Read cached models from DB settings. Returns None if cache is stale or missing."""
        try:
            from ..database import get_connection

            with get_connection() as conn:
                cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (_CACHE_KEY,))
                row = cursor.fetchone()
                if not row or not row["value"]:
                    return None

                cache = json.loads(row["value"])
                entry = cache.get(backend_type)
                if not entry:
                    return None

                # Invalidate if schema version changed (normalization logic updated)
                if entry.get("schema_version") != _CACHE_SCHEMA_VERSION:
                    return None

                cached_at = datetime.fromisoformat(entry["cached_at"])
                age = datetime.now(timezone.utc) - cached_at
                if age.days >= _CACHE_MAX_AGE_DAYS:
                    return None  # Stale

                return entry["models"]
        except Exception as e:
            logger.debug(f"Model discovery cache read failed: {e}")
            return None

    @classmethod
    def _set_cached_models(cls, backend_type: str, models: list[str]):
        """Write models to DB cache."""
        try:
            from ..database import get_connection

            with get_connection() as conn:
                cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (_CACHE_KEY,))
                row = cursor.fetchone()
                cache = {}
                if row and row["value"]:
                    try:
                        cache = json.loads(row["value"])
                    except (json.JSONDecodeError, TypeError):
                        pass

                cache[backend_type] = {
                    "models": models,
                    "cached_at": datetime.now(timezone.utc).isoformat(),
                    "schema_version": _CACHE_SCHEMA_VERSION,
                }

                conn.execute(
                    """
                    INSERT INTO settings (key, value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                    """,
                    (_CACHE_KEY, json.dumps(cache)),
                )
                conn.commit()
        except Exception as e:
            logger.debug(f"Model discovery cache write failed: {e}")
