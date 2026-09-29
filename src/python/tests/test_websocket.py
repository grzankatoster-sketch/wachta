"""The WebSocket client, checked against a server written separately from it.

A frame codec tested against its own encoder proves nothing: both sides agree on the same mistake.
So the server here decodes bytes by hand from RFC 6455 - length in the low seven bits, 126 and 127
as escapes to a 16- and 64-bit length, the mask key after the length, payload XORed with it - and
never calls anything from wachta_detectors.websocket. What is being checked is the wire, not the
round trip through one implementation.

The one property that only a real server can check is the masking. The spec makes it mandatory for
clients, real servers close the connection with 1002 without it, and a self-consistent test would
pass happily on an unmasked client.
"""
import base64
import hashlib
import socket
import struct
import threading

import pytest

from wachta_detectors.websocket import WebSocket, WebSocketError

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _accept_for(key: str) -> str:
    return base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()


class Serwer:
    """Minimal RFC 6455 server on loopback. Records what the client masked and sent."""

    def __init__(self, scenario, extensions: str | None = None, bad_accept: bool = False):
        self.scenario = scenario          # callable(serwer) po handshake'u
        self.extensions = extensions
        self.bad_accept = bad_accept
        self.received: list[tuple[int, bytes]] = []
        self.masked_flags: list[bool] = []
        self.error: BaseException | None = None
        self._listener = socket.socket()
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(1)
        self.port = self._listener.getsockname()[1]
        self._conn: socket.socket | None = None
        self._buffer = b""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.port}/v0/stream"

    # --- strona serwera -----------------------------------------------------

    def _run(self):
        try:
            self._conn, _ = self._listener.accept()
            self._conn.settimeout(10)
            head = b""
            while b"\r\n\r\n" not in head:
                head += self._conn.recv(4096)
            lines = head.decode("latin-1").split("\r\n")
            # RFC 6455 4.2.1: the opening handshake is a GET. A real server answers anything else
            # with 405 and never upgrades, so a permissive test server would hide a broken client.
            assert lines[0].startswith("GET "), f"handshake nie jest GET: {lines[0]}"
            assert any(ln.lower() == "upgrade: websocket" for ln in lines), "brak naglowka Upgrade"
            key = next(ln.split(":", 1)[1].strip() for ln in lines
                       if ln.lower().startswith("sec-websocket-key"))
            accept = "zle" if self.bad_accept else _accept_for(key)
            response = ["HTTP/1.1 101 Switching Protocols", "Upgrade: websocket",
                        "Connection: Upgrade", f"Sec-WebSocket-Accept: {accept}"]
            if self.extensions:
                response.append(f"Sec-WebSocket-Extensions: {self.extensions}")
            self._conn.sendall(("\r\n".join(response) + "\r\n\r\n").encode())
            self.scenario(self)
        except BaseException as exc:   # blad serwera ma byc widoczny w tescie, nie zgubiony w watku
            self.error = exc
        finally:
            if self._conn is not None:
                self._conn.close()
            self._listener.close()

    def _read(self, count: int) -> bytes:
        while len(self._buffer) < count:
            piece = self._conn.recv(65536)
            if not piece:
                raise AssertionError("klient zerwal polaczenie wczesniej niz test zakladal")
            self._buffer += piece
        head, self._buffer = self._buffer[:count], self._buffer[count:]
        return head

    def read_frame(self) -> tuple[int, bytes]:
        first, second = self._read(2)
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        self.masked_flags.append(masked)
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read(8))[0]
        mask = self._read(4) if masked else b""
        data = self._read(length) if length else b""
        if masked:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.received.append((opcode, data))
        return opcode, data

    def send_frame(self, opcode: int, payload: bytes = b"") -> None:
        """Server frames are never masked - that is the asymmetry the client has to get right."""
        self.send_fragment(opcode, payload, fin=True)

    def send_fragment(self, opcode: int, payload: bytes = b"", fin: bool = True) -> None:
        header = bytes([(0x80 if fin else 0x00) | opcode])
        size = len(payload)
        if size < 126:
            header += bytes([size])
        elif size < 65536:
            header += bytes([126]) + struct.pack("!H", size)
        else:
            header += bytes([127]) + struct.pack("!Q", size)
        self._conn.sendall(header + payload)

    def send_text(self, text: str) -> None:
        self.send_frame(0x1, text.encode("utf-8"))

    def join(self):
        self._thread.join(10)
        if self.error is not None:
            raise self.error


