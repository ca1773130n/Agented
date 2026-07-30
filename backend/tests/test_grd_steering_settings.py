"""GRD 0.5.0 research-steering settings — the two knobs an operator can reach
from the settings page, backed by the project's real ``.planning/config.json``.

The point of these tests is that the settings are REAL: a toggle that writes
Agented's own settings table would change nothing about how GRD behaves, so
every test here asserts against the file GRD actually reads.
"""

import json

import pytest

from app.services import grd_config_service as gcs


@pytest.fixture
def project_with_planning(isolated_db, tmp_path):
    """A project whose local_path holds a realistic GRD config."""
    from app.db.connection import get_connection

    root = tmp_path / "proj"
    (root / ".planning").mkdir(parents=True)
    (root / ".planning" / "config.json").write_text(
        json.dumps(
            {
                "model_profile": "quality",
                "autonomous_mode": True,
                "workflow": {"research": True},
                "research_gates": {
                    "verification_design": False,
                    "interactive": {"enabled": True, "seed": True, "fallback": "panel"},
                },
                "tracker": {"provider": "none"},
            },
            indent=2,
        )
    )
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, local_path) VALUES (?,?,?)",
            ("proj-1", "P1", str(root)),
        )
        conn.commit()
    return root


def _config(root):
    return json.loads((root / ".planning" / "config.json").read_text())


def test_reads_both_settings(project_with_planning):
    entry = gcs.get_steering("proj-1")
    assert entry["configured"] is True
    assert entry["autonomous_mode"] is True
    assert entry["interactive_enabled"] is True
    assert entry["interactive_fallback"] == "panel"


def test_defaults_match_grd_when_keys_absent(isolated_db, tmp_path):
    """A pre-0.5.0 config has no `interactive` block at all. We must report GRD's
    OWN defaults (enabled false, fallback 'recommended' — defaultInteractive() in
    checkpoints.ts), not invent our own, or the UI shows a state GRD disagrees
    with."""
    from app.db.connection import get_connection

    root = tmp_path / "old"
    (root / ".planning").mkdir(parents=True)
    (root / ".planning" / "config.json").write_text(json.dumps({"model_profile": "quality"}))
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, local_path) VALUES (?,?,?)",
            ("proj-old", "Old", str(root)),
        )
        conn.commit()

    entry = gcs.get_steering("proj-old")
    assert entry["configured"] is True
    assert entry["autonomous_mode"] is False
    assert entry["interactive_enabled"] is False
    assert entry["interactive_fallback"] == "recommended"


def test_unknown_fallback_value_reads_as_recommended(isolated_db, tmp_path):
    """GRD warns and reverts an unrecognised fallback to 'recommended'. Showing
    the raw junk instead would tell the operator a lie about what will run."""
    from app.db.connection import get_connection

    root = tmp_path / "junk"
    (root / ".planning").mkdir(parents=True)
    (root / ".planning" / "config.json").write_text(
        json.dumps({"research_gates": {"interactive": {"fallback": "telepathy"}}})
    )
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, local_path) VALUES (?,?,?)",
            ("proj-junk", "Junk", str(root)),
        )
        conn.commit()

    assert gcs.get_steering("proj-junk")["interactive_fallback"] == "recommended"


def test_write_preserves_every_other_key(project_with_planning):
    """This file is GRD's, not ours. A patch must not drop model_profile,
    workflow, tracker, or the sibling pre-0.5.0 research gate."""
    before = _config(project_with_planning)
    gcs.set_steering("proj-1", autonomous_mode=False)
    after = _config(project_with_planning)

    assert after["autonomous_mode"] is False
    assert after["model_profile"] == before["model_profile"]
    assert after["workflow"] == before["workflow"]
    assert after["tracker"] == before["tracker"]
    # the sibling gate inside the block we reached into
    assert after["research_gates"]["verification_design"] is False
    assert after["research_gates"]["interactive"]["seed"] is True
    assert after["research_gates"]["interactive"]["enabled"] is True


def test_patch_fallback_only_leaves_autonomous_mode_alone(project_with_planning):
    gcs.set_steering("proj-1", interactive_fallback="recommended")
    after = _config(project_with_planning)
    assert after["research_gates"]["interactive"]["fallback"] == "recommended"
    assert after["autonomous_mode"] is True  # untouched


def test_patch_both_at_once(project_with_planning):
    entry = gcs.set_steering("proj-1", autonomous_mode=False, interactive_fallback="recommended")
    assert entry["autonomous_mode"] is False
    assert entry["interactive_fallback"] == "recommended"
    after = _config(project_with_planning)
    assert after["autonomous_mode"] is False
    assert after["research_gates"]["interactive"]["fallback"] == "recommended"


def test_builds_missing_nesting_without_replacing_siblings(isolated_db, tmp_path):
    """Setting fallback on a config whose research_gates exists but has no
    `interactive` must add the block, not replace research_gates wholesale."""
    from app.db.connection import get_connection

    root = tmp_path / "partial"
    (root / ".planning").mkdir(parents=True)
    (root / ".planning" / "config.json").write_text(
        json.dumps({"research_gates": {"baseline_review": True}})
    )
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, local_path) VALUES (?,?,?)",
            ("proj-p", "P", str(root)),
        )
        conn.commit()

    gcs.set_steering("proj-p", interactive_fallback="panel")
    gates = json.loads((root / ".planning" / "config.json").read_text())["research_gates"]
    assert gates["baseline_review"] is True  # sibling survived
    assert gates["interactive"]["fallback"] == "panel"


