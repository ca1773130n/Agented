"""Tests for the Tesserae integration.

The Tesserae CLI is mocked at the subprocess boundary so tests stay
hermetic; the integration's own normalisation + DB lookups are
exercised end-to-end against ``isolated_db``.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from app.services import tesserae_integration as ti


def _seed_project_with_tesserae(
    project_id: str,
    *,
    root: Path | None = None,
    name: str = "Test",
) -> str:
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name, local_path, "
            "tesserae_project_root) VALUES (?, ?, ?, ?)",
            (project_id, name, str(root) if root else None, str(root) if root else None),
        )
        conn.commit()
    return project_id


def _seed_super_agent_session(
    session_id: str,
    *,
    project_id: str | None = None,
    status: str = "completed",
    conversation_log: str = "[]",
) -> None:
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO super_agents (id, name) VALUES ('sa-tess', 'SA')")
        conn.execute(
            "INSERT INTO super_agent_sessions (id, super_agent_id, "
            "status, project_id, conversation_log, started_at) "
            "VALUES (?, 'sa-tess', ?, ?, ?, datetime('now'))",
            (session_id, status, project_id, conversation_log),
        )
        conn.commit()


# ---------- project linkage --------------------------------------------------


def test_get_tesserae_root_returns_none_when_unset(isolated_db):
    _seed_project_with_tesserae("proj-no-tess", root=None)
    assert ti.get_tesserae_root("proj-no-tess") is None


def test_get_tesserae_root_returns_path_when_set(isolated_db, tmp_path):
    _seed_project_with_tesserae("proj-with-tess", root=tmp_path)
    out = ti.get_tesserae_root("proj-with-tess")
    assert out is not None
    assert out == tmp_path


def test_set_tesserae_root_is_idempotent(isolated_db, tmp_path):
    _seed_project_with_tesserae("proj-set", root=None)
    ti.set_tesserae_root("proj-set", tmp_path)
    ti.set_tesserae_root("proj-set", tmp_path)
    assert ti.get_tesserae_root("proj-set") == tmp_path.resolve()


def test_build_activity_summary_rejects_argv_flag_smuggling():
    """`day`/`project` become CLI argv — a leading-dash value must be rejected
    (argv flag smuggling), never handed to the subprocess."""
    with patch.object(ti, "_run_tesserae") as run:
        assert ti.build_activity_summary(period="day", project="--output=/tmp/x")["ok"] is False
        assert ti.build_activity_summary(period="day", day="--week")["ok"] is False
        assert ti.build_activity_summary(period="week", day="-9999-01-01")["ok"] is False
        run.assert_not_called()


def test_build_decisions_rejects_argv_flag_smuggling():
    """Same argv-injection guard on `tesserae decisions` inputs."""
    with patch.object(ti, "_run_tesserae") as run:
        assert ti.build_decisions(period="day", project="--json=/etc/passwd")["ok"] is False
        assert ti.build_decisions(period="day", day="--week")["ok"] is False
        run.assert_not_called()


def test_build_decisions_parses_json_array():
    """Structured --json output is parsed into a decisions list."""
    from app.services.tesserae_integration import TesseraeOpResult

    payload = '[{"ts":"2026-07-05T00:00:00+00:00","source":"human","project":"p","question":"q","answer":"a","options":["a","b"]}]'
    fake = TesseraeOpResult(op="decisions", ok=True, stdout=payload, stderr="")
    with patch.object(ti, "_run_tesserae", return_value=fake):
        # refresh=True bypasses the result cache so we exercise the parse.
        res = ti.build_decisions(period="day", day="2026-07-05", include_agent=False, refresh=True)
    assert res["ok"] is True
    assert len(res["decisions"]) == 1
    assert res["decisions"][0]["source"] == "human"


def test_build_activity_summary_caches_result(tmp_path, monkeypatch):
    """A second call with the same params (no refresh) is served from cache —
    the slow multi-project scan (`_run_tesserae`) runs only once."""
    from app.services.tesserae_integration import TesseraeOpResult

    monkeypatch.setattr(ti, "_TESSERAE_CACHE_DIR", tmp_path / "cache")
    fake = TesseraeOpResult(op="summary", ok=True, stdout="# Activity summary — d\nbody", stderr="")
    with patch.object(ti, "_run_tesserae", return_value=fake) as run:
        r1 = ti.build_activity_summary(period="day", day="2020-01-01")  # past → immutable cache
        r2 = ti.build_activity_summary(period="day", day="2020-01-01")
        r3 = ti.build_activity_summary(period="day", day="2020-01-01", refresh=True)
    assert r1["ok"] and r2 == r1
    assert run.call_count == 2  # call 1 (miss) + call 3 (refresh); call 2 served from cache


# ---------- session normalization -------------------------------------------


def test_normalize_super_agent_extracts_message_count_and_preview():
    log = json.dumps(
        [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world this is the assistant"},
            {"role": "user", "content": "ok"},
        ]
    )
    out = ti._normalize_super_agent_session(
        {
            "conversation_log": log,
            "started_at": "2026-01-01",
            "ended_at": "2026-01-02",
            "super_agent_id": "sa-1",
        }
    )
    assert out["message_count"] == 3
    assert "world this is the assistant" in out["redacted_preview"]


# ---------- on_session_complete handler -------------------------------------


def test_handler_noop_for_project_without_tesserae(isolated_db):
    """Tesserae unset → handler must NOT call the CLI."""
    _seed_project_with_tesserae("proj-noop", root=None)
    _seed_super_agent_session("sess-1", project_id="proj-noop")
    with patch.object(ti, "subprocess") as mock_sp:
        ti.on_session_complete(
            "super_agent",
            "sess-1",
            "proj-noop",
            "completed",
            None,
        )
    mock_sp.run.assert_not_called()


def test_handler_skips_failed_outcomes(isolated_db, tmp_path):
    """Failure paths are owned by the annotator/extractor — Tesserae
    consolidates SUCCESSFUL trajectories. A failed status doesn't fire
    Tesserae."""
    (tmp_path / ".tesserae").mkdir()
    _seed_project_with_tesserae("proj-fail", root=tmp_path)
    _seed_super_agent_session("sess-fail", project_id="proj-fail", status="terminated")
    with patch.object(ti, "subprocess") as mock_sp:
        ti.on_session_complete(
            "super_agent",
            "sess-fail",
            "proj-fail",
            "terminated",
            None,
        )
    mock_sp.run.assert_not_called()


def test_handler_invokes_cli_with_normalized_batch(isolated_db, tmp_path):
    """Happy path: completed session on a Tesserae-enabled project →
    CLI invoked exactly once with a tempfile containing the normalized
    batch."""
    (tmp_path / ".tesserae").mkdir()
    _seed_project_with_tesserae("proj-go", root=tmp_path, name="GoProject")
    log = json.dumps(
        [
            {"role": "assistant", "content": "I learned the layout"},
        ]
    )
    _seed_super_agent_session("sess-go", project_id="proj-go", conversation_log=log)

    class _FakeResult:
        returncode = 0
        stdout = "Imported harness sessions: 1"
        stderr = ""

    captured: dict = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        # Verify the tempfile contains valid JSON with at least one
        # normalised entry.
        json_path = cmd[3]
        captured["payload"] = json.loads(Path(json_path).read_text())
        return _FakeResult()

    with patch.object(ti.subprocess, "run", side_effect=_fake_run):
        ti.on_session_complete(
            "super_agent",
            "sess-go",
            "proj-go",
            "completed",
            None,
        )

    # Modern top-level form (0.9.0 retired `tesserae project sessions import`).
    assert captured["cmd"][1:3] == ["sessions", "import"]
    assert "project" not in captured["cmd"][:3]
    assert "--project" in captured["cmd"]
    assert str(tmp_path.resolve()) in captured["cmd"]
    # Payload normalized correctly.
    assert isinstance(captured["payload"], list)
    assert captured["payload"]
    entry = captured["payload"][0]
    assert entry["project_root"] == str(tmp_path.resolve())
    assert entry["project_name"] == "GoProject"
    assert entry["id"] == "agented:super_agent:sess-go"


def test_handler_swallows_cli_missing(isolated_db, tmp_path):
    """If the Tesserae CLI isn't installed, the handler must NOT raise
    — observability never blocks the session-completion chain."""
    (tmp_path / ".tesserae").mkdir()
    _seed_project_with_tesserae("proj-no-cli", root=tmp_path)
    _seed_super_agent_session("sess-no-cli", project_id="proj-no-cli")
    with patch.object(ti.subprocess, "run", side_effect=FileNotFoundError("no tesserae")):
        # Must not raise.
        ti.on_session_complete(
            "super_agent",
            "sess-no-cli",
            "proj-no-cli",
            "completed",
            None,
        )


def test_set_tesserae_root_auto_binds_mcp_server(isolated_db, tmp_path):
    """Enabling Tesserae for a project upserts a per-project mcp_server
    entry pointing at the project's graph.json AND adds a
    project_forge_bindings row (kind=mcp_server, enabled=1). This is
    what gives the team-leader super-agent ``tesserae_ask`` at
    runtime without any operator-side MCP config."""
    _seed_project_with_tesserae("proj-bind", root=None)
    ti.set_tesserae_root("proj-bind", tmp_path)

    from app.db.connection import get_connection

    with get_connection() as conn:
        # mcp_servers row exists with the expected name + command
        srv = conn.execute(
            "SELECT id, name, command, args FROM mcp_servers WHERE name = ?",
            ("tesserae-proj-bind",),
        ).fetchone()
        assert srv is not None
        assert srv["command"] == ti._TESSERAE_MCP_COMMAND
        assert ".tesserae/graph.json" in srv["args"]

        # Project binding exists + is enabled
        binding = conn.execute(
            "SELECT id, kind, asset_id, enabled FROM project_forge_bindings "
            "WHERE project_id = ? AND kind = 'mcp_server'",
            ("proj-bind",),
        ).fetchone()
        assert binding is not None
        assert str(binding["asset_id"]) == str(srv["id"])
        assert binding["enabled"] == 1


def test_unset_tesserae_root_disables_mcp_binding(isolated_db, tmp_path):
    """Disabling Tesserae flips the binding's enabled flag (keeps the
    mcp_servers row for history). Operator can re-enable + the
    binding wakes up again."""
    _seed_project_with_tesserae("proj-unbind", root=None)
    ti.set_tesserae_root("proj-unbind", tmp_path)
    ti.unset_tesserae_root_bindings("proj-unbind")

    from app.db.connection import get_connection

    with get_connection() as conn:
        binding = conn.execute(
            "SELECT enabled FROM project_forge_bindings "
            "WHERE project_id = ? AND kind = 'mcp_server'",
            ("proj-unbind",),
        ).fetchone()
        assert binding is not None
        assert binding["enabled"] == 0


def test_re_enable_tesserae_re_enables_existing_binding(isolated_db, tmp_path):
    """Don't create a duplicate mcp_servers row when an operator
    disables then re-enables. The existing row + binding both come
    back online."""
    _seed_project_with_tesserae("proj-cycle", root=None)
    ti.set_tesserae_root("proj-cycle", tmp_path)
    ti.unset_tesserae_root_bindings("proj-cycle")
    ti.set_tesserae_root("proj-cycle", tmp_path)

    from app.db.connection import get_connection

    with get_connection() as conn:
        # Exactly ONE mcp_server, exactly ONE binding, both alive.
        servers = conn.execute(
            "SELECT id FROM mcp_servers WHERE name = ?",
            ("tesserae-proj-cycle",),
        ).fetchall()
        assert len(servers) == 1
        bindings = conn.execute(
            "SELECT enabled FROM project_forge_bindings "
            "WHERE project_id = ? AND kind = 'mcp_server'",
            ("proj-cycle",),
        ).fetchall()
        assert len(bindings) == 1
        assert bindings[0]["enabled"] == 1


def test_export_skips_when_tesserae_root_uninitialized(isolated_db, tmp_path):
    """Tesserae column set, but the workspace at that path doesn't have
    ``.tesserae/`` yet (operator forgot to ``tesserae init``).
    Skip the import and log a hint — don't try anyway."""
    _seed_project_with_tesserae("proj-uninit", root=tmp_path)
    # NOTE: no .tesserae/ created
    _seed_super_agent_session("sess-uninit", project_id="proj-uninit")
    result = ti.export_sessions_to_tesserae("proj-uninit")
    assert result["imported"] == 0
    assert result["skipped_reason"] == "tesserae_not_initialized"


