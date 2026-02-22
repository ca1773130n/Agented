"""
Simple Flask backend for the Skills Playground example webapp.
Provides basic CRUD operations for testing Claude skills.
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime
import uuid

app = Flask(__name__)
CORS(app)

# In-memory storage for todos
todos = []


@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat()})


@app.route("/api/todos", methods=["GET"])
def list_todos():
    """List all todos."""
    return jsonify({"todos": todos, "count": len(todos)})


@app.route("/api/todos", methods=["POST"])
def create_todo():
    """Create a new todo."""
    data = request.get_json()
    if not data or "title" not in data:
        return jsonify({"error": "Title is required"}), 400

    todo = {
        "id": str(uuid.uuid4()),
        "title": data["title"],
        "description": data.get("description", ""),
        "completed": False,
        "priority": data.get("priority", "medium"),
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    todos.append(todo)
    return jsonify(todo), 201


@app.route("/api/todos/<todo_id>", methods=["GET"])
def get_todo(todo_id):
    """Get a specific todo."""
    todo = next((t for t in todos if t["id"] == todo_id), None)
    if not todo:
        return jsonify({"error": "Todo not found"}), 404
    return jsonify(todo)


@app.route("/api/todos/<todo_id>", methods=["PUT"])
def update_todo(todo_id):
    """Update a todo."""
    todo = next((t for t in todos if t["id"] == todo_id), None)
    if not todo:
        return jsonify({"error": "Todo not found"}), 404

    data = request.get_json()
    if "title" in data:
        todo["title"] = data["title"]
    if "description" in data:
        todo["description"] = data["description"]
    if "completed" in data:
        todo["completed"] = data["completed"]
    if "priority" in data:
        todo["priority"] = data["priority"]
    todo["updated_at"] = datetime.utcnow().isoformat()

    return jsonify(todo)


@app.route("/api/todos/<todo_id>", methods=["DELETE"])
def delete_todo(todo_id):
    """Delete a todo."""
    global todos
    initial_count = len(todos)
    todos = [t for t in todos if t["id"] != todo_id]

    if len(todos) == initial_count:
        return jsonify({"error": "Todo not found"}), 404

    return jsonify({"message": "Todo deleted"})


@app.route("/api/todos/<todo_id>/toggle", methods=["POST"])
def toggle_todo(todo_id):
    """Toggle a todo's completed status."""
    todo = next((t for t in todos if t["id"] == todo_id), None)
    if not todo:
        return jsonify({"error": "Todo not found"}), 404

    todo["completed"] = not todo["completed"]
    todo["updated_at"] = datetime.utcnow().isoformat()

    return jsonify(todo)


# User authentication endpoints (simple mock)
users = {}
sessions = {}


@app.route("/api/auth/register", methods=["POST"])
def register():
    """Register a new user."""
    data = request.get_json()
    if not data or "username" not in data or "password" not in data:
        return jsonify({"error": "Username and password are required"}), 400

    if data["username"] in users:
        return jsonify({"error": "Username already exists"}), 409

    users[data["username"]] = {
        "id": str(uuid.uuid4()),
        "username": data["username"],
        "password": data["password"],  # In production, hash this!
        "created_at": datetime.utcnow().isoformat(),
    }

    return jsonify({"message": "User created", "user_id": users[data["username"]]["id"]}), 201


@app.route("/api/auth/login", methods=["POST"])
def login():
    """Login a user."""
    data = request.get_json()
    if not data or "username" not in data or "password" not in data:
        return jsonify({"error": "Username and password are required"}), 400

    user = users.get(data["username"])
    if not user or user["password"] != data["password"]:
        return jsonify({"error": "Invalid credentials"}), 401

    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "user_id": user["id"],
        "username": user["username"],
        "created_at": datetime.utcnow().isoformat(),
    }

    return jsonify(
        {
            "message": "Login successful",
            "session_id": session_id,
            "user": {"id": user["id"], "username": user["username"]},
        }
    )


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    """Logout a user."""
    session_id = request.headers.get("X-Session-Id")
    if session_id and session_id in sessions:
        del sessions[session_id]
    return jsonify({"message": "Logged out"})


if __name__ == "__main__":
    app.run(debug=True, port=5050)
