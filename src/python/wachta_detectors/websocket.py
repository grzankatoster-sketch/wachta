"""A WebSocket client small enough to read, written against RFC 6455.

Why not a library: the detectors image runs `uv run --no-dev`, so every dependency has to go through
pyproject.toml AND uv.lock. AISStream needs exactly one thing this project does not already have - a
text WebSocket that reads frames - and that is about a hundred lines. The rest of the popular clients
is asyncio, compression and subprotocol negotiation that the loop in run.py would never use.

Two decisions here exist because of scars, not taste:

  * We do NOT offer permessage-deflate. RFC 6455 section 9.1 lets a server use only extensions the
    client asked for, so not asking is what guarantees the payload arrives uncompressed. The official
    AISStream python example turns deflate ON; a client that negotiates it and then forgets to
    inflate reads binary noise. This repo already lost an AIS source once to exactly that shape of
    bug (urllib does not gunzip by itself), so the compression is refused at the handshake instead of
    being handled later.
  * Every client frame is masked. The spec requires it and real servers close the connection with
    1002 when it is missing - a failure that only shows up against the live server, never in a test
    written against one's own encoder.
"""
import base64
import hashlib
import os
import socket
import ssl
import struct
from urllib.parse import urlparse

# RFC 6455 section 1.3: the server appends this to Sec-WebSocket-Key and SHA-1s the result.
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_CONTINUATION = 0x0
OP_TEXT = 0x1
OP_BINARY = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA

MAX_FRAME_BYTES = 8 * 1024 * 1024   # AIS message is < 1 kB; anything this size is a broken length


class WebSocketError(Exception):
    """Handshake refused, frame malformed, or the peer closed mid-message."""