# ── 0.9.0 migration: init / ingest / build-site use MODERN top-level argv ──
# (Tesserae 0.9.0 retired the `tesserae project <cmd>` group; these regress to
#  exit-2 stubs if the `project` prefix ever creeps back in.)


def _capture_argv(monkeypatch):
    cap: dict = {}

    class _Ok:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(ti.subprocess, "run", lambda cmd, **kw: cap.update(cmd=cmd) or _Ok())
    return cap


def test_init_uses_modern_top_level_argv(isolated_db, tmp_path, monkeypatch):
    _seed_project_with_tesserae("proj-init", root=tmp_path)
    cap = _capture_argv(monkeypatch)
    res = ti.init_workspace("proj-init")
    assert res.ok
    assert cap["cmd"][1] == "init" and "project" not in cap["cmd"][:2]
    assert "--project" in cap["cmd"] and "--bare" in cap["cmd"] and "--yes" in cap["cmd"]


def test_ingest_uses_modern_top_level_argv(isolated_db, tmp_path, monkeypatch):
    (tmp_path / "README.md").write_text("# r")
    _seed_project_with_tesserae("proj-ing", root=tmp_path)
    cap = _capture_argv(monkeypatch)
    res = ti.ingest_paths("proj-ing", ["README.md"])
    assert res.ok
    assert cap["cmd"][1] == "ingest" and "project" not in cap["cmd"][:2]
    assert "--project" in cap["cmd"]
    assert str((tmp_path / "README.md")) in cap["cmd"]


