"""Super-agent layered memory: registry sync (attribution + org hierarchy) and
L1 distilled-runbook read. The Tesserae CLI itself is not exercised here — the
attribution + distill mechanics were verified end-to-end against tesserae 0.21.0
during design; these lock the Agented-side registry composition + artifact parse."""

import json
import os
import sys
import textwrap
import time

import pytest

from app.services import super_agent_memory as sam


@pytest.fixture
def project_with_super_agents(isolated_db, tmp_path, monkeypatch):
    """A project whose tesserae root is tmp_path, with two super-agents (a leader
    and its report) that each ran a session in the project."""
    root = tmp_path / "ws"
    root.mkdir()
    monkeypatch.setattr(sam, "get_tesserae_root", lambda pid: root)
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name) VALUES (?,?)", ("proj-1", "P1"))
        conn.execute(
            "INSERT INTO super_agents (id, name, backend_type, parent_super_agent_id) VALUES (?,?,?,?)",
            ("super-lead", "Lead", "claude", None),
        )
        conn.execute(
            "INSERT INTO super_agents (id, name, backend_type, parent_super_agent_id) VALUES (?,?,?,?)",
            ("super-rep", "Reporter", "claude", "super-lead"),
        )
        for sid, sa in (("s1", "super-lead"), ("s2", "super-rep")):
            conn.execute(
                "INSERT INTO super_agent_sessions (id, super_agent_id, project_id) VALUES (?,?,?)",
                (sid, sa, "proj-1"),
            )
        conn.commit()
    return root


def test_agent_key_is_deterministic():
    assert sam.agent_key("super-abc") == "claude:unknown:super-abc"


@pytest.mark.parametrize(
    "bad", ["../etc/passwd", "a/b", "a\\b", "x\x00y", "", "with space", "super-x\n", "\nsuper-x"]
)
def test_agent_key_rejects_unsafe_ids(bad):
    # codex Low: the id becomes a path component — a `/`/`..`/NUL id must never
    # reach the filesystem.
    with pytest.raises(ValueError):
        sam.agent_key(bad)


def test_read_agent_memory_unsafe_id_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(sam, "get_tesserae_root", lambda pid: tmp_path)
    mem = sam.read_agent_memory("proj-1", "../../../etc/passwd")
    assert mem["notes"] == [] and mem["text"] == "" and mem["key"] is None


def test_read_agent_memory_rejects_oversize_artifact(tmp_path, monkeypatch):
    root = tmp_path / "ws"
    monkeypatch.setattr(sam, "get_tesserae_root", lambda pid: root)
    monkeypatch.setattr(sam, "_MEMORY_ARTIFACT_MAX_BYTES", 100)
    art = root / ".tesserae" / "agents" / sam.agent_key("super-x") / "distilled.graph.json"
    art.parent.mkdir(parents=True)
    art.write_text(
        json.dumps({"nodes": [{"type": "DistilledNote", "name": "n", "description": "z" * 500}]})
    )
    mem = sam.read_agent_memory("proj-1", "super-x")
    assert mem["notes"] == []  # over the byte cap → not read


def test_read_agent_memory_caps_notes_list(tmp_path, monkeypatch):
    root = tmp_path / "ws"
    monkeypatch.setattr(sam, "get_tesserae_root", lambda pid: root)
    key = sam.agent_key("super-big")
    art = root / ".tesserae" / "agents" / key / "distilled.graph.json"
    art.parent.mkdir(parents=True)
    big = "z" * 5000
    art.write_text(
        json.dumps(
            {
                "nodes": [
                    {"type": "DistilledNote", "name": f"n{i}", "description": big}
                    for i in range(10)
                ]
            }
        )
    )
    mem = sam.read_agent_memory("proj-1", "super-big", max_chars=6000)
    # codex Medium: notes list must be capped alongside text, not return all 10
    assert len(mem["notes"]) < 10
    assert len("\n\n".join(f"{n['title']}{n['body']}" for n in mem["notes"])) <= 6100


def test_sync_registry_maps_hierarchy_and_label_rules(project_with_super_agents):
    root = project_with_super_agents
    path = sam.sync_agent_registry("proj-1")
    assert path == root / ".tesserae" / "agents" / "registry.json"
    reg = json.loads(path.read_text())
    assert reg["version"] == 1
    lead, rep = "claude:unknown:super-lead", "claude:unknown:super-rep"
    # each super-agent → its own agent key, attributed by an agent_label rule
    assert reg["agents"][lead]["match"] == [{"label": "super-lead"}]
    assert reg["agents"][lead]["label"] == "Lead"
    # the report's parent is the leader (org hierarchy from parent_super_agent_id)
    assert reg["agents"][rep]["parent"] == lead
    # the leader has no parent that ran here → reports to org:root
    assert reg["agents"][lead]["parent"] == "org:root"


