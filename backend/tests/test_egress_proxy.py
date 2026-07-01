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
