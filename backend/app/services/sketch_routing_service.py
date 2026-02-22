"""Hybrid sketch classification and routing service.

Classification pipeline: keyword -> cache -> LLM -> fallback.
Routing: maps classified sketches to SuperAgent or team targets.
"""

import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Keyword dictionaries
# =============================================================================

PHASE_KEYWORDS: Dict[str, List[str]] = {
    "research": [
        "research",
        "investigate",
        "analyze",
        "study",
        "explore",
        "compare",
        "benchmark",
        "survey",
        "literature",
        "review options",
    ],
    "planning": [
        "plan",
        "design",
        "architect",
        "structure",
        "outline",
        "roadmap",
        "strategy",
        "proposal",
        "specification",
        "blueprint",
    ],
    "execution": [
        "build",
        "implement",
        "code",
        "create",
        "develop",
        "fix",
        "deploy",
        "migrate",
        "refactor",
        "integrate",
    ],
    "review": [
        "review",
        "audit",
        "test",
        "validate",
        "verify",
        "check",
        "evaluate",
        "assess",
        "approve",
        "quality",
    ],
}

DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "frontend": ["ui", "ux", "vue", "component", "css", "layout", "page", "view"],
    "backend": ["api", "route", "service", "database", "sql", "endpoint", "server"],
    "security": ["auth", "security", "vulnerability", "permission", "token", "encrypt"],
    "testing": ["test", "coverage", "e2e", "unit", "integration", "fixture"],
    "devops": ["deploy", "ci", "cd", "docker", "pipeline", "monitor"],
    "documentation": ["docs", "readme", "guide", "tutorial", "specification"],
}

COMPLEXITY_SIGNALS: Dict[str, List[str]] = {
    "low": ["simple", "quick", "minor", "small", "tweak", "typo"],
    "medium": ["add", "update", "modify", "extend", "enhance"],
    "high": ["redesign", "rewrite", "overhaul", "migrate", "architectural"],
}


# =============================================================================
# SketchRoutingService
# =============================================================================


