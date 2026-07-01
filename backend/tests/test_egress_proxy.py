"""L2 tests for the deny-by-default egress allowlist proxy (24-02).

Uses a local asyncio echo server + a raw client through the proxy — no real
network. Async bodies are driven with ``asyncio.run`` so no pytest-asyncio dep is
required.
"""

import asyncio

import pytest

from app.services import egress_proxy
from app.services.egress_proxy import proxy_env, start_egress_proxy


def _proxy_port(url: str) -> int:
    return int(url.rsplit(":", 1)[1])


async def _echo_handler(reader, writer):
    while True:
        data = await reader.read(1024)
        if not data:
            break
        writer.write(data)
        await writer.drain()
    writer.close()


def test_allowlisted_host_connects():
    async def _run():
        echo_server = await asyncio.start_server(_echo_handler, "127.0.0.1", 0)
        echo_port = echo_server.sockets[0].getsockname()[1]
        proxy = await start_egress_proxy(allowlist={"127.0.0.1"})
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", _proxy_port(proxy.url))
            writer.write(f"CONNECT 127.0.0.1:{echo_port} HTTP/1.1\r\n\r\n".encode())
            await writer.drain()
            resp = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5)
            assert resp.startswith(b"HTTP/1.1 200"), resp
            # round-trip bytes through the tunnel
            writer.write(b"hello")
            await writer.drain()
            echoed = await asyncio.wait_for(reader.readexactly(5), timeout=5)
            assert echoed == b"hello"
            writer.close()
        finally:
            await proxy.stop()
            echo_server.close()
            await echo_server.wait_closed()

    asyncio.run(_run())


def test_denied_host_blocked_and_logged(monkeypatch):
    captured: list = []
    monkeypatch.setattr(egress_proxy.logger, "warning", lambda *a, **k: captured.append(a))

    async def _run():
        proxy = await start_egress_proxy(allowlist=set(), session_id="s1")
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", _proxy_port(proxy.url))
            writer.write(b"CONNECT evil.test:443 HTTP/1.1\r\n\r\n")
            await writer.drain()
            resp = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5)
            assert resp.startswith(b"HTTP/1.1 403"), resp
            # proxy closes the connection after the 403
            tail = await asyncio.wait_for(reader.read(), timeout=5)
            assert tail == b""
            writer.close()
        finally:
            await proxy.stop()

    asyncio.run(_run())

    assert captured, "expected a structured deny log"
    flat = " ".join(str(a) for a in captured)
    assert "evil.test" in flat
    assert "deny" in flat


def test_empty_allowlist_denies_everything():
    async def _run():
        proxy = await start_egress_proxy(allowlist=set())
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", _proxy_port(proxy.url))
            writer.write(b"CONNECT github.com:443 HTTP/1.1\r\n\r\n")
            await writer.drain()
            resp = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5)
            assert resp.startswith(b"HTTP/1.1 403"), resp
            writer.close()
        finally:
            await proxy.stop()

    asyncio.run(_run())


def test_proxy_env_yields_https_proxy():
    class _FakeHandle:
        url = "http://127.0.0.1:12345"

    env = proxy_env(_FakeHandle())
    assert env["HTTPS_PROXY"] == "http://127.0.0.1:12345"
    assert env["HTTP_PROXY"] == "http://127.0.0.1:12345"
    # NO_PROXY must NOT broadly bypass the proxy (no wildcard).
    assert "*" not in env["NO_PROXY"]
    assert env["NO_PROXY"] == "127.0.0.1,localhost"


def test_threaded_proxy_start_stop():
    proxy = egress_proxy.ThreadedEgressProxy(allowlist={"127.0.0.1"}, session_id="t1").start()
    try:
        assert proxy.url and proxy.url.startswith("http://127.0.0.1:")
    finally:
        proxy.stop()


# --------------------------------------------------------------------------- #
# crit 3 (24-fix): egress proxy start failure must FAIL CLOSED (refuse the launch)
# instead of continuing with no egress filtering.
# --------------------------------------------------------------------------- #
def test_egress_start_failure_fails_closed(monkeypatch):
    from app.services import sandbox_wrap
    from app.services.execution_service import ExecutionService
    from app.services.policy_service import PolicyDenied

    monkeypatch.setattr(sandbox_wrap, "sandbox_enabled", lambda: True)

    class _BoomProxy:
        def __init__(self, *a, **k):
            pass

        def start(self):
            raise RuntimeError("bind failed")

    monkeypatch.setattr(egress_proxy, "ThreadedEgressProxy", _BoomProxy)

    with pytest.raises(PolicyDenied):
        ExecutionService._start_egress_proxy_or_fail_closed(
            execution_id="ex-1",
            policy_session_id="s1",
            env_overrides={},
            proc_env={},
        )


