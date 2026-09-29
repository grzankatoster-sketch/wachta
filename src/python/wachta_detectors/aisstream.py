"""AISStream: the southern Baltic, which the Finnish network does not reach.

Measured on the live database, 2026-09-29, over 20 h of Digitraffic ingestion (165 202 positions,
1210 hulls): 55.48-65.80N, and only 178 fixes (0.11%) south of 57N. Gdansk Bay, the Polish coast,
the Kaliningrad approaches and the Danish straits each contained exactly ZERO positions. The map
declares 48-70N / 0-40E, so it was promising an area it never showed.

This module is the second AIS source. It is a push stream, not a poll: AISStream keeps a WebSocket
open and sends a message whenever a receiver hears one. The detector loop is a tick loop, so the two
are joined by a buffer - a background reader keeps the socket open and writes the newest fix per
MMSI into `ShipBuffer`, and the loop drains it every couple of minutes, exactly where it already
drains Digitraffic.

Three choices here were made by measurement and are written down with the numbers, because none of
them is obvious:

  * the bounding box (see BALTIC_SOUTH),
  * which source wins when both see the same hull (see PRIMARY_WINS_WINDOW),
  * which AIS message types we ask for (see MESSAGE_TYPES).
"""
import json
import logging
import re
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .websocket import WebSocket, WebSocketError

log = logging.getLogger("wachta.aisstream")

URL = "wss://stream.aisstream.io/v0/stream"
SOURCE_ID = "aisstream-baltic-s"

# Ten sam naglowek co reszta projektu. adsb.lol odpowiadalo 403 bez opisowego User-Agent,
# Digitraffic tak samo - nie czekamy, az AISStream tez zacznie.
USER_AGENT = "wachta-project/0.1 (situational awareness, non-commercial)"


@dataclass(frozen=True)
class BoundingBox:
    """AISStream takes corners as [[lat1, lon1], [lat2, lon2]]; lat first, unlike GeoJSON."""
    lat_min: float
    lon_min: float
    lat_max: float
    lon_max: float

    def as_pairs(self) -> list[list[float]]:
        return [[self.lat_min, self.lon_min], [self.lat_max, self.lon_max]]

    def contains(self, lat: float, lon: float) -> bool:
        return self.lat_min <= lat <= self.lat_max and self.lon_min <= lon <= self.lon_max


# Pudelko wybrane pomiarem nakladania sie z Digitrafficiem, nie "na oko". Z 886 statkow, ktore
# Digitraffic mial zywe (pozycja mlodsza niz 30 min) 2026-09-29, w tym prostokacie siedzialo 11
# (1,24%). Szersze warianty sprawdzone tym samym zapytaniem: 53,5-59,0N/9-24E daje 39 nakladek
# (4,4%), a 53,5-60,0N/9-30E az 372 (42%) - czyli polowe ruchu pobieralibysmy dwa razy. Wezsze
# 53,5-57,5N/9-24E daje zero nakladek, ale obcina Zatoke Ryska i polnocna Gotlandie, wiec kosztuje
# wiecej niz oszczedza. Stad gorna krawedz 58,5N: 1,24% nakladki zdejmuje regula w drop_covered().
BALTIC_SOUTH = BoundingBox(lat_min=53.5, lon_min=9.0, lat_max=58.5, lon_max=24.0)

# O ktore typy wiadomosci prosimy. Klasa A (PositionReport) to statki handlowe - tankowce, masowce,
# promy: caly material dla D4/D5/D6/D7. ShipStaticData dowozi nazwe, IMO i typ, ktorych sam
# PositionReport nie ma. Klasy B (male jednostki, jachty, czesc kutrow) NIE bierzemy swiadomie: w
# Zatoce Gdanskiej latem to dominujacy ruch, ktory dla detektorow ciemnej floty jest szumem, a
# kosztuje pasmo i wiersze. Brak klasy B jest odnotowany w docs/SOURCES.md jako luka pokrycia.
MESSAGE_TYPES = ("PositionReport", "ShipStaticData")

# Kiedy uznajemy, ze Digitraffic "trzyma" ten kadlub i AISStream ma sie nie wtracac. Zmierzone na
# zywej bazie 2026-09-29, 41 013 kolejnych roznic czasu miedzy pozycjami tego samego MMSI z 12 h:
# mediana 179 s, p90 240 s, p95 360 s, p99 801 s. Udzial przerw miesczacych sie w oknie:
# 6 min - 94,73%, 15 min - 99,12%, 30 min - 99,66%. Piatnascie minut kupuje 4,4 pp wobec szesciu,
# a trzydziesci dokłada juz tylko 0,54 pp i dwa razy dluzej blokuje statek, ktory NAPRAWDE wyszedl
# z zasiegu finskiej sieci. Stad 15 min.
PRIMARY_WINS_WINDOW = timedelta(minutes=15)

