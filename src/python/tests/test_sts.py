from datetime import datetime, timedelta, timezone

from wachta_detectors.anchor import ShipFix
from wachta_detectors.sts import StsRules, anchorages, find_encounters, offshore

T0 = datetime(2024, 12, 25, 8, 0, tzinfo=timezone.utc)
KM_PER_DEG = 111.0


def fix(mmsi: str, minute: float, lat: float, lon: float, sog: float | None = 0.4,
        name: str | None = None) -> ShipFix:
    return ShipFix(mmsi=mmsi, ts=T0 + timedelta(minutes=minute), lat=lat, lon=lon, sog=sog, name=name)


def alongside(mmsi: str, minutes: int, lat: float, lon: float, sog: float | None = 0.4,
              name: str | None = None, start: int = 0, sailed: bool = True) -> list[ShipFix]:
    """A ship holding one position, reporting every minute.

    Unless told otherwise it also sails in beforehand and leaves afterwards, because that is what a
    ship meeting another ship does - and what a boat tied to a quay never does.
    """
    held = [fix(mmsi, m, lat, lon, sog, name) for m in range(start, start + minutes)]
    if not sailed:
        return held
    approach = [fix(mmsi, start - 20 + i, lat - (20 - i) * 0.003, lon, 8.0, name) for i in range(20)]
    leaving = [fix(mmsi, start + minutes + i, lat + i * 0.003, lon, 8.0, name) for i in range(20)]
    return approach + held + leaving


def test_two_ships_side_by_side_for_an_hour_are_found():
    fixes = (alongside("111", 60, 55.00, 13.00, name="ALFA")
             + alongside("222", 60, 55.0027, 13.00, name="BETA"))   # ok. 300 m
    found = offshore(find_encounters(fixes))
    assert len(found) == 1
    assert {found[0].mmsi_a, found[0].mmsi_b} == {"111", "222"}
    assert {found[0].name_a, found[0].name_b} == {"ALFA", "BETA"}
    assert found[0].duration >= timedelta(minutes=30)
    assert found[0].min_separation_km < 0.5


def test_ships_a_few_kilometres_apart_are_not_a_pair():
    fixes = alongside("111", 60, 55.00, 13.00) + alongside("222", 60, 55.03, 13.00)  # 3,3 km
    assert find_encounters(fixes) == []


def test_brief_passing_is_not_a_transfer():
    fixes = alongside("111", 60, 55.00, 13.00) + alongside("222", 10, 55.0027, 13.00)
    assert find_encounters(fixes) == []


def test_ships_under_way_are_not_transferring():
    fixes = (alongside("111", 60, 55.00, 13.00, sog=9.0)
             + alongside("222", 60, 55.0027, 13.00, sog=9.0))
    assert find_encounters(fixes) == []


def test_anchorage_is_derived_from_the_traffic():
    crowd = []
    for i in range(14):
        crowd += alongside(f"a{i}", 30, 55.00 + i * 0.0005, 13.00, sog=0.1, sailed=False)
    found = anchorages(crowd)
    assert found, "kratka z kilkunastoma stojacymi statkami to kotwicowisko"


def test_meeting_inside_an_anchorage_is_marked_not_hidden():
    crowd = []
    for i in range(14):
        crowd += alongside(f"a{i}", 60, 55.00 + i * 0.0005, 13.00, sog=0.1)
    encounters = find_encounters(crowd)
    assert encounters, "spotkania maja byc znalezione..."
    assert all(e.in_anchorage for e in encounters)
    assert offshore(encounters) == []      # ...ale nie maja trafic na liste do czytania


def test_the_same_meeting_out_at_sea_does_show_up():
    far = alongside("111", 60, 57.50, 5.00, name="ALFA") + alongside("222", 60, 57.5027, 5.00, name="BETA")
    assert len(offshore(find_encounters(far))) == 1


def test_pair_split_across_grid_cells_is_still_found():
    # Statki po dwoch stronach granicy kratki: to wlasnie tu polowiczne sasiedztwo gubilo pary.
    rules = StsRules()
    edge_lat = 55.00 - (55.00 % rules.cell_deg)
    fixes = (alongside("999", 60, edge_lat - 0.0015, 13.00)      # nizsza kratka, wyzszy numer
             + alongside("111", 60, edge_lat + 0.0015, 13.00))   # wyzsza kratka, nizszy numer
    assert len(offshore(find_encounters(fixes, rules))) == 1


def test_break_longer_than_the_rule_splits_one_meeting_into_none():
    # Kontakt 20 min, przerwa 30 min, kontakt 20 min: dwa za krotkie spotkania, nie jedno dlugie.
    fixes = (alongside("111", 20, 55.00, 13.00) + alongside("111", 20, 55.00, 13.00, start=50)
             + alongside("222", 20, 55.0027, 13.00) + alongside("222", 20, 55.0027, 13.00, start=50))
    assert find_encounters(fixes) == []