def test_build_site_maps_to_serve_dry_run(isolated_db, tmp_path, monkeypatch):
    _seed_project_with_tesserae("proj-bs", root=tmp_path)
    cap = _capture_argv(monkeypatch)
    res = ti.build_site("proj-bs")
    assert res.ok
    # 0.9.0 has no `build-site`; the site is built by `serve` (auto-build),
    # and `--dry-run` builds without starting a blocking server.
    assert cap["cmd"][1] == "serve" and "--dry-run" in cap["cmd"]
    assert "build-site" not in cap["cmd"] and "project" not in cap["cmd"][:2]


def test_run_tesserae_subcommand_helper_is_gone():
    # The dead helper that hardcoded the broken `project` prefix must stay gone.
    assert not hasattr(ti, "_run_tesserae_subcommand")


# --- 0.17 doctor / 0.16 sessions / 0.16 max_turns wiring ---------------------


def test_build_doctor_parses_report_even_on_nonzero_exit(monkeypatch):
    """`tesserae doctor --json` exits 1 when it FINDS issues — a valid report,
    not a CLI failure. build_doctor must parse stdout regardless of exit code."""
    from app.services.tesserae_integration import TesseraeOpResult

    report = {
        "project_root": "/x",
        "exit_code": 1,
        "fixed": [],
        "findings": [
            {
                "check_id": "graph_parse",
                "category": "core",
                "severity": "warn",
                "message": "stale",
                "suggestion": "recompile",
                "fixable": True,
            }
        ],
    }
    # ok=False mimics the non-zero exit; stdout still carries the JSON.
    fake = TesseraeOpResult(
        op="doctor", ok=False, stdout=json.dumps(report), stderr="", reason="exit_1"
    )
    with patch.object(ti, "_run_tesserae", return_value=fake):
        res = ti.build_doctor(refresh=True)
    assert res["ok"] is True
    assert len(res["report"]["findings"]) == 1
    assert res["report"]["findings"][0]["severity"] == "warn"


