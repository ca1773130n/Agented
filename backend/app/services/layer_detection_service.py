"""Layer detection service — agent layer and role auto-detection."""

import re
from typing import List


class LayerDetectionService:
    """Service for detecting agent layers, roles, and matching skills."""

    # Layer detection keywords
    LAYER_KEYWORDS = {
        "backend": [
            "backend",
            "api",
            "database",
            "server",
            "rest",
            "graphql",
            "sql",
            "nosql",
            "orm",
            "microservice",
        ],
        "frontend": [
            "frontend",
            "ui",
            "component",
            "react",
            "vue",
            "angular",
            "css",
            "html",
            "web",
            "browser",
            "dom",
        ],
        "design": [
            "design",
            "ux",
            "ui design",
            "wireframe",
            "prototype",
            "figma",
            "sketch",
            "visual",
            "layout",
            "typography",
        ],
        "analysis": [
            "analysis",
            "requirements",
            "specification",
            "documentation",
            "planning",
            "architecture",
            "system design",
            "rfc",
        ],
        "test": [
            "test",
            "testing",
            "qa",
            "quality",
            "e2e",
            "unit test",
            "integration test",
            "automation",
            "cypress",
            "playwright",
        ],
        "management": [
            "management",
            "project",
            "scrum",
            "agile",
            "sprint",
            "roadmap",
            "timeline",
            "coordination",
            "stakeholder",
        ],
        "maintenance": [
            "maintenance",
            "support",
            "bug fix",
            "patch",
            "upgrade",
            "migration",
            "refactor",
            "technical debt",
            "legacy",
        ],
        "data": [
            "data",
            "ml",
            "machine learning",
            "analytics",
            "etl",
            "pipeline",
            "bigquery",
            "spark",
        ],
        "mobile": ["mobile", "ios", "android", "react native", "flutter", "swift", "kotlin"],
    }

    @classmethod
    def _detect_layer(cls, content: str, role: str = None) -> str:
        """Detect the layer (backend, frontend, etc.) from agent content and role.

        Returns detected layer or 'backend' as default.
        """
        text = (content + " " + (role or "")).lower()

        # Check each layer's keywords
        layer_scores = {layer: 0 for layer in cls.LAYER_KEYWORDS}
        for layer, keywords in cls.LAYER_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    layer_scores[layer] += 1

        # Return layer with highest score, or 'backend' if no matches
        max_layer = max(layer_scores, key=layer_scores.get)
        if layer_scores[max_layer] > 0:
            return max_layer
        return "backend"

    @classmethod
    def _detect_role(cls, content: str, name: str = None) -> str:
        """Extract detected role from agent content.

        Looks for role-related patterns in the content.
        Returns first sentence or summary as detected role.
        """
        # Look for explicit role patterns
        role_patterns = [
            r"acts as[:\s]+([^.!?\n]+)",
            r"role[:\s]+([^.!?\n]+)",
            r"responsible for[:\s]+([^.!?\n]+)",
            r"you are[:\s]+([^.!?\n]+)",
            r"^#\s*([^\n]+)",  # First markdown heading
        ]

        for pattern in role_patterns:
            match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
            if match:
                role = match.group(1).strip()
                if len(role) > 10 and len(role) < 200:
                    return role

        # Fallback: use first sentence from content
        sentences = re.split(r"[.!?\n]", content)
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 20 and len(sentence) < 200:
                return sentence

        return None

    @classmethod
    def _match_skills(cls, agent_skills: List[str], available_skills: List[str]) -> List[str]:
        """Match agent skills against available skills in the database.

        Returns list of matched skill names.
        """
        if not agent_skills or not available_skills:
            return []

        matched = []
        agent_skills_lower = [s.lower() for s in agent_skills]
        for available in available_skills:
            if available.lower() in agent_skills_lower:
                matched.append(available)

        return matched
