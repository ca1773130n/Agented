"""GrdCliService deep-research reader tests (GRD 0.4.14).

Covers ``list_deep_reports`` / ``read_deep_report`` — the pure on-disk readers
for the standalone dated report ``/grd:deep-research`` writes under
``.planning/milestones/<milestone>/research/deep-research/<slug>-<date>.md``.
Directly exercises the path-traversal guard on ``read_deep_report`` (the name
comes from a URL param), which the route test can't reach because Litestar's
``{name:str}`` segment never spans a slash.
"""

import os

from app.services.grd_cli_service import GrdCliService


def _seed(tmp_path, milestone, name, body="# report"):
    d = tmp_path / ".planning" / "milestones" / milestone / "research" / "deep-research"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body)
    return d / name


def test_list_empty_when_dir_missing(tmp_path):
    assert GrdCliService.list_deep_reports(str(tmp_path)) == []


def test_list_across_milestones_newest_first(tmp_path):
    _seed(tmp_path, "v0.10.0", "old-2026-07-01.md")
    newer = _seed(tmp_path, "v0.11.0", "new-2026-07-06.md")
    # bump mtime so ordering is deterministic
    os.utime(str(newer), (2_000_000_000, 2_000_000_000))

    reports = GrdCliService.list_deep_reports(str(tmp_path))
    assert len(reports) == 2
    assert reports[0]["name"] == "new-2026-07-06.md"
    assert reports[0]["milestone"] == "v0.11.0"
    assert reports[0]["path"].endswith(
        os.path.join("v0.11.0", "research", "deep-research", "new-2026-07-06.md")
    )
    names = {r["name"] for r in reports}
    assert names == {"old-2026-07-01.md", "new-2026-07-06.md"}


def test_read_returns_markdown(tmp_path):
    _seed(tmp_path, "v0.11.0", "foo-2026-07-06.md", body="# Deep\n\nbody")
    out = GrdCliService.read_deep_report(str(tmp_path), "foo-2026-07-06.md")
    assert out == {"name": "foo-2026-07-06.md", "markdown": "# Deep\n\nbody"}


def test_read_missing_is_none(tmp_path):
    out = GrdCliService.read_deep_report(str(tmp_path), "ghost.md")
    assert out == {"name": "ghost.md", "markdown": None}


def test_read_rejects_path_traversal(tmp_path):
    # A real secret one dir above the project must never be reachable.
    (tmp_path / "secret.md").write_text("TOP SECRET")
    _seed(tmp_path, "v0.11.0", "ok-2026-07-06.md")

    for evil in ["../secret.md", "../../etc/passwd", "a/b.md", "..%2Fsecret.md"]:
        out = GrdCliService.read_deep_report(str(tmp_path), evil)
        assert out["markdown"] is None, f"traversal not blocked: {evil}"