def test_build_doctor_fails_on_unparseable(monkeypatch):
    from app.services.tesserae_integration import TesseraeOpResult

    fake = TesseraeOpResult(
        op="doctor", ok=False, stdout="tesserae: command not found", stderr="", reason="cli_missing"
    )
    with patch.object(ti, "_run_tesserae", return_value=fake):
        res = ti.build_doctor(refresh=True)
    assert res["ok"] is False
    assert res["report"] is None


def test_build_lint_parses_report_even_on_nonzero_exit(monkeypatch):
    """`tesserae lint --json` exits non-zero when it FINDS issues — a valid report,
    not a CLI failure. build_lint must parse stdout regardless of exit code, and a
    leading stderr note (e.g. the 0.19 cognee-removal diagnostic) must not matter."""
    from app.services.tesserae_integration import TesseraeOpResult

    report = {
        "findings": [
            {
                "severity": "warning",
                "code": "GRAPH_WIKI_DRIFT",
                "message": "wiki page drifted from graph",
                "node_id": "n-1",
                "path": "/x/wiki.md",
                "suggested_fix": "recompile",
                "auto_fixable": False,
            }
        ],
        "by_code": {"GRAPH_WIKI_DRIFT": 1},
        "by_severity": {"info": 0, "warning": 1, "error": 0},
    }
    fake = TesseraeOpResult(
        op="lint", ok=False, stdout=json.dumps(report), stderr="note: cognee removed", reason="exit_1"
    )
    with patch.object(ti, "_run_tesserae", return_value=fake):
        res = ti.build_lint(refresh=True)
    assert res["ok"] is True
    assert res["report"]["by_severity"]["warning"] == 1
    assert res["report"]["findings"][0]["code"] == "GRAPH_WIKI_DRIFT"