def test_egress_disabled_returns_no_proxy(monkeypatch):
    """With AGENTED_SANDBOX off there is no egress proxy — proc_env passes through
    unchanged and nothing fails (the fail-closed rule only bites when opted in)."""
    from app.services import sandbox_wrap
    from app.services.execution_service import ExecutionService

    monkeypatch.setattr(sandbox_wrap, "sandbox_enabled", lambda: False)
    handle, url, env = ExecutionService._start_egress_proxy_or_fail_closed(
        execution_id="ex",
        policy_session_id="s",
        env_overrides={},
        proc_env={"A": "B"},
    )
    assert handle is None
    assert url is None
    assert env == {"A": "B"}


# --------------------------------------------------------------------------- #
# BLOCKER 2 (24-fix): ThreadedEgressProxy.start() must BLOCK until actually
# listening and FAIL CLOSED (raise) if it never becomes ready — no half-built
# handle with url=None handed to a caller that then launches unfiltered.
# --------------------------------------------------------------------------- #
def test_threaded_proxy_not_ready_raises(monkeypatch):
    """A proxy whose boot never signals readiness → start() raises after timeout."""

    async def _never_ready(*a, **k):
        await asyncio.Event().wait()  # hang forever; readiness is never set

    monkeypatch.setattr(egress_proxy, "start_egress_proxy", _never_ready)
    tp = egress_proxy.ThreadedEgressProxy(allowlist={"x"}, session_id="hang")
    with pytest.raises(RuntimeError):
        tp.start(timeout=0.3)
    assert tp.url is None


def test_threaded_proxy_boot_error_raises(monkeypatch):
    """A proxy whose async boot RAISES → start() surfaces it as a fail-closed error
    instead of returning a url-less handle."""

    async def _boom(*a, **k):
        raise OSError("bind failed")

    monkeypatch.setattr(egress_proxy, "start_egress_proxy", _boom)
    tp = egress_proxy.ThreadedEgressProxy(allowlist={"x"}, session_id="boom")
    with pytest.raises(RuntimeError):
        tp.start(timeout=2.0)
    assert tp.url is None


def test_egress_not_ready_url_none_fails_closed(monkeypatch):
    """A proxy whose start() returns but exposes NO url (never became ready, yet did
    not raise) is treated as failure → PolicyDenied BEFORE any Popen. The old code
    trusted the dead ``.url`` and launched without egress filtering (fail open)."""
    from app.services import sandbox_wrap
    from app.services.execution_service import ExecutionService
    from app.services.policy_service import PolicyDenied

    monkeypatch.setattr(sandbox_wrap, "sandbox_enabled", lambda: True)

    class _NotReadyProxy:
        def __init__(self, *a, **k):
            self.url = None

        def start(self, *a, **k):
            return self  # returns but never became ready (url stays None)

    monkeypatch.setattr(egress_proxy, "ThreadedEgressProxy", _NotReadyProxy)
    with pytest.raises(PolicyDenied):
        ExecutionService._start_egress_proxy_or_fail_closed(
            execution_id="ex-nr",
            policy_session_id="s-nr",
            env_overrides={},
            proc_env={},
        )


# --------------------------------------------------------------------------- #
# MAJOR 2 (24-fix): a FAILED start() must leak NEITHER a daemon thread NOR an
# event loop — teardown cancels+awaits the boot task, stops AND closes the loop,
# and joins the thread. N repeated failures must not grow the live thread count.
# --------------------------------------------------------------------------- #
def test_threaded_proxy_repeated_boot_errors_no_leak(monkeypatch):
    import threading

    async def _boom(*a, **k):
        raise OSError("bind failed")

    monkeypatch.setattr(egress_proxy, "start_egress_proxy", _boom)
    baseline = threading.active_count()
    for _ in range(8):
        tp = egress_proxy.ThreadedEgressProxy(allowlist={"x"}, session_id="leak-boom")
        with pytest.raises(RuntimeError):
            tp.start(timeout=2.0)
        assert not tp._thread.is_alive(), "boot thread must be joined, not leaked"
        assert tp._loop.is_closed(), "event loop must be closed, not leaked"
    assert threading.active_count() <= baseline + 1, "threads leaked across repeated failures"


def test_threaded_proxy_repeated_not_ready_no_leak(monkeypatch):
    """The cancel path (boot never signals ready): the pending boot task must be
    cancelled AND its CancelledError delivered (task done, not orphaned) before the
    loop stops — then thread joined + loop closed. No leak across repeats."""
    import threading

    async def _never_ready(*a, **k):
        await asyncio.Event().wait()  # hang forever; readiness never set

    monkeypatch.setattr(egress_proxy, "start_egress_proxy", _never_ready)
    baseline = threading.active_count()
    for _ in range(6):
        tp = egress_proxy.ThreadedEgressProxy(allowlist={"x"}, session_id="leak-nr")
        with pytest.raises(RuntimeError):
            tp.start(timeout=0.2)
        assert not tp._thread.is_alive(), "hung boot thread must be joined, not leaked"
        assert tp._loop.is_closed(), "event loop must be closed, not leaked"
        # The boot task actually finished (cancelled + retrieved), not left pending.
        assert tp._boot_task is None or tp._boot_task.done()
    assert threading.active_count() <= baseline + 1, "threads leaked across repeated failures"
