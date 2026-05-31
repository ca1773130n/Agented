"""Phase E2 Task 4 — KG signals wired into ``gather_inputs`` + workspace.

These tests cover the best-effort KG-signal source: ``gather_inputs``
surfaces a ``kg_signals`` key (gathered from the compiled Tesserae graph),
the gather is guarded so a KG outage degrades to ``[]`` without blocking a
round, and ``build_workspace`` projects the signals to ``KG_SIGNALS.md``
ranked by salience weight.

Note: ``gather_kg_signals`` is imported *inside* ``gather_inputs`` (local
import), so we patch it at its SOURCE module, not on ``harness_evolver``.
"""

from __future__ import annotations

from app.db.connection import get_connection
from app.models.harness_evolution import KGSignalItem
from app.services.harness_evolver import READABLE_KINDS, build_workspace, gather_inputs


def _empty_primitives() -> dict:
    """build_workspace iterates every READABLE_KIND, so the primitives dict
    must contain all kinds (even when empty)."""
    return {k: [] for k in READABLE_KINDS}


def _seed_project(project_id: str, name: str = "KG Test Project") -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name) VALUES (?, ?)",
            (project_id, name),
        )
        conn.commit()


def _signal(question: str, content: str, weight: float, *, forged: bool = False) -> KGSignalItem:
    return KGSignalItem(
        signal_id=f"kgs-{abs(hash((question, content))) % 100000:05d}",
        project_id="proj-kg",
        question=question,
        content=content,
        weight=weight,
        already_forged=forged,
        first_seen_at="2026-05-01T00:00:00Z",
        captured_at="2026-05-30T00:00:00Z",
    )


# --------------------------------------------------------------------------
# 4.1 — gather_inputs surfaces kg_signals
# --------------------------------------------------------------------------


def test_gather_inputs_includes_kg_signals_key(isolated_db, monkeypatch):
    """When ``gather_kg_signals`` returns signals, ``gather_inputs`` exposes
    them as ``model_dump()`` dicts under the ``kg_signals`` key."""
    _seed_project("proj-kg-a")

    sigs = [
        _signal("Why retries fail?", "Add a retry guard hook.", 0.65),
        _signal("Deploy ordering?", "Migrations before deploy.", 0.4),
    ]
    monkeypatch.setattr(
        "app.services.harness_kg_signals.gather_kg_signals",
        lambda project_id, **kw: sigs,
    )

    inputs = gather_inputs("proj-kg-a", limit=10)
    assert "kg_signals" in inputs
    assert len(inputs["kg_signals"]) == 2
    # Items are plain dicts (model_dump), not Pydantic objects.
    first = inputs["kg_signals"][0]
    assert isinstance(first, dict)
    assert first["content"] == "Add a retry guard hook."
    assert first["weight"] == 0.65
    assert "signal_id" in first and "already_forged" in first


def test_gather_inputs_forwards_forged_index(isolated_db, monkeypatch):
    """``gather_inputs`` passes a ``forged_index`` built from bound primitive
    asset ``content`` strings; assets without ``content`` (mcp_servers) must
    not raise via the ``.get("content") or ""`` guard."""
    _seed_project("proj-kg-fi")
    captured: dict = {}

    def _fake(project_id, *, forged_index=None, **kw):
        captured["forged_index"] = forged_index
        return []

    monkeypatch.setattr("app.services.harness_kg_signals.gather_kg_signals", _fake)

    inputs = gather_inputs("proj-kg-fi", limit=10)
    assert inputs["kg_signals"] == []
    # No bound primitives → empty index, but the kwarg was supplied.
    assert captured["forged_index"] == []


def test_gather_inputs_kg_signal_failure_degrades_to_empty(isolated_db, monkeypatch):
    """A raising ``gather_kg_signals`` is swallowed: ``kg_signals == []`` and
    the other input streams are intact (the try/except guard)."""
    _seed_project("proj-kg-boom")

    def _boom(project_id, **kw):
        raise RuntimeError("tesserae exploded")

    monkeypatch.setattr("app.services.harness_kg_signals.gather_kg_signals", _boom)

    inputs = gather_inputs("proj-kg-boom", limit=10)
    assert inputs["kg_signals"] == []
    # Sibling keys still present and well-formed.
    assert inputs["project_id"] == "proj-kg-boom"
    assert "primitives" in inputs
    assert inputs["trajectories"] == []
    assert inputs["takeaways"] == []


# --------------------------------------------------------------------------
# 4.3 — build_workspace writes KG_SIGNALS.md
# --------------------------------------------------------------------------


def test_build_workspace_writes_kg_signals_sorted_by_weight(tmp_path):
    """``KG_SIGNALS.md`` is written when signals are present, contains each
    signal's content + weight, and is ordered by weight descending (the
    highest-weight section appears before the lower one)."""
    inputs = {
        "project_id": "proj-kg",
        "primitives": _empty_primitives(),
        "trajectories": [],
        "takeaways": [],
        "kg_signals": [
            _signal("Low one?", "LOW-WEIGHT-CONTENT", 0.35).model_dump(),
            _signal("High one?", "HIGH-WEIGHT-CONTENT", 0.7, forged=True).model_dump(),
        ],
    }

    scratch = build_workspace(inputs, tmp_path / "ws")
    md_path = scratch / "KG_SIGNALS.md"
    assert md_path.is_file()
    text = md_path.read_text()

    assert "HIGH-WEIGHT-CONTENT" in text
    assert "LOW-WEIGHT-CONTENT" in text
    assert "weight 0.70" in text
    assert "weight 0.35" in text
    # Higher weight ranked first.
    assert text.index("HIGH-WEIGHT-CONTENT") < text.index("LOW-WEIGHT-CONTENT")
    # already_forged annotation rendered on the forged signal.
    assert "already-forged" in text


def test_build_workspace_omits_kg_signals_when_empty(tmp_path):
    """No signals → ``KG_SIGNALS.md`` is not created at all."""
    inputs = {
        "project_id": "proj-kg",
        "primitives": _empty_primitives(),
        "trajectories": [],
        "takeaways": [],
        "kg_signals": [],
    }
    scratch = build_workspace(inputs, tmp_path / "ws")
    assert not (scratch / "KG_SIGNALS.md").exists()


def test_build_workspace_omits_kg_signals_when_key_absent(tmp_path):
    """``kg_signals`` key entirely absent (older inputs dict) → no file,
    no KeyError."""
    inputs = {
        "project_id": "proj-kg",
        "primitives": _empty_primitives(),
        "trajectories": [],
        "takeaways": [],
    }
    scratch = build_workspace(inputs, tmp_path / "ws")
    assert not (scratch / "KG_SIGNALS.md").exists()


# --------------------------------------------------------------------------
# 4.4 — prompt references KG_SIGNALS.md
# --------------------------------------------------------------------------


def test_prompt_references_kg_signals_file(tmp_path):
    """PROMPT.md points Codex at ``KG_SIGNALS.md`` so the signals are read."""
    inputs = {
        "project_id": "proj-kg",
        "primitives": _empty_primitives(),
        "trajectories": [],
        "takeaways": [],
        "kg_signals": [],
    }
    scratch = build_workspace(inputs, tmp_path / "ws")
    prompt = (scratch / "PROMPT.md").read_text()
    assert "KG_SIGNALS.md" in prompt