def test_handshake_i_wymiana_tekstu():
    def scenario(s):
        s.read_frame()                 # subskrypcja od klienta
        s.send_text('{"MessageType":"PositionReport"}')
        s.send_frame(0x8, struct.pack("!H", 1000))

    serwer = Serwer(scenario)
    client = WebSocket.connect(serwer.url)
    client.settimeout(10)
    client.send_text("czesc")
    assert client.recv_text() == '{"MessageType":"PositionReport"}'
    assert client.recv_text() is None      # zamkniecie po stronie serwera
    client.close_socket()
    serwer.join()
    assert serwer.received[0] == (0x1, b"czesc")


def test_klient_maskuje_kazda_ramke():
    """RFC 6455 5.1: a client frame without the mask bit is a protocol error. Only a server sees it."""
    def scenario(s):
        s.read_frame()
        s.send_frame(0x8, struct.pack("!H", 1000))

    serwer = Serwer(scenario)
    client = WebSocket.connect(serwer.url)
    client.send_text("x")
    client.recv_text()
    client.close_socket()
    serwer.join()
    assert serwer.masked_flags == [True]


def test_ping_dostaje_pong():
    """AISStream keeps the connection alive with pings; a client that ignores them gets dropped."""
    def scenario(s):
        s.read_frame()
        s.send_frame(0x9, b"zyjesz?")
        s.read_frame()                 # pong
        s.send_text("po pingu")
        s.send_frame(0x8, struct.pack("!H", 1000))

    serwer = Serwer(scenario)
    client = WebSocket.connect(serwer.url)
    client.settimeout(10)
    client.send_text("start")
    assert client.recv_text() == "po pingu"
    client.close_socket()
    serwer.join()
    assert serwer.received[1] == (0xA, b"zyjesz?")


def test_dluga_wiadomosc_ponad_125_bajtow():
    """Over 125 bytes the length escapes to 16 bits - in both directions."""
    duzy = "x" * 1000
    def scenario(s):
        s.read_frame()
        s.send_frame(0x1, duzy.encode())
        s.send_frame(0x8, struct.pack("!H", 1000))

    serwer = Serwer(scenario)
    client = WebSocket.connect(serwer.url)
    client.settimeout(10)
    client.send_text("y" * 300)
    assert client.recv_text() == duzy
    client.close_socket()
    serwer.join()
    assert serwer.received[0] == (0x1, b"y" * 300)


def test_wiadomosc_w_dwoch_fragmentach():
    """A server may split one message across frames; only the last has FIN set.

    Treating a continuation frame as a message of its own would hand the parser half a JSON object,
    and half an AIS message decodes into nothing - silently, once in a while, under load.
    """
    def scenario(s):
        s.read_frame()
        s.send_fragment(0x1, b'{"MessageType":', fin=False)
        s.send_fragment(0x0, b'"PositionReport"}', fin=True)
        s.send_frame(0x8, struct.pack("!H", 1000))

    serwer = Serwer(scenario)
    client = WebSocket.connect(serwer.url)
    client.settimeout(10)
    client.send_text("start")
    assert client.recv_text() == '{"MessageType":"PositionReport"}'
    client.close_socket()
    serwer.join()


def test_serwer_nie_moze_narzucic_kompresji():
    """We never offer permessage-deflate, so a server enabling it means the payload is not readable.

    Failing loudly here is the whole point: the repo already shipped a source that read gzip as text
    because nobody checked, and compressed frames would look like corrupted JSON forever.
    """
    serwer = Serwer(lambda s: None, extensions="permessage-deflate")
    with pytest.raises(WebSocketError, match="rozszerzenie"):
        WebSocket.connect(serwer.url)
    serwer.join()


def test_zly_accept_konczy_polaczenie():
    serwer = Serwer(lambda s: None, bad_accept=True)
    with pytest.raises(WebSocketError, match="Sec-WebSocket-Accept"):
        WebSocket.connect(serwer.url)
    serwer.join()


def test_odmowa_uaktualnienia():
    """A plain HTTP answer (403, a captive portal, a proxy) must not be read as a stream."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    def serve():
        conn, _ = listener.accept()
        conn.recv(4096)
        conn.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
        conn.close()
        listener.close()

    threading.Thread(target=serve, daemon=True).start()
    with pytest.raises(WebSocketError, match="403"):
        WebSocket.connect(f"ws://127.0.0.1:{port}/v0/stream")
