"""Tests for sketch classification and routing (service + endpoints).

Tests cover:
- Keyword classification: phase detection, domain detection, complexity, confidence, required keys
- Cache lookup: similar match, miss, empty DB
- Routing: required keys, no targets, execution phase team match
- API endpoints: classify, route, not found, unclassified route
"""

import json

import pytest

from app.db.sketches import add_sketch, get_sketch, update_sketch
from app.db.teams import add_team
from app.services.sketch_routing_service import SketchRoutingService

# =============================================================================
# Keyword classification tests
# =============================================================================


class TestKeywordClassification:
    """Tests for SketchRoutingService._keyword_classify()."""

    def test_keyword_classify_execution_phase(self):
        """'build a REST API for user auth' -> phase='execution', 'backend' in domains."""
        result = SketchRoutingService._keyword_classify("build a rest api for user auth")
        assert result["phase"] == "execution"
        assert "backend" in result["domains"]

    def test_keyword_classify_research_phase(self):
        """'research best practices for caching' -> phase='research'."""
        result = SketchRoutingService._keyword_classify("research best practices for caching")
        assert result["phase"] == "research"

    def test_keyword_classify_planning_phase(self):
        """'design the architecture for new microservice' -> phase='planning'."""
        result = SketchRoutingService._keyword_classify(
            "design the architecture for new microservice"
        )
        assert result["phase"] == "planning"

    def test_keyword_classify_review_phase(self):
        """'audit the security of authentication module' -> phase='review'."""
        result = SketchRoutingService._keyword_classify(
            "audit the security of authentication module"
        )
        assert result["phase"] == "review"

    def test_keyword_classify_returns_required_keys(self):
        """Any input returns dict with phase, domains, complexity, confidence, source keys."""
        result = SketchRoutingService._keyword_classify("anything at all")
        required_keys = {"phase", "domains", "complexity", "confidence", "source"}
        assert required_keys.issubset(result.keys())
        assert isinstance(result["phase"], str)
        assert isinstance(result["domains"], list)
        assert isinstance(result["complexity"], str)
        assert isinstance(result["confidence"], (int, float))
        assert isinstance(result["source"], str)

    def test_keyword_classify_high_confidence_clear_input(self):
        """Input with 3+ phase keywords gets confidence >= 0.6."""
        # 3 execution keywords: build, implement, create
        result = SketchRoutingService._keyword_classify(
            "build and implement and create a new backend api service"
        )
        assert result["phase"] == "execution"
        assert result["confidence"] >= 0.6

    def test_keyword_classify_low_confidence_ambiguous(self):
        """Single-word ambiguous input gets confidence < 0.6."""
        result = SketchRoutingService._keyword_classify("hello")
        assert result["confidence"] < 0.6

    def test_keyword_classify_domain_detection(self):
        """'add vue component for dashboard UI' -> 'frontend' in domains."""
        result = SketchRoutingService._keyword_classify("add vue component for dashboard ui")
        assert "frontend" in result["domains"]

    def test_keyword_classify_complexity_high(self):
        """'redesign the entire authentication system' -> complexity='high'."""
        result = SketchRoutingService._keyword_classify("redesign the entire authentication system")
        assert result["complexity"] == "high"

    def test_keyword_classify_complexity_low(self):
        """'fix a simple typo in readme' -> complexity='low'."""
        result = SketchRoutingService._keyword_classify("fix a simple typo in readme")
        assert result["complexity"] == "low"


# =============================================================================
# Cache lookup tests
# =============================================================================


class TestCacheLookup:
    """Tests for SketchRoutingService._check_cache()."""

    def test_cache_finds_similar_sketch(self):
        """Add a classified sketch to DB, _check_cache with similar text returns classification."""
        # Create a classified sketch
        sid = add_sketch("build REST API endpoints for user management", content="backend service")
        classification = {
            "phase": "execution",
            "domains": ["backend"],
            "complexity": "medium",
            "confidence": 0.8,
        }
        update_sketch(sid, classification_json=json.dumps(classification), status="classified")

        # Check cache with very similar text
        result = SketchRoutingService._check_cache(
            "build REST API endpoints for user management", "backend service"
        )
        assert result is not None
        assert result["phase"] == "execution"

    def test_cache_misses_for_unrelated_text(self):
        """Add classified sketch, cache with completely different text returns None."""
        sid = add_sketch(
            "build REST API endpoints for user management",
            content="backend service implementation",
        )
        classification = {
            "phase": "execution",
            "domains": ["backend"],
            "complexity": "medium",
            "confidence": 0.8,
        }
        update_sketch(sid, classification_json=json.dumps(classification), status="classified")

        # Completely different text
        result = SketchRoutingService._check_cache(
            "quarterly financial report analysis", "spreadsheet pivot tables and charts"
        )
        assert result is None

    def test_cache_returns_none_when_no_classified_sketches(self):
        """Empty DB, _check_cache returns None."""
        result = SketchRoutingService._check_cache("anything", "at all")
        assert result is None