# Stara pozycja nie ma wygladac jak biezaca - ta sama liczba, ktorej uzywa sciezka Digitraffic.
MAX_POSITION_AGE = timedelta(minutes=30)
# Zegar nadajnika bywa przestawiony. Pozycja "z przyszlosci" psuje kazdy detektor liczacy czas
# miedzy pozycjami (ujemny czas -> nieskonczona predkosc), wiec odrzucamy ja przy wejsciu.
MAX_CLOCK_SKEW = timedelta(minutes=2)

# AIS koduje "brak danych" wartosciami spoza zakresu, a nie pustym polem.
LAT_UNAVAILABLE = 91.0
LON_UNAVAILABLE = 181.0
SOG_UNAVAILABLE = 102.3
COG_UNAVAILABLE = 360.0

POSITION_TYPES = ("PositionReport",)
STATIC_TYPES = ("ShipStaticData",)

_FRACTION = re.compile(r"\.(\d+)")


def subscription(api_key: str, boxes: Iterable[BoundingBox] = (BALTIC_SOUTH,),
                 message_types: Iterable[str] = MESSAGE_TYPES) -> dict:
    """The first frame after the handshake. AISStream drops the connection if it is late or absent."""
    return {
        "APIKey": api_key,
        "BoundingBoxes": [b.as_pairs() for b in boxes],
        "FilterMessageTypes": list(message_types),
    }


def parse_time(value: object) -> datetime | None:
    """MetaData.time_utc, which is a Go timestamp: '2026-09-29 07:11:02.123456789 +0000 UTC'.

    Nine fractional digits and the trailing ' UTC' both defeat datetime.fromisoformat, so the string
    is trimmed to what it understands rather than parsed with a format that would break the first
    time AISStream prints eight digits instead of nine.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().removesuffix(" UTC").strip()
    # Nanosekundy przycinamy do mikrosekund i DOPEŁNIAMY zerami, a nie spacjami: ".5" to pol sekundy,
    # czyli 500000 us, nie 5 us - pomylka warta 0,5 s w kazdej pozycji.
    match = _FRACTION.search(text)
    if match:
        text = text[:match.start()] + "." + match.group(1)[:6].ljust(6, "0") + text[match.end():]
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _clean_text(value: object) -> str | None:
    """AIS pads names with spaces and with '@', which is the six-bit alphabet's NUL."""
    if not isinstance(value, str):
        return None
    text = value.replace("@", " ").strip()
    return text or None


@dataclass(frozen=True)
class Position:
    mmsi: str
    ts: datetime
    lat: float
    lon: float
    sog: float | None
    cog: float | None
    nav_status: str | None
    name: str | None


@dataclass(frozen=True)
class Static:
    """Name, IMO and type - the PositionReport carries none of them."""
    mmsi: str
    name: str | None
    imo: str | None
    ship_type: str | None


def parse_message(message: object, now: datetime) -> Position | Static | None:
    """One AISStream envelope in, one usable fact out - or None, which is the common case.

    Returning None covers everything we deliberately do not act on: other message types, positions
    the transmitter marked as unavailable, and timestamps a receiver's clock invented.
    """
    if not isinstance(message, dict):
        return None
    kind = message.get("MessageType")
    body = message.get("Message")
    meta = message.get("MetaData") if isinstance(message.get("MetaData"), dict) else {}
    if not isinstance(body, dict):
        return None
    payload = body.get(kind)
    if not isinstance(payload, dict):
        return None

    mmsi = payload.get("UserID") or meta.get("MMSI") or meta.get("MMSI_String")
    mmsi = str(mmsi).strip() if mmsi is not None else ""
    if not mmsi or mmsi == "0":
        return None

    if kind in STATIC_TYPES:
        imo = payload.get("ImoNumber")
        ship_type = payload.get("Type")
        return Static(
            mmsi=mmsi,
            name=_clean_text(payload.get("Name")) or _clean_text(meta.get("ShipName")),
            imo=str(imo) if isinstance(imo, int) and imo > 0 else None,
            ship_type=str(ship_type) if isinstance(ship_type, int) and ship_type > 0 else None,
        )

    if kind not in POSITION_TYPES:
        return None

    lat, lon = _number(payload.get("Latitude")), _number(payload.get("Longitude"))
    if lat is None or lon is None or abs(lat) > 90.0 or abs(lon) > 180.0:
        # 91 / 181 to kod "brak pozycji", nie wspolrzedne - przepuszczone wyladowalyby na mapie
        # jako statek na biegunie.
        return None

    ts = parse_time(meta.get("time_utc") or meta.get("TimeUtc")) or now
    if ts > now + MAX_CLOCK_SKEW:
        return None

    sog = _number(payload.get("Sog"))
    cog = _number(payload.get("Cog"))
    nav = payload.get("NavigationalStatus")
    return Position(
        mmsi=mmsi,
        ts=ts,
        lat=lat,
        lon=lon,
        sog=sog if sog is not None and 0.0 <= sog < SOG_UNAVAILABLE else None,
        cog=cog if cog is not None and 0.0 <= cog < COG_UNAVAILABLE else None,
        nav_status=str(nav) if isinstance(nav, int) and 0 <= nav <= 15 else None,
        name=_clean_text(meta.get("ShipName")),
    )


