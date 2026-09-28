from datetime import datetime, timedelta, timezone

from wachta_detectors.anchor import ShipFix
from wachta_detectors.gaps import GapRules, find_gaps, impossible, suspicious

T0 = datetime(2024, 12, 25, 6, 0, tzinfo=timezone.utc)


def fix(mmsi: str, minutes: float, lat: float = 59.90, lon: float = 26.00,
        sog: float | None = 10.0, name: str | None = None) -> ShipFix:
    return ShipFix(mmsi=mmsi, ts=T0 + timedelta(minutes=minutes), lat=lat, lon=lon, sog=sog, name=name)


def sailing(mmsi: str, start: float, stop: float, step: float = 5.0,
            lat: float = 59.90, lon: float = 26.00, sog: float | None = 10.0) -> list[ShipFix]:
    """A ship reporting normally every few minutes, drifting slowly east."""
    out, minute = [], start
    while minute <= stop:
        out.append(fix(mmsi, minute, lat, lon + (minute - start) * 0.002, sog))
        minute += step
    return out


def crowd(count: int = 5, start: float = 0.0, stop: float = 240.0) -> list[ShipFix]:
    """Other traffic in the same square: the witnesses that prove the receiver was awake."""
    out = []
    for i in range(count):
        out += sailing(f"crowd{i}", start, stop, lat=59.90 + i * 0.01, lon=26.01)
    return out


def test_ship_silent_among_witnesses_is_flagged():
    track = sailing("111", 0, 30) + sailing("111", 150, 180, lon=26.30)
    alerts = suspicious(find_gaps(track + crowd()))
    assert len(alerts) == 1
    assert alerts[0].mmsi == "111"
    assert alerts[0].listeners >= 3
    assert alerts[0].duration == timedelta(minutes=120)


def test_silence_with_nobody_around_is_not_evidence():
    track = sailing("111", 0, 30) + sailing("111", 150, 180, lon=26.30)
    alerts = find_gaps(track)
    assert [a.verdict for a in alerts] == ["brak swiadkow - luka w zasiegu"]
    assert suspicious(alerts) == []


def test_whole_square_going_quiet_is_a_station_outage():
    # Piec statkow milknie w tej samej kratce w tej samej chwili - to nie piec decyzji zalog.
    fixes = []
    for i in range(5):
        fixes += sailing(f"s{i}", 0, 30, lat=59.90 + i * 0.001)
        fixes += sailing(f"s{i}", 150, 180, lat=59.90 + i * 0.001, lon=26.30)
    alerts = find_gaps(fixes)
    assert alerts, "zaniki powinny zostac znalezione, tylko inaczej ocenione"
    assert all(a.verdict == "prawdopodobna awaria odbioru" for a in alerts)
    assert suspicious(alerts) == []


def test_moored_ship_is_not_a_case():
    track = sailing("111", 0, 30, sog=0.1) + sailing("111", 150, 180, lon=26.30, sog=0.1)
    assert find_gaps(track + crowd()) == []


def test_short_break_in_reporting_is_normal():
    track = sailing("111", 0, 30) + sailing("111", 60, 90, lon=26.10)
    assert find_gaps(track + crowd()) == []


def test_gap_longer_than_the_window_is_end_of_voyage_not_an_episode():
    track = sailing("111", 0, 30) + sailing("111", 60 * 20, 60 * 20 + 30, lon=27.0)
    assert find_gaps(track + crowd(stop=60 * 21)) == []


def test_ship_reappearing_in_the_same_spot_is_ignored():
    # Nie ruszyl sie, wiec albo stal, albo to blad odbioru - nie ma czego tlumaczyc.
    track = [fix("111", 0), fix("111", 30), fix("111", 150), fix("111", 180)]
    assert [a for a in find_gaps(track + crowd()) if a.mmsi == "111"] == []


def test_implied_speed_shows_how_fast_it_must_have_sailed():
    track = sailing("111", 0, 30) + sailing("111", 90, 120, lon=27.00)
    alert = suspicious(find_gaps(track + crowd()))[0]
    assert alert.shift_km > 50
    assert alert.implied_kt > 25      # szybciej, niz plynie tankowiec: cos tu nie gra


def test_witnesses_must_be_in_the_same_square():
    # Ruch o pol stopnia dalej to inna stacja brzegowa - nie swiadczy o tym, czego tam slychac.
    track = sailing("111", 0, 30) + sailing("111", 150, 180, lon=26.30)
    far = []
    for i in range(5):
        far += sailing(f"far{i}", 0, 240, lat=59.90, lon=29.00 + i * 0.01)
    assert suspicious(find_gaps(track + far)) == []


