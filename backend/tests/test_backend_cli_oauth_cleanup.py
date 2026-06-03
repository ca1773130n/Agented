"""Regression: OAuth temp dir is cleaned up when a CLI session finishes (C2).

Each login mkdtemp's a dir holding the fake-browser script + the captured OAuth
URL. Previously these leaked one-per-login forever; _finish_session must remove
the dir (and cancel_session routes through _finish_session).
"""

import os
import tempfile

from app.services.backend_cli_service import BackendCLIService as Svc


def test_finish_session_removes_oauth_temp_dir():
    url_dir = tempfile.mkdtemp(prefix="agented-oauth-test-")
    with open(os.path.join(url_dir, "url.txt"), "w") as f:
        f.write("https://accounts.google.com/o/oauth2/...secret")
    sid = "cli-cleanup-1"
    with Svc._lock:
        Svc._sessions[sid] = {
            "backend_id": "b1",
            "backend_type": "claude",
            "action": "login",
            "started_at": "now",
            "oauth_url_file": os.path.join(url_dir, "url.txt"),
            "oauth_url_dir": url_dir,
        }
        Svc._subscribers[sid] = []

    assert os.path.isdir(url_dir)
    Svc._finish_session(sid, "completed", exit_code=0)
    assert not os.path.exists(url_dir)  # temp dir (and captured URL) removed

    # housekeeping: cancel the completion-cleanup timer started by _finish_session
    with Svc._lock:
        timer = Svc._cleanup_timers.pop(sid, None)
        Svc._completed.pop(sid, None)
    if timer:
        timer.cancel()