def test_build_lint_fails_on_unparseable(monkeypatch):
    from app.services.tesserae_integration import TesseraeOpResult

    fake = TesseraeOpResult(
        op="lint", ok=False, stdout="tesserae: command not found", stderr="", reason="cli_missing"
    )
    with patch.object(ti, "_run_tesserae", return_value=fake):
        res = ti.build_lint(refresh=True)
    assert res["ok"] is False
    assert res["report"] is None


def test_build_lint_rejects_non_report_envelope(monkeypatch):
    """A JSON object WITHOUT ``findings`` (e.g. an error blob) must not be accepted
    + cached as a clean lint."""
    from app.services.tesserae_integration import TesseraeOpResult

    fake = TesseraeOpResult(
        op="lint", ok=False, stdout='{"error": "no graph"}', stderr="", reason="err"
    )
    with patch.object(ti, "_run_tesserae", return_value=fake):
        res = ti.build_lint(refresh=True)
    assert res["ok"] is False


def test_graph_status_parses_overview():
    from app.services.tesserae_integration import TesseraeOpResult

    payload = (
        '{"project":"/x","nodes":4042,"edges":13401,"graph_corrupt":false,'
        '"sessions":977,"last_compile":"2026-07-07T16:05:42","vault":"/v","site":"/s"}'
    )
    fake = TesseraeOpResult(op="status", ok=True, stdout=payload, stderr="")
    with patch.object(ti, "_run_tesserae", return_value=fake):
        res = ti.graph_status()
    assert res["ok"] is True
    assert res["status"]["nodes"] == 4042
    assert res["status"]["edges"] == 13401


def test_graph_status_rejects_non_status_envelope():
    """A JSON object without `nodes` (e.g. an error blob) must not be accepted."""
    from app.services.tesserae_integration import TesseraeOpResult

    fake = TesseraeOpResult(op="status", ok=False, stdout='{"error":"no graph"}', stderr="")
    with patch.object(ti, "_run_tesserae", return_value=fake):
        assert ti.graph_status()["ok"] is False


def test_query_graph_parses_hits():
    from app.services.tesserae_integration import TesseraeOpResult

    payload = (
        '{"question":"loop","hits":[{"title":"Core Loop","kind":"sources","href":"h",'
        '"score":0.83,"excerpt":"e","page_path":"/p","node_id":"sources:core","arxiv_id":null}]}'
    )
    fake = TesseraeOpResult(op="query", ok=True, stdout=payload, stderr="")
    with patch.object(ti, "_run_tesserae", return_value=fake) as run:
        res = ti.query_graph("loop", top_k=5)
    assert res["ok"] is True
    assert len(res["hits"]) == 1
    assert res["hits"][0]["node_id"] == "sources:core"
    # argv carries the guarded positional + bounds
    args = run.call_args[0][1]
    assert args[:2] == ["query", "loop"] and "--json" in args and "5" in args


