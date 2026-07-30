"""Super-agent layered memory — map Agented super-agents onto Tesserae 0.21.0
per-agent knowledge graphs.

Tesserae 0.21.0 grows a layered KG *per agent* (``harness:account:role``):

- **L0** — the project graph mints one ``Agent`` node per observed agent plus
  ``performed_by`` edges (raw attribution, zero LLM).
- **L1** — ``tesserae distill`` writes one ``.tesserae/agents/<key>/distilled.graph.json``
  per agent: its own distilled runbook, bounded to a single read.
- **L2'** — distilling an agent that has *reports* rolls up the reports' L1s, so a
  manager sees only the distilled layer of its team.

This module maps each Agented **super-agent** to a Tesserae agent identity, wires
the super-agent hierarchy (``parent_super_agent_id``) into Tesserae's manager org,
runs the distill pass, and reads a super-agent's own distilled memory back for
injection into its harness context.

Attribution is by a registry ``{"label": <super_agent_id>}`` rule, because
Agented's session export (``tesserae_integration._normalize_super_agent_session``)
already stamps every super-agent session with ``agent_label = super_agent_id``.
That export also uses ``harness="claude"`` and no config-root, so Tesserae composes
the account slug as ``"unknown"`` — hence the deterministic key below. Verified
end-to-end against tesserae 0.21.0 (``agents list --json`` + ``distill --all``). If
the export ever sets ``harness=backend_type`` or a real config-root, update
``agent_key`` to match, or attribution silently collapses to one ``default`` agent.
"""

import hashlib
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from app.db.connection import get_connection

from .tesserae_integration import (
    _TESSERAE_CMD,
    _graph_digest,
    _tesserae_env,
    get_distill_enabled,
    get_tesserae_root,
    logger,
)

# L1 node types worth surfacing to an agent's own context.
_MEMORY_NODE_TYPES = ("DistilledNote", "ExpertiseProfile")
# A distilled L1 artifact is designed for a single ~48k read; refuse anything
# wildly larger before loading it (defends the harness prompt budget + memory).
_MEMORY_ARTIFACT_MAX_BYTES = 512 * 1024
# Super-agent ids are server-generated ``super-<suffix>``; enforce that shape
# before the id becomes a filesystem path component (defense-in-depth against a
# malformed/poisoned persisted id escaping the agents dir with ``..``/``/``/NUL).
# ``fullmatch`` (not ``$``, which permits a trailing newline) anchors the whole id.
_SAFE_SA_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")


def agent_key(super_agent_id: str) -> str:
    """Tesserae agent identity for an Agented super-agent. See module docstring
    for why the harness/account components are pinned to ``claude:unknown``.

    Rejects an id that isn't a plain ``[A-Za-z0-9_-]`` token — the key becomes a
    path component, so a ``/``/``..``/NUL id must never reach the filesystem.

    LOWERCASED, and that is load-bearing rather than cosmetic. Tesserae's
    ``sanitize_agent_key`` lowercases, and ``AgentRegistry._validate`` raises on
    any key that differs from its own sanitized form — for the WHOLE file, not
    the offending entry. ``_SAFE_SA_ID`` permits uppercase, so a single
    super-agent id carrying one capital letter would have made tesserae reject
    the entire registry, taking every other agent's attribution with it. The ids
    this repo generates are lowercase ``super-<suffix>``, so this changes no key
    in practice; it removes the trap for an id that arrives from anywhere else.
    Lowercasing cannot widen the charset, so the path-safety guarantee above is
    unaffected."""
    if not _SAFE_SA_ID.fullmatch(super_agent_id or ""):
        raise ValueError(f"unsafe super_agent_id: {super_agent_id!r}")
    return f"claude:unknown:{super_agent_id.lower()}"


