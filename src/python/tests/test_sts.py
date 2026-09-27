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
