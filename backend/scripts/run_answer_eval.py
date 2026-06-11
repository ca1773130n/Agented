#!/usr/bin/env python3
"""Run an answer-quality evaluation (baseline vs pipeline) from the command line.

Usage::

    uv run python scripts/run_answer_eval.py --project-id <project_id> \\
        [--n 8] [--judge-backend claude]

The script calls run_eval synchronously (no daemon thread), prints the
aggregate score table, and exits 0.
"""

from __future__ import annotations

import argparse
import sys


def _fmt(v) -> str:
    if v is None:
        return "  n/a "
    return f"{v:+.3f}" if v < 0 else f" {v:.3f}"


def _fmt_score(v) -> str:
    if v is None:
        return "  n/a "
    return f"  {v:.3f}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a baseline-vs-pipeline answer quality evaluation.",
    )
    parser.add_argument("--project-id", required=True, help="Project ID to evaluate")
    parser.add_argument(
        "--n",
        type=int,
        default=8,
        help="Number of questions to evaluate (default 8)",
    )
    parser.add_argument(
        "--judge-backend",
        default="claude",
        help="LLM backend to use for judge calls (default: claude)",
    )
    args = parser.parse_args()

    from app.services.answer_eval_service import AnswerEvalService

    print(
        f"\nRunning answer eval for project={args.project_id!r}  "
        f"n={args.n}  judge_backend={args.judge_backend!r}\n"
    )

    run_id = AnswerEvalService.run_eval(
        args.project_id,
        n=args.n,
        judge_backend=args.judge_backend,
    )

    from app.db.answer_eval import get_run, list_results

    run = get_run(run_id)
    results = list_results(run_id)

    print(f"Run ID:  {run_id}")
    print(f"Status:  {run.get('status')}")
    print(f"Created: {run.get('created_at')}")
    print(f"Finished:{run.get('finished_at')}")
    print()

    # --- Aggregate table ---
    header = f"{'Metric':<22}  {'Baseline':>10}  {'Pipeline':>10}  {'Delta':>10}"
    sep = "-" * len(header)
    print(header)
    print(sep)
    for metric in ("groundedness", "sufficiency", "quality"):
        b_val = run.get(f"baseline_{metric}")
        p_val = run.get(f"pipeline_{metric}")
        d_val = run.get(f"delta_{metric}")
        print(f"{metric:<22}  {_fmt_score(b_val):>10}  {_fmt_score(p_val):>10}  {_fmt(d_val):>10}")
    print(sep)
    print()

    if not results:
        print("No per-question results recorded.")
        return 0

    # --- Per-question table ---
    print(f"{'Question':<50}  {'Arm':<10}  {'G':>6}  {'S':>6}  {'Q':>6}  {'Reason'}")
    print("-" * 100)
    for r in results:
        q = (r.get("question") or "")[:48]
        arm = r.get("arm", "")
        g = r.get("groundedness")
        s = r.get("sufficiency")
        q_score = r.get("quality")
        reason = (r.get("judge_reason") or "")[:30]
        g_str = f"{g:.2f}" if g is not None else " n/a"
        s_str = f"{s:.2f}" if s is not None else " n/a"
        q_str = f"{q_score:.2f}" if q_score is not None else " n/a"
        print(f"{q:<50}  {arm:<10}  {g_str:>6}  {s_str:>6}  {q_str:>6}  {reason}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