def test_sync_registry_parent_absent_from_project_falls_back_to_root(
    isolated_db, tmp_path, monkeypatch
):
    root = tmp_path / "ws"
    root.mkdir()
    monkeypatch.setattr(sam, "get_tesserae_root", lambda pid: root)
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name) VALUES (?,?)", ("proj-1", "P1"))
        # parent exists in super_agents but never ran a session in proj-1
        conn.execute(
            "INSERT INTO super_agents (id, name, parent_super_agent_id) VALUES (?,?,?)",
            ("super-elsewhere", "Elsewhere", None),
        )
        conn.execute(
            "INSERT INTO super_agents (id, name, parent_super_agent_id) VALUES (?,?,?)",
            ("super-child", "Child", "super-elsewhere"),
        )
        conn.execute(
            "INSERT INTO super_agent_sessions (id, super_agent_id, project_id) VALUES (?,?,?)",
            ("s1", "super-child", "proj-1"),
        )
        conn.commit()
    reg = json.loads(sam.sync_agent_registry("proj-1").read_text())
    # unknown-to-this-project parent would make the registry fail to load, so we
    # must fall back to org:root rather than reference a non-declared agent
    assert reg["agents"]["claude:unknown:super-child"]["parent"] == "org:root"


def test_sync_registry_breaks_parent_cycle(isolated_db, tmp_path, monkeypatch):
    # codex Medium: parent_super_agent_id has only an existence FK, so A→B→A is
    # possible; a cyclic registry makes Tesserae reject the whole file. Cyclic
    # nodes must fall back to org:root.
    root = tmp_path / "ws"
    root.mkdir()
    monkeypatch.setattr(sam, "get_tesserae_root", lambda pid: root)
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute("INSERT INTO projects (id, name) VALUES (?,?)", ("proj-1", "P1"))
        # Insert without the cycle first (FK), then close the loop via UPDATE.
        conn.execute("INSERT INTO super_agents (id, name) VALUES (?,?)", ("super-a", "A"))
        conn.execute(
            "INSERT INTO super_agents (id, name, parent_super_agent_id) VALUES (?,?,?)",
            ("super-b", "B", "super-a"),
        )
        conn.execute(
            "UPDATE super_agents SET parent_super_agent_id=? WHERE id=?", ("super-b", "super-a")
        )
        for sid, sa in (("s1", "super-a"), ("s2", "super-b")):
            conn.execute(
                "INSERT INTO super_agent_sessions (id, super_agent_id, project_id) VALUES (?,?,?)",
                (sid, sa, "proj-1"),
            )
        conn.commit()
    reg = json.loads(sam.sync_agent_registry("proj-1").read_text())
    parents = {k: v["parent"] for k, v in reg["agents"].items()}
    # the cycle is broken — not both pointing at each other
    assert "org:root" in parents.values()
    assert not (
        parents["claude:unknown:super-a"] == "claude:unknown:super-b"
        and parents["claude:unknown:super-b"] == "claude:unknown:super-a"
    )


def test_sync_registry_no_super_agents_returns_none(isolated_db, tmp_path, monkeypatch):
    root = tmp_path / "ws"
    root.mkdir()
    monkeypatch.setattr(sam, "get_tesserae_root", lambda pid: root)
    assert sam.sync_agent_registry("proj-empty") is None


def test_read_agent_memory_parses_distilled_notes(tmp_path, monkeypatch):
    root = tmp_path / "ws"
    monkeypatch.setattr(sam, "get_tesserae_root", lambda pid: root)
    key = sam.agent_key("super-lead")
    art = root / ".tesserae" / "agents" / key / "distilled.graph.json"
    art.parent.mkdir(parents=True)
    art.write_text(
        json.dumps(
            {
                "nodes": [
                    {"type": "DistilledNote", "name": "Gotcha: X", "description": "do Y not Z"},
                    {"type": "ExpertiseProfile", "name": "Expertise", "description": "auth, db"},
                    {
                        "type": "SessionDecision",
                        "name": "ignored",
                        "description": "not a memory type",
                    },
                ]
            }
        )
    )
    mem = sam.read_agent_memory("proj-1", "super-lead")
    assert mem["key"] == key
    assert len(mem["notes"]) == 2  # SessionDecision excluded
    assert "Gotcha: X" in mem["text"] and "do Y not Z" in mem["text"]
    assert "ignored" not in mem["text"]


def test_read_agent_memory_missing_artifact_is_empty_not_error(tmp_path, monkeypatch):
    monkeypatch.setattr(sam, "get_tesserae_root", lambda pid: tmp_path)
    mem = sam.read_agent_memory("proj-1", "super-none")
    assert mem["notes"] == [] and mem["text"] == ""


