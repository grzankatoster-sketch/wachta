"""AISStream: the southern Baltic source, proven without a key.

The sample in fixtures/aisstream_sample.jsonl is NOT captured traffic - this repository has no
AISStream key yet. It was built message by message from aisstream.io's own OpenAPI models
(github.com/aisstream/ais-message-models, PositionReport.md and ShipStaticData.md, read 2026-09-29),
so every field name and type comes from the provider rather than from a guess. The moment a key
exists, eval/feasibility/record_aisstream.py overwrites this file with real frames and these tests
run unchanged - that is the point of keeping the parser and the socket in separate modules.

What the sample deliberately contains, because each line is a way the live stream breaks something:
  * a hull in Gdansk Bay, with its ShipStaticData arriving as a separate message,
  * a hull off Kaliningrad at anchor,
  * Sog 102.3 and Cog 360 - the AIS codes for "not available", not a ship doing 102 knots,
  * Latitude 91 / Longitude 181 - the code for "no position", which would land a ship on the pole,
  * a BaseStationReport, which is a shore mast and not a ship at all,
  * an OLDER position for a hull that already reported a newer one,
  * a hull in the Gulf of Finland, where Digitraffic already looks - the deduplication case,
  * a timestamp two and a half hours in the future, from a receiver with a wrong clock.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from wachta_detectors import aisstream
from wachta_detectors.aisstream import (
    BALTIC_SOUTH,
    AisStreamReader,
    BoundingBox,
    ShipBuffer,
    drop_covered,
    parse_message,
    parse_time,
    reader_from_env,
    subscription,
)
from wachta_detectors.websocket import WebSocketError

SAMPLE = Path(__file__).parent / "fixtures" / "aisstream_sample.jsonl"
NOW = datetime(2026, 9, 29, 7, 1, tzinfo=timezone.utc)


def probka() -> list[dict]:
    return [json.loads(line) for line in SAMPLE.read_text(encoding="utf-8").splitlines() if line.strip()]


def wypelniony_bufor() -> ShipBuffer:
    buffer = ShipBuffer()
    for message in probka():
        buffer.accept(message, NOW)
    return buffer


# --- subskrypcja ------------------------------------------------------------

def test_subskrypcja_ma_klucz_pudelko_i_filtr():
    frame = subscription("KLUCZ", [BALTIC_SOUTH])
    assert frame["APIKey"] == "KLUCZ"
    assert frame["FilterMessageTypes"] == ["PositionReport", "ShipStaticData"]
    assert frame["BoundingBoxes"] == [[[53.5, 9.0], [58.5, 24.0]]]


def test_pudelko_podaje_szerokosc_przed_dlugoscia():
    """AISStream takes [lat, lon]; GeoJSON, which this repo uses everywhere else, takes [lon, lat].

    Swapped, the subscription asks for a box off the coast of Somalia and the map stays empty with
    no error anywhere - so the order is asserted, not trusted.
    """
    lat_min, lon_min = BoundingBox(53.5, 9.0, 58.5, 24.0).as_pairs()[0]
    assert (lat_min, lon_min) == (53.5, 9.0)


def test_pudelko_obejmuje_akweny_ktorych_brakowalo():
    """The four areas measured empty in the live database on 2026-09-29."""
    assert BALTIC_SOUTH.contains(54.52, 18.55)    # Zatoka Gdanska
    assert BALTIC_SOUTH.contains(54.81, 19.90)    # podejscia do Kaliningradu
    assert BALTIC_SOUTH.contains(54.10, 14.25)    # Swinoujscie
    assert BALTIC_SOUTH.contains(55.70, 12.60)    # Sund
    assert not BALTIC_SOUTH.contains(60.15, 24.95)   # Helsinki - to juz Digitraffic


# --- parsowanie -------------------------------------------------------------

def test_probka_daje_tylko_realne_pozycje():
    ships = {s["mmsi"]: s for s in wypelniony_bufor().drain(NOW)}
    assert set(ships) == {"261009000", "273451020", "219018842", "230982000"}


def test_pozycja_i_dane_statyczne_lacza_sie_w_jeden_wiersz():
    ship = {s["mmsi"]: s for s in wypelniony_bufor().drain(NOW)}["261009000"]
    assert (ship["lat"], ship["lon"]) == (54.5231, 18.5519)
    assert ship["sog"] == 11.4 and ship["cog"] == 87.3
    assert ship["nav_status"] == "0"
    assert ship["imo"] == "9105254"          # tylko z ShipStaticData, PositionReport tego nie ma
    assert ship["ship_type"] == "70"
    assert ship["name"] == "KAPITAN POINC"   # bez wypelniaczy '@' i spacji


def test_brak_pozycji_nie_laduje_na_biegunie():
    """Latitude 91 / Longitude 181 is the AIS code for 'no position', not a coordinate."""
    assert all(s["mmsi"] != "244660000" for s in wypelniony_bufor().drain(NOW))


def test_niedostepne_sog_i_cog_sa_puste_a_nie_zerowe():
    """102.3 kt and 360 deg are 'not available'. Stored as numbers they are a ship at Mach 0.15."""
    ship = {s["mmsi"]: s for s in wypelniony_bufor().drain(NOW)}["219018842"]
    assert ship["sog"] is None and ship["cog"] is None


def test_stacja_brzegowa_to_nie_statek():
    assert all(s["mmsi"] != "2610001" for s in wypelniony_bufor().drain(NOW))


def test_pozycja_z_przyszlosci_odrzucona():
    """A clock two hours fast gives a negative time between fixes, and every detector divides by it."""
    assert all(s["mmsi"] != "636092123" for s in wypelniony_bufor().drain(NOW))


def test_starsza_pozycja_nie_cofa_statku():
    """The sample repeats one hull with an older fix; the newer one must survive."""
    ship = {s["mmsi"]: s for s in wypelniony_bufor().drain(NOW)}["261009000"]
    assert ship["ts"] == datetime(2026, 9, 29, 7, 0, 11, 482913, tzinfo=timezone.utc)


@pytest.mark.parametrize("text, mikrosekundy", [
    ("2026-09-29 07:00:11.482913745 +0000 UTC", 482913),
    ("2026-09-29 07:00:11.5 +0000 UTC", 500000),     # pol sekundy, nie 5 mikrosekund
    ("2026-09-29 07:00:11 +0000 UTC", 0),
])
def test_ulamki_sekundy_dopelniane_zerami(text, mikrosekundy):
    assert parse_time(text).microsecond == mikrosekundy


@pytest.mark.parametrize("text", ["", "   ", "wczoraj", None, 17])
def test_niepoprawny_czas_daje_none(text):
    assert parse_time(text) is None


def test_brak_czasu_w_kopercie_bierze_czas_odbioru():
    """time_utc missing is not a reason to drop a position - the tick's clock is close enough."""
    wiadomosc = {"MessageType": "PositionReport", "MetaData": {"MMSI": 111},
                 "Message": {"PositionReport": {"UserID": 261009000, "Latitude": 54.5, "Longitude": 18.5}}}
    assert parse_message(wiadomosc, NOW).ts == NOW


