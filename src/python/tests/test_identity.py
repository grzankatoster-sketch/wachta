from datetime import datetime, timedelta, timezone

from wachta_detectors.anchor import ShipFix
from wachta_detectors.identity import (
    IdentityRules,
    examine,
    find_jumps,
    implied_kt,
    renamed,
    scan,
)

T0 = datetime(2024, 12, 25, 0, 0, tzinfo=timezone.utc)


def fix(mmsi: str, minute: float, lat: float, lon: float, name: str | None = None) -> ShipFix:
    return ShipFix(mmsi=mmsi, ts=T0 + timedelta(minutes=minute), lat=lat, lon=lon, sog=8.0, name=name)


def sailing(mmsi: str, start: int, count: int, lat: float, lon: float,
            name: str | None = None, step: float = 0.004) -> list[ShipFix]:
    """A plausible run: about 8 knots north, one position every two minutes."""
    return [fix(mmsi, start + 2 * i, lat + i * step, lon, name) for i in range(count)]


def test_implied_speed_is_distance_over_time():
    a, b = fix("1", 0, 55.0, 13.0), fix("1", 60, 55.5, 13.0)
    assert 28 < implied_kt(a, b) < 32       # 55,5 km w godzine to ok. 30 wezlow


def test_a_normal_track_says_nothing():
    report = examine(sailing("219000111", 0, 30, 55.0, 13.0))
    assert report.verdict == "spojny"
    assert report.jumps == []


def test_one_wild_fix_is_called_a_bad_point_not_fraud():
    track = sailing("219000111", 0, 15, 55.0, 13.0)
    track.insert(8, fix("219000111", 15, 40.0, 3.0))       # jeden punkt w Hiszpanii
    report = examine(sorted(track, key=lambda f: f.ts))
    assert report.jumps, "skok ma zostac zauwazony"
    assert report.verdict == "bledny punkt"


def test_track_alternating_between_two_areas_is_two_hulls():
    # Ten sam numer melduje sie na przemian pod Bornholmem i pod Gotlandia.
    track = []
    for lap in range(3):
        track += sailing("219000111", lap * 200, 5, 55.0, 13.0)
        track += sailing("219000111", lap * 200 + 100, 5, 57.5, 18.0)
    report = examine(sorted(track, key=lambda f: f.ts))
    assert report.verdict == "dwa kadluby"
    assert len(report.clusters) == 2
    assert report.alternations >= 2


def test_two_areas_but_only_one_crossing_is_not_enough():
    # Statek moze raz przeplynac dlugi odcinek bez meldunku - to jeszcze nie dwa kadluby.
    track = sailing("219000111", 0, 6, 55.0, 13.0) + sailing("219000111", 100, 6, 57.5, 18.0)
    assert examine(sorted(track, key=lambda f: f.ts)).verdict == "bledny punkt"


def test_short_stubs_do_not_count_as_evidence():
    # Dwa pojedyncze punkty daleko od toru to szum odbiornika, nie drugi statek.
    track = sailing("219000111", 0, 20, 55.0, 13.0)
    track.insert(5, fix("219000111", 9, 57.5, 18.0))
    track.insert(14, fix("219000111", 27, 57.5, 18.0))
    report = examine(sorted(track, key=lambda f: f.ts))
    assert report.verdict == "bledny punkt"


def test_clusters_report_where_the_hulls_were():
    track = []
    for lap in range(3):
        track += sailing("219000111", lap * 200, 5, 55.0, 13.0)
        track += sailing("219000111", lap * 200 + 100, 5, 57.5, 18.0)
    clusters = examine(sorted(track, key=lambda f: f.ts)).clusters
    assert {round(c[0]) for c in clusters} == {55, 58}
    assert sum(c[2] for c in clusters) >= 6


def test_jumps_carry_the_numbers_that_justify_them():
    track = sailing("219000111", 0, 5, 55.0, 13.0) + sailing("219000111", 12, 5, 57.5, 18.0)
    jump = find_jumps(sorted(track, key=lambda f: f.ts))[0]
    assert jump.implied_kt > 40
    assert jump.km > 300
    assert jump.minutes > 0


