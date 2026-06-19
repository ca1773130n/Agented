# backend/tests/test_loop_progress.py
import os
import tempfile

from app.services.loop_progress import head_commit, made_progress


def test_made_progress_true_on_new_commit():
    assert made_progress(prev="abc123", current="def456") is True


def test_made_progress_false_when_unchanged():
    assert made_progress(prev="abc123", current="abc123") is False


def test_head_commit_returns_none_outside_repo():
    # Use the real system temp root, not pytest's ``tmp_path``: in this
    # environment TMPDIR points inside the Agented git repo, so ``tmp_path``
    # (and mkdtemp) land inside a tracked tree and ``git rev-parse HEAD``
    # resolves to the parent repo. ``/tmp`` is genuinely outside any repo.
    with tempfile.TemporaryDirectory(dir="/tmp") as d:
        assert os.path.isdir(d)
        assert head_commit(d) is None