class WebSocket:
    """One text WebSocket connection. Blocking, single-threaded, no reconnect.

    Reconnecting belongs to the caller: the loop in run.py already knows how long a tick lasts and
    what a failed tick costs, and a client that retries on its own would hide the outage from it.
    """

    def __init__(self, sock: socket.socket, max_frame_bytes: int = MAX_FRAME_BYTES):
        self._sock = sock
        self._max_frame_bytes = max_frame_bytes
        self._buffer = b""

    # --- polaczenie ---------------------------------------------------------

    @classmethod
    def connect(cls, url: str, headers: dict[str, str] | None = None, timeout: float = 30.0,
                context: ssl.SSLContext | None = None) -> "WebSocket":
        parsed = urlparse(url)
        secure = parsed.scheme == "wss"
        port = parsed.port or (443 if secure else 80)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        sock = socket.create_connection((parsed.hostname, port), timeout=timeout)
        if secure:
            context = context or ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=parsed.hostname)
        ws = cls(sock)
        try:
            ws._handshake(parsed.hostname, port, path, secure, headers or {})
        except BaseException:
            ws.close_socket()
            raise
        return ws

    def _handshake(self, host: str, port: int, path: str, secure: bool, extra: dict[str, str]) -> None:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        host_header = host if port == (443 if secure else 80) else f"{host}:{port}"
        lines = [
            f"GET {path} HTTP/1.1",
            f"Host: {host_header}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {key}",
            "Sec-WebSocket-Version: 13",
        ]
        lines += [f"{k}: {v}" for k, v in extra.items()]
        self._sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("ascii"))

        head = self._read_until(b"\r\n\r\n")
        text = head.decode("latin-1")
        status = text.split("\r\n", 1)[0]
        if " 101" not in status:
            raise WebSocketError(f"serwer odmowil uaktualnienia polaczenia: {status.strip()}")

        received = {}
        for line in text.split("\r\n")[1:]:
            if ":" in line:
                name, value = line.split(":", 1)
                received[name.strip().lower()] = value.strip()
        expected = base64.b64encode(hashlib.sha1((key + GUID).encode("ascii")).digest()).decode("ascii")
        if received.get("sec-websocket-accept") != expected:
            raise WebSocketError("zly Sec-WebSocket-Accept - to nie jest serwer WebSocket")
        # Nie prosilismy o zadne rozszerzenie, wiec serwer nie ma prawa zadnego wlaczyc. Jesli
        # jednak wlaczyl, ramki sa skompresowane i kazdy dalszy odczyt to smieci - lepiej zerwac tu.
        if received.get("sec-websocket-extensions"):
            raise WebSocketError(
                f"serwer narzucil rozszerzenie, o ktore nie prosilismy: {received['sec-websocket-extensions']}")

    # --- odczyt / zapis -----------------------------------------------------

    def send_text(self, text: str) -> None:
        self._send_frame(OP_TEXT, text.encode("utf-8"))

    def recv_text(self) -> str | None:
        """Next text message, or None when the peer closed cleanly.

        Ping is answered here rather than by the caller: AISStream keeps the connection alive with
        pings, and a client that ignores them is dropped after a couple of minutes - which looks
        exactly like "the source went quiet" in the logs.
        """
        opcode, payload = None, b""
        while True:
            fin, frame_op, data = self._read_frame()
            if frame_op == OP_CLOSE:
                self._send_frame(OP_CLOSE, data[:2] if len(data) >= 2 else b"")
                return None
            if frame_op == OP_PING:
                self._send_frame(OP_PONG, data)
                continue
            if frame_op == OP_PONG:
                continue
            if frame_op == OP_CONTINUATION:
                if opcode is None:
                    raise WebSocketError("kontynuacja bez ramki poczatkowej")
            else:
                opcode, payload = frame_op, b""
            payload += data
            if len(payload) > self._max_frame_bytes:
                raise WebSocketError("wiadomosc ponad limit - zrywam zamiast rosnac w nieskonczonosc")
            if fin:
                if opcode == OP_BINARY:
                    # Nie prosilismy o kompresje i nie umawialismy sie na dane binarne; zamiast
                    # zgadywac kodowanie, mowimy glosno, ze protokol sie rozjechal.
                    raise WebSocketError("ramka binarna na strumieniu tekstowym")
                return payload.decode("utf-8", "replace")

    def _read_frame(self) -> tuple[bool, int, bytes]:
        header = self._read_exactly(2)
        fin = bool(header[0] & 0x80)
        opcode = header[0] & 0x0F
        masked = bool(header[1] & 0x80)
        length = header[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read_exactly(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read_exactly(8))[0]
        if length > self._max_frame_bytes:
            raise WebSocketError(f"ramka {length} B ponad limit {self._max_frame_bytes} B")
        mask = self._read_exactly(4) if masked else b""
        data = self._read_exactly(length) if length else b""
        if masked:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        return fin, opcode, data

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        header = bytes([0x80 | opcode])
        size = len(payload)
        if size < 126:
            header += bytes([0x80 | size])
        elif size < 65536:
            header += bytes([0x80 | 126]) + struct.pack("!H", size)
        else:
            header += bytes([0x80 | 127]) + struct.pack("!Q", size)
        self._sock.sendall(header + mask + masked)

    # --- bajty --------------------------------------------------------------

    def _read_until(self, marker: bytes) -> bytes:
        while marker not in self._buffer:
            piece = self._sock.recv(4096)
            if not piece:
                raise WebSocketError("polaczenie zerwane w trakcie handshake'u")
            self._buffer += piece
            if len(self._buffer) > 64 * 1024:
                raise WebSocketError("naglowki handshake'u ponad 64 kB")
        head, _, rest = self._buffer.partition(marker)
        self._buffer = rest
        return head + marker

    def _read_exactly(self, count: int) -> bytes:
        while len(self._buffer) < count:
            piece = self._sock.recv(max(4096, count - len(self._buffer)))
            if not piece:
                raise WebSocketError("polaczenie zerwane w srodku ramki")
            self._buffer += piece
        head, self._buffer = self._buffer[:count], self._buffer[count:]
        return head

    # --- zamykanie ----------------------------------------------------------

    def close(self, code: int = 1000) -> None:
        try:
            self._send_frame(OP_CLOSE, struct.pack("!H", code))
        except OSError:
            pass
        self.close_socket()

    def close_socket(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass

    def settimeout(self, seconds: float | None) -> None:
        self._sock.settimeout(seconds)

    def __enter__(self) -> "WebSocket":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