class SketchRoutingService:
    """Hybrid classification + routing service for sketches."""

    KEYWORD_CONFIDENCE_THRESHOLD = 0.6
    CACHE_SIMILARITY_THRESHOLD = 0.5
    DEFAULT_LLM_MODEL = "openai/claude-sonnet-4-20250514"

    @classmethod
    def classify(cls, sketch: dict) -> dict:
        """Run the full classification pipeline: keyword -> cache -> LLM -> fallback.

        Returns dict with keys: phase, domains, complexity, confidence, source.
        """
        title = sketch.get("title", "")
        content = sketch.get("content", "")
        text = f"{title} {content}".lower()

        # Step 1: keyword classification
        keyword_result = cls._keyword_classify(text)

        if keyword_result["confidence"] >= cls.KEYWORD_CONFIDENCE_THRESHOLD:
            keyword_result["source"] = "keyword"
            return keyword_result

        # Step 2: cache lookup
        cache_result = cls._check_cache(title, content)
        if cache_result is not None:
            cache_result["confidence"] = min(cache_result.get("confidence", 0.7), 0.7)
            cache_result["source"] = "cache"
            return cache_result

        # Step 3: LLM classification
        llm_result = cls._llm_classify(text)
        if llm_result is not None:
            llm_result["source"] = "llm"
            return llm_result

        # Step 4: fallback to keyword result with low confidence marker
        keyword_result["source"] = "keyword_low_confidence"
        return keyword_result

    @classmethod
    def _keyword_classify(cls, text: str) -> dict:
        """Score-based keyword classification.

        Returns dict with phase, domains, complexity, confidence, source.
        """
        # Score each phase
        phase_scores: Dict[str, int] = {}
        for phase, keywords in PHASE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text)
            phase_scores[phase] = score

        max_score = max(phase_scores.values()) if phase_scores else 0
        best_phase = max(phase_scores, key=phase_scores.get) if phase_scores else "execution"

        # Phase confidence: 3+ matches = 1.0
        phase_confidence = min(max_score / 3, 1.0) if max_score > 0 else 0.0

        # Detect domains
        domains = []
        for domain, keywords in DOMAIN_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                domains.append(domain)

        # Detect complexity (first match wins, default medium)
        complexity = "medium"
        for level, signals in COMPLEXITY_SIGNALS.items():
            if any(signal in text for signal in signals):
                complexity = level
                break

        # Overall confidence
        domain_factor = 0.8 if domains else 0.5
        confidence = round(phase_confidence * domain_factor, 3)

        return {
            "phase": best_phase,
            "domains": domains,
            "complexity": complexity,
            "confidence": confidence,
            "source": "keyword",
        }

    @classmethod
    def _check_cache(cls, title: str, content: str) -> Optional[dict]:
        """Check recently classified sketches for trigram similarity match."""
        from ..db.sketches import get_recent_classified_sketches

        classified = get_recent_classified_sketches(limit=100)
        if not classified:
            return None

        new_text = f"{title} {content}".lower()
        new_trigrams = cls._trigrams(new_text)

        if not new_trigrams:
            return None

        for cached in classified:
            cached_text = f"{cached.get('title', '')} {cached.get('content', '')}".lower()
            cached_trigrams = cls._trigrams(cached_text)

            if not cached_trigrams:
                continue

            intersection = new_trigrams & cached_trigrams
            union = new_trigrams | cached_trigrams
            similarity = len(intersection) / len(union) if union else 0.0

            if similarity > cls.CACHE_SIMILARITY_THRESHOLD:
                try:
                    return json.loads(cached["classification_json"])
                except (json.JSONDecodeError, TypeError, KeyError):
                    continue

        return None

    @classmethod
    def _trigrams(cls, text: str) -> set:
        """Compute set of 3-word sliding window trigrams from text."""
        words = text.split()
        if len(words) < 3:
            return set()
        return {tuple(words[i : i + 3]) for i in range(len(words) - 2)}

    @classmethod
    def _llm_classify(cls, text: str) -> Optional[dict]:
        """Attempt LLM-based classification with graceful fallback."""
        try:
            import litellm
        except ImportError:
            logger.debug("litellm not available, skipping LLM classification")
            return None

        system_prompt = (
            "You are a sketch classifier for a software project management tool.\n"
            "Classify the given text into:\n"
            "- phase: one of 'research', 'planning', 'execution', 'review'\n"
            "- domains: list of relevant domains from: frontend, backend, security, testing, devops, documentation\n"
            "- complexity: one of 'low', 'medium', 'high'\n"
            "- confidence: float between 0.0 and 1.0\n\n"
            "Respond with ONLY a JSON object, no other text:\n"
            '{"phase": "...", "domains": [...], "complexity": "...", "confidence": 0.0}'
        )

        try:
            # Try to get api_base from CLIProxyManager
            api_base = None
            try:
                from .cliproxy_manager import CLIProxyManager

                api_base = CLIProxyManager.get_base_url()
            except Exception:
                pass

            # Try to get model from settings, fall back to default
            model = cls.DEFAULT_LLM_MODEL
            try:
                from ..db.settings import get_setting

                stored_model = get_setting("sketch_llm_model")
                if stored_model:
                    model = stored_model
            except Exception:
                pass  # Use default if settings unavailable

            logger.info("Using LLM model %s for sketch classification", model)

            kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Classify this sketch:\n\n{text}"},
                ],
                "timeout": 5,
                "api_key": "not-needed",
            }
            if api_base:
                kwargs["api_base"] = api_base

            response = litellm.completion(**kwargs)

            content = response.choices[0].message.content.strip()
            result = json.loads(content)

            # Validate required keys
            required = {"phase", "domains", "complexity", "confidence"}
            if not required.issubset(result.keys()):
                logger.warning("LLM classification missing required keys: %s", result)
                return None

            return result

        except Exception as e:
            logger.warning("LLM classification failed: %s", e)
            return None

    @classmethod
    def route(cls, classification: dict) -> dict:
        """Route a classified sketch to a SuperAgent or team target.

        Returns dict with target_type, target_id, reason.
        """
        from ..db.super_agents import get_all_super_agents
        from ..db.teams import get_all_teams

        phase = classification.get("phase", "")
        domains = classification.get("domains", [])

        super_agents = get_all_super_agents()
        teams = get_all_teams()

        # Research or planning -> find SuperAgent whose name/description matches phase
        if phase in ("research", "planning"):
            for sa in super_agents:
                sa_name = (sa.get("name") or "").lower()
                sa_desc = (sa.get("description") or "").lower()
                if phase in sa_name or phase in sa_desc:
                    return {
                        "target_type": "super_agent",
                        "target_id": sa["id"],
                        "reason": f"SuperAgent '{sa.get('name')}' matches phase '{phase}'",
                    }

        # Execution -> find team whose description matches any classified domain
        if phase == "execution" and domains:
            for team in teams:
                team_desc = (team.get("description") or "").lower()
                team_name = (team.get("name") or "").lower()
                for domain in domains:
                    if domain in team_desc or domain in team_name:
                        return {
                            "target_type": "team",
                            "target_id": team["id"],
                            "reason": f"Team '{team.get('name')}' matches domain '{domain}'",
                        }

        # Review -> find SuperAgent with review/audit capabilities
        if phase == "review":
            for sa in super_agents:
                sa_name = (sa.get("name") or "").lower()
                sa_desc = (sa.get("description") or "").lower()
                if (
                    "review" in sa_name
                    or "audit" in sa_name
                    or "review" in sa_desc
                    or "audit" in sa_desc
                ):
                    return {
                        "target_type": "super_agent",
                        "target_id": sa["id"],
                        "reason": f"SuperAgent '{sa.get('name')}' has review/audit capabilities",
                    }

        # No match found
        return {
            "target_type": "none",
            "target_id": None,
            "reason": f"No matching target found for phase={phase}, domains={domains}",
        }
