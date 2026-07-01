"""L7 egress allowlist proxy (phase 24, 24-02).

A tiny stdlib-``asyncio`` deny-by-default forward proxy that gates outbound
network for autonomous / auto-implement harness runs. It filters on the CLEARTEXT
``CONNECT host:port`` line (the TLS SNI host is visible without any MITM / cert
store) and on the ``Host:``/absolute-form line for plain HTTP:

  * host in the per-session allowlist  → ``200 Connection Established`` + a
    bidirectional byte pump (``asyncio.open_connection`` + two copy tasks);
  * host NOT in the allowlist          → ``403 Forbidden`` + a structured deny log
    ``{session_id, host, port, action: "deny"}`` + close.

``proxy_env(handle)`` yields ``HTTPS_PROXY``/``HTTP_PROXY`` = the ephemeral proxy
url and a NON-bypassing ``NO_PROXY`` for Plan 03 to inject into the sandboxed
child's env (matching the sandbox ``--setenv``).

ponytail: this homegrown CONNECT proxy is a DELIBERATE choice over mitmproxy — it
needs no TLS interception, no cert store, no extra dependency, and is trivially
CI-testable. Ceiling: it cannot filter by URL path or inspect TLS-encrypted
bodies; the upgrade path for that is a mitmproxy addon (cert injected into the
sandbox CA bundle). And env-only egress is BEST-EFFORT — a hostile child can unset
``HTTPS_PROXY`` or dial a raw IP; airtight no-bypass needs netns + nftables forcing
all egress to the proxy port (deferred — see 24-RESEARCH Pitfall 3).
"""

from __future__ import annotations

import asyncio
import logging
import threading

logger = logging.getLogger(__name__)

_PUMP_CHUNK = 65536


