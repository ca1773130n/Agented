"""Takeaway extractor — the positive-learning side of Life-Harness.

Where ``harness_failure_annotator`` captures mistakes (H2/H3/H4 incidents),
this service captures what the agent / user / environment *taught* the
session: preferences, discovered procedures, tool patterns, constraints,
domain facts. Each takeaway either auto-applies to its target (memory /
rule / KG) when confidence is high and auto-apply is enabled, or queues
for operator review via the Activity-lane Takeaways card.

Two extraction modes:
    - **Heuristic** (default, no LLM): regex patterns over the parsed
      trajectory. Cheap, runs on every completed session.
    - **LLM** (opt-in via ``AGENTED_TAKEAWAY_LLM=1``): would call Codex
      with the transcript + extraction prompt. Skeleton only — wire your
      preferred LLM here when ready.

Auto-apply is OFF by default. Set ``AGENTED_TAKEAWAY_AUTOAPPLY=1`` to
let high-confidence (>=0.85) takeaways write straight to memory / KG /
rules at extraction time. Lower-confidence and impactful kinds always
queue for operator review.

Hooks into the same ``session_events`` channel as the annotator, so the
extractor sees every completed session across every producer (trigger,
super-agent, project session, workflow).
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any, Optional

from app.db import harness_takeaways as repo
from app.services.harness_failure_annotator import (
    SessionPayload,
    _FETCHERS,
    parse_claude_stream,
)

logger = logging.getLogger(__name__)

EXTRACTOR_VERSION = "heuristic-0.1.0"
LLM_EXTRACTOR_VERSION = "llm-0.1.0"
HIGH_CONFIDENCE = 0.85


# ---------------------------------------------------------------------------
# Heuristic patterns
# ---------------------------------------------------------------------------

@dataclass
class _Pattern:
    """A regex-based takeaway detector.

    The ``regex`` runs against assistant content_text. ``kind`` is the
    takeaway category. ``confidence`` is a hand-tuned prior. ``target``
    suggests where it should ultimately land. ``payload_builder`` (when
    present) projects the regex match into the target's expected payload
    shape.
    """
    regex: re.Pattern
    kind: str
    confidence: float
    target: Optional[str]
    description: str


# User preferences — when the agent claims to remember a preference.
_USER_PREF_REMEMBER = _Pattern(
    regex=re.compile(
        r"(?:I'?ll|I will|got it,?\s+I'll)\s+remember\s+(?:that\s+)?"
        r"(?:you\s+)?(?:prefer|want|always|like)\b[:.,]?\s*(.{10,200}?)(?:[.!\n]|$)",
        re.IGNORECASE,
    ),
    kind="user_preference",
    confidence=0.90,
    target="memory",
    description="agent acknowledged a stored user preference",
)

# User-stated preferences — explicit "use X" / "always Y" by the user.
_USER_PREF_USER_STATED = _Pattern(
    regex=re.compile(
        r"(?:please|always|never|prefer|use)\s+"
        r"((?:use|do|avoid|stick to|stop|don'?t use)\s+[^.!\n]{5,150})",
        re.IGNORECASE,
    ),
    kind="user_preference",
    confidence=0.55,
    target="memory",
    description="user stated a preference",
)

# Discovered procedures — agent narrates a multi-step procedure.
_DISCOVERED_PROCEDURE = _Pattern(
    regex=re.compile(
        r"(?:I learned|I found|I figured out|The (?:right|correct) way to)\s+"
        r"(.{15,250}?)(?:[.!\n]|$)",
        re.IGNORECASE,
    ),
    kind="discovered_procedure",
    confidence=0.65,
    target="skill",
    description="agent narrated a procedural insight",
)

# Constraints — environment told the agent it can't do X.
_CONSTRAINT = _Pattern(
    regex=re.compile(
        r"(?:must|cannot|can'?t|need to|required to|requires)\s+"
        r"([^.!\n]{10,200}?)\b",
        re.IGNORECASE,
    ),
    kind="constraint",
    confidence=0.50,
    target="rule",
    description="constraint discovered during execution",
)

# Domain facts — file path / URL / config reference.
_DOMAIN_FACT_PATH = _Pattern(
    regex=re.compile(
        r"(?:lives at|located at|configured in|defined in|stored in)\s+"
        r"`?([^\s`]+\.[a-zA-Z0-9]{2,8})`?",
    ),
    kind="domain_fact",
    confidence=0.75,
    target="knowledge_graph",
    description="agent referenced a specific file / config path",
)

# Tool pattern — agent reports a tool combination that works.
_TOOL_PATTERN = _Pattern(
    regex=re.compile(
        r"(?:I'll|I will)\s+use\s+(\w+)\s+(?:to|for)\s+([^.!\n]{5,150})",
        re.IGNORECASE,
    ),
    kind="tool_pattern",
    confidence=0.45,
    target=None,
    description="agent declared a tool-for-task pattern",
)


_PATTERNS: tuple[_Pattern, ...] = (
    _USER_PREF_REMEMBER,
    _USER_PREF_USER_STATED,
    _DISCOVERED_PROCEDURE,
    _CONSTRAINT,
    _DOMAIN_FACT_PATH,
    _TOOL_PATTERN,
)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _extract_heuristic(
    session_kind: str,
    session_id: str,
    project_id: Optional[str],
    payload: SessionPayload,
) -> list[dict[str, Any]]:
    """Walk the parsed trajectory and run pattern detectors. Returns
    takeaway dicts ready for ``harness_takeaways.insert_many``."""
    if payload.backend_type == "claude":
        events = parse_claude_stream(payload.text)
    else:
        events = []
    if not events:
        return []

    out: list[dict[str, Any]] = []
    for ev in events:
        if ev.role != "assistant" or not ev.content_text:
            continue
        for pat in _PATTERNS:
            for m in pat.regex.finditer(ev.content_text):
                content = m.group(1).strip() if m.groups() else m.group(0).strip()
                if not content or len(content) < 5:
                    continue
                out.append({
                    "session_kind": session_kind,
                    "session_id": session_id,
                    "project_id": project_id,
                    "kind": pat.kind,
                    "content": content[:500],
                    "confidence": pat.confidence,
                    "evidence": {
                        "event_index": ev.index,
                        "pattern": pat.description,
                        "match_snippet": m.group(0)[:240],
                    },
                    "suggested_target": pat.target,
                    "suggested_payload": _build_payload(
                        pat.target, pat.kind, content, project_id,
                    ),
                    "extractor_version": EXTRACTOR_VERSION,
                })
    return _dedupe(out)


def _build_payload(
    target: Optional[str], kind: str, content: str, project_id: Optional[str],
) -> dict[str, Any]:
    """Project the takeaway into a target-shaped payload so the applier
    doesn't have to re-derive it."""
    if target == "memory":
        return {"key": _slugify(content), "value": content}
    if target == "rule":
        return {
            "name": _slugify(content)[:50],
            "description": content,
            "rule_type": "convention" if kind == "user_preference" else "validation",
        }
    if target == "knowledge_graph":
        return {"name": content[:100], "entity_type": kind}
    if target == "skill":
        return {
            "title": _slugify(content)[:60],
            "when": "extracted from session takeaway",
            "recipe": content,
        }
    return {}


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return s or "takeaway"


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop duplicates within a single session (same kind + normalised content)."""
    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []
    for it in items:
        key = (it["kind"], it["content"].lower().strip())
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


# ---------------------------------------------------------------------------
# LLM-based extraction (opt-in via AGENTED_TAKEAWAY_LLM=1)
# ---------------------------------------------------------------------------

_LLM_PROMPT_TEMPLATE = """You are analysing one AI-agent session transcript and
extracting reusable TAKEAWAYS — facts, preferences, procedures, constraints,
or patterns revealed during the session that future sessions on the same
project should remember.

