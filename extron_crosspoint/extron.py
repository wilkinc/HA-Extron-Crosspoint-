"""Persistent async TCP client for Extron SIS protocol with auto-reconnect."""

import asyncio
import logging
import re
import socket
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
        
        # Callbacks registered per output: callback(out_num, in_num, plane)
        self._callbacks: list[Callable[[int, int, str], None]] = []

        # Matches responses like:
        # 'Out2 In1 All', 'Out1 In2 RGB', 'Out1 In3 Aud', 'In1 Out2'
        self._tie_regex = re.compile(
            r"(?:Out(\d+)\s+In(\d+)(?:\s+(All|RGB|Aud))?|In(\d+)\s+Out(\d+))",
            re.IGNORECASE,
        )

    @property
    def is_connected(self) -> bool:
        return self._connected

    def register_callback(self, callback: Callable[[int, int, str], None]) -> None:
        """Register a callback for tie change events."""
        self._callbacks.append(callback)

    async def start(self) -> None:
        """Start the persistent background listener and heartbeat supervisor."""
        self._running = True
        asyncio.create_task(self._connection_supervisor())

    async def stop(self) -> None:
        """Close the socket connection cleanly."""
        self._running = False
        await self._disconnect()

    async def _disconnect(self) -> None:
        """Internal teardown of the current socket."""
        async with self._lock:
            self._connected = False
            if self._writer:
                try:
                    self._writer.close()
                    await self._writer.wait_closed()
                except Exception:
                    pass
                self._writer = None
                self._reader = None

    async def _connection_supervisor(self) -> None:
        """Continuously maintain connection through power cycles."""
        backoff = 3
        while self._running:
            try:
                _LOGGER.info("Attempting connection to Extron at %s:%s...", self.host, self.port)
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), timeout=4.0
                )

                # Enable OS-level TCP keepalive
                sock = writer.get_extra_info("socket")
                if sock is not None:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

                async with self._lock:
                    self._reader = reader
                    self._writer = writer
                    self._connected = True

                backoff = 3
                _LOGGER.info("Successfully connected to Extron CrossPoint at %s", self.host)

                # Query current ties on connection to sync initial state
                await self.query_all_ties()

                # Concurrently run reader loop and periodic heartbeat
                done, pending = await asyncio.wait(
                    [
                        asyncio.create_task(self._read_loop()),
                        asyncio.create_task(self._heartbeat_loop()),
                    ],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                for task in pending:
                    task.cancel()

            except (asyncio.TimeoutError, OSError) as err:
                _LOGGER.debug(
                    "Extron unreachable/offline (%s). Retrying in %ss...", err, backoff
                )
            except Exception as err:
                _LOGGER.error("Unexpected error in Extron supervisor: %s", err)

            await self._disconnect()

            if self._running:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def _read_loop(self) -> None:
        """Continuously reads incoming data from the Extron."""
        buffer = ""
        while self._running and self._connected:
            if not self._reader:
                break
            try:
                data = await self._reader.read(1024)
                if not data:
                    _LOGGER.info("Extron closed socket (EOF detected, likely powered off).")
                    break

                text = data.decode("ascii", errors="ignore")
                buffer += text

                while "\r\n" in buffer:
                    line, buffer = buffer.split("\r\n", 1)
                    line = line.strip()
                    if line:
                        self._process_message(line)

            except Exception as err:
                _LOGGER.warning("Socket read error (connection dropped): %s", err)
                break

    async def _heartbeat_loop(self) -> None:
        """Periodic ping every 15s to detect ungraceful power-downs immediately."""
        while self._running and self._connected:
            await asyncio.sleep(15)
            # Harmless Information query 'I'
            success = await self.send_command("I")
            if not success:
                _LOGGER.warning("Extron heartbeat failed. Triggering reconnect...")
                break

    def _process_message(self, line: str) -> None:
        """Parse Extron feedback lines and trigger entity updates."""
        _LOGGER.debug("Extron raw input: %s", line)

        match = self._tie_regex.search(line)
        if match:
            if match.group(1) is not None:
                out_num = int(match.group(1))
                in_num = int(match.group(2))
                plane = (match.group(3) or "all").lower()
            else:
                in_num = int(match.group(4))
                out_num = int(match.group(5))
                plane = "all"

            _LOGGER.debug(
                "Parsed tie: Output %s -> Input %s (plane: %s)", out_num, in_num, plane
            )
            for cb in self._callbacks:
                cb(out_num, in_num, plane)

    async def send_command(self, cmd: str) -> bool:
        """Send a command through the persistent socket."""
        async with self._lock:
            if not self._connected or not self._writer:
                return False
            try:
                full_cmd = f"{cmd}\r\n".encode("ascii")
                self._writer.write(full_cmd)
                await asyncio.wait_for(self._writer.drain(), timeout=2.0)
                return True
            except Exception as err:
                _LOGGER.warning(
                    "Failed sending command '%s' to Extron (%s). Marking socket dead.",
                    cmd,
                    err,
                )
                self._connected = False
                return False

    async def route(self, in_num: int, out_num: int, tie_type: str = "all") -> bool:
        """Route input to output. tie_type: 'all' (!), 'video' (%), 'audio' ($)"""
        suffix = "!" if tie_type == "all" else ("%" if tie_type == "video" else "$")
        return await self.send_command(f"{in_num}*{out_num}{suffix}")

    async def query_all_ties(self) -> None:
        """Send query to request active matrix configuration."""
        await self.send_command("I")
