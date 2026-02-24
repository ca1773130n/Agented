"""Skills.sh integration service -- uses skills.sh HTTP API for search, npx CLI for install."""

import json
import logging
import os
import re
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from http import HTTPStatus
from typing import Tuple

logger = logging.getLogger(__name__)

# In-memory cache (follows DeployService._marketplace_cache pattern)
_skills_sh_cache: dict = {}  # {"query": {"data": [...], "fetched_at": float}}
_CACHE_TTL = 300  # 5 minutes

_SKILLS_SH_API_URL = "https://skills.sh/api/search"


class SkillsShService:
    _semaphore = threading.Semaphore(2)  # Max 2 concurrent CLI calls globally
    _npx_available: bool | None = None  # Cached npx availability check

    # Per-IP rate limiting for install: track last install time per source IP
    _install_timestamps: dict = {}  # {ip: last_install_epoch}
    _install_lock = threading.Lock()
    INSTALL_MIN_INTERVAL = 30  # Seconds between install calls per IP

    @classmethod
    def search(cls, query: str = "") -> Tuple[dict, int]:
        """Search skills from skills.sh via HTTP API."""
        cache_key = query.strip().lower()

        # Check cache
        entry = _skills_sh_cache.get(cache_key)
        if entry and (time.time() - entry["fetched_at"] < _CACHE_TTL):
            return {"results": entry["data"], "source": "skills.sh"}, HTTPStatus.OK

        # skills.sh API requires min 2 chars; use a broad term for empty queries
        search_query = query.strip() if len(query.strip()) >= 2 else "claude"

        results = cls._search_via_api(search_query)

        # Cross-reference with installed skills
        try:
            from .skills_service import SkillsService

            installed_skills = SkillsService.discover_all_skills()
            installed_names = {s["name"].lower() for s in installed_skills}
            for result in results:
                result["installed"] = result["name"].lower() in installed_names
        except Exception as e:
            logger.warning("Failed to discover installed skills for cross-reference: %s", e)

        _skills_sh_cache[cache_key] = {"data": results, "fetched_at": time.time()}
        return {"results": results, "source": "skills.sh", "npx_available": True}, HTTPStatus.OK

    @classmethod
    def install_skill(cls, source: str, client_ip: str = "unknown") -> Tuple[dict, int]:
        """Install a skill via npx skills add."""
        if not source or not source.strip():
            return {"error": "source is required"}, HTTPStatus.BAD_REQUEST

        if not cls._is_npx_available():
            return {"error": "npx is not available"}, HTTPStatus.SERVICE_UNAVAILABLE

        # Per-IP rate limiting: prevent one caller from monopolizing the semaphore
        with cls._install_lock:
            last = cls._install_timestamps.get(client_ip, 0)
            now = time.time()
            elapsed = now - last
            if elapsed < cls.INSTALL_MIN_INTERVAL:
                retry_after = int(cls.INSTALL_MIN_INTERVAL - elapsed) + 1
                return {
                    "error": "Too many install requests. Please wait before trying again.",
                    "retry_after": retry_after,
                }, HTTPStatus.TOO_MANY_REQUESTS
            cls._install_timestamps[client_ip] = now

        # Acquire global concurrency slot
        acquired = cls._semaphore.acquire(blocking=False)
        if not acquired:
            return {
                "error": "Server busy. Too many concurrent installations. Please try again shortly.",
            }, HTTPStatus.SERVICE_UNAVAILABLE

        install_cmd = f"npx -y skills add {source} --global --yes"
        cmd = ["npx", "-y", "skills", "add", source, "--global", "--yes"]
        env = {**os.environ, "NO_COLOR": "1"}

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
                stdin=subprocess.DEVNULL,
            )

            stdout_cleaned = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
            stderr_cleaned = re.sub(r"\x1b\[[0-9;]*m", "", result.stderr)

            if result.returncode == 0:
                # Register the skill in user_skills table
                registration_warning = None
                try:
                    from ..database import add_user_skill, get_user_skill_by_name

                    # Extract skill name from source
                    if "@" in source:
                        skill_name = source.split("@")[-1]
                    else:
                        skill_name = source.split("/")[-1] if "/" in source else source

                    existing = get_user_skill_by_name(skill_name)
                    if not existing:
                        add_user_skill(
                            skill_name=skill_name,
                            skill_path=f"~/.claude/skills/{skill_name}",
                            description=f"Installed from skills.sh ({source})",
                            metadata=json.dumps(
                                {"skills_sh_source": source, "install_cmd": install_cmd}
                            ),
                        )
                except Exception as e:
                    logger.warning("Failed to register skill in user_skills: %s", e)
                    registration_warning = (
                        "Skill files were installed successfully, but registration in the "
                        "database failed — the skill may not appear in listings until the "
                        "server is restarted."
                    )

                # Clear the search cache
                _skills_sh_cache.clear()

                response: dict = {
                    "message": f"Skill installed from {source}",
                    "output": stdout_cleaned,
                }
                if registration_warning:
                    response["warning"] = registration_warning
                return response, HTTPStatus.OK
            else:
                return {"error": f"Install failed: {stderr_cleaned}"}, HTTPStatus.BAD_REQUEST

        except subprocess.TimeoutExpired:
            return {"error": "Installation timed out"}, HTTPStatus.GATEWAY_TIMEOUT
        except Exception as e:
            return {"error": f"Install error: {str(e)}"}, HTTPStatus.INTERNAL_SERVER_ERROR
        finally:
            cls._semaphore.release()

    @classmethod
    def _search_via_api(cls, query: str) -> list:
        """Search skills.sh using the HTTP API (much more reliable than CLI)."""
        url = f"{_SKILLS_SH_API_URL}?q={urllib.parse.quote(query)}&limit=200"
        try:
            req = urllib.request.Request(
                url, headers={"Accept": "application/json", "User-Agent": "Agented/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read())

            skills = data.get("skills", [])
            results = []
            for s in skills:
                source = s.get("source", "")
                skill_id = s.get("skillId", s.get("name", ""))
                full_id = s.get("id", "")
                installs = s.get("installs", 0)

                results.append(
                    {
                        "name": s.get("name", skill_id),
                        "description": f"{installs:,} installs" if installs else None,
                        "source": source,
                        "installs": installs,
                        "detail_url": f"https://skills.sh/{full_id}" if full_id else None,
                        "install_cmd": (
                            f"npx skills add {source}@{skill_id} --global --yes"
                            if source
                            else f"npx skills add {skill_id} --global --yes"
                        ),
                    }
                )
            return results
        except Exception as e:
            logger.warning("skills.sh API search failed: %s", e)
            return []

    @classmethod
    def _is_npx_available(cls) -> bool:
        """Check if npx is available on the system. Caches the result."""
        if cls._npx_available is not None:
            return cls._npx_available

        try:
            result = subprocess.run(["npx", "--version"], capture_output=True, timeout=5)
            cls._npx_available = result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            cls._npx_available = False

        return cls._npx_available