def test_query_graph_rejects_argv_flag_smuggling_and_bounds():
    """`question`/`kind` become CLI argv; a leading-dash value or an out-of-range
    top_k must be rejected before the subprocess runs."""
    with patch.object(ti, "_run_tesserae") as run:
        assert ti.query_graph("")["ok"] is False  # empty
        assert ti.query_graph("--json=/etc/passwd")["ok"] is False  # flag smuggle
        assert ti.query_graph("x", top_k=0)["ok"] is False  # bad bound
        assert ti.query_graph("x", top_k=999)["ok"] is False  # over cap
        assert ti.query_graph("x", kind="--evil")["ok"] is False  # kind smuggle
        run.assert_not_called()


def test_run_research_rejects_argv_and_bounds():
    """`query` becomes CLI argv; a leading-dash value or out-of-range knob must be
    rejected before the (slow, costly) subprocess runs."""
    with patch.object(ti, "_run_tesserae") as run:
        assert ti.run_research("")["ok"] is False  # empty
        assert ti.run_research("--output=/etc/passwd")["ok"] is False  # flag smuggle
        assert ti.run_research("x", breadth=99)["ok"] is False  # over cap
        assert ti.run_research("x", depth=0)["ok"] is False  # bad bound
        assert ti.run_research("x", top_k=99)["ok"] is False  # over cap
        run.assert_not_called()


def test_run_research_reads_report_from_output_path():
    """Happy path: the runner passes `--output <tmp>`, then reads that file back as
    the report markdown (so it doesn't have to guess the slug)."""
    from app.services.tesserae_integration import TesseraeOpResult

    def _fake_run(op, args, *, cwd, timeout):
        # args carries `--output <path>`; write the report there like the real CLI.
        out = args[args.index("--output") + 1]
        Path(out).write_text("# Research report\n\nfindings", encoding="utf-8")
        return TesseraeOpResult(op="research", ok=True, stdout="wrote report", stderr="")

    with patch.object(ti, "_run_tesserae", side_effect=_fake_run):
        res = ti.run_research("how do loops work?", breadth=2, depth=1)
    assert res["ok"] is True
    assert "# Research report" in res["report_md"]


def test_run_research_fails_when_no_report_produced():
    from app.services.tesserae_integration import TesseraeOpResult

    fake = TesseraeOpResult(op="research", ok=False, stdout="", stderr="no LLM backend")
    with patch.object(ti, "_run_tesserae", return_value=fake):
        res = ti.run_research("q")
    assert res["ok"] is False
    assert res["report_md"] == ""


def test_run_research_async_job_lifecycle():
    """The async wrapper stores a running job, runs run_research in a thread, and
    marks it completed with the report in the job result."""
    import time as _t

    with patch.object(
        ti, "run_research", return_value={"ok": True, "query": "q", "report_md": "# R", "reason": None}
    ):
        job_id = ti.run_research_async("q")
        assert job_id.startswith("tess-research-")
        # poll the in-memory job store until the daemon thread finishes
        for _ in range(50):
            job = ti.get_op_job(job_id)
            if job and job["status"] != "running":
                break
            _t.sleep(0.02)
    job = ti.get_op_job(job_id)
    assert job["status"] == "completed"
    assert job["result"]["report_md"] == "# R"


def test_config_status_parses_provider_and_liveness():
    from app.services.tesserae_integration import TesseraeOpResult

    text = (
        "Tesserae LLM backend (resolved for .):\n"
        "  provider   : codex   [~/.tesserae/config.json]\n"
        "  codex_home : /Users/x/.codex   [env CODEX_HOME]\n"
        "  effort     : medium   [default]\n\n"
        "  liveness   : ✓ OK (backend responded)\n"
    )
    fake = TesseraeOpResult(op="config", ok=True, stdout=text, stderr="")
    with patch.object(ti, "_run_tesserae", return_value=fake):
        res = ti.config_status()
    assert res["ok"] is True
    assert res["provider"] == "codex"
    assert res["effort"] == "medium"
    assert res["liveness_ok"] is True
    assert res["source"] == "~/.tesserae/config.json"