class ShipBuffer:
    """Newest position per MMSI, with the static data folded in, waiting for the next tick.

    Bounded on purpose. A stream that nobody drains - a database down for an hour - must cost memory
    that is proportional to the number of hulls in the box, not to the number of messages received,
    so only the newest fix per MMSI is kept and the static table is capped.
    """

    def __init__(self, max_static: int = 20_000):
        self._positions: dict[str, Position] = {}
        self._static: dict[str, Static] = {}
        self._emitted: dict[str, datetime] = {}
        self._max_static = max_static
        self._lock = threading.Lock()
        self.received = 0
        self.ignored = 0

    def accept(self, message: object, now: datetime) -> bool:
        parsed = parse_message(message, now)
        with self._lock:
            self.received += 1
            if parsed is None:
                self.ignored += 1
                return False
            if isinstance(parsed, Static):
                if parsed.mmsi not in self._static and len(self._static) >= self._max_static:
                    self._static.pop(next(iter(self._static)))
                self._static[parsed.mmsi] = parsed
                return True
            held = self._positions.get(parsed.mmsi)
            if held is not None and parsed.ts < held.ts:
                return False
            self._positions[parsed.mmsi] = parsed
            return True

    def drain(self, now: datetime, max_age: timedelta = MAX_POSITION_AGE) -> list[dict]:
        """Everything new since the last drain, in the shape repository.insert_ship_positions wants.

        A fix is emitted once. Without that marker the same position would be rewritten every tick
        for as long as a ship stays silent, and D4 - which looks for AIS going quiet - would never
        see a gap, because the database would keep inventing fresh rows for a hull nobody can hear.
        """
        with self._lock:
            ships, stale = [], []
            for mmsi, pos in self._positions.items():
                if now - pos.ts > max_age:
                    stale.append(mmsi)
                    continue
                if self._emitted.get(mmsi) is not None and pos.ts <= self._emitted[mmsi]:
                    continue
                meta = self._static.get(mmsi)
                ships.append({
                    "mmsi": mmsi,
                    "ts": pos.ts,
                    "lat": pos.lat,
                    "lon": pos.lon,
                    "sog": pos.sog,
                    "cog": pos.cog,
                    "name": pos.name or (meta.name if meta else None),
                    "imo": meta.imo if meta else None,
                    "ship_type": meta.ship_type if meta else None,
                    "nav_status": pos.nav_status,
                })
                self._emitted[mmsi] = pos.ts
            for mmsi in stale:
                self._positions.pop(mmsi, None)
                self._emitted.pop(mmsi, None)
            return ships

    def __len__(self) -> int:
        with self._lock:
            return len(self._positions)


def drop_covered(ships: list[dict], covered: set[str]) -> tuple[list[dict], list[dict]]:
    """Deduplication between the two AIS sources: the national network wins, the crowd fills the rest.

    Returns (kept, dropped).

    Why Digitraffic wins where both hear the same hull: it is Fintraffic's own shore network - the
    national authority's receivers, trust_tier 2 - and every position comes with the vessel registry
    behind it (IMO, type, draught), which AISStream's PositionReport does not carry. AISStream is a
    volunteer aggregation with no SLA, trust_tier 3. Just as important, keeping both would be
    actively harmful rather than merely redundant: two independent receivers give the same hull two
    positions a few hundred metres and a few seconds apart, and D7 measures implied speed between
    consecutive fixes of one MMSI. Two sources for one ship manufacture impossible speeds, which is
    precisely the signature D7 reports as "one number, two hulls".

    The rule is written over MMSI rather than over geography so that it keeps holding if Fintraffic
    ever extends its network south - nothing here has to be re-tuned, the overlap simply shifts.
    """
    kept = [s for s in ships if s["mmsi"] not in covered]
    dropped = [s for s in ships if s["mmsi"] in covered]
    return kept, dropped


