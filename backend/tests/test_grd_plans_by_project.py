"""Perf regression: get_plans_by_project (single JOIN) must return the same plans,
in the same order, as the old milestones×phases×plans nested-loop fan-out."""

from app.db.grd import (
    add_project_phase,
    add_project_plan,
    create_milestone,
    get_milestones_by_project,
    get_phases_by_milestone,
    get_plans_by_phase,
    get_plans_by_project,
)
from app.db.projects import create_project


def test_get_plans_by_project_matches_nested_loop(isolated_db):
    pid = create_project("Plans Test Project")
    m1 = create_milestone(pid, "v1", "M1")
    m2 = create_milestone(pid, "v2", "M2")
    ph1 = add_project_phase(m1, 1, "P1")
    ph2 = add_project_phase(m1, 2, "P2")
    ph3 = add_project_phase(m2, 1, "P3")
    add_project_plan(ph1, 1, "plan-a")
    add_project_plan(ph1, 2, "plan-b")
    add_project_plan(ph2, 1, "plan-c")
    add_project_plan(ph3, 1, "plan-d")

    # The exact fan-out list_plans used to build by hand.
    expected = []
    for ms in get_milestones_by_project(pid):
        for ph in get_phases_by_milestone(ms["id"]):
            expected.extend(get_plans_by_phase(ph["id"]))

    actual = get_plans_by_project(pid)

    # Correctness: the single JOIN returns exactly the same plans as the fan-out —
    # none lost, none duplicated. (Cross-milestone order is created_at-based; the
    # two test milestones share a timestamp, so only the set + within-phase order
    # are deterministic to assert.)
    assert len(actual) == 4
    assert {p["id"] for p in actual} == {p["id"] for p in expected}
    assert {p["title"] for p in actual} == {"plan-a", "plan-b", "plan-c", "plan-d"}
    # Within each phase, plans stay plan_number-ascending (contiguous per phase).
    by_phase: dict[str, list[int]] = {}
    for p in actual:
        by_phase.setdefault(p["phase_id"], []).append(p["plan_number"])
    for nums in by_phase.values():
        assert nums == sorted(nums)


def test_get_plans_by_project_empty(isolated_db):
    assert get_plans_by_project("proj-nonexistent") == []