def test_read_agent_memory_bounds_output(tmp_path, monkeypatch):
    root = tmp_path / "ws"
    monkeypatch.setattr(sam, "get_tesserae_root", lambda pid: root)
    key = sam.agent_key("super-big")
    art = root / ".tesserae" / "agents" / key / "distilled.graph.json"
    art.parent.mkdir(parents=True)
    big = "z" * 5000
    art.write_text(
        json.dumps(
            {
                "nodes": [
                    {"type": "DistilledNote", "name": f"n{i}", "description": big}
                    for i in range(10)
                ]
            }
        )
    )
    mem = sam.read_agent_memory("proj-1", "super-big", max_chars=6000)
    assert len(mem["text"]) <= 6100  # a couple notes, not all ten


# --- Tesserae 0.22 `agents drill` audit escalation ---------------------------


def test_read_agent_memory_extracts_member_refs(project_with_super_agents):
    root = project_with_super_agents
    key = sam.agent_key("super-lead")
    art = root / ".tesserae" / "agents" / key / "distilled.graph.json"
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "type": "DistilledNote",
                        "name": "Gotcha",
                        "description": "watch the lock",
                        "metadata": {
                            "member_refs": [
                                {"node_id": "SessionInsight:f1", "content_hash": "h1"},
                                {"node_id": "SessionInsight:f2", "content_hash": "h2"},
                                {"content_hash": "no-node-id"},  # skipped
                            ]
                        },
                    }
                ]
            }
        )
    )
    mem = sam.read_agent_memory("proj-1", "super-lead")
    assert mem["notes"][0]["refs"] == ["SessionInsight:f1", "SessionInsight:f2"]


def test_agent_drill_rejects_flag_shaped_node_id(project_with_super_agents, monkeypatch):
    """A `--flag`-shaped node_id must be rejected BEFORE any subprocess runs."""

    def _boom(*a, **k):
        raise AssertionError("subprocess must not run for an unsafe node_id")

    monkeypatch.setattr(sam.subprocess, "run", _boom)
    res = sam.agent_drill("proj-1", "super-lead", "--output=/etc/passwd")
    assert res == {"ok": False, "reason": "unsafe_node_id"}


def test_agent_drill_puts_node_id_after_separator(project_with_super_agents, monkeypatch):
    """Flags BEFORE `--`, node_id AFTER — so a valid-token id can never land in
    flag position and smuggle a CLI option."""
    captured: dict = {}

    class _P:
        returncode = 0
        stdout = "L0 evidence here"
        stderr = ""

    def _run(argv, **k):
        captured["argv"] = argv
        return _P()

    monkeypatch.setattr(sam.subprocess, "run", _run)
    res = sam.agent_drill("proj-1", "super-lead", "SessionInsight:f1")
    argv = captured["argv"]
    assert "--" in argv
    assert argv.index("--") < argv.index("SessionInsight:f1")
    assert argv[argv.index("--") + 1] == "SessionInsight:f1"
    assert "--agent" in argv and sam.agent_key("super-lead") in argv
    assert res["ok"] is True and res["text"] == "L0 evidence here"


def test_agent_drill_disabled_without_root(monkeypatch):
    monkeypatch.setattr(sam, "get_tesserae_root", lambda pid: None)
    assert sam.agent_drill("proj-x", "super-lead", "SessionInsight:f1") == {
        "ok": False,
        "reason": "tesserae_disabled",
    }


# ---------------------------------------------------------------------------
# Automatic-distill spend gate. `tesserae distill --all` costs money, so the
# automatic caller prices the pass with a free `--dry-run` first and REFUSES the
# real run over budget. The operator path passes no budget and stays unpriced.
# ---------------------------------------------------------------------------


def _Proc(stdout="", returncode=0, stderr=""):
    """One `_run_distill` result: (returncode, stdout, stderr). `returncode=None`
    is the timeout signal."""
    return (returncode, stdout, stderr)


def _write_graph(root, body="A"):
    """`distill_super_agents` re-hashes graph.json to prove the run distills the
    bytes the dry run priced, so the budgeted path needs one to exist."""
    tess = root / ".tesserae"
    tess.mkdir(parents=True, exist_ok=True)
    (tess / "graph.json").write_text(json.dumps({"nodes": [], "marker": body}))


@pytest.fixture
def distill_enabled(project_with_super_agents, monkeypatch):
    monkeypatch.setattr(sam, "get_distill_enabled", lambda pid: True)
    _write_graph(project_with_super_agents)
    return project_with_super_agents


def _record_subprocess(monkeypatch, *procs):
    """Patch `_run_distill` to return `procs` in order, recording each argv."""
    argvs: list[list[str]] = []
    seq = list(procs)

    def _run(argv, **k):
        argvs.append(list(argv))
        return seq.pop(0) if seq else _Proc()

    monkeypatch.setattr(sam, "_run_distill", _run)
    return argvs