# =============================================================================
# Routing tests
# =============================================================================


class TestRouting:
    """Tests for SketchRoutingService.route()."""

    def test_route_returns_required_keys(self):
        """route() returns dict with target_type, target_id, reason keys."""
        classification = {
            "phase": "execution",
            "domains": ["backend"],
            "complexity": "medium",
            "confidence": 0.8,
        }
        result = SketchRoutingService.route(classification)
        required_keys = {"target_type", "target_id", "reason"}
        assert required_keys.issubset(result.keys())

    def test_route_no_targets_returns_none_type(self):
        """route with no SuperAgents or teams in DB returns target_type='none'."""
        classification = {
            "phase": "execution",
            "domains": ["backend"],
            "complexity": "medium",
            "confidence": 0.8,
        }
        result = SketchRoutingService.route(classification)
        assert result["target_type"] == "none"
        assert result["target_id"] is None

    def test_route_execution_phase_finds_team(self):
        """Add a team with matching domain description, route execution sketch finds it."""
        team_id = add_team(name="Backend Team", description="Handles backend api and services")
        assert team_id is not None

        classification = {
            "phase": "execution",
            "domains": ["backend"],
            "complexity": "medium",
            "confidence": 0.8,
        }
        result = SketchRoutingService.route(classification)
        assert result["target_type"] == "team"
        assert result["target_id"] == team_id
        assert "backend" in result["reason"].lower()


# =============================================================================
# API endpoint tests
# =============================================================================


class TestClassifyRouteEndpoints:
    """Tests for /admin/sketches/:id/classify and /admin/sketches/:id/route endpoints."""

    @pytest.fixture(autouse=True)
    def setup_client(self, client):
        """Provide Flask test client to each test."""
        self.client = client

    def test_classify_endpoint_updates_sketch(self):
        """POST /admin/sketches/:id/classify returns 200, sketch status becomes 'classified'."""
        sketch_id = add_sketch("build a REST API for user auth", content="backend api service")
        resp = self.client.post(f"/admin/sketches/{sketch_id}/classify")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["message"] == "Sketch classified"
        assert "classification" in data
        assert "phase" in data["classification"]

        # Verify DB state
        sketch = get_sketch(sketch_id)
        assert sketch["status"] == "classified"
        assert sketch["classification_json"] is not None

    def test_classify_endpoint_sketch_not_found(self):
        """POST /admin/sketches/sketch-nope/classify returns 404."""
        resp = self.client.post("/admin/sketches/sketch-nope/classify")
        assert resp.status_code == 404

    def test_route_endpoint_updates_sketch(self):
        """Classify first, then POST /admin/sketches/:id/route returns 200, status becomes 'routed'."""
        sketch_id = add_sketch("build a REST API for user auth", content="backend api service")
        # First classify
        self.client.post(f"/admin/sketches/{sketch_id}/classify")
        # Then route
        resp = self.client.post(f"/admin/sketches/{sketch_id}/route")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["message"] == "Sketch routed"
        assert "routing" in data
        assert "target_type" in data["routing"]

        # Verify DB state
        sketch = get_sketch(sketch_id)
        assert sketch["status"] == "routed"
        assert sketch["routing_json"] is not None

    def test_route_endpoint_unclassified_returns_400(self):
        """POST /admin/sketches/:id/route on draft sketch returns 400."""
        sketch_id = add_sketch("Unclassified sketch")
        resp = self.client.post(f"/admin/sketches/{sketch_id}/route")
        assert resp.status_code == 400
        data = resp.get_json()
        assert "classified" in data["error"].lower()