@pytest.mark.parametrize("wiadomosc", [None, "tekst", {}, {"MessageType": "PositionReport"},
                                       {"MessageType": "PositionReport", "Message": {}},
                                       {"MessageType": "PositionReport", "Message": {"PositionReport": {}}}])
def test_smieci_nie_wywracaja_parsera(wiadomosc):
    assert parse_message(wiadomosc, NOW) is None


# --- bufor ------------------------------------------------------------------

def test_ta_sama_pozycja_zapisywana_raz():
    """D4 looks for AIS going quiet. Re-emitting the last known fix every tick means it never can.

    The database would keep growing fresh rows for a hull nobody is hearing, and the silence the
    detector exists to find would be papered over by the ingestion itself.
    """
    buffer = wypelniony_bufor()
    assert len(buffer.drain(NOW)) == 4
    assert buffer.drain(NOW) == []


def test_nowsza_pozycja_po_oproznieniu_wychodzi():
    buffer = wypelniony_bufor()
    buffer.drain(NOW)
    buffer.accept({"MessageType": "PositionReport",
                   "MetaData": {"MMSI": 261009000, "time_utc": "2026-09-29 07:00:59.000000000 +0000 UTC"},
                   "Message": {"PositionReport": {"UserID": 261009000, "Latitude": 54.53,
                                                  "Longitude": 18.57, "Sog": 11.6, "Cog": 88.0}}}, NOW)
    nowe = buffer.drain(NOW)
    assert [s["mmsi"] for s in nowe] == ["261009000"]
    assert nowe[0]["lat"] == 54.53


def test_przestarzale_pozycje_znikaja_z_bufora():
    """Older than MAX_POSITION_AGE is not a current position; a stopped stream must empty out."""
    buffer = wypelniony_bufor()
    pozniej = NOW + aisstream.MAX_POSITION_AGE + timedelta(minutes=1)
    assert buffer.drain(pozniej) == []
    assert len(buffer) == 0


# --- deduplikacja dwoch zrodel ----------------------------------------------

def test_digitraffic_wygrywa_gdy_oba_zrodla_slysza_ten_sam_kadlub():
    """Measured overlap: 11 of 886 live Digitraffic hulls sat inside the subscribed box (1.24%)."""
    ships = wypelniony_bufor().drain(NOW)
    kept, dropped = drop_covered(ships, {"230982000"})       # prom w Zatoce Finskiej
    assert [s["mmsi"] for s in dropped] == ["230982000"]
    assert "230982000" not in {s["mmsi"] for s in kept}
    assert len(kept) == 3


def test_poludniowe_kadluby_przechodza_bo_digitraffic_ich_nie_ma():
    ships = wypelniony_bufor().drain(NOW)
    kept, dropped = drop_covered(ships, set())
    assert dropped == [] and len(kept) == 4