def _project_super_agents(conn, project_id: str) -> list[dict]:
    """Super-agents with at least one COMPLETED session in this project, with
    name + parent. Scoped to the project because the registry is per-project.

    The ``status = 'completed'`` filter must match
    ``tesserae_integration._gather_project_sessions``, which exports only
    completed sessions. Without it the two disagreed: a still-running delegate
    was DECLARED in the registry but never EXPORTED, so tesserae saw an agent
    with no attributed sessions and printed ``no-sessions`` for it. That is not
    cosmetic — a declared-but-unexported agent is exactly the shape that makes a
    manager's distill raise ``DistillError`` and exit 1, taking the whole
    project's pass down with it (see ``_MANAGER_CHILDREN_UNBUILT_MARKER``).

    Consequence worth knowing: delegated sessions are long-lived and only reach
    ``completed`` via an explicit ``end_session`` or the 7-day stale sweep, so
    expertise lags the work that earned it.
    """
    rows = conn.execute(
        """SELECT DISTINCT sa.id AS id, sa.name AS name,
                  sa.parent_super_agent_id AS parent_super_agent_id
           FROM super_agent_sessions sas
           JOIN super_agents sa ON sa.id = sas.super_agent_id
           WHERE sas.project_id = ? AND sas.status = 'completed'""",
        (project_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def sync_agent_registry(project_id: str) -> Optional[Path]:
    """Write ``.tesserae/agents/registry.json`` mapping each of the project's
    super-agents to a Tesserae agent identity + org parent. Returns the path, or
    ``None`` when tesserae is disabled or no super-agent has run here."""
    root = get_tesserae_root(project_id)
    if root is None:
        return None
    with get_connection() as conn:
        sas = _project_super_agents(conn, project_id)
    if not sas:
        return None
    present = {s["id"] for s in sas}
    parent_of = {s["id"]: s.get("parent_super_agent_id") for s in sas}

    def _acyclic_parent(sa_id: str) -> Optional[str]:
        """The super-agent's parent id, but only if it's present in this project
        and the chain doesn't loop back — ``parent_super_agent_id`` has just an
        existence FK, so A→B→A cycles are possible and would make Tesserae reject
        the whole registry. Nodes in a cycle report to org:root instead."""
        seen: set[str] = set()
        cur = parent_of.get(sa_id)
        while cur is not None and cur in present:
            if cur == sa_id or cur in seen:
                return None  # cycle reachable from this edge → break it
            seen.add(cur)
            cur = parent_of.get(cur)
        direct = parent_of.get(sa_id)
        return direct if direct in present else None

    agents: dict[str, dict] = {}
    for s in sas:
        try:
            key = agent_key(s["id"])
        except ValueError:
            logger.warning("sync_agent_registry: skipping unsafe super_agent_id %r", s["id"])
            continue
        parent_id = _acyclic_parent(s["id"])
        # A registry parent MUST be a declared, acyclic agent (the loader fails
        # loud on unknown parents and cycles), else report to org:root.
        parent = agent_key(parent_id) if parent_id else "org:root"
        agents[key] = {
            "label": s.get("name") or s["id"],
            "parent": parent,
            "match": [{"label": s["id"]}],
        }
    reg_dir = root / ".tesserae" / "agents"
    reg_dir.mkdir(parents=True, exist_ok=True)
    reg_path = reg_dir / "registry.json"
    reg_path.write_text(json.dumps({"version": 1, "agents": agents}, indent=2))
    return reg_path


# ``tesserae distill`` has no ``--json``; both numbers are scraped from the
# per-agent stdout lines (cli.py:6148-6151 dry-run, :6156 real run).
_ESTIMATE_RE = re.compile(r"estimated_llm_calls=(\d+)")
_LLM_CALLS_RE = re.compile(r"\bllm_calls=(\d+)")
# tesserae prints exactly this and exits 0 when the registry scopes to no Agent
# node in the compiled graph (cli.py:6131). Nothing to price is not a broken
# pricer, and the two must not share a reason code — see _estimate_distill_calls.
_NO_AGENTS_MARKER = "No agents observed in the compiled graph"

# The OTHER healthy-but-unpriced shape, and the one this machine's data actually
# produces. An agent that exists in the registry but has nothing attributed to it
# prints its own line and ``continue``s WITHOUT an ``estimated_llm_calls=``
# (cli.py:6144-6146). When that is true of EVERY agent, ``results`` is non-empty —
# so ``_NO_AGENTS_MARKER`` is absent — yet not one estimate line was printed and
# the exit code is 0. Without this marker that priced-at-zero pass is
# indistinguishable from a broken pricer and refuses as
# ``estimate_unavailable_no_estimate``, which then still burns the 6 h window.
# ``skipped-watermark`` is the third ``continue`` without an estimate but CANNOT
# occur here: ``agent_distill.py:1970`` bypasses the watermark skip under
# ``dry_run``, so ``no-sessions`` is the only one a dry run can emit.
_NO_SESSIONS_MARKER = "no-sessions (nothing attributed to this agent)"

# The L2' hierarchy's structural trap. ``sync_agent_registry`` declares
# ``parent = <other agent>`` whenever one super-agent parents another — that IS the
# manager-rollup feature. But tesserae's ``_distill_manager`` raises
# ``DistillError`` unconditionally when a declared child has no
# ``distilled.graph.json`` (agent_distill.py:2472-2479), and a child with nothing
# attributed never writes one (it returns ``no-sessions`` at :1940). A dry run
# cannot write one either — it returns at :2236, before the artifact write.
# MEASURED against tesserae 0.28.2: BOTH ``distill --all --dry-run`` AND the real
# ``distill --all`` exit 1 on that shape, so the operator's Distill button does not
# clear it. Detected here only to report it under an honest, actionable reason.
_MANAGER_CHILDREN_UNBUILT_MARKER = "have no distilled artifact"


def _scope_digest(root: Path) -> str:
    """Digest of EVERYTHING that decides what a distill pass will do.

    ``_graph_digest`` covers ``graph.json`` only, and it must stay that way — the
    auto-distill policy uses it to decide whether the corpus CHANGED, and folding
    the registry into that would make any super-agent rename dispatch a paid run.

    But the priced-vs-distilled guarantee needs more than the graph: scope also
    comes from ``.tesserae/agents/registry.json``, which is what tesserae reads as
    ``known_agent_keys``. Pricing a pass over registry A and then distilling
    registry B would spend outside the estimate that authorised it, so the
    re-check before the spawn hashes both. ``""`` when the graph is unreadable,
    which the caller already treats as "refuse"; a missing registry contributes a
    fixed marker rather than failing, since ``sync_agent_registry`` has by then
    returned a path and its absence is itself a change worth refusing on.
    """
    graph = _graph_digest(root)
    if not graph:
        return ""
    h = hashlib.sha256(graph.encode())
    try:
        h.update(
            hashlib.sha256((root / ".tesserae" / "agents" / "registry.json").read_bytes()).digest()
        )
    except OSError:
        h.update(b"no-registry")
    return h.hexdigest()


# Grace period to drain the pipes after the process group has been SIGKILLed.
# ``communicate()`` resumes from the same accumulated buffer across a timed-out
# call (CPython ``Popen._fileobj2output``), so this returns everything the run
# printed before we killed it — not a second, partial read.
_DISTILL_DRAIN_SECONDS = 10


def _drained_text(buf: str | bytes | None) -> str:
    """Decode a buffer taken off a ``TimeoutExpired``.

    ``Popen._check_timeout`` builds the exception with the raw accumulated
    chunks — ``output=b"".join(...)``, i.e. **bytes even under ``text=True``**;
    only ``subprocess.run`` re-``communicate()``s to decode. Measured on this
    interpreter. Feeding that straight to the ``llm_calls=`` regex is a
    ``TypeError``, which would escape ``distill_super_agents``' never-raises
    contract and leave the auto-distill record permanently unresolved.
    """
    if isinstance(buf, bytes):
        return buf.decode(errors="replace")
    return buf or ""


def _run_distill(
    argv: list[str], *, root: Path, env: dict[str, str], timeout: int
) -> tuple[Optional[int], str, str]:
    """Run one tesserae distill subprocess; return ``(returncode, stdout, stderr)``
    with ``returncode is None`` meaning TIMED OUT.

    Two deliberate departures from ``subprocess.run(timeout=...)``, both about
    spend:

    - ``start_new_session`` + ``killpg``. ``run``'s ``proc.kill()`` reaps only the
      tesserae process, leaving its own children running and then draining their
      inherited pipes with NO timeout — the wedge tesserae itself hit. ``killpg``
      reaps everything still in tesserae's group, which on the dry-run path is the
      whole cost: minutes of CPU chewing the ~12 MB graph.

      **It does not reach the provider call.** Tesserae spawns the Claude/Codex CLI
      with ``start_new_session=True`` of its own (``tesserae/llm_json.py`` ``_run_cli``),
      so that process sits in a different session; ``killpg`` on tesserae's group
      does not signal it, and because tesserae is SIGKILLed its own cleanup never
      runs either. A real run killed at 1800 s can therefore leave one in-flight
      provider call orphaned — which is precisely why the partial ``llm_calls=``
      salvage below is a FLOOR rather than a total.
    - stdout is RETURNED on the timeout path instead of discarded. The per-agent
      ``llm_calls=`` lines already printed are the only evidence of what a killed
      run cost; throwing them away is what let a 30-minute timeout be filed as
      zero spend.

    Spawn failures propagate as ``OSError``; both callers catch it and split off
    ``FileNotFoundError`` (no CLI) from the rest, so neither ever raises.
    """
    proc = subprocess.Popen(
        argv,
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
        return proc.returncode, out or "", err or ""
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            proc.kill()  # group gone or unreachable — at least reap the child
        try:
            out, err = proc.communicate(timeout=_DISTILL_DRAIN_SECONDS)
        except subprocess.TimeoutExpired as drained:
            # A session-escaping grandchild (the provider CLI) can still hold the
            # pipes open past the killpg; salvage the buffer the exception carries.
            out, err = _drained_text(drained.stdout), _drained_text(drained.stderr)
        return None, out or "", err or ""


def _estimate_distill_calls(root: Path, *, timeout: int = 300) -> tuple[Optional[int], str]:
    """Price a distill pass in provider calls WITHOUT spending anything.
    Returns ``(estimate, reason)``; ``estimate is None`` means REFUSE TO SPEND
    because the pass could not be priced. ``0`` is a successful pricing of an
    empty scope — a different fact, and the caller reports it as
    ``nothing_to_distill`` rather than pointing the operator at a pre-flight
    that is working fine.

    Zero-spend is verified in tesserae's source, not assumed: under ``dry_run``
    the LLM stage adds ``_planned_provider_calls(request)`` to
    ``estimated_llm_calls`` and returns the deterministic fallback *before*
    ``self.summarizer(request)`` (``agent_distill.py:1567``), and ``distill_agent``
    returns before the artifact write (``:2234``) with ``state=None`` throughout.

    It bypasses the per-agent watermark skip (``:1970`` is gated on ``not
    options.dry_run``), so it OVER-counts relative to a real run — but the shared
    distill cache is a *file* cache read before that accounting (``:1531``), so
    the overcount covers only genuinely uncached clusters. It is an approximation
    in one other direction too: dry-run clustering runs with ``state=None``
    (``:1999``) and so without the memo the real run uses, and cluster shapes can
    differ. Treat it as a go/no-go, never as a guaranteed bound.

    ⚠️ **The ``timeout`` is UNVALIDATED.** This dry run has never been executed
    against a real corpus — the live ``graph.json`` is ~12 MB and the pass does
    full scope closure + clustering for *every* agent. If 300 s is short the
    feature fails closed (no spend) and logs the elapsed seconds it was killed
    at; that log line is the evidence to set the real number from. The measured
    duration of every successful pricing run is logged for the same reason.
    """
    started = time.monotonic()
    try:
        rc, stdout, stderr = _run_distill(
            [_TESSERAE_CMD, "distill", "--all", "--dry-run", "--project", str(root)],
            root=root,
            env={**_tesserae_env(), "TESSERAE_AGENT_DISTILL": "1"},
            timeout=timeout,
        )
    except FileNotFoundError:
        return None, "cli_missing"
    except OSError as exc:
        # PermissionError, ENOMEM, ENOEXEC… Popen raises these too, and
        # distill_super_agents promises never to raise.
        logger.warning("tesserae: distill dry-run could not be spawned for %s: %s", root, exc)
        return None, "spawn_failed"
    elapsed = time.monotonic() - started
    if rc is None:
        logger.warning(
            "tesserae: distill dry-run for %s blew its %ds pricing budget (killed the "
            "process group at %.0fs). No provider calls were made, but the pass cannot "
            "be priced and will not run. This is the datapoint the 300s budget was "
            "never validated against — raise _estimate_distill_calls(timeout=) if it recurs.",
            root,
            timeout,
            elapsed,
        )
        return None, "timeout"
    if rc != 0:
        blob = f"{stderr or ''}\n{stdout or ''}"
        if _MANAGER_CHILDREN_UNBUILT_MARKER in blob:
            # STRUCTURAL, not transient: this project's registry declares a manager
            # whose child has no distilled artifact, and a dry run cannot create one
            # (agent_distill.py:2236 returns before the artifact write), so pricing
            # can never succeed while that shape holds. Reported under its own reason
            # so the operator sees the actual cause instead of a generic non-zero
            # exit that reads like a broken CLI. MEASURED against tesserae 0.28.2 —
            # the real ``--all`` run fails identically, so this does not clear by
            # clicking Distill; see the note in CLAUDE.md.
            logger.warning(
                "tesserae: distill dry-run for %s cannot be priced — the agent registry "
                "declares a manager whose child has no distilled artifact yet, and "
                "neither a dry run nor `distill --all` can create one. Every declared "
                "child needs attributed sessions in the compiled graph first. No spend. "
                "tesserae said: %s",
                root,
                (stderr or "").strip()[:300],
            )
            return None, "manager_children_unbuilt"
        logger.warning(
            "tesserae: distill dry-run for %s exited %d in %.1fs: %s",
            root,
            rc,
            elapsed,
            (stderr or "").strip()[:300],
        )
        return None, "exit_nonzero"
    hits = _ESTIMATE_RE.findall(stdout)
    if not hits:
        if _NO_AGENTS_MARKER in stdout:
            # Priced successfully; the scope is empty. The old code returned
            # None here, so an ordinary "this project has no agents in the
            # graph yet" was reported to the operator as a broken pre-flight
            # ("could not price the pass"). Zero flows to nothing_to_distill.
            logger.info(
                "tesserae: distill dry-run for %s found no agents in the compiled "
                "graph — nothing to distill, priced at 0 in %.1fs",
                root,
                elapsed,
            )
            return 0, "no_agents_in_graph"
        if _NO_SESSIONS_MARKER in stdout:
            # Agents exist, but nothing is attributed to any of them, so tesserae
            # priced every one at zero without printing a single estimate line.
            # Same meaning as the empty scope above — nothing to distill — and it
            # must NOT be reported as a pre-flight failure.
            logger.info(
                "tesserae: distill dry-run for %s scoped only agents with no attributed "
                "sessions — nothing to distill, priced at 0 in %.1fs",
                root,
                elapsed,
            )
            return 0, "no_sessions_for_any_agent"
        return None, "no_estimate"
    est = sum(int(h) for h in hits)
    logger.info(
        "tesserae: distill dry-run priced %s at %d provider call(s) in %.1fs (budget %ds)",
        root,
        est,
        elapsed,
        timeout,
    )
    return est, "ok"


def distill_super_agents(
    project_id: str,
    *,
    timeout: int = 1800,
    max_estimated_llm_calls: Optional[int] = None,
) -> dict[str, Any]:
    """Sync the registry, then run ``tesserae distill --all`` (agent-distill
    enabled via env) to rebuild every super-agent's L1 runbook + L2' manager
    rollups. Gated on the per-project distill toggle. Best-effort — every failure
    path returns a status dict, never raises.

    ``max_estimated_llm_calls`` adds a **go/no-go** spend gate — emphatically not
    a cap. A free ``--dry-run`` prices the pass first and the real run is REFUSED
    if the estimate exceeds the budget or cannot be obtained; once authorised the
    run is uncapped and may spend more than the estimate (see
    :func:`_estimate_distill_calls` for the two ways the estimate and the run can
    disagree). What IS enforced is that the run distills the bytes that were
    priced: ``graph.json`` is re-hashed immediately before the spawn and the run
    is refused (``graph_moved_during_pricing``) if a concurrent compile moved it.
    Operator-initiated distills pass nothing and are unpriced + unbounded,
    exactly as before — a human clicking Distill has consented to the spend."""
    root = get_tesserae_root(project_id)
    if root is None:
        return {"ok": False, "reason": "tesserae_disabled"}
    if not get_distill_enabled(project_id):
        return {"ok": False, "reason": "distill_disabled"}
    reg = sync_agent_registry(project_id)
    if reg is None:
        return {"ok": False, "reason": "no_super_agents"}
    if max_estimated_llm_calls is not None:
        # Pre-flight AFTER the registry sync — the dry run scopes agents through it.
        # Hash the scope BEFORE pricing: the estimate only authorises the corpus it
        # actually looked at (see the re-check before the spawn below). Both inputs,
        # not just the graph — the registry written just above is what tesserae
        # reads as ``known_agent_keys``, so it decides the scope every bit as much.
        priced_digest = _scope_digest(root)
        est, why = _estimate_distill_calls(root)
        if est is None:
            logger.warning(
                "tesserae: auto-distill refused for %s — pass not priced (%s); no spend",
                project_id,
                why,
            )
            return {
                "ok": False,
                "reason": f"estimate_unavailable_{why}",
                "registry": str(reg),
                "llm_calls": 0,
            }
        if est == 0:
            return {
                "ok": True,
                "reason": "nothing_to_distill",
                "registry": str(reg),
                "estimated_llm_calls": 0,
                "llm_calls": 0,
            }
        if est > max_estimated_llm_calls:
            logger.warning(
                "tesserae: auto-distill refused for %s — estimate %d calls > budget %d; "
                "run Distill from Settings → Memory System to approve the spend",
                project_id,
                est,
                max_estimated_llm_calls,
            )
            return {
                "ok": False,
                "reason": f"estimate_over_budget_{est}",
                "registry": str(reg),
                "estimated_llm_calls": est,
                "llm_calls": 0,
            }
        # Pricing took minutes; a compile (auto-policy or the operator's Compile
        # button) can land in that window and grow the corpus the real run then
        # distills, turning "≤60 authorised" into an unbounded bill. Refuse instead
        # of re-pricing in a loop — the next compile past the 6 h window reprices.
        if not priced_digest or _scope_digest(root) != priced_digest:
            logger.warning(
                "tesserae: auto-distill refused for %s — the distill scope "
                "(graph.json or agents/registry.json) moved while the pass was being "
                "priced (estimate %d is stale); no spend, will reprice "
                "on the next compile",
                project_id,
                est,
            )
            return {
                "ok": False,
                "reason": "graph_moved_during_pricing",
                "registry": str(reg),
                "estimated_llm_calls": est,
                "llm_calls": 0,
            }
    # tesserae distill no-ops unless agent-distill is opted in (env or config).
    # Scrubbed base (REQ-41): distill IS an LLM operation, so a server-baked
    # inference key must not reach it when AGENTED_SERVER_NO_LLM_KEYS is on.
    env = {**_tesserae_env(), "TESSERAE_AGENT_DISTILL": "1"}
    try:
        rc, stdout, stderr = _run_distill(
            # Deliberately UNCAPPED — no ``--max-llm-calls``. That flag is not a
            # spend control on this path, it is silent artifact damage: an
            # over-budget cluster takes the deterministic fallback
            # (agent_distill.py:1580), capped fallbacks are NOT cached
            # (:1520-1524), and the scope watermark is stamped unconditionally at
            # the tail of distill_agent (:2282) — while the watermark skip (:1970)
            # is gated only on --full/--dry-run, so --retry-fallbacks cannot lift
            # it. A capped run therefore freezes fallback prose into the runbook
            # until someone runs --full. The budget is a go/no-go BEFORE the run
            # (see max_estimated_llm_calls), never a throttle inside it.
            [_TESSERAE_CMD, "distill", "--all", "--project", str(root)],
            root=root,
            env=env,
            timeout=timeout,
        )
    except FileNotFoundError:
        return {"ok": False, "reason": "cli_missing", "llm_calls": 0}
    except OSError as exc:
        # Keeps the "never raises" contract above true for the spawn failures
        # that are not a missing CLI (PermissionError, ENOMEM, …).
        logger.warning("tesserae distill --all could not be spawned for %s: %s", project_id, exc)
        return {"ok": False, "reason": "spawn_failed", "llm_calls": 0}
    # Sum the per-agent ``llm_calls=`` from the FULL stdout, before the tail
    # truncation below — what it actually cost, not "it fired". Parsed BEFORE the
    # timeout branch, because a killed run is exactly the case where the number
    # matters most.
    calls = sum(int(h) for h in _LLM_CALLS_RE.findall(stdout))
    if rc is None:
        # A timeout is the largest and least-known spend on this path. Report it
        # as a FLOOR — the agents that finished printed their cost, the agent we
        # killed mid-flight did not — never as the zero it used to read as.
        logger.warning(
            "tesserae distill --all TIMED OUT for %s after %ds; process group killed. "
            "Spend is NOT zero and NOT fully known: ≥%d provider call(s) from agents "
            "that finished, plus whatever the interrupted agent had already issued.",
            project_id,
            timeout,
            calls,
        )
        return {
            "ok": False,
            "reason": f"timeout_after_{timeout}s",
            "registry": str(reg),
            "llm_calls": calls,
            "llm_calls_partial": True,
            "stdout_tail": stdout[-500:],
        }
    ok = rc == 0
    if not ok:
        logger.warning("tesserae distill --all failed for %s: %s", project_id, stderr[:300])
    return {
        "ok": ok,
        "registry": str(reg),
        "llm_calls": calls,
        "stdout_tail": stdout[-500:],
    }


def read_agent_memory(
    project_id: str, super_agent_id: str, *, max_chars: int = 6000
) -> dict[str, Any]:
    """Load a super-agent's L1 distilled runbook and return a compact, bounded
    memory block for injection into its harness context. Empty (not an error)
    when the agent has no distilled artifact yet."""
    root = get_tesserae_root(project_id)
    if root is None:
        return {"key": None, "notes": [], "text": ""}
    try:
        key = agent_key(super_agent_id)
    except ValueError:
        logger.warning("read_agent_memory: unsafe super_agent_id %r", super_agent_id)
        return {"key": None, "notes": [], "text": ""}
    agents_root = (root / ".tesserae" / "agents").resolve()
    art = (agents_root / key / "distilled.graph.json").resolve()
    # Belt-and-suspenders: the resolved artifact path must stay under the agents
    # dir (the key was already token-validated, but never trust a path built from
    # a persisted id without a containment check).
    if os.path.commonpath([str(agents_root), str(art)]) != str(agents_root):
        logger.warning("read_agent_memory: path escapes agents dir for %r", super_agent_id)
        return {"key": key, "notes": [], "text": ""}
    try:
        if art.stat().st_size > _MEMORY_ARTIFACT_MAX_BYTES:
            logger.warning("read_agent_memory: artifact over size cap for %s", key)
            return {"key": key, "notes": [], "text": ""}
        data = json.loads(art.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"key": key, "notes": [], "text": ""}
    # Cap BOTH the notes list and the rendered text as we collect — a runaway
    # artifact must not blow the harness prompt budget or return every node.
    notes: list[dict[str, Any]] = []
    lines: list[str] = []
    total = 0
    for n in data.get("nodes", []):
        if n.get("type") not in _MEMORY_NODE_TYPES:
            continue
        title = (n.get("name") or "").strip()
        body = (n.get("description") or "").strip()
        if not (title or body):
            continue
        chunk = f"**{title}**\n{body}".strip()
        if total + len(chunk) > max_chars:
            break
        # The L0 evidence a distilled note cites — each drillable back to raw
        # source via `agents drill` (0.22). Bounded: a note can cite many refs,
        # but the panel drills one at a time.
        md = n.get("metadata") or {}
        refs = [
            r["node_id"]
            for r in (md.get("member_refs") or [])
            if isinstance(r, dict) and isinstance(r.get("node_id"), str)
        ][:6]
        notes.append({"title": title, "body": body, "refs": refs})
        lines.append(chunk)
        total += len(chunk)
    return {"key": key, "notes": notes, "text": "\n\n".join(lines)}


def agent_org(project_id: str, *, timeout: int = 30) -> Optional[list[dict[str, Any]]]:
    """Return Tesserae's agent org for this project (``tesserae agents list
    --json``): one row per agent — ``{key, label, parent, sessions, registered}``.
    ``None`` when tesserae is disabled or the CLI fails."""
    root = get_tesserae_root(project_id)
    if root is None:
        return None
    try:
        proc = subprocess.run(
            [_TESSERAE_CMD, "agents", "list", "--project", str(root), "--json"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_tesserae_env(),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


# A tesserae graph node id (``member_refs[].node_id``) is a plain token. Validate
# it before it becomes a CLI positional; combined with the ``--`` terminator
# below, a ``--flag``-shaped id can never smuggle a CLI option.
_SAFE_NODE_ID = re.compile(r"[A-Za-z0-9:._-]{1,256}")
_DRILL_MAX_CHARS = 8000


def agent_drill(
    project_id: str, super_agent_id: str, node_id: str, *, timeout: int = 30
) -> dict[str, Any]:
    """Audit-escalate a distilled note back to its raw L0 evidence via
    ``tesserae agents drill`` (Tesserae 0.22): given a ``member_refs[].node_id``
    from this super-agent's distilled memory, resolve it against L0 and report
    the underlying evidence + status (alive / changed / absorbed / gone).

    Bounded, best-effort text (the CLI has no ``--json``). ``ok=False`` with a
    reason on any failure — never raises, never 500s the panel."""
    root = get_tesserae_root(project_id)
    if root is None:
        return {"ok": False, "reason": "tesserae_disabled"}
    try:
        key = agent_key(super_agent_id)
    except ValueError:
        return {"ok": False, "reason": "unsafe_super_agent_id"}
    if not _SAFE_NODE_ID.fullmatch(node_id or ""):
        return {"ok": False, "reason": "unsafe_node_id"}
    try:
        proc = subprocess.run(
            # Flags BEFORE the ``--`` terminator; node_id after it, so a
            # ``--flag``-shaped id can never smuggle a CLI option (the argv-guard
            # class already hardened elsewhere in this codebase).
            [
                _TESSERAE_CMD,
                "agents",
                "drill",
                "--agent",
                key,
                "--project",
                str(root),
                "--",
                node_id,
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_tesserae_env(),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"ok": False, "reason": "cli_unavailable"}
    if proc.returncode != 0:
        return {"ok": False, "reason": (proc.stderr or "").strip()[:200] or "drill_failed"}
    # Drilled content derives from adversarial transcripts (raw L0 evidence) —
    # bound it and treat it as untrusted DATA; a caller injecting it into a
    # prompt must wrap_tainted, and the panel must render it as text, never HTML.
    return {
        "ok": True,
        "key": key,
        "node_id": node_id,
        "text": (proc.stdout or "")[:_DRILL_MAX_CHARS],
    }
