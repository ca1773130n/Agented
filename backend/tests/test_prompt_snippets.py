"""Tests for prompt snippet CRUD and resolution."""

from app.db.prompt_snippets import create_snippet
from app.services.prompt_snippet_service import SnippetService


def test_create_snippet(client):
    """POST /admin/prompt-snippets creates snippet with correct fields."""
    resp = client.post(
        "/admin/prompt-snippets/",
        json={"name": "greeting", "content": "Hello World", "description": "A greeting"},
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["snippet"]["name"] == "greeting"
    assert data["snippet"]["content"] == "Hello World"
    assert data["snippet"]["description"] == "A greeting"


def test_create_duplicate_name_rejected(client):
    """Creating snippet with existing name returns 409."""
    client.post(
        "/admin/prompt-snippets/",
        json={"name": "unique_name", "content": "first"},
    )
    resp = client.post(
        "/admin/prompt-snippets/",
        json={"name": "unique_name", "content": "second"},
    )
    assert resp.status_code == 409


def test_list_snippets(client):
    """GET /admin/prompt-snippets returns list."""
    client.post("/admin/prompt-snippets/", json={"name": "snip1", "content": "c1"})
    client.post("/admin/prompt-snippets/", json={"name": "snip2", "content": "c2"})
    resp = client.get("/admin/prompt-snippets/")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["snippets"]) >= 2


def test_update_snippet(client):
    """PUT /admin/prompt-snippets/{id} updates content."""
    create_resp = client.post(
        "/admin/prompt-snippets/",
        json={"name": "editable", "content": "original"},
    )
    snippet_id = create_resp.get_json()["snippet"]["id"]

    resp = client.put(
        f"/admin/prompt-snippets/{snippet_id}",
        json={"content": "updated"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["snippet"]["content"] == "updated"


def test_delete_snippet(client):
    """DELETE /admin/prompt-snippets/{id} removes snippet."""
    create_resp = client.post(
        "/admin/prompt-snippets/",
        json={"name": "deletable", "content": "to delete"},
    )
    snippet_id = create_resp.get_json()["snippet"]["id"]

    resp = client.delete(f"/admin/prompt-snippets/{snippet_id}")
    assert resp.status_code == 200

    get_resp = client.get(f"/admin/prompt-snippets/{snippet_id}")
    assert get_resp.status_code == 404


def test_resolve_snippets_basic(isolated_db):
    """Create snippet 'greeting' and resolve '{{greeting}}' to its content."""
    create_snippet(name="greeting", content="Hello World")
    result = SnippetService.resolve_snippets("Say: {{greeting}}")
    assert result == "Say: Hello World"


def test_resolve_snippets_missing(isolated_db):
    """Resolve '{{nonexistent}}' returns unchanged."""
    result = SnippetService.resolve_snippets("{{nonexistent}}")
    assert result == "{{nonexistent}}"


def test_resolve_snippets_nested(isolated_db):
    """Create A referencing {{B}}, B with content; resolve A has B resolved."""
    create_snippet(name="inner", content="nested value")
    create_snippet(name="outer", content="prefix {{inner}} suffix")
    result = SnippetService.resolve_snippets("{{outer}}")
    assert result == "prefix nested value suffix"


def test_resolve_snippets_circular(isolated_db):
    """Circular references terminate without hanging."""
    create_snippet(name="circA", content="see {{circB}}")
    create_snippet(name="circB", content="see {{circA}}")
    result = SnippetService.resolve_snippets("{{circA}}")
    # Should terminate; circular ref left unresolved
    assert "{{circA}}" in result or "{{circB}}" in result


def test_resolve_endpoint(client):
    """POST /admin/prompt-snippets/resolve resolves snippet references."""
    client.post(
        "/admin/prompt-snippets/",
        json={"name": "helper", "content": "resolved text"},
    )
    resp = client.post(
        "/admin/prompt-snippets/resolve",
        json={"text": "Use {{helper}} here"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["resolved"] == "Use resolved text here"
