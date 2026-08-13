"""Switching localhost TCP forwarder — TEST HARNESS ONLY.

The kit's sparring peer dials a single --peer URL, but the split architecture
serves each role from its own process/port. For the self-test we present one
stable URL and forward raw TCP to the ACTIVE window's role worker. On every
target switch all open connections are closed, so a keep-alive HTTP client
reconnects and lands on the new target. Production matches need none of this:
real opponents dial our two declared URLs directly.
"""

from __future__ import annotations

import asyncio
import contextlib


class SwitchingProxy:
    """Listen on one port; pipe each new connection to the current target port."""

    def __init__(self, host: str, listen_port: int, target_port: int) -> None:
        self.host = host
        self.listen_port = listen_port
        self.target_port = target_port
        self._server: asyncio.AbstractServer | None = None
        self._writers: set[asyncio.StreamWriter] = set()

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self.host, self.listen_port)

    async def set_target(self, port: int) -> None:
        """Retarget and drop every live connection so clients re-dial cleanly."""
        if port == self.target_port:
            return
        self.target_port = port
        for w in list(self._writers):
            with contextlib.suppress(Exception):
                w.close()
        self._writers.clear()
        await asyncio.sleep(0.1)  # let closes land before the next window's dial

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            up_reader, up_writer = await asyncio.open_connection(self.host, self.target_port)
        except OSError:
            writer.close()
            return
        self._writers.update((writer, up_writer))

        async def pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
            with contextlib.suppress(Exception):
                while True:
                    data = await src.read(65536)
                    if not data:
                        break
                    dst.write(data)
                    await dst.drain()
            with contextlib.suppress(Exception):
                dst.close()

        await asyncio.gather(pipe(reader, up_writer), pipe(up_reader, writer))
        self._writers.difference_update((writer, up_writer))

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
        for w in list(self._writers):
            with contextlib.suppress(Exception):
                w.close()
        self._writers.clear()
