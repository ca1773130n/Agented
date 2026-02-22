"""SPA catch-all route for production deep linking.

Uses Flask's 404 error handler instead of a catch-all route to avoid
interfering with existing API route method handling (e.g., 405 responses
for wrong HTTP methods on API endpoints).
"""

import os

from flask import Blueprint, jsonify, send_from_directory

spa_bp = Blueprint("spa", __name__)


@spa_bp.app_errorhandler(404)
def spa_fallback(error):
    """Serve index.html for non-API 404s (enables SPA deep linking in production)."""
    from flask import request

    path = request.path.lstrip("/")

    # Don't intercept API 404s -- let them return JSON as normal
    api_prefixes = ("api/", "admin/", "health/", "docs/", "openapi/")
    if path.startswith(api_prefixes):
        return jsonify({"error": "Not found"}), 404

    # Serve the built frontend's index.html
    static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "static")
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(os.path.abspath(static_dir), "index.html")
    return jsonify({"error": "Frontend not built"}), 404