def test_missing_speed_does_not_hide_a_gap():
    track = sailing("111", 0, 30, sog=None) + sailing("111", 150, 180, lon=26.30, sog=None)
    assert len(suspicious(find_gaps(track + crowd()))) == 1


def test_name_is_carried_from_either_side():
    track = sailing("111", 0, 30) + [fix("111", 150, lon=26.30, name="EAGLE S"),
                                     fix("111", 155, lon=26.31, name="EAGLE S")]
    assert suspicious(find_gaps(track + crowd()))[0].name == "EAGLE S"


def test_rules_can_be_tightened():
    track = sailing("111", 0, 30) + sailing("111", 150, 180, lon=26.30)
    strict = GapRules(min_listeners=99)
    assert suspicious(find_gaps(track + crowd(), strict)) == []


def test_empty_input_is_safe():
    assert find_gaps([]) == []
    assert suspicious([]) == []


def test_two_gaps_of_one_ship_are_both_reported():
    track = (sailing("111", 0, 30) + sailing("111", 150, 180, lon=26.30)
             + sailing("111", 300, 330, lon=26.60))
    assert len(suspicious(find_gaps(track + crowd(stop=400)))) == 2


def test_flagged_gaps_come_first():
    quiet = sailing("222", 0, 30, lat=70.0, lon=5.0) + sailing("222", 150, 180, lat=70.0, lon=5.3)
    loud = sailing("111", 0, 30) + sailing("111", 150, 180, lon=26.30)
    alerts = find_gaps(quiet + loud + crowd())
    assert alerts[0].verdict == "cisza przy dzialajacym odbiorze"


def test_ship_that_barely_moved_was_parked_not_dark():
    # 2 km w dwie godziny to postoj przy nabrzezu, nawet jesli przed cisza plynal.
    track = sailing("111", 0, 30) + [fix("111", 150, lon=26.09), fix("111", 180, lon=26.09)]
    alerts = [a for a in find_gaps(track + crowd()) if a.mmsi == "111"]
    assert alerts and alerts[0].motion == "statek praktycznie stal"
    assert suspicious(alerts) == []


def test_impossible_speed_is_reported_separately():
    # 400 km w godzine: zaden kadlub tego nie zrobil, wiec to blad pozycji albo dwa statki
    # pod jednym numerem MMSI - warto przeczytac, ale to nie jest gaszenie transpondera.
    track = sailing("111", 0, 30) + sailing("111", 120, 150, lon=32.00)
    alerts = [a for a in find_gaps(track + crowd()) if a.mmsi == "111"]
    assert alerts and alerts[0].implied_kt > 30
    assert impossible(alerts) == alerts
    assert suspicious(alerts) == []


def test_plain_sailing_through_the_silence_is_the_case_we_want():
    track = sailing("111", 0, 30) + sailing("111", 150, 180, lon=26.45)
    alert = suspicious(find_gaps(track + crowd()))[0]
    assert alert.motion == "plynal w czasie ciszy"
    assert 2 < alert.implied_kt < 30


def test_station_outage_counts_parked_ships_too():
    """Znalezione w audycie: licznik rownoczesnych zanikow powstawal dopiero z kandydatow.

    Statki stojace pod stacja nie przechodzily filtru ruchu, wiec padajaca stacja cichla "tylko
    jednemu" statkowi - temu plynacemu - i jego cisza dostawala etykiete dzialajacego odbioru.
    """
    fixes = []
    for i in range(5):                      # piec statkow STOJACYCH: nie sa kandydatami...
        fixes += sailing(f"stoi{i}", 0, 30, lat=59.90 + i * 0.001, sog=0.1)
        fixes += sailing(f"stoi{i}", 150, 180, lat=59.90 + i * 0.001, sog=0.1)
    fixes += sailing("111", 0, 30) + sailing("111", 150, 180, lon=26.30)   # ...a ten plynie
    fixes += crowd()

    alerts = [a for a in find_gaps(fixes) if a.mmsi == "111"]
    assert alerts, "zanik plynacego statku ma byc widziany"
    assert alerts[0].simultaneous >= 4
    assert alerts[0].verdict == "prawdopodobna awaria odbioru"
    assert suspicious(alerts) == []