def test_distill_refuses_when_estimate_over_budget(distill_enabled, monkeypatch):
    """Over-budget ⇒ the dry run happens, the REAL run does not."""
    argvs = _record_subprocess(
        monkeypatch,
        _Proc("claude:unknown:super-lead  dry-run  clusters=9 estimated_llm_calls=999 scope=9\n"),
    )
    res = sam.distill_super_agents("proj-1", max_estimated_llm_calls=60)
    assert len(argvs) == 1, "the real distill must not run"
    assert "--dry-run" in argvs[0]
    assert res["ok"] is False
    assert res["reason"].startswith("estimate_over_budget")
    assert res["estimated_llm_calls"] == 999


def test_distill_runs_when_estimate_within_budget(distill_enabled, monkeypatch):
    """Control: under budget ⇒ dry run then the real, uncapped run."""
    argvs = _record_subprocess(
        monkeypatch,
        _Proc("claude:unknown:super-lead  dry-run  clusters=2 estimated_llm_calls=4 scope=2\n"),
        _Proc("claude:unknown:super-lead  written  clusters=2 llm_calls=4 cache_hits=0\n"),
    )
    res = sam.distill_super_agents("proj-1", max_estimated_llm_calls=60)
    assert len(argvs) == 2
    assert "--dry-run" in argvs[0] and "--dry-run" not in argvs[1]
    assert "--max-llm-calls" not in argvs[1], "a cap would freeze fallback prose behind a watermark"
    assert res["ok"] is True and res["llm_calls"] == 4


def test_distill_zero_estimate_is_noop(distill_enabled, monkeypatch):
    """Nothing to distill ⇒ report success without spawning the real run."""
    argvs = _record_subprocess(
        monkeypatch,
        _Proc("claude:unknown:super-lead  dry-run  clusters=0 estimated_llm_calls=0 scope=0\n"),
    )
    res = sam.distill_super_agents("proj-1", max_estimated_llm_calls=60)
    assert len(argvs) == 1
    assert res == {
        "ok": True,
        "reason": "nothing_to_distill",
        "registry": res["registry"],
        "estimated_llm_calls": 0,
        "llm_calls": 0,
    }


@pytest.mark.parametrize(
    ("dry", "why"),
    [
        (_Proc("", returncode=2, stderr="boom"), "exit_nonzero"),
        (_Proc("no estimate printed at all\n"), "no_estimate"),
        (_Proc("a  dry-run  clusters=1 est", returncode=None), "timeout"),
    ],
)
def test_distill_estimate_unavailable_refuses(distill_enabled, monkeypatch, dry, why):
    """Fail CLOSED: if the pass cannot be priced, it does not run — and the audit
    trail says WHICH failure, so an unvalidated 300 s pricing budget is
    distinguishable from a broken CLI instead of both reading
    `estimate_unavailable`."""
    argvs = _record_subprocess(monkeypatch, dry)
    res = sam.distill_super_agents("proj-1", max_estimated_llm_calls=60)
    assert len(argvs) == 1, "an unpriced pass must never reach the real run"
    assert res["ok"] is False and res["reason"] == f"estimate_unavailable_{why}"
    assert res["llm_calls"] == 0, "a refusal spent nothing and must say so"


def test_operator_distill_has_no_preflight_and_no_cap(distill_enabled, monkeypatch):
    """No budget kwarg (the operator button) ⇒ byte-for-byte the old behaviour:
    exactly one subprocess, no --dry-run, no --max-llm-calls."""
    argvs = _record_subprocess(
        monkeypatch, _Proc("claude:unknown:super-lead  written  clusters=1 llm_calls=3\n")
    )
    res = sam.distill_super_agents("proj-1")
    assert len(argvs) == 1
    assert "--dry-run" not in argvs[0] and "--max-llm-calls" not in argvs[0]
    assert res["ok"] is True


def test_distill_opt_out_never_spawns_anything(project_with_super_agents, monkeypatch):
    """The per-project opt-in gates BOTH paths, pre-flight included."""
    monkeypatch.setattr(sam, "get_distill_enabled", lambda pid: False)

    def _boom(*a, **k):
        raise AssertionError("no subprocess may run for an opted-out project")

    monkeypatch.setattr(sam, "_run_distill", _boom)
    assert sam.distill_super_agents("proj-1", max_estimated_llm_calls=60) == {
        "ok": False,
        "reason": "distill_disabled",
    }


