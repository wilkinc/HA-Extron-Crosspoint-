"""Persistent async TCP client for Extron SIS protocol."""

import asyncio
import logging
import re
from typing import Callable, Dict, Optional

_LOGGER = logging.getLogger(__name__)


class ExtronClient:
    """Maintains a persistent TCP connection to an Extron CrossPoint."""

    def __init__(self, host: str, port: int = 23):
        self.host = host
        self.port = port
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._connected = False
        self._running = False
        self._lock = asyncio.Lock()
        self._callbacks: Dict[int, list[Callable[[int], None]]] = {}

        self._tie_regex = re.compile(
            r"(?:Out(\d+)\s+In(\d+)|In(\d+)\s+Out(\d+))", re.IGNORECASE
        )

    @property
    def is_connected(self) -> bool:
        return self._connected

    def register_callback(self, out_num: int, callback: Callable[[int], None]) -> None:
        """Register a callback when an output changes its input tie."""
        if out_num not in self._callbacks:
            self._callbacks[out_num] = []
        self._callbacks[out_num].append(callback)

    async def start(self) -> None:
        """Start the persistent background listener."""
        self._running = True
        asyncio.create_task(self._connection_loop())

    async def stop(self) -> None:
        """Close the socket connection cleanly."""
        self._running = False
        async with self._lock:
            if self._writer:
                try:
                    self._writer.close()
                    await self._writer.wait_closed()
                except Exception:
                    pass
                self._writer = None
                self._reader = None
                self._connected = False

    async def _connection_loop(self) -> None:
        """Continuously maintain connection with auto-reconnect."""
        backoff = 2
        while self._running:
            try:
                _LOGGER.info("Connecting to Extron at %s:%s...", self.host, self.port)
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), timeout=5.0
                )
                async with self._lock:
                    self._reader = reader
                    self._writer = writer
                    self._connected = True
                backoff = 2
                _LOGGER.info("Connected to Extron CrossPoint at %s", self.host)

                await self.query_all_ties()
                await self._read_loop()

            except (asyncio.TimeoutError, OSError) as err:
                _LOGGER.warning(
                    "Extron connection lost/failed (%s). Reconnecting in %ss...",
                    err,
                    backoff,
                )
            except Exception as err:
                _LOGGER.error("Unexpected error in Extron connection loop: %s", err)

            async with self._lock:
                self._connected = False
                self._reader = None
                self._writer = None

            if self._running:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _read_loop(self) -> None:
        """Read incoming stream, parsing unsolicited front-panel events."""
        buffer = ""
        while self._running and self._connected:
            if not self._reader:
                break
            try:
                data = await self._reader.read(1024)
                if not data:
                    _LOGGER.warning("Extron closed connection remotely.")
                    break

                text = data.decode("ascii", errors="ignore")
                buffer += text

                while "\r\n" in buffer:
                    line, buffer = buffer.split("\r\n", 1)
                    line = line.strip()
                    if line:
                        self._process_message(line)

            except Exception as err:
                _LOGGER.warning("Error reading from Extron socket: %s", err)
                break

    def _process_message(self, line: str) -> None:
        """Parse Extron feedback lines and trigger entity updates."""
        _LOGGER.debug("Extron raw input: %s", line)

        match = self._tie_regex.search(line)
        if match:
            if match.group(1) is not None:
                out_num = int(match.group(1))
                in_num = int(match.group(2))
            else:
                in_num = int(match.group(3))
                out_num = int(match.group(4))

            _LOGGER.debug("Parsed tie event: Output %s -> Input %s", out_num, in_num)
            if out_num in self._callbacks:
                for cb in self._callbacks[out_num]:
                    cb(in_num)

    async def send_command(self, cmd: str) -> bool:
        """Send a command through the persistent socket."""
        async with self._lock:
            if not self._connected or not self._writer:
                _LOGGER.warning("Cannot send command '%s': Extron not connected", cmd)
                return False
            try:
                full_cmd = f"{cmd}\r\n".encode("ascii")
                self._writer.write(full_cmd)
                await self._writer.drain()
                return True
            except Exception as err:
                _LOGGER.error("Failed writing command '%s' to Extron: %s", cmd, err)
                self._connected = False
                return False

    async def route(self, in_num: int, out_num: int, tie_type: str = "all") -> bool:
        """Route input to output. tie_type: 'all' (!), 'video' (%), 'audio' ($)"""
        suffix = "!" if tie_type == "all" else ("%" if tie_type == "video" else "$")
        return await self.send_command(f"{in_num}*{out_num}{suffix}")

    async def query_all_ties(self) -> None:
        """Send query to request active configuration."""
        await self.send_command("I")