def test_config_status_marks_dead_backend():
    from app.services.tesserae_integration import TesseraeOpResult

    text = "  provider   : claude\n  liveness   : ✗ FAILED (no response)\n"
    fake = TesseraeOpResult(op="config", ok=True, stdout=text, stderr="")
    with patch.object(ti, "_run_tesserae", return_value=fake):
        res = ti.config_status()
    assert res["liveness_ok"] is False


def test_config_status_empty_output_is_failure():
    from app.services.tesserae_integration import TesseraeOpResult

    fake = TesseraeOpResult(op="config", ok=False, stdout="", stderr="cli missing", reason="cli_missing")
    with patch.object(ti, "_run_tesserae", return_value=fake):
        assert ti.config_status()["ok"] is False


def test_engine_refresh_async_job_lifecycle():
    import time as _t

    from app.services.tesserae_integration import TesseraeOpResult

    fake = TesseraeOpResult(op="engine", ok=True, stdout="drained", stderr="")
    with patch.object(ti, "_run_tesserae", return_value=fake):
        job_id = ti.engine_refresh_async()
        assert job_id.startswith("tess-engine-")
        for _ in range(50):
            job = ti.get_op_job(job_id)
            if job and job["status"] != "running":
                break
            _t.sleep(0.02)
    job = ti.get_op_job(job_id)
    assert job["status"] == "completed"
    assert job["op"] == "engine-refresh"


def test_list_sessions_parses_array_and_caps_limit():
    from app.services.tesserae_integration import TesseraeOpResult

    rows = [
        {"date": "2026-07-01", "harness": "codex", "project": "P", "title": "t1", "slug": "s1"},
        {"date": "2026-07-01", "harness": "claude", "project": "P", "title": "t2", "slug": "s2"},
    ]
    fake = TesseraeOpResult(op="sessions_list", ok=True, stdout=json.dumps(rows), stderr="")
    with patch.object(ti, "_run_tesserae", return_value=fake):
        res = ti.list_sessions(limit=1)
    assert res["ok"] is True
    assert len(res["sessions"]) == 1  # capped
    assert res["sessions"][0]["slug"] == "s1"


def test_list_sessions_rejects_flag_smuggling_and_bad_limit():
    with patch.object(ti, "_run_tesserae") as run:
        assert ti.list_sessions(project="--json=/etc/passwd")["ok"] is False
        assert ti.list_sessions(limit=0)["ok"] is False
        run.assert_not_called()


def test_max_turns_validation_rejects_nonpositive():
    with patch.object(ti, "_run_tesserae") as run:
        assert ti.build_activity_summary(period="day", max_turns=0)["ok"] is False
        assert ti.build_decisions(period="day", max_turns=-3)["ok"] is False
        run.assert_not_called()


def test_ask_tesserae_no_llm_by_default_llm_opt_in(isolated_db, tmp_path):
    """Tesserae 0.18 made `ask` synthesize an LLM answer by default; the grounding
    callers must keep the cheap ranked-retrieval path (--no-llm) unless they opt in."""
    _seed_project_with_tesserae("proj-ask", root=tmp_path)
    cap: dict = {}

    class _R:
        returncode = 0
        stdout = "hits"
        stderr = ""

    def fake_run(cmd, **kw):
        cap["cmd"] = cmd
        return _R()

    with patch.object(ti.subprocess, "run", fake_run):
        assert ti.ask_tesserae("proj-ask", "q") == "hits"
        assert "--no-llm" in cap["cmd"]  # default: cheap raw retrieval preserved
        assert ti.ask_tesserae("proj-ask", "q", use_llm=True) == "hits"
        assert "--no-llm" not in cap["cmd"]  # opt-in: new planned LLM answer
        assert cap["cmd"][cap["cmd"].index("--") + 1] == "q"  # question after `--`
