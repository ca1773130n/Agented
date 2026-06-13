"""Phase 1 (SkillOpt integration) — held-out question partition.

build_question_set gains a seed-partitioned, run-disjoint train/eval split so
the Skill-Sleep gate can score a candidate skill on questions DISJOINT from the
ones an edit was derived from (SkillOpt's "never optimize against the val
split", approximated). partition=None keeps the existing top-n behavior.
"""

from __future__ import annotations


def _seed(project_id: str, n: int) -> None:
    from app.db import harness_kg_signals

    for i in range(n):
        harness_kg_signals.record_signal(
            signal_id=f"sig-{project_id}-{i}",
            project_id=project_id,
            question=f"How does subsystem {i} behave under load?",
            content=f"answer {i}",
            round_id="r1",
            already_forged=False,
            weight=1.0,
            now="2026-01-01T00:00:00",
        )


def test_partition_none_preserves_default_behavior(isolated_db):
    from app.services.answer_eval_service import AnswerEvalService

    _seed("proj-part", 12)
    default = AnswerEvalService.build_question_set("proj-part", n=8)
    explicit = AnswerEvalService.build_question_set("proj-part", n=8, partition=None)
    assert default == explicit
    assert len(default) <= 8


def test_train_eval_are_disjoint_and_deterministic(isolated_db):
    from app.services.answer_eval_service import AnswerEvalService

    _seed("proj-part2", 20)
    train = AnswerEvalService.build_question_set("proj-part2", n=8, partition="train", seed=7)
    eval_ = AnswerEvalService.build_question_set("proj-part2", n=8, partition="eval", seed=7)

    assert train, "train half should be non-empty for a 20-signal corpus"
    assert eval_, "eval half should be non-empty"
    assert set(train).isdisjoint(set(eval_)), "train and eval must not overlap"

    # Deterministic: same seed → same split.
    again = AnswerEvalService.build_question_set("proj-part2", n=8, partition="train", seed=7)
    assert train == again


def test_partition_seed_changes_split(isolated_db):
    from app.services.answer_eval_service import AnswerEvalService

    _seed("proj-part3", 30)
    a = AnswerEvalService.build_question_set("proj-part3", n=12, partition="train", seed=1)
    b = AnswerEvalService.build_question_set("proj-part3", n=12, partition="train", seed=2)
    # Different seeds should generally produce different partitions.
    assert a != b