def test_refuses_unknown_fallback(project_with_planning):
    with pytest.raises(ValueError, match="interactive_fallback"):
        gcs.set_steering("proj-1", interactive_fallback="panel_of_experts")
    # and nothing was written
    assert _config(project_with_planning)["research_gates"]["interactive"]["fallback"] == "panel"


def test_missing_config_fails_closed_rather_than_creating_one(isolated_db, tmp_path):
    """Writing a fresh config.json into a project GRD was never initialised in
    would look like a working setup while silently defining every other GRD
    setting by omission."""
    from app.db.connection import get_connection

    root = tmp_path / "nogrd"
    root.mkdir()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, local_path) VALUES (?,?,?)",
            ("proj-none", "None", str(root)),
        )
        conn.commit()

    assert gcs.get_steering("proj-none")["configured"] is False
    with pytest.raises(ValueError, match="no readable GRD config"):
        gcs.set_steering("proj-none", autonomous_mode=True)
    assert not (root / ".planning").exists()


def test_corrupt_config_reads_as_unconfigured_and_is_never_clobbered(isolated_db, tmp_path):
    """A config we merely failed to PARSE must not be overwritten — that would
    destroy a real GRD setup."""
    from app.db.connection import get_connection

    root = tmp_path / "corrupt"
    (root / ".planning").mkdir(parents=True)
    cfg = root / ".planning" / "config.json"
    cfg.write_text("{not json at all")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, name, local_path) VALUES (?,?,?)",
            ("proj-c", "C", str(root)),
        )
        conn.commit()

    assert gcs.get_steering("proj-c")["configured"] is False
    with pytest.raises(ValueError):
        gcs.set_steering("proj-c", autonomous_mode=True)
    assert cfg.read_text() == "{not json at all"


def test_project_without_local_path_is_unconfigured(isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name) VALUES (?,?)", ("proj-nolp", "NoLP"))
        conn.commit()

    entry = gcs.get_steering("proj-nolp")
    assert entry["configured"] is False and entry["config_path"] is None
    with pytest.raises(ValueError, match="local_path"):
        gcs.set_steering("proj-nolp", autonomous_mode=True)


def test_written_file_stays_grd_formatted(project_with_planning):
    """indent=2 + trailing newline, matching GRD's own writer — otherwise every
    toggle churns the whole file in git."""
    gcs.set_steering("proj-1", autonomous_mode=False)
    text = (project_with_planning / ".planning" / "config.json").read_text()
    assert text.endswith("\n")
    assert '\n  "autonomous_mode"' in text
    assert json.loads(text)["autonomous_mode"] is False


def test_no_tmp_file_left_behind(project_with_planning):
    gcs.set_steering("proj-1", autonomous_mode=False)
    leftovers = list((project_with_planning / ".planning").glob("*.tmp"))
    assert leftovers == []


# ---------------------------------------------------------------------------
# Route layer — the service tests above bypass HTTP, so these cover the
# validation the handler owns and the status-code split.
# ---------------------------------------------------------------------------


def test_route_lists_projects(project_with_planning):
    from app_litestar.routes.grd_settings import list_grd_steering

    body = list_grd_steering.fn()
    assert [p["project_id"] for p in body["projects"]] == ["proj-1"]


def test_route_happy_path_patches_both(project_with_planning):
    from app_litestar.routes.grd_settings import set_grd_steering

    body = set_grd_steering.fn(
        "proj-1", {"autonomous_mode": False, "interactive_fallback": "recommended"}
    )
    assert body["project"]["autonomous_mode"] is False
    assert body["project"]["interactive_fallback"] == "recommended"
    assert _config(project_with_planning)["autonomous_mode"] is False


def test_route_rejects_empty_patch(project_with_planning):
    """A 200 on an empty body would look like a saved change that never was."""
    from litestar.exceptions import ValidationException

    from app_litestar.routes.grd_settings import set_grd_steering

    with pytest.raises(ValidationException):
        set_grd_steering.fn("proj-1", {})
    with pytest.raises(ValidationException):
        set_grd_steering.fn("proj-1", None)


@pytest.mark.parametrize(
    "payload",
    [
        {"interactive_fallback": "panel_of_experts"},
        {"autonomous_mode": "yes"},
        {"autonomous_mode": 1},
    ],
)
def test_route_rejects_bad_types_and_values(project_with_planning, payload):
    from litestar.exceptions import ValidationException

    from app_litestar.routes.grd_settings import set_grd_steering

    with pytest.raises(ValidationException):
        set_grd_steering.fn("proj-1", payload)
    # unchanged on disk
    assert _config(project_with_planning)["autonomous_mode"] is True


def test_route_missing_project_is_404_but_unconfigured_is_400(isolated_db, tmp_path):
    """Different failures, different codes: a project that doesn't exist is a
    404; one that exists but has no GRD config is a valid request this project
    simply cannot accept."""
    from litestar.exceptions import NotFoundException, ValidationException

    from app.db.connection import get_connection
    from app_litestar.routes.grd_settings import set_grd_steering

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name) VALUES (?,?)", ("proj-bare", "Bare"))
        conn.commit()

    with pytest.raises(NotFoundException):
        set_grd_steering.fn("proj-nope", {"autonomous_mode": True})
    with pytest.raises(ValidationException):
        set_grd_steering.fn("proj-bare", {"autonomous_mode": True})


def test_list_includes_every_project(project_with_planning, isolated_db):
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name) VALUES (?,?)", ("proj-2", "Bare"))
        conn.commit()

    rows = gcs.list_steering()
    by_id = {r["project_id"]: r for r in rows}
    assert by_id["proj-1"]["configured"] is True
    assert by_id["proj-2"]["configured"] is False