def test_drift_distinguishes_a_standstill_from_a_slow_drift():
    # Oba dryfuja razem, ale przyplynely tu o wlasnych silach - tak jak przy prawdziwym spotkaniu.
    def drifting(mmsi: str, lat0: float) -> list[ShipFix]:
        approach = [fix(mmsi, -20 + i, lat0 - (20 - i) * 0.003, 13.00, 8.0) for i in range(20)]
        return approach + [fix(mmsi, m, lat0 + m * 0.0004, 13.00) for m in range(60)]

    drifting_a = drifting("111", 55.00)
    drifting_b = drifting("222", 55.0027)
    drift = offshore(find_encounters(drifting_a + drifting_b))[0]
    still = offshore(find_encounters(alongside("111", 60, 57.5, 5.0) + alongside("222", 60, 57.5027, 5.0)))[0]
    assert drift.drift_km > 2
    assert still.drift_km < 0.1


def test_three_ships_together_give_three_pairs():
    fixes = (alongside("111", 60, 55.00, 13.00) + alongside("222", 60, 55.0027, 13.00)
             + alongside("333", 60, 55.0054, 13.00))
    pairs = {(e.mmsi_a, e.mmsi_b) for e in offshore(find_encounters(fixes))}
    assert pairs == {("111", "222"), ("222", "333"), ("111", "333")}


def test_missing_speed_does_not_exclude_a_ship():
    fixes = alongside("111", 60, 55.00, 13.00, sog=None) + alongside("222", 60, 55.0027, 13.00, sog=None)
    found = offshore(find_encounters(fixes))
    assert len(found) == 1
    assert found[0].mean_sog is None


def test_empty_input_is_safe():
    assert find_encounters([]) == []
    assert anchorages([]) == set()
    assert offshore([]) == []


def test_offshore_meetings_are_listed_before_anchorage_ones():
    crowd = []
    for i in range(14):
        crowd += alongside(f"a{i}", 60, 55.00 + i * 0.0005, 13.00, sog=0.1)
    sea = alongside("111", 60, 57.50, 5.00) + alongside("222", 60, 57.5027, 5.00)
    assert find_encounters(crowd + sea)[0].in_anchorage is False


def test_two_boats_tied_to_a_quay_all_day_are_not_a_transfer():
    # To bylo 3119 falszywych spotkan na prawdziwej dobie: kutry przy kei, ktore nigdzie nie plynely.
    fixes = (alongside("111", 600, 56.99, 10.31, sog=0.0, name="KUTER A", sailed=False)
             + alongside("222", 600, 56.9903, 10.31, sog=0.0, name="KUTER B", sailed=False))
    found = find_encounters(fixes)
    assert found, "spotkanie jest w danych..."
    assert all(not e.both_under_way for e in found)
    assert offshore(found) == []       # ...ale nie jest przeladunkiem


def test_meeting_lasting_the_whole_day_is_a_berth_not_an_episode():
    fixes = (alongside("111", 60 * 20, 57.5, 5.0, name="ALFA")
             + alongside("222", 60 * 20, 57.5027, 5.0, name="BETA"))
    assert find_encounters(fixes) == []


def test_speed_is_worked_out_from_positions_when_the_field_is_missing():
    # Statek bez pola predkosci, ale przeplynal 20 km w 20 minut - to jest plyniecie.
    def silent(mmsi: str, lat0: float) -> list[ShipFix]:
        approach = [fix(mmsi, -20 + i, lat0 - (20 - i) * 0.003, 13.0, None) for i in range(20)]
        return approach + [fix(mmsi, m, lat0, 13.0, None) for m in range(60)]

    found = offshore(find_encounters(silent("111", 55.0) + silent("222", 55.0027)))
    assert len(found) == 1
    assert found[0].both_under_way


def test_ship_without_a_speed_field_is_judged_by_its_positions():
    # Znalezione w audycie: brak pola SOG znaczyl "wolno", wiec statek pedzacy 21 wezlow przez
    # ciesnine liczyl sie jako stojacy przez ponad godzine - i mogl utworzyc falszywa pare.
    from wachta_detectors.sts import stationary_periods
    pedzi = [ShipFix("219000222", T0 + timedelta(minutes=m), 55.0 + m * 0.006, 13.0, None)
             for m in range(80)]
    assert stationary_periods(pedzi) == []


def test_missing_speed_but_actually_stopped_still_counts():
    stoi = [ShipFix("219000222", T0 + timedelta(minutes=m), 55.0, 13.0, None) for m in range(80)]
    approach = [ShipFix("219000222", T0 + timedelta(minutes=-20 + i), 55.0 - (20 - i) * 0.004, 13.0, 8.0)
                for i in range(20)]
    from wachta_detectors.sts import stationary_periods
    assert len(stationary_periods(approach + stoi)) == 1