def test_speed_limit_can_be_argued_with():
    track = sailing("219000111", 0, 5, 55.0, 13.0) + sailing("219000111", 60, 5, 55.6, 13.0)
    assert find_jumps(track, IdentityRules(max_hull_kt=5.0))
    assert find_jumps(track, IdentityRules(max_hull_kt=200.0)) == []


def test_scan_puts_the_two_hull_cases_first():
    two = []
    for lap in range(3):
        two += sailing("219000222", lap * 200, 5, 55.0, 13.0)
        two += sailing("219000222", lap * 200 + 100, 5, 57.5, 18.0)
    noisy = sailing("219000111", 0, 15, 54.0, 11.0)
    noisy.insert(8, fix("219000111", 15, 40.0, 3.0))
    found = scan(two + noisy)
    assert found[0].mmsi == "219000222"
    assert found[0].verdict == "dwa kadluby"
    assert {r.mmsi for r in found} == {"219000111", "219000222"}


def test_consistent_ships_are_not_in_the_output():
    assert scan(sailing("219000111", 0, 30, 55.0, 13.0)) == []


def test_one_number_two_names_is_listed_separately():
    track = sailing("219000111", 0, 10, 55.0, 13.0, name="ALFA") + sailing("219000111", 30, 10, 55.1, 13.0, name="BETA")
    found = renamed(track)
    assert [r.mmsi for r in found] == ["219000111"]
    assert found[0].names == ("ALFA", "BETA")


def test_one_name_throughout_is_not_a_rename():
    assert renamed(sailing("219000111", 0, 20, 55.0, 13.0, name="ALFA")) == []


def test_empty_and_single_fix_tracks_are_safe():
    assert scan([]) == []
    assert examine([]).verdict == "spojny"
    assert examine([fix("219000111", 0, 55.0, 13.0)]).verdict == "spojny"


def test_two_distant_fixes_in_the_same_second_are_impossible():
    # Znalezione w audycie: kod zwracal 0 wezlow przy zerowym czasie, zeby nie dzielic przez zero,
    # i tym samym wyrzucal najmocniejszy mozliwy dowod. Kadlub moze byc szybki, ale nie moze byc
    # w dwoch miejscach w tej samej sekundzie.
    track = [fix("219000111", 0, 55.0, 13.0), fix("219000111", 0, 57.5, 18.0),
             fix("219000111", 2, 55.01, 13.0)]
    report = examine(sorted(track, key=lambda f: f.ts))
    assert report.jumps, "sprzecznosc w tej samej sekundzie ma byc widoczna"
    assert report.verdict != "spojny"


def test_same_instant_in_the_same_place_is_only_a_duplicate():
    # Dwa meldunki z tej samej sekundy i tego samego miejsca to powtorzony pakiet, nie dwa statki.
    track = [fix("219000111", 0, 55.0, 13.0), fix("219000111", 0, 55.0, 13.0),
             fix("219000111", 2, 55.004, 13.0)]
    assert examine(track).verdict == "spojny"


def test_rescue_aircraft_is_not_an_impostor_for_flying():
    # 111xxxxxx to w standardzie ITU statek powietrzny SAR. 160 wezlow to jego normalna predkosc.
    from wachta_detectors.identity import mmsi_kind
    assert mmsi_kind("111219515") == "statek powietrzny SAR"
    heli = []
    for lap in range(3):
        heli += sailing("111219515", lap * 60, 5, 55.0, 9.3, step=0.05)
        heli += sailing("111219515", lap * 60 + 30, 5, 56.2, 10.2, step=0.05)
    assert scan(sorted(heli, key=lambda f: f.ts)) == []


def test_reserved_prefixes_are_named_not_guessed():
    from wachta_detectors.identity import mmsi_kind
    assert mmsi_kind("992191234") == "znak nawigacyjny"
    assert mmsi_kind("982191234") == "jednostka pomocnicza"
    assert mmsi_kind("002191234") == "stacja brzegowa"
    assert mmsi_kind("219006091") == "statek"
    assert mmsi_kind("") == "statek"


def test_an_ordinary_ship_number_is_still_judged():
    track = []
    for lap in range(3):
        track += sailing("219006091", lap * 200, 5, 55.0, 13.0)
        track += sailing("219006091", lap * 200 + 100, 5, 57.5, 18.0)
    assert [r.verdict for r in scan(sorted(track, key=lambda f: f.ts))] == ["dwa kadluby"]