class AisStreamReader:
    """Background thread holding the subscription open, so the tick loop can stay a tick loop.

    Everything that talks to the network is injected (`connect`), because the one thing that must be
    provable without an API key is that a recorded stream of AISStream frames turns into the right
    rows. The reconnect policy is here rather than in WebSocket for the same reason: it is a
    decision about this source, and it is testable with a fake connector that fails on demand.
    """

    def __init__(self, api_key: str, boxes: Iterable[BoundingBox] = (BALTIC_SOUTH,),
                 url: str = URL, connect: Callable[..., WebSocket] | None = None,
                 buffer: ShipBuffer | None = None, retry_seconds: float = 30.0,
                 clock: Callable[[], datetime] | None = None):
        if not api_key:
            raise ValueError("AISStream wymaga klucza - ustaw AISSTREAM_API_KEY")
        self._api_key = api_key
        self._boxes = tuple(boxes)
        self._url = url
        self._connect = connect or WebSocket.connect
        self._retry = retry_seconds
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.buffer = buffer or ShipBuffer()
        self.last_error: str | None = None
        self.connections = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # --- sterowanie ---------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self.run, name="aisstream", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
            self._thread = None

    def drain(self, now: datetime) -> list[dict]:
        return self.buffer.drain(now)

    # --- petla --------------------------------------------------------------

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as exc:   # kazda awaria zrodla to jedna sesja, nie koniec watku
                self.last_error = repr(exc)[:200]
                log.warning("AISStream: sesja przerwana (%s), ponawiam za %.0f s",
                            self.last_error, self._retry)
            if self._stop.wait(self._retry):
                return

    def run_once(self) -> None:
        """One connection, from the subscription to the close - the whole source, minus the retry.

        Public because this is the seam the tests use: a recorded stream of frames goes in through a
        fake connector and rows come out, with no key, no network and no thread.
        """
        websocket = self._connect(self._url, headers={"User-Agent": USER_AGENT})
        self.connections += 1
        try:
            websocket.send_text(json.dumps(subscription(self._api_key, self._boxes)))
            while not self._stop.is_set():
                text = websocket.recv_text()
                if text is None:
                    log.info("AISStream: serwer zamknal polaczenie")
                    return
                self._handle(text)
        finally:
            try:
                websocket.close()
            except Exception:
                pass

    def _handle(self, text: str) -> None:
        try:
            message = json.loads(text)
        except ValueError:
            self.last_error = f"nie-JSON w strumieniu: {text[:80]}"
            return
        # Bledny klucz nie wywala polaczenia - AISStream odpowiada jedna ramka {"error": ...} i
        # milczy. Bez tej galezi wygladaloby to jak "morze jest puste", a nie jak "klucz jest zly".
        if isinstance(message, dict) and (message.get("error") or message.get("Error")):
            self.last_error = str(message.get("error") or message.get("Error"))[:200]
            log.error("AISStream odrzucil subskrypcje: %s", self.last_error)
            raise WebSocketError(self.last_error)
        self.buffer.accept(message, self._clock())


def reader_from_env(env, boxes: Iterable[BoundingBox] = (BALTIC_SOUTH,)) -> AisStreamReader | None:
    """Started only when a key exists. No key is a normal state, not a failure.

    The southern Baltic is then simply missing from the map, which docs/SOURCES.md says out loud -
    a source silently degrading to nothing is worse than a source that is visibly absent.
    """
    key = (env.get("AISSTREAM_API_KEY") or "").strip()
    if not key:
        log.warning("AISStream: brak AISSTREAM_API_KEY - poludniowy Baltyk pozostaje bez pokrycia "
                    "(instrukcja zdobycia klucza w docs/SOURCES.md)")
        return None
    reader = AisStreamReader(key, boxes)
    reader.start()
    log.info("AISStream: subskrypcja %s", [b.as_pairs() for b in boxes])
    return reader