class EgressProxy:
    """Deny-by-default asyncio forward proxy bound to an ephemeral loopback port."""

    def __init__(self, allowlist, *, session_id: str | None = None):
        # Empty allowlist ⇒ deny EVERYTHING (deny-by-default). Normalize to a set.
        self.allowlist: set[str] = set(allowlist or ())
        self.session_id = session_id
        self._server: asyncio.AbstractServer | None = None
        self.url: str | None = None

    def _allowed(self, host: str) -> bool:
        host = (host or "").strip().strip("[]").lower()
        return host in self.allowlist

    def _log_deny(self, host: str, port: int) -> None:
        # Structured deny record — the escape test (Plan 05) and operators key off
        # host/action. Keep host in the message so a plain-string spy can see it.
        logger.warning(
            "egress deny: session=%s host=%s port=%s action=deny",
            self.session_id,
            host,
            port,
        )

    async def _pump(self, src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
        try:
            while True:
                chunk = await src.read(_PUMP_CHUNK)
                if not chunk:
                    break
                dst.write(chunk)
                await dst.drain()
        except (ConnectionError, asyncio.IncompleteReadError, OSError):
            pass
        finally:
            try:
                dst.close()
            except OSError:
                pass

    async def _tunnel(self, reader, writer, host: str, port: int) -> None:
        try:
            remote_reader, remote_writer = await asyncio.open_connection(host, port)
        except OSError:
            writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            try:
                await writer.drain()
            except OSError:
                pass
            writer.close()
            return
        await asyncio.gather(
            self._pump(reader, remote_writer),
            self._pump(remote_reader, writer),
        )

    @staticmethod
    def _parse_plain_http_host(request_line: str, header_block: str) -> tuple[str, int]:
        """Best-effort host/port for a plain-HTTP request (absolute-form or Host:)."""
        parts = request_line.split()
        target = parts[1] if len(parts) >= 2 else ""
        host = ""
        if "://" in target:  # absolute-form: GET http://host:port/path HTTP/1.1
            rest = target.split("://", 1)[1]
            host = rest.split("/", 1)[0]
        if not host:
            for line in header_block.splitlines():
                if line.lower().startswith("host:"):
                    host = line.split(":", 1)[1].strip()
                    break
        port = 80
        if ":" in host:
            host, _, port_s = host.rpartition(":")
            try:
                port = int(port_s)
            except ValueError:
                port = 80
        return host, port

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line_raw = await reader.readline()
            if not request_line_raw:
                writer.close()
                return
            request_line = request_line_raw.decode("latin-1", "replace").strip()
            parts = request_line.split()
            method = parts[0].upper() if parts else ""

            if method == "CONNECT":
                hostport = parts[1] if len(parts) >= 2 else ""
                host, _, port_s = hostport.partition(":")
                try:
                    port = int(port_s) if port_s else 443
                except ValueError:
                    port = 443
                # Drain the (empty) header block up to the blank line.
                while True:
                    line = await reader.readline()
                    if line in (b"\r\n", b"\n", b""):
                        break
                if self._allowed(host):
                    writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    await writer.drain()
                    await self._tunnel(reader, writer, host, port)
                    return
                self._log_deny(host, port)
                writer.write(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                await writer.drain()
                writer.close()
                return

            # Plain HTTP — read the header block, resolve host, allow/deny.
            header_lines = []
            while True:
                line = await reader.readline()
                if line in (b"\r\n", b"\n", b""):
                    break
                header_lines.append(line.decode("latin-1", "replace"))
            host, port = self._parse_plain_http_host(request_line, "".join(header_lines))
            if self._allowed(host):
                await self._tunnel(reader, writer, host, port)
                return
            self._log_deny(host, port)
            writer.write(b"HTTP/1.1 403 Forbidden\r\n\r\n")
            await writer.drain()
            writer.close()
        except (ConnectionError, OSError, asyncio.IncompleteReadError):
            try:
                writer.close()
            except OSError:
                pass

    async def start(self) -> "EgressProxy":
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        port = self._server.sockets[0].getsockname()[1]
        self.url = f"http://127.0.0.1:{port}"
        return self

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except OSError:
                pass
            self._server = None


async def start_egress_proxy(allowlist, *, session_id: str | None = None) -> EgressProxy:
    """Start a deny-by-default egress proxy on an ephemeral loopback port.

    Returns a started :class:`EgressProxy` exposing ``.url`` and an async ``.stop()``.
    An EMPTY allowlist blocks everything (deny-by-default) — the correct default for
    autonomous / auto-implement runs.
    """
    proxy = EgressProxy(allowlist, session_id=session_id)
    await proxy.start()
    return proxy


def proxy_env(handle) -> dict[str, str]:
    """Env overrides that route a child's HTTP(S) through the egress proxy.

    ``NO_PROXY`` exempts ONLY loopback (so the child can still talk to local
    services) — never a broad ``*`` that would defeat the proxy (Pitfall 3).
    """
    return {
        "HTTPS_PROXY": handle.url,
        "HTTP_PROXY": handle.url,
        "NO_PROXY": "127.0.0.1,localhost",
    }


class ThreadedEgressProxy:
    """Synchronous facade over :class:`EgressProxy` for the sync harness Popen sites.

    Runs the asyncio proxy on its own event loop in a daemon thread so a blocking
    ``subprocess.Popen`` launch path (execution_service) can start/stop it without
    an ambient event loop. ``.url`` is populated before :meth:`start` returns.
    """

    def __init__(self, allowlist, *, session_id: str | None = None):
        self._allowlist = allowlist
        self._session_id = session_id
        self._loop = asyncio.new_event_loop()
        self._proxy: EgressProxy | None = None
        self.url: str | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._ready = threading.Event()
        self._boot_error: BaseException | None = None
        self._boot_task: asyncio.Task | None = None

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)

        async def _boot():
            try:
                self._proxy = await start_egress_proxy(self._allowlist, session_id=self._session_id)
                self.url = self._proxy.url
            except asyncio.CancelledError:  # timed-out boot cancelled by start() — quiet
                raise
            except BaseException as exc:  # noqa: BLE001 - surfaced to start() below
                # Capture the boot failure so ``start()`` can FAIL CLOSED instead of
                # returning a half-built proxy with ``url=None`` (BLOCKER 2).
                self._boot_error = exc
            finally:
                # Always signal — success OR failure — so ``start()`` never blocks the
                # full timeout on a boot that already errored.
                self._ready.set()

        self._boot_task = self._loop.create_task(_boot())
        self._loop.run_forever()

    def _shutdown_loop(self) -> None:
        """Cancel a still-pending boot task then stop the loop (fail-closed teardown).

        Cancelling first avoids a dangling ``_boot`` task being destroyed while pending
        when a never-ready boot is abandoned on timeout.
        """

        def _cancel_and_stop() -> None:
            if self._boot_task is not None and not self._boot_task.done():
                self._boot_task.cancel()
            self._loop.stop()

        self._loop.call_soon_threadsafe(_cancel_and_stop)

    def start(self, timeout: float = 5.0) -> "ThreadedEgressProxy":
        """Start the proxy thread and BLOCK until it is actually listening.

        SECURITY (24-fix, BLOCKER 2): the previous version returned ``self``
        unconditionally after ``wait(timeout)`` even when the proxy never became
        ready (``url`` still ``None``) or boot raised — the caller then trusted a
        dead ``.url`` and launched WITHOUT egress filtering (fail open). Now a
        not-ready / errored / url-less start RAISES ``RuntimeError`` so the launch
        path fails closed. On failure the event loop is stopped to avoid leaking the
        daemon thread.
        """
        self._thread.start()
        if not self._ready.wait(timeout):
            self._shutdown_loop()
            raise RuntimeError(f"egress proxy did not become ready within {timeout}s (fail closed)")
        if self._boot_error is not None or not self.url:
            self._shutdown_loop()
            raise RuntimeError(
                "egress proxy failed to start (no listening url) — fail closed"
            ) from self._boot_error
        return self

    def stop(self) -> None:
        if self._proxy is not None:
            fut = asyncio.run_coroutine_threadsafe(self._proxy.stop(), self._loop)
            try:
                fut.result(timeout=5.0)
            except (TimeoutError, Exception):  # noqa: BLE001 - best-effort teardown
                pass
        self._loop.call_soon_threadsafe(self._loop.stop)
