"""Answer-eval routes — baseline-vs-pipeline quality evaluation.

Routes (absolute paths, Router(path="/")):
  POST /admin/answer-eval/run       → start eval run (daemon thread), return {run_id}
  GET  /admin/answer-eval/runs      → list runs (optional ?project_id=)
  GET  /admin/answer-eval/runs/{run_id:int} → run detail + results
"""

from __future__ import annotations

import threading
from typing import Any, Optional

from litestar import Router, get, post
from litestar.exceptions import NotFoundException
from msgspec import Struct

from app.db.answer_eval import create_run, get_run, list_results, list_runs


class RunRequestBody(Struct):
    project_id: str
    n: int = 8
    judge_backend: str = "claude"


@post("/admin/answer-eval/run", sync_to_thread=False, status_code=201)
def start_eval_run(data: RunRequestBody) -> dict[str, Any]:
    """Start an answer-eval run in a daemon thread. Returns {run_id} immediately.

    The route pre-allocates the run_id so the caller can poll for it; the
    thread NEVER creates a second run (run_id is passed through).
    """
    from app.services.answer_eval_service import AnswerEvalService

    run_id = create_run(data.project_id, judge_backend=data.judge_backend)

    def _worker():
        try:
            AnswerEvalService.run_eval(
                data.project_id,
                n=data.n,
                judge_backend=data.judge_backend,
                run_id=run_id,
            )
        except Exception:
            import logging

            logging.getLogger(__name__).warning("answer-eval run %d failed", run_id, exc_info=True)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

    return {"run_id": run_id}


@get("/admin/answer-eval/runs", sync_to_thread=False)
def list_eval_runs(project_id: Optional[str] = None, limit: int = 20) -> dict[str, Any]:
    """List eval runs, optionally filtered by project_id."""
    runs = list_runs(project_id=project_id, limit=min(int(limit), 100))
    return {"runs": runs, "total": len(runs)}


@get("/admin/answer-eval/runs/{run_id:int}", sync_to_thread=False)
def get_eval_run(run_id: int) -> dict[str, Any]:
    """Get a single eval run with its per-question results."""
    run = get_run(run_id)
    if run is None:
        raise NotFoundException(detail=f"eval run {run_id} not found")
    results = list_results(run_id)
    return {"run": run, "results": results}


answer_eval_router = Router(
    path="/",
    route_handlers=[start_eval_run, list_eval_runs, get_eval_run],
)
