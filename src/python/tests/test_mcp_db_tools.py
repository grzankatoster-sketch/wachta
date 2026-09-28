"""The live-database tools: they must appear only with a database, and never answer without saying when.

Two behaviours here are load-bearing and are tested as such:

  * a missing (or broken, or unreachable) database costs the four live tools and nothing else. The
    server still starts and still serves the snapshots.
  * every live answer carries its own caveat, and that caveat states when the data is from and how
    much of it there is. A stack started ten minutes ago returns almost nothing, and "almost nothing"
    reads like a quiet sky unless the answer says which one it is.

No real database is needed: a recording fake stands in for the connection, which also lets the tests
assert what actually reaches SQL - the arguments must arrive as bound parameters, never as text.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from wachta_detectors.mcp_server import build_from_env
from wachta_detectors.tools import MAX_OKNO_MINUT, MAX_PUNKTOW_TORU, MAX_WIERSZY, build_toolbox

FIXTURES = Path(__file__).resolve().parents[3] / "eval" / "fixtures"
NARZEDZIA_BAZY = {"samoloty_na_zywo", "zaklocenia_gps", "alerty_detektorow", "tor_samolotu"}

TERAZ = datetime(2026, 9, 28, 10, 13, tzinfo=timezone.utc)
STARSZY = TERAZ - timedelta(minutes=9)


class _Kursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeConn:
    """A connection that answers from canned rows and remembers every statement it was given.

    Keyed on a fragment of the normalised SQL rather than the whole query, so the tests do not break
    every time somebody reformats a SELECT.
    """

    def __init__(self, odpowiedzi: dict[str, list[tuple]]):
        self.odpowiedzi = odpowiedzi
        self.log: list[tuple[str, tuple]] = []

    def execute(self, sql, params=None):
        plaskie = " ".join(sql.split())
        self.log.append((plaskie, params))
        for fragment, rows in self.odpowiedzi.items():
            if fragment in plaskie:
                return _Kursor(rows)
        return _Kursor([])

    def __enter__(self):
        return self

    def __exit__(self, *wyjatek):
        return False


PELNA_BAZA = {
    # position_window / live_aircraft
    "count(DISTINCT hex), count(*)": [(994, 24000, STARSZY, TERAZ)],
    "ORDER BY hex, ts DESC": [("4b1815", "SWR123", "A320", False, 55.1, 17.2, 31000, 420.0, 90.0, 9, TERAZ)],
    # jamming
    "count(*), min(hour), max(hour) FROM jamming_cell": [(105, STARSZY, TERAZ)],
    "SELECT hour, h3, n_aircraft, n_degraded FROM jamming_cell": [(TERAZ, "841f42dffffffff", 40, 12)],
    # alerty
    "count(*), min(created_at)": [(3, STARSZY, TERAZ)],
    "SELECT detector, entity_id": [("D1", "4b1815", STARSZY, 55.1, 17.2, 0.8, "new", TERAZ, {"gap_min": 12})],
    # tor
    "count(*), min(ts), max(ts), max(flight)": [(120, STARSZY, TERAZ, "SWR123", "A320", False)],
    "SELECT ts, lat, lon, alt_baro_ft": [(TERAZ, 55.1, 17.2, 31000, 420.0, 90.0, 9, False)],
}

PUSTA_BAZA = {
    "count(DISTINCT hex), count(*)": [(0, 0, None, None)],
    "count(*), min(hour), max(hour) FROM jamming_cell": [(0, None, None)],
    "count(*), min(created_at)": [(0, None, None)],
    "count(*), min(ts), max(ts), max(flight)": [(0, None, None, None, None, None)],
}


def fake_db(odpowiedzi=None):
    """A connection factory like the real one - a fresh (fake) connection per call."""
    polaczenia = []

    def connect():
        conn = FakeConn(PELNA_BAZA if odpowiedzi is None else odpowiedzi)
        polaczenia.append(conn)
        return conn

    connect.polaczenia = polaczenia
    return connect


def wywolaj(nazwa, args=None, odpowiedzi=None):
    db = fake_db(odpowiedzi)
    box = build_toolbox(FIXTURES, db=db)
    return box.call(nazwa, args or {}), db


ARGUMENTY = {"tor_samolotu": {"hex": "4b1815"}}


# --- obecnosc narzedzi ------------------------------------------------------

def test_live_tools_are_absent_without_a_database():
    assert not NARZEDZIA_BAZY & set(build_toolbox(FIXTURES).names())


def test_live_tools_appear_when_a_database_is_given():
    assert NARZEDZIA_BAZY <= set(build_toolbox(FIXTURES, db=fake_db()).names())


def test_snapshot_tools_survive_the_arrival_of_a_database():
    # Tryb na migawkach nie moze zniknac tylko dlatego, ze baza wstala.
    names = set(build_toolbox(FIXTURES, db=fake_db()).names())
    assert {"ciche_statki", "przeladunki", "tozsamosc_statkow", "tory_dyzurne"} <= names


def test_server_starts_without_a_database_at_all():
    # Zachowanie krytyczne: brak WACHTA_DB kosztuje cztery narzedzia, nie serwer.
    box = build_from_env(FIXTURES, {"WACHTA_MCP_NO_SEARCH": "1"})
    assert not NARZEDZIA_BAZY & set(box.names())
    assert "ciche_statki" in box.names()


def test_server_starts_when_the_database_is_unreachable():
    # Port 1 nikt nie slucha - polaczenie odpada od razu, a serwer ma i tak wstac.
    box = build_from_env(FIXTURES, {"WACHTA_MCP_NO_SEARCH": "1",
                                    "WACHTA_DB": "postgresql://postgres:XXXX@127.0.0.1:1/wachta"})
    assert not NARZEDZIA_BAZY & set(box.names())
    assert "ciche_statki" in box.names()


def test_server_starts_when_the_dsn_is_nonsense():
    box = build_from_env(FIXTURES, {"WACHTA_MCP_NO_SEARCH": "1", "WACHTA_DB": "to nie jest dsn"})
    assert not NARZEDZIA_BAZY & set(box.names())


# --- zastrzezenie: z kiedy i ile -------------------------------------------

@pytest.mark.parametrize("nazwa", sorted(NARZEDZIA_BAZY))
def test_every_live_answer_says_when_the_data_is_from_and_how_much(nazwa):
    answer, _ = wywolaj(nazwa, ARGUMENTY.get(nazwa))
    zastrzezenie = answer["zastrzezenie"]
    assert "odczyt" in zastrzezenie
    assert "rekordow" in zastrzezenie
    assert TERAZ.isoformat() in zastrzezenie           # skad i do kiedy siegaja dane
    assert "okno" in zastrzezenie
    assert answer["odczyt"]


@pytest.mark.parametrize("nazwa", sorted(NARZEDZIA_BAZY))
def test_an_empty_window_is_named_as_a_young_stack_not_as_silence(nazwa):
    # To jest cala stawka tego wymagania: model nie moze przeczytac pustej bazy jako "nic sie nie dzieje".
    answer, _ = wywolaj(nazwa, ARGUMENTY.get(nazwa), odpowiedzi=PUSTA_BAZA)
    zastrzezenie = answer["zastrzezenie"]
    assert "nie ma ani jednego rekordu" in zastrzezenie
    assert "NIE ze nic sie nie dzieje" in zastrzezenie
    assert answer["pokazano"] == 0


@pytest.mark.parametrize("nazwa", sorted(NARZEDZIA_BAZY))
def test_live_answers_are_json_serialisable(nazwa):
    # Znaczniki czasu z bazy to datetime; przez stdio ma pojsc JSON, wiec konwersja jest obowiazkowa.
    answer, _ = wywolaj(nazwa, ARGUMENTY.get(nazwa))
    assert json.loads(json.dumps(answer, ensure_ascii=False))["zastrzezenie"]


# --- SQL: parametry, nie sklejanie -----------------------------------------

WSTRZYKNIECIE = "'; DROP TABLE alert; --"


def test_arguments_reach_sql_as_bound_parameters_never_as_text():
    for nazwa, args in (("tor_samolotu", {"hex": WSTRZYKNIECIE}),
                        ("alerty_detektorow", {"detektor": WSTRZYKNIECIE})):
        _, db = wywolaj(nazwa, args)
        zapytania = [zapis for conn in db.polaczenia for zapis in conn.log]
        assert zapytania, f"{nazwa} nie odpytal bazy"
        for sql, params in zapytania:
            assert "DROP TABLE" not in sql, f"{nazwa} skleja argument z zapytaniem"
        assert any(WSTRZYKNIECIE.lower() in str(params).lower() for _, params in zapytania)


def test_the_row_limit_reaches_sql_as_a_number_we_chose():
    _, db = wywolaj("samoloty_na_zywo", {"ile": 100000})
    limity = [params[-1] for sql, params in db.polaczenia[0].log if "LIMIT %s" in sql]
    assert limity == [MAX_WIERSZY]


def test_a_track_has_its_own_higher_but_still_hard_limit():
    _, db = wywolaj("tor_samolotu", {"hex": "4b1815", "ile": 100000})
    limity = [params[-1] for sql, params in db.polaczenia[0].log if "LIMIT %s" in sql]
    assert limity == [MAX_PUNKTOW_TORU]


def test_a_nonsense_limit_falls_back_instead_of_crashing():
    answer, db = wywolaj("samoloty_na_zywo", {"ile": "duzo"})
    limity = [params[-1] for sql, params in db.polaczenia[0].log if "LIMIT %s" in sql]
    assert limity == [10]
    assert answer["zastrzezenie"]


def test_the_window_cannot_be_widened_past_retention():
    answer, db = wywolaj("samoloty_na_zywo", {"minuty": 99999999})
    assert answer["okno_minut"] == MAX_OKNO_MINUT
    od = db.polaczenia[0].log[0][1][0]
    assert datetime.now(timezone.utc) - od <= timedelta(minutes=MAX_OKNO_MINUT + 1)


def test_a_nonsense_window_falls_back_to_the_default():
    answer, _ = wywolaj("zaklocenia_gps", {"minuty": "godzina"})
    assert answer["okno_minut"] == 60


# --- tresc odpowiedzi -------------------------------------------------------

def test_live_aircraft_reports_the_whole_window_not_just_the_shown_rows():
    # "Pokazano 1" bez "w oknie 994" to zdanie, ktore model przeczyta jako "leci jeden samolot".
    answer, _ = wywolaj("samoloty_na_zywo", {"ile": 1})
    assert answer["samolotow_w_oknie"] == 994
    assert answer["pozycji_w_oknie"] == 24000
    assert answer["pokazano"] == 1


def test_jamming_cells_carry_a_level_and_a_place():
    answer, _ = wywolaj("zaklocenia_gps")
    komorka = answer["komorki"][0]
    assert komorka["poziom"] in {"low", "medium", "high"}
    assert -90 <= komorka["lat"] <= 90 and -180 <= komorka["lon"] <= 180
    assert komorka["samolotow"] == 40 and komorka["z_gorszym_gps"] == 12


def test_alerts_can_be_narrowed_to_one_detector():
    _, db = wywolaj("alerty_detektorow", {"detektor": "D1"})
    assert all("D1" in str(params) for _, params in db.polaczenia[0].log)


def test_an_empty_detector_filter_means_all_detectors():
    answer, _ = wywolaj("alerty_detektorow", {"detektor": "  "})
    assert answer["detektor"] is None


def test_a_track_without_a_hex_is_refused():
    box = build_toolbox(FIXTURES, db=fake_db())
    with pytest.raises(ValueError):
        box.call("tor_samolotu", {})


def test_a_hex_is_normalised_before_it_reaches_the_query():
    # Baza trzyma adresy malymi literami; model pisze je roznie i nie powinien dostawac pustego toru.
    _, db = wywolaj("tor_samolotu", {"hex": "  4B1815 "})
    assert all(params[0] == "4b1815" for _, params in db.polaczenia[0].log)