Output a JSON ARRAY (no preamble, no markdown fences). Each element is an
object with these fields:

  kind                — one of: {valid_kinds}
  content             — 1-2 sentence summary, max 500 chars
  confidence          — your honest estimate, 0.0-1.0
  suggested_target    — one of: {valid_targets}, or null if unclear
  rationale           — short evidence quote from the transcript

Rules:
  - Only extract takeaways that are NEW and ACTIONABLE.
  - Don't restate the task itself or obvious project facts.
  - Prefer 3-5 high-confidence takeaways over 20 low-confidence ones.
  - Suggest a ``target`` only when the takeaway clearly belongs in one
    of memory / rule / skill / knowledge_graph / claude_md.
  - If nothing meaningful is in the transcript, output ``[]``.

TRANSCRIPT:

{transcript}
"""

_TAKEAWAY_LLM_TIMEOUT_DEFAULT = 60
_TAKEAWAY_LLM_MIN_BYTES_DEFAULT = 2048
_TAKEAWAY_LLM_TRANSCRIPT_CAP = 50_000


def _llm_enabled() -> bool:
    return os.environ.get("AGENTED_TAKEAWAY_LLM", "0") == "1"


def _llm_min_text_bytes() -> int:
    raw = os.environ.get(
        "AGENTED_TAKEAWAY_LLM_MIN_BYTES", str(_TAKEAWAY_LLM_MIN_BYTES_DEFAULT),
    )
    try:
        return max(0, int(raw))
    except ValueError:
        return _TAKEAWAY_LLM_MIN_BYTES_DEFAULT


def _llm_timeout() -> int:
    raw = os.environ.get(
        "AGENTED_TAKEAWAY_LLM_TIMEOUT", str(_TAKEAWAY_LLM_TIMEOUT_DEFAULT),
    )
    try:
        return max(5, int(raw))
    except ValueError:
        return _TAKEAWAY_LLM_TIMEOUT_DEFAULT


def _llm_codex_cmd() -> list[str]:
    """Codex argv for extraction. Same {PROMPT} substitution as the
    evolver. Independent override via ``AGENTED_TAKEAWAY_CODEX_CMD`` so
    operators can pin a cheaper model for extraction vs. evolution."""
    raw = os.environ.get("AGENTED_TAKEAWAY_CODEX_CMD") or os.environ.get(
        "AGENTED_CODEX_CMD",
    )
    if raw:
        try:
            return shlex.split(raw)
        except ValueError:
            logger.warning("AGENTED_TAKEAWAY_CODEX_CMD malformed; using default")
    return ["codex", "exec", "--skip-git-repo-check", "{PROMPT}"]


def _run_codex_for_extraction(prompt: str, *, timeout: int) -> str:
    """Invoke Codex with the extraction prompt and return its stdout.

    Mockable: tests patch this entire function to return canned JSON
    without spawning a real Codex CLI.
    """
    template = _llm_codex_cmd()
    if "{PROMPT}" in template:
        cmd = [prompt if part == "{PROMPT}" else part for part in template]
        stdin_input = None
    else:
        cmd = list(template)
        stdin_input = prompt

    try:
        result = subprocess.run(
            cmd,
            cwd=tempfile.gettempdir(),
            input=stdin_input,
            timeout=timeout,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"codex CLI not found ({template[0]}); set "
            f"AGENTED_TAKEAWAY_CODEX_CMD or AGENTED_CODEX_CMD"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"codex extraction timed out after {timeout}s"
        ) from exc
    if result.returncode != 0:
        err = (result.stderr or "").replace(
            "Reading additional input from stdin...", "",
        ).strip()
        raise RuntimeError(
            f"codex extraction exited {result.returncode}: {err[:300]}"
        )
    return result.stdout or ""


def _slice_json_array(text: str) -> str:
    """Codex may emit a preamble before the JSON. Slice from the first
    ``[`` to the matching last ``]``."""
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return "[]"
    return text[start : end + 1]


def _extract_llm(
    session_kind: str,
    session_id: str,
    project_id: Optional[str],
    payload: SessionPayload,
) -> list[dict[str, Any]]:
    """Call Codex on the transcript and parse takeaways from its JSON
    output. Returns ``[]`` when extraction is disabled, the transcript is
    too short to be worth the LLM cost, or anything goes wrong."""
    if not _llm_enabled():
        return []
    text = payload.text or ""
    if len(text.encode("utf-8")) < _llm_min_text_bytes():
        return []

    transcript = text[:_TAKEAWAY_LLM_TRANSCRIPT_CAP]
    prompt = _LLM_PROMPT_TEMPLATE.format(
        valid_kinds=", ".join(sorted(repo.VALID_KINDS)),
        valid_targets=", ".join(sorted(repo.VALID_TARGETS)),
        transcript=transcript,
    )

    try:
        raw_output = _run_codex_for_extraction(prompt, timeout=_llm_timeout())
    except RuntimeError as exc:
        logger.warning("takeaway LLM: %s", exc)
        return []

    try:
        items_raw = json.loads(_slice_json_array(raw_output))
    except (TypeError, ValueError) as exc:
        logger.warning("takeaway LLM: malformed JSON output (%s)", exc)
        return []
    if not isinstance(items_raw, list):
        return []

    out: list[dict[str, Any]] = []
    for raw in items_raw:
        if not isinstance(raw, dict):
            continue
        kind = raw.get("kind")
        if kind not in repo.VALID_KINDS:
            continue
        target = raw.get("suggested_target")
        if target is not None and target not in repo.VALID_TARGETS:
            target = None
        content = str(raw.get("content") or "").strip()
        if not content:
            continue
        try:
            confidence = float(raw.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))
        out.append({
            "session_kind": session_kind,
            "session_id": session_id,
            "project_id": project_id,
            "kind": kind,
            "content": content[:500],
            "confidence": confidence,
            "evidence": {
                "extractor": "llm",
                "rationale": str(raw.get("rationale") or "")[:500],
            },
            "suggested_target": target,
            "suggested_payload": _build_payload(target, kind, content, project_id),
            "extractor_version": LLM_EXTRACTOR_VERSION,
        })
    return out


# ---------------------------------------------------------------------------
# Apply-target writers (auto-apply path)
# ---------------------------------------------------------------------------

def _apply_to_memory(takeaway: dict[str, Any]) -> Optional[str]:
    """Write to ``agent_memory`` working-memory keyed on project_id. Returns
    the storage key on success or ``None`` on failure."""
    project_id = takeaway.get("project_id")
    if not project_id:
        return None
    payload = takeaway.get("suggested_payload") or {}
    key = payload.get("key") or _slugify(takeaway["content"])
    value = payload.get("value") or takeaway["content"]
    try:
        from app.db.agent_memory import (
            get_working_memory,
            upsert_working_memory,
        )
        existing = get_working_memory(project_id, entity_type="project")
        existing_content = (existing or {}).get("content") or "{}"
        try:
            bucket = json.loads(existing_content)
            if not isinstance(bucket, dict):
                bucket = {}
        except (TypeError, ValueError):
            bucket = {}
        bucket[key] = {
            "value": value,
            "source_takeaway_id": takeaway["id"],
            "kind": takeaway.get("kind"),
        }
        upsert_working_memory(
            entity_id=project_id,
            entity_type="project",
            content=json.dumps(bucket, default=str),
        )
        return key
    except Exception:
        logger.warning(
            "takeaway: memory write failed for %s", takeaway["id"], exc_info=True,
        )
        return None


def _apply_to_knowledge_graph(takeaway: dict[str, Any]) -> Optional[str]:
    project_id = takeaway.get("project_id")
    if not project_id:
        return None
    payload = takeaway.get("suggested_payload") or {}
    name = payload.get("name") or takeaway["content"][:100]
    entity_type = payload.get("entity_type") or takeaway["kind"]
    try:
        from app.db.knowledge_graph import upsert_entity
        eid = upsert_entity(
            agent_id=project_id,
            name=name,
            entity_type=entity_type,
        )
        return str(eid) if eid else None
    except Exception:
        logger.warning(
            "takeaway: KG write failed for %s", takeaway["id"], exc_info=True,
        )
        return None


def _project_local_or_user_path(
    project_id: str,
    project_subpath: str,
    user_subpath: str,
) -> "Path":
    """Pick a write target for a project-scoped artifact.

    Preference order:

    1. ``<project.local_path>/<project_subpath>`` — the project's own
       working tree (what Claude Code reads natively for project-scoped
       skills, CLAUDE.md, etc). Requires the project row to have a
       ``local_path`` set.
    2. ``~/.claude/<user_subpath>`` — user-scope fallback. The caller
       is responsible for namespacing inside ``user_subpath`` (typically
       with a ``agented-<project_id>/`` prefix or by baking the
       project_id into the artifact itself) so multiple projects
       coexist without collision.
    """
    from pathlib import Path

    try:
        from app.db.connection import get_connection

        with get_connection() as conn:
            row = conn.execute(
                "SELECT local_path FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
        if row and row["local_path"]:
            return Path(row["local_path"]).expanduser() / project_subpath
    except Exception:
        pass
    return Path(os.path.expanduser("~/.claude")) / user_subpath


def _project_skills_root(project_id: str) -> "Path":
    """``SKILL.md`` package directory. See ``_project_local_or_user_path``."""
    return _project_local_or_user_path(
        project_id,
        project_subpath=".claude/skills",
        user_subpath=f"skills/agented-{project_id}",
    )


def _render_skill_md(takeaway: dict[str, Any]) -> str:
    """Render the takeaway as a SKILL.md package body.

    Format: YAML frontmatter (Claude Code's existing convention) +
    a Markdown body describing the recipe.
    """
    payload = takeaway.get("suggested_payload") or {}
    title = payload.get("title") or _slugify(takeaway["content"])[:60]
    when = payload.get("when") or "extracted from session takeaway"
    recipe = payload.get("recipe") or takeaway["content"]
    description = takeaway["content"][:200]

    frontmatter = (
        "---\n"
        f'name: {title}\n'
        f'description: {description!s}\n'
        f'source: agented-takeaway\n'
        f'takeaway_id: {takeaway["id"]}\n'
        f'kind: {takeaway["kind"]}\n'
        f'confidence: {takeaway.get("confidence", 0.5)}\n'
        "---\n"
    )
    body = (
        f"\n# {title}\n\n"
        f"**When to use:** {when}\n\n"
        f"## Recipe\n\n{recipe}\n\n"
        f"---\n*Surfaced by Agented from a session takeaway. Edit as needed.*\n"
    )
    return frontmatter + body


def _apply_to_skill(takeaway: dict[str, Any]) -> Optional[str]:
    """Materialize a takeaway as a ``.claude/skills/<name>/SKILL.md`` package
    and register it via Forge's existing ``add_project_skill``. Returns the
    skill_name (the natural identifier) on success."""
    from pathlib import Path

    project_id = takeaway.get("project_id")
    if not project_id:
        return None

    payload = takeaway.get("suggested_payload") or {}
    skill_name = (
        payload.get("title")
        or payload.get("name")
        or _slugify(takeaway["content"])
    )
    skill_name = _slugify(skill_name)[:60]
    if not skill_name:
        return None

    try:
        root = _project_skills_root(project_id)
        skill_dir = root / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(_render_skill_md(takeaway), encoding="utf-8")
    except OSError as exc:
        logger.warning(
            "takeaway: skill write failed for %s: %s",
            takeaway["id"], exc,
        )
        return None

    try:
        from app.db.projects import add_project_skill

        add_project_skill(
            project_id=project_id,
            skill_name=skill_name,
            skill_path=str(skill_path),
            source="agented-takeaway",
        )
    except Exception:
        logger.warning(
            "takeaway: add_project_skill failed for %s",
            takeaway["id"], exc_info=True,
        )
        # Filesystem artifact survives even if DB binding fails; operator
        # can manually re-bind. Return the skill_name so the takeaway is
        # still marked applied.

    return skill_name


def _project_claude_md_path(project_id: str) -> "Path":
    """Project CLAUDE.md path. See ``_project_local_or_user_path``.

    The user-scope fallback writes to ``~/.claude/CLAUDE.md`` (a shared
    file). The managed-section start marker includes the project_id so
    multiple projects coexist without colliding.
    """
    return _project_local_or_user_path(
        project_id,
        project_subpath="CLAUDE.md",
        user_subpath="CLAUDE.md",
    )


_AGENTED_TAKEAWAY_MARKER_START_TMPL = (
    "<!-- Agented Takeaways: project {project_id} "
    "(managed; edits between these markers will be overwritten) -->"
)
_AGENTED_TAKEAWAY_MARKER_END = "<!-- End Agented Takeaways -->"
_AGENTED_TAKEAWAY_SECTION_HEADING = "## Session Takeaways"


def _render_takeaway_bullet(takeaway: dict[str, Any]) -> str:
    """One markdown bullet per takeaway. The HTML comment carries the
    takeaway_id so idempotency works on re-apply."""
    kind = takeaway.get("kind", "takeaway").replace("_", " ")
    content = (takeaway.get("content") or "").strip().replace("\n", " ")
    return f"- <!--tk:{takeaway['id']}--> **{kind}** — {content}"


def _apply_to_claude_md(takeaway: dict[str, Any]) -> Optional[str]:
    """Insert the takeaway as a bullet inside a project-scoped, marker-
    delimited section of CLAUDE.md. Idempotent: re-applying the same
    takeaway is a no-op (detected via the ``tk:<id>`` HTML comment in
    the existing bullet). Operator-authored content outside the markers
    is never touched."""
    project_id = takeaway.get("project_id")
    if not project_id:
        return None

    path = _project_claude_md_path(project_id)
    start_marker = _AGENTED_TAKEAWAY_MARKER_START_TMPL.format(
        project_id=project_id,
    )

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError as exc:
        logger.warning(
            "takeaway: CLAUDE.md read failed for %s: %s",
            takeaway["id"], exc,
        )
        return None

    bullet = _render_takeaway_bullet(takeaway)
    marker_id_token = f"tk:{takeaway['id']}"

    start_idx = existing.find(start_marker)
    end_idx = existing.find(_AGENTED_TAKEAWAY_MARKER_END, max(0, start_idx))

    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        # Section already present — idempotency check then append.
        section = existing[start_idx:end_idx]
        if marker_id_token in section:
            return f"already-present:{takeaway['id']}"
        before_end = existing[:end_idx].rstrip()
        after_end = existing[end_idx:]
        new_text = f"{before_end}\n{bullet}\n{after_end}"
    elif start_idx != -1 and end_idx == -1:
        # Orphaned start marker (operator deleted the end). Truncate
        # everything after the start and rewrite a clean section.
        before = existing[:start_idx].rstrip()
        new_text = (
            f"{before}\n\n{start_marker}\n"
            f"{_AGENTED_TAKEAWAY_SECTION_HEADING}\n\n"
            f"{bullet}\n"
            f"{_AGENTED_TAKEAWAY_MARKER_END}\n"
        )
    else:
        # No section yet — append fresh.
        sep = "\n\n" if existing.strip() else ""
        body = existing.rstrip()
        new_text = (
            f"{body}{sep}{start_marker}\n"
            f"{_AGENTED_TAKEAWAY_SECTION_HEADING}\n\n"
            f"{bullet}\n"
            f"{_AGENTED_TAKEAWAY_MARKER_END}\n"
        )

    try:
        path.write_text(new_text, encoding="utf-8")
    except OSError as exc:
        logger.warning(
            "takeaway: CLAUDE.md write failed for %s: %s",
            takeaway["id"], exc,
        )
        return None

    return f"claude_md:{takeaway['id']}"


def _apply_to_rule(takeaway: dict[str, Any]) -> Optional[str]:
    project_id = takeaway.get("project_id")
    if not project_id:
        return None
    payload = takeaway.get("suggested_payload") or {}
    try:
        from app.db.rules import create_rule
        rid = create_rule(
            name=payload.get("name") or _slugify(takeaway["content"]),
            description=payload.get("description") or takeaway["content"],
            rule_type=payload.get("rule_type", "validation"),
            project_id=project_id,
        )
        return str(rid) if rid else None
    except Exception:
        logger.warning(
            "takeaway: rule write failed for %s", takeaway["id"], exc_info=True,
        )
        return None


_APPLIERS = {
    "memory": _apply_to_memory,
    "knowledge_graph": _apply_to_knowledge_graph,
    "rule": _apply_to_rule,
    "skill": _apply_to_skill,
    "claude_md": _apply_to_claude_md,
}


def apply_takeaway(takeaway_id: str) -> dict[str, Any]:
    """Operator-triggered apply path. Returns ``{applied: bool, ...}``."""
    tk = repo.get(takeaway_id)
    if tk is None:
        return {"applied": False, "reason": f"not found: {takeaway_id}"}
    if tk.get("applied"):
        return {"applied": False, "reason": "already applied"}
    if tk.get("dismissed"):
        return {"applied": False, "reason": "dismissed"}
    target = tk.get("suggested_target")
    applier = _APPLIERS.get(target) if target else None
    if applier is None:
        return {
            "applied": False,
            "reason": (
                f"no auto-applier for target {target!r}"
                if target else "no suggested target"
            ),
        }
    asset_id = applier(tk)
    if asset_id is None:
        return {"applied": False, "reason": "applier returned no id"}
    repo.mark_applied(takeaway_id, target=target, asset_id=asset_id)
    return {
        "applied": True, "target": target, "asset_id": asset_id,
        "takeaway_id": takeaway_id,
    }


def dismiss_takeaway(takeaway_id: str, *, reason: Optional[str] = None) -> dict:
    tk = repo.get(takeaway_id)
    if tk is None:
        return {"dismissed": False, "reason": "not found"}
    repo.mark_dismissed(takeaway_id, reason=reason)
    return {"dismissed": True, "takeaway_id": takeaway_id}


# ---------------------------------------------------------------------------
# Session-completion handler
# ---------------------------------------------------------------------------

def _autoapply_enabled() -> bool:
    return os.environ.get("AGENTED_TAKEAWAY_AUTOAPPLY", "0") == "1"


def extract_for_session(
    session_kind: str,
    session_id: str,
    *,
    project_id: Optional[str] = None,
) -> list[str]:
    """Pull the session's text via the annotator's fetcher map, run the
    extractor, persist takeaways. Returns the new takeaway ids."""
    fetcher = _FETCHERS.get(session_kind)
    if fetcher is None:
        return []
    try:
        payload = fetcher(session_id)
    except Exception:
        logger.debug(
            "takeaway: fetcher %s/%s raised",
            session_kind, session_id, exc_info=True,
        )
        return []
    if payload is None:
        return []
    resolved_project_id = project_id or payload.project_id
    heuristic = _extract_heuristic(
        session_kind, session_id, resolved_project_id, payload,
    )
    llm = _extract_llm(
        session_kind, session_id, resolved_project_id, payload,
    )
    # Cross-source dedup: LLM may surface the same takeaway the regex
    # already caught. Heuristic comes first so it wins ties (cheaper,
    # deterministic).
    items = _dedupe(heuristic + llm)
    if not items:
        return []
    try:
        ids = repo.insert_many(items)
    except Exception:
        logger.warning("takeaway: insert_many failed", exc_info=True)
        return []

    if _autoapply_enabled():
        for tk_id, tk in zip(ids, items):
            if tk["confidence"] < HIGH_CONFIDENCE:
                continue
            if tk.get("suggested_target") not in _APPLIERS:
                continue
            try:
                tk_row = repo.get(tk_id)
                if tk_row:
                    apply_takeaway(tk_id)
            except Exception:
                continue
    return ids


def on_session_complete(
    session_kind: str,
    session_id: str,
    project_id: Optional[str],
    status: str,
    output: Optional[dict],
) -> None:
    """Handler for ``execution_events.register_session_handler``. Fires
    alongside the annotator on every session completion. Best-effort —
    extractor failures must never block other handlers."""
    try:
        extract_for_session(session_kind, session_id, project_id=project_id)
    except Exception:
        logger.warning(
            "takeaway: extract failed for %s/%s",
            session_kind, session_id, exc_info=True,
        )