def test_llm_calls_parsed_from_full_stdout(distill_enabled, monkeypatch):
    """Cost is summed over every agent from the FULL stdout — the 500-char tail
    would drop the early agents on a real multi-agent run."""
    noise = "x" * 900
    stdout = (
        "claude:unknown:super-lead  written  clusters=2 llm_calls=11 cache_hits=0\n"
        f"{noise}\n"
        "claude:unknown:super-rep  written  clusters=1 llm_calls=6 cache_hits=0\n"
    )
    _record_subprocess(
        monkeypatch,
        _Proc("a  dry-run  clusters=3 estimated_llm_calls=17 scope=3\n"),
        _Proc(stdout),
    )
    res = sam.distill_super_agents("proj-1", max_estimated_llm_calls=60)
    assert res["llm_calls"] == 17
    assert len(res["stdout_tail"]) == 500


def test_estimate_regex_ignores_estimated_llm_calls(distill_enabled, monkeypatch):
    """`llm_calls=` must not match inside `estimated_llm_calls=` — otherwise a
    dry-run-shaped line would be reported as money spent."""
    _record_subprocess(
        monkeypatch,
        _Proc("a  dry-run  clusters=1 estimated_llm_calls=5 scope=1\n"),
        _Proc("a  skipped-watermark (inputs unchanged)\nb  dry-run  estimated_llm_calls=42 s=1\n"),
    )
    res = sam.distill_super_agents("proj-1", max_estimated_llm_calls=60)
    assert res["llm_calls"] == 0


# ---------------------------------------------------------------------------
# F2 — a killed run's spend must read as unknown-and-non-zero, never as zero.
# ---------------------------------------------------------------------------


def test_timeout_reports_partial_spend_not_zero(distill_enabled, monkeypatch):
    """The inverted case: the 1800 s timeout is the LARGEST and least-known
    spend, and it used to be filed as `0 provider calls` because the timeout
    branch returned before stdout was parsed.

    Both directions: dropping `llm_calls`/`llm_calls_partial` from the timeout
    return, or moving the parse back below the timeout branch, fails this test;
    `test_distill_runs_when_estimate_within_budget` is the paired control showing
    a completed run still reports an exact, unflagged count.
    """
    partial_stdout = (
        "claude:unknown:super-lead  written  clusters=2 llm_calls=11 cache_hits=0\n"
        "claude:unknown:super-rep  written  clusters=1 llm_calls=6 cache_hits=0\n"
        # ...and a third agent was mid-flight when we killed the group.
    )
    _record_subprocess(
        monkeypatch,
        _Proc("a  dry-run  clusters=3 estimated_llm_calls=20 scope=3\n"),
        _Proc(partial_stdout, returncode=None),
    )
    res = sam.distill_super_agents("proj-1", max_estimated_llm_calls=60, timeout=1800)
    assert res["ok"] is False
    assert res["reason"] == "timeout_after_1800s"
    assert res["llm_calls"] == 17, "the finished agents' cost is on stdout — salvage it"
    assert res["llm_calls_partial"] is True, "17 is a FLOOR; the killed agent never printed"


def test_completed_run_is_not_flagged_partial(distill_enabled, monkeypatch):
    """Control for the above: an exact count must not be presented as a floor."""
    _record_subprocess(
        monkeypatch,
        _Proc("a  dry-run  clusters=1 estimated_llm_calls=4 scope=1\n"),
        _Proc("a  written  clusters=1 llm_calls=4 cache_hits=0\n"),
    )
    res = sam.distill_super_agents("proj-1", max_estimated_llm_calls=60)
    assert res["llm_calls"] == 4
    assert "llm_calls_partial" not in res


# Stand-in for the tesserae process tree, in BOTH shapes that matter: one child
# inside our process group, and one spawned the way tesserae actually spawns the
# provider CLI (`tesserae/llm_json.py` `_run_cli`) — `start_new_session=True`,
# i.e. its own session, out of reach of a killpg on our group.
_TREE_SCRIPT = textwrap.dedent(
    """
    import subprocess, sys, time
    sleeper = [sys.executable, "-c", "import time; time.sleep(60)"]
    ingroup = subprocess.Popen(sleeper)
    open(sys.argv[1], "w").write(str(ingroup.pid))
    quiet = {} if sys.argv[3] == "inherit" else {
        "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
    }
    escaped = subprocess.Popen(sleeper, start_new_session=True, **quiet)
    open(sys.argv[2], "w").write(str(escaped.pid))
    print("agent  written  clusters=1 llm_calls=7 cache_hits=0", flush=True)
    time.sleep(60)
    """
)


def _run_tree(tmp_path, escaped_pipes):
    """Time `_run_distill` out against `_TREE_SCRIPT`. Returns
    `(rc, stdout, ingroup_pid, escaped_pid)`; the caller must reap `escaped_pid`."""
    ingroup_pidfile = tmp_path / "ingroup.pid"
    escaped_pidfile = tmp_path / "escaped.pid"
    rc, stdout, _ = sam._run_distill(
        [
            sys.executable,
            "-c",
            _TREE_SCRIPT,
            str(ingroup_pidfile),
            str(escaped_pidfile),
            escaped_pipes,
        ],
        root=tmp_path,
        env=dict(os.environ),
        timeout=3,
    )
    return rc, stdout, int(ingroup_pidfile.read_text()), int(escaped_pidfile.read_text())