def test_pair_is_found_at_high_latitude_where_a_degree_of_longitude_is_short():
    # Znalezione w audycie: zasieg siatki byl staly, wiec na 75 stopniu szerokosci para odlegla
    # o 0,63 km znikala mimo limitu 0,8 km - stopien dlugosci ma tam juz tylko 28,7 km.
    lat = 75.0
    lon_step = 0.63 / (111.0 * __import__("math").cos(__import__("math").radians(lat)))
    fixes = alongside("219000111", 60, lat, 20.0) + alongside("219000222", 60, lat, 20.0 + lon_step)
    found = offshore(find_encounters(fixes))
    assert len(found) == 1
    assert 0.5 < found[0].min_separation_km < 0.8


class TestPostojeNaPelnymTorze:
    """Znalezione w audycie: odcinki postoju budowano z PRZEFILTROWANEGO toru.

    Szybkie pozycje odrzucano przed segmentacja, wiec dowod, ze statek odplynal, znikal razem z
    nimi. Dwa postoje rozdzielone potwierdzonym tranzytem wracaly jako jeden dlugi postoj o srodku
    w punkcie, w ktorym statek nigdy nie stal - a to wlasnie te postoje karmia D5 dark STS.
    """

    @staticmethod
    def postoj(mmsi, od, ile, lat, lon):
        return [fix(mmsi, od + 5 * i, lat, lon, 0.2) for i in range(ile)]

    def dwa_postoje_z_tranzytem(self):
        # 40 minut w miejscu, 6 km tranzytu z pelna predkoscia, 40 minut w nowym miejscu
        tranzyt = [fix("111111111", 40 + 5 * i, 55.0 + 0.027 * i, 18.0, 12.0) for i in (1, 2)]
        return self.postoj("111111111", 0, 9, 55.0, 18.0) + tranzyt + self.postoj("111111111", 52, 9, 55.054, 18.0)

    def test_confirmed_movement_ends_a_stop(self):
        from wachta_detectors.sts import stationary_periods

        postoje = stationary_periods(self.dwa_postoje_z_tranzytem())
        assert len(postoje) == 2, "tranzyt miedzy postojami to koniec postoju, nie jego srodek"
        assert [p.duration for p in postoje] == [timedelta(minutes=40), timedelta(minutes=40)]

    def test_the_centre_is_a_place_the_ship_actually_sat_at(self):
        from wachta_detectors.sts import stationary_periods

        for p in stationary_periods(self.dwa_postoje_z_tranzytem()):
            assert p.lat in (55.0, 55.054), p.lat

    def test_a_stop_that_wanders_too_far_is_not_one_stop(self):
        from wachta_detectors.sts import stationary_periods

        # Wolne raporty bez ani jednej szybkiej pozycji, ale przesuniete lacznie o 12 km: sam czas
        # tego nie rozdzieli, bo zadna przerwa nie przekracza max_gap. Rozdzielic musi odleglosc.
        wleczenie = [fix("222222222", 5 * i, 55.0 + 0.0075 * i, 18.0, 0.4) for i in range(16)]
        dlugi = stationary_periods(wleczenie, StsRules(max_spread_km=100.0))
        assert len(dlugi) == 1 and dlugi[0].duration == timedelta(minutes=75)   # bez limitu: jeden

        postoje = stationary_periods(wleczenie)
        assert len(postoje) < 2 or all(p.duration < timedelta(minutes=75) for p in postoje)
        assert not any(p.duration == timedelta(minutes=75) for p in postoje), \
            "12 km przemieszczenia nie jest jednym postojem"

    def test_movement_ends_a_stop_even_when_the_ship_barely_moved(self):
        from wachta_detectors.sts import stationary_periods

        # Krotki skok o 1,85 km: za blisko, zeby rozdzielil go limit przemieszczenia, i za szybko,
        # zeby rozdzielila go przerwa w raportach. Zostaje jedyny prawdziwy powod - statek plynal.
        skok = [fix("444444444", 40 + 5 * i, 55.0 + 0.00833 * i, 18.0, 8.0) for i in (1, 2)]
        tor = self.postoj("444444444", 0, 9, 55.0, 18.0) + skok + self.postoj("444444444", 52, 9, 55.0166, 18.0)

        postoje = stationary_periods(tor)
        assert len(postoje) == 2
        assert [p.duration for p in postoje] == [timedelta(minutes=40), timedelta(minutes=40)]

    def test_an_undisturbed_stop_is_still_one_stop(self):
        from wachta_detectors.sts import stationary_periods

        [p] = stationary_periods(self.postoj("333333333", 0, 20, 55.0, 18.0))
        assert p.duration == timedelta(minutes=95)