def test_okno_pierwszenstwa_ma_pomiar_za_soba():
    """15 min covers 99.12% of consecutive Digitraffic fixes per hull (41 013 gaps, 12 h, 2026-09-29).

    6 min would cover 94.73% and let the crowd source in on every twentieth ship that Fintraffic is
    still tracking; 30 min adds only 0.54 pp and doubles how long a hull that really left Finnish
    coverage stays suppressed.
    """
    assert aisstream.PRIMARY_WINS_WINDOW == timedelta(minutes=15)


# --- czytnik ----------------------------------------------------------------

class FakeSocket:
    """Stands in for WebSocket: hands out recorded lines, then whatever the scenario says."""

    def __init__(self, lines, koniec=None):
        self.sent: list[str] = []
        self._lines = list(lines)
        self._koniec = koniec
        self.closed = False

    def send_text(self, text):
        self.sent.append(text)

    def recv_text(self):
        if self._lines:
            return self._lines.pop(0)
        if self._koniec is not None:
            raise self._koniec
        return None

    def close(self):
        self.closed = True


def test_czytnik_zamienia_nagrana_probke_na_wiersze():
    linie = SAMPLE.read_text(encoding="utf-8").splitlines()
    socket = FakeSocket(linie)
    reader = AisStreamReader("KLUCZ", connect=lambda *a, **k: socket, clock=lambda: NOW)
    reader.run_once()
    assert json.loads(socket.sent[0])["APIKey"] == "KLUCZ"
    assert socket.closed
    assert len(reader.drain(NOW)) == 4


def test_czytnik_wysyla_subskrypcje_zanim_cokolwiek_przeczyta():
    """AISStream drops the connection if the subscription does not arrive within three seconds."""
    kolejnosc = []
    socket = FakeSocket([])
    socket.send_text = lambda t: kolejnosc.append("subskrypcja")
    socket.recv_text = lambda: kolejnosc.append("odczyt") or None
    reader = AisStreamReader("KLUCZ", connect=lambda *a, **k: socket, clock=lambda: NOW)
    reader.run_once()
    assert kolejnosc[:2] == ["subskrypcja", "odczyt"]


def test_zly_klucz_jest_bledem_a_nie_pustym_morzem():
    """AISStream answers a bad key with one {"error": ...} frame and then says nothing.

    Swallowed, that is indistinguishable from an empty sea - and an empty southern Baltic is exactly
    the bug this whole source exists to fix, so it must never be the silent outcome.
    """
    socket = FakeSocket(['{"error":"Invalid APIKey"}'])
    reader = AisStreamReader("ZLY", connect=lambda *a, **k: socket, clock=lambda: NOW)
    with pytest.raises(WebSocketError, match="Invalid APIKey"):
        reader.run_once()
    assert reader.last_error == "Invalid APIKey"


def test_nie_json_nie_przerywa_sesji():
    """A proxy error page in the middle of the stream costs one message, not the connection."""
    pierwsza = SAMPLE.read_text(encoding="utf-8").splitlines()[0]
    socket = FakeSocket(["<html>503 Service Unavailable</html>", pierwsza])
    reader = AisStreamReader("KLUCZ", connect=lambda *a, **k: socket, clock=lambda: NOW)
    reader.run_once()
    assert reader.last_error.startswith("nie-JSON")
    assert len(reader.drain(NOW)) == 1


def test_caly_lancuch_przez_prawdziwe_gniazdo(tmp_path):
    """The real thread, the real WebSocket, the real frames - only aisstream.io is replaced.

    Every other test here cuts the socket out to keep the parser honest. This one puts it back: a
    loopback server (test_websocket.Serwer, whose framing is written independently of the client)
    replays the recorded sample, and what comes out is the rows the loop would write. Without this,
    "tested offline" would mean "tested against my own mocks", and the handshake, the subscription
    timing and the frame codec would first be exercised on the day a key appears.
    """
    from test_websocket import Serwer

    linie = SAMPLE.read_text(encoding="utf-8").splitlines()

    def scenario(s):
        s.read_frame()                       # subskrypcja
        for line in linie:
            s.send_text(line)
        s.send_frame(0x8, b"\x03\xe8")       # 1000, zamkniecie po stronie serwera

    serwer = Serwer(scenario)
    reader = AisStreamReader("KLUCZ", url=serwer.url, clock=lambda: NOW)
    reader.run_once()
    serwer.join()

    wyslane = json.loads(serwer.received[0][1].decode())
    assert wyslane["APIKey"] == "KLUCZ"
    assert wyslane["BoundingBoxes"] == [[[53.5, 9.0], [58.5, 24.0]]]
    ships = reader.drain(NOW)
    assert sorted(s["mmsi"] for s in ships) == ["219018842", "230982000", "261009000", "273451020"]
    assert reader.connections == 1


def test_czytnik_bez_klucza_nie_powstaje():
    with pytest.raises(ValueError, match="AISSTREAM_API_KEY"):
        AisStreamReader("")


def test_brak_klucza_w_srodowisku_to_stan_normalny():
    """No key is how this repository runs today; it must log, not crash the detector loop."""
    assert reader_from_env({}) is None
    assert reader_from_env({"AISSTREAM_API_KEY": "   "}) is None