def _exited_within(pid, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


def _reap(pid):
    try:
        os.kill(pid, 9)  # don't leak it into the rest of the suite
    except ProcessLookupError:
        pass


def test_run_distill_reaps_its_group_but_not_a_session_escaping_grandchild(tmp_path):
    """`_run_distill` against a REAL subprocess tree, because this is exactly what
    `subprocess.run(timeout=...)` gets wrong: it kills the direct child only, then
    drains the pipes the survivors still hold with no timeout at all.

    Two grandchildren on purpose, pinning both halves of the narrowed claim. The
    in-group one is what `killpg` buys over `proc.kill()`. The other is the
    PRODUCTION shape of tesserae's provider call — `llm_json._run_cli` spawns the
    Claude/Codex CLI with `start_new_session=True` — and it SURVIVES, which is why
    the docs say a timeout can still orphan one provider call instead of claiming
    it cannot. The old version of this test spawned only an in-group grandchild
    and called it the provider call, so it pinned the fiction.

    Both directions: drop `start_new_session=True`/`killpg` from `_run_distill` and
    the in-group grandchild survives (first assert fails); return `""` instead of
    the drained buffer on timeout and the salvaged `llm_calls=` line disappears.
    """
    rc, stdout, ingroup, escaped = _run_tree(tmp_path, "devnull")
    try:
        assert rc is None, "the run must be reported as timed out"
        assert "llm_calls=7" in stdout, "partial stdout is the only evidence of spend"
        assert _exited_within(ingroup), "killpg must reap everything left in tesserae's group"
        assert not _exited_within(escaped, 1.0), (
            "documented reality: killpg does NOT reach the provider CLI's own session"
        )
    finally:
        _reap(escaped)


def test_run_distill_returns_str_when_the_drain_also_times_out(tmp_path):
    """The escaping grandchild inherits the pipes, so `communicate()` blocks past
    the killpg and the drain times out too — the one branch that reads its output
    off a `TimeoutExpired` instead of a clean `communicate()`.

    That attribute is BYTES even under `text=True` (`Popen._check_timeout` builds
    the exception from the raw chunks; only `subprocess.run` re-communicates to
    decode), so before `_drained_text` this returned bytes and the caller's
    `_LLM_CALLS_RE.findall` raised `TypeError: cannot use a string pattern on a
    bytes-like object` — escaping `distill_super_agents`' never-raises contract and
    leaving the audit record unresolved forever.

    Both directions: revert `_drained_text` to `drained.stdout or ""` and the type
    assert fails and the parse raises; return `""` and the salvaged floor is lost.
    """
    rc, stdout, ingroup, escaped = _run_tree(tmp_path, "inherit")
    try:
        assert rc is None
        assert isinstance(stdout, str), "the caller parses this with a str regex"
        assert sam._LLM_CALLS_RE.findall(stdout) == ["7"], "the killed run's floor survives"
        assert _exited_within(ingroup)
    finally:
        _reap(escaped)


# ---------------------------------------------------------------------------
# F3 — the estimate only authorises the corpus it actually priced.
# ---------------------------------------------------------------------------


def test_refuses_when_graph_moves_between_pricing_and_run(distill_enabled, monkeypatch):
    """A compile landing in the T0→T1 window grows what the (uncapped) real run
    distills, so `estimate 55 ≤ 60` would authorise an unbounded bill.

    The dry run itself rewrites graph.json here, standing in for the operator's
    Compile button firing while pricing is in flight.
    """
    root = distill_enabled

    def _run(argv, **k):
        if "--dry-run" in argv:
            _write_graph(root, "MOVED")  # a compile lands mid-pricing
            return _Proc("a  dry-run  clusters=5 estimated_llm_calls=55 scope=5\n")
        raise AssertionError("the real run must not spawn against an unpriced corpus")

    monkeypatch.setattr(sam, "_run_distill", _run)
    res = sam.distill_super_agents("proj-1", max_estimated_llm_calls=60)
    assert res["ok"] is False
    assert res["reason"] == "graph_moved_during_pricing"
    assert res["llm_calls"] == 0


def test_stable_graph_still_runs(distill_enabled, monkeypatch):
    """Control: the guard must not block the ordinary case where nothing moved."""
    argvs = _record_subprocess(
        monkeypatch,
        _Proc("a  dry-run  clusters=5 estimated_llm_calls=55 scope=5\n"),
        _Proc("a  written  clusters=5 llm_calls=51 cache_hits=0\n"),
    )
    res = sam.distill_super_agents("proj-1", max_estimated_llm_calls=60)
    assert len(argvs) == 2 and res["ok"] is True


def test_refuses_when_the_agent_registry_moves_between_pricing_and_run(
    distill_enabled, monkeypatch
):
    """The graph is not the whole scope. Tesserae reads
    `.tesserae/agents/registry.json` as `known_agent_keys`, so pricing a pass over
    registry A and then distilling registry B spends outside the estimate that
    authorised it — with graph.json byte-identical throughout, which a graph-only
    digest cannot see. Guards the "the priced bytes are the distilled bytes" claim
    against the second input.
    """
    root = distill_enabled
    reg_path = root / ".tesserae" / "agents" / "registry.json"

    def _run(argv, **k):
        if "--dry-run" in argv:
            # graph.json deliberately untouched; only the scope registry moves.
            reg_path.write_text(
                json.dumps({"version": 1, "agents": {"claude:unknown:super-new": {}}})
            )
            return _Proc("a  dry-run  clusters=5 estimated_llm_calls=55 scope=5\n")
        raise AssertionError("the real run must not spawn against an unpriced scope")

    monkeypatch.setattr(sam, "_run_distill", _run)
    res = sam.distill_super_agents("proj-1", max_estimated_llm_calls=60)
    assert res["ok"] is False
    assert res["reason"] == "graph_moved_during_pricing"


def test_operator_path_is_not_gated_on_the_graph_digest(project_with_super_agents, monkeypatch):
    """The digest guard belongs to the budget, not to distill: an operator who
    clicked Distill has consented, and must still get a run on a project whose
    graph.json is absent (no budget kwarg ⇒ no pricing ⇒ nothing to invalidate)."""
    monkeypatch.setattr(sam, "get_distill_enabled", lambda pid: True)
    argvs = _record_subprocess(monkeypatch, _Proc("a  written  clusters=1 llm_calls=3\n"))
    res = sam.distill_super_agents("proj-1")
    assert len(argvs) == 1 and res["ok"] is True


def test_missing_graph_refuses_the_budgeted_path(project_with_super_agents, monkeypatch):
    """...and the mirror image: with a budget, no graph.json means the priced
    bytes cannot be shown to be the distilled bytes, so it fails closed."""
    monkeypatch.setattr(sam, "get_distill_enabled", lambda pid: True)

    def _run(argv, **k):
        assert "--dry-run" in argv, "only the free pass may run"
        return _Proc("a  dry-run  clusters=1 estimated_llm_calls=3 scope=1\n")

    monkeypatch.setattr(sam, "_run_distill", _run)
    res = sam.distill_super_agents("proj-1", max_estimated_llm_calls=60)
    assert res["reason"] == "graph_moved_during_pricing"


# ---------------------------------------------------------------------------
# F4 — the pre-flight is free of provider calls, and its budget is enforced by
# killing the process group rather than leaking CPU-minutes.
# ---------------------------------------------------------------------------


def test_estimate_dry_run_argv_is_the_free_pass(distill_enabled, monkeypatch):
    """The whole design rests on `--dry-run` spending nothing (verified in
    tesserae's `agent_distill.py:1567`, which returns the deterministic fallback
    before `self.summarizer(request)`). Lock the argv that makes it so — losing
    `--dry-run` turns the pre-flight into a second full-price run."""
    argvs: list[list[str]] = []

    def _run(argv, **k):
        argvs.append(list(argv))
        return _Proc("a  dry-run  clusters=1 estimated_llm_calls=1 scope=1\n")

    monkeypatch.setattr(sam, "_run_distill", _run)
    sam._estimate_distill_calls(distill_enabled)
    assert argvs[0][:4] == [sam._TESSERAE_CMD, "distill", "--all", "--dry-run"]


def test_estimate_timeout_is_reported_as_timeout(distill_enabled, monkeypatch):
    """The 300 s pricing budget has never run against the real ~12 MB graph. When
    it is too short the outcome must be legible as a budget problem, not as a
    broken CLI — that log/reason is the only evidence available to set the real
    number from."""
    monkeypatch.setattr(sam, "_run_distill", lambda argv, **k: _Proc("", returncode=None))
    assert sam._estimate_distill_calls(distill_enabled) == (None, "timeout")


def test_estimate_cli_missing_is_distinguishable(distill_enabled, monkeypatch):
    """Control: a genuinely absent CLI is a different reason."""

    def _run(argv, **k):
        raise FileNotFoundError("tesserae")

    monkeypatch.setattr(sam, "_run_distill", _run)
    assert sam._estimate_distill_calls(distill_enabled) == (None, "cli_missing")


def test_estimate_spawn_failure_is_not_raised_at_the_caller(distill_enabled, monkeypatch):
    """`distill_super_agents` documents that it NEVER raises, but only
    FileNotFoundError was caught — a PermissionError from Popen escaped through
    the pre-flight and out of the function (contained only by run_op_async's
    last-resort handler, which files it as a bare job failure)."""

    def _run(argv, **k):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(sam, "_run_distill", _run)
    assert sam._estimate_distill_calls(distill_enabled) == (None, "spawn_failed")
    res = sam.distill_super_agents("proj-1", max_estimated_llm_calls=60)
    assert res["reason"] == "estimate_unavailable_spawn_failed"


def test_estimate_real_run_spawn_failure_is_not_raised(distill_enabled, monkeypatch):
    """Same guard on the unpriced operator path, where there is no pre-flight to
    absorb it first."""

    def _run(argv, **k):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(sam, "_run_distill", _run)
    res = sam.distill_super_agents("proj-1")
    assert res == {"ok": False, "reason": "spawn_failed", "llm_calls": 0}


# ---------------------------------------------------------------------------
# "Nothing to price" is not "the pricer is broken" (F7)
# ---------------------------------------------------------------------------


def test_empty_scope_prices_at_zero_instead_of_reading_as_broken(distill_enabled, monkeypatch):
    """A registry with agents that match no Agent node in the compiled graph
    makes tesserae print its marker and exit 0 (cli.py:6131). No
    `estimated_llm_calls=` line matches, which used to return None and tell the
    operator the pass "could not be priced" — pointing them at a pre-flight that
    worked perfectly. It is an EMPTY SCOPE: priced at 0, spends nothing, and
    reports `nothing_to_distill`.
    """
    empty = _Proc(
        "No agents observed in the compiled graph — import sessions and "
        "run `tesserae compile` first (then `tesserae agents init`).\n"
    )
    argvs = _record_subprocess(monkeypatch, empty, empty)
    assert sam._estimate_distill_calls(distill_enabled) == (0, "no_agents_in_graph")
    res = sam.distill_super_agents("proj-1", max_estimated_llm_calls=60)
    assert res["reason"] == "nothing_to_distill" and res["ok"] is True
    assert len(argvs) == 2, "the dry run per call; the real run must never spawn"
    assert all("--dry-run" in a for a in argvs)


def test_agents_with_no_attributed_sessions_price_at_zero(distill_enabled, monkeypatch):
    """G4 — the OTHER empty scope, and the one this machine's data produces.

    Agents exist in the registry, so `results` is non-empty and the
    `No agents observed` marker is NOT printed; but every agent is `no-sessions`,
    which `continue`s without an `estimated_llm_calls=` line (cli.py:6144-6146)
    and exits 0. That used to fall through to `no_estimate` and refuse as
    `estimate_unavailable_no_estimate` — a healthy "nothing to distill" reported
    as a broken pre-flight, which then still consumed the 6 h window.
    """
    no_sessions = _Proc(
        "super-alice  no-sessions (nothing attributed to this agent)\n"
        "super-bob  no-sessions (nothing attributed to this agent)\n"
    )
    argvs = _record_subprocess(monkeypatch, no_sessions, no_sessions)
    assert sam._estimate_distill_calls(distill_enabled) == (0, "no_sessions_for_any_agent")
    res = sam.distill_super_agents("proj-1", max_estimated_llm_calls=60)
    assert res["reason"] == "nothing_to_distill" and res["ok"] is True
    assert len(argvs) == 2, "the dry run per call; the real run must never spawn"
    assert all("--dry-run" in a for a in argvs)


def test_mixed_no_sessions_and_priced_agents_sum_only_the_priced(distill_enabled, monkeypatch):
    """The marker must not short-circuit a pass that DID price something. One
    agent with nothing attributed alongside two real ones prices at 3+4, not 0 —
    otherwise a project would silently stop distilling the moment it gained a
    single unattributed agent."""
    mixed = _Proc(
        "super-alice  dry-run  clusters=2 estimated_llm_calls=3 scope=9\n"
        "super-idle  no-sessions (nothing attributed to this agent)\n"
        "super-bob  dry-run  clusters=1 estimated_llm_calls=4 scope=5\n"
    )
    _record_subprocess(monkeypatch, mixed, mixed)
    assert sam._estimate_distill_calls(distill_enabled) == (7, "ok")


def test_unrecognised_zero_estimate_output_still_fails_closed(distill_enabled, monkeypatch):
    """The paired control, and the reason the branch keys on the MARKER rather
    than on "no estimate lines": output this function cannot account for is a
    broken pricer and must still refuse. Widening the branch to `if not hits:
    return 0` makes this test fail and the one above pass."""
    _record_subprocess(monkeypatch, _Proc("tesserae: unexpected internal state\n"))
    assert sam._estimate_distill_calls(distill_enabled) == (None, "no_estimate")
