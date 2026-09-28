from datetime import datetime, timedelta, timezone

from wachta_detectors.anchor import ShipFix
from wachta_detectors.dark_sts import DarkStsRules, find_dark_sts, pair_up
from wachta_detectors.gaps import find_gaps, suspicious
from wachta_detectors.sts import stationary_periods

T0 = datetime(2024, 12, 25, 8, 0, tzinfo=timezone.utc)


def fix(mmsi: str, minute: float, lat: float, lon: float, sog: float | None = 0.3,
        name: str | None = None) -> ShipFix:
    return ShipFix(mmsi=mmsi, ts=T0 + timedelta(minutes=minute), lat=lat, lon=lon, sog=sog, name=name)


def arrives_and_stops(mmsi: str, lat: float, lon: float, stop_at: int = 0, minutes: int = 120,
                      name: str | None = None) -> list[ShipFix]:
    """A ship that sails in under its own power and then holds position."""
    approach = [fix(mmsi, stop_at - 20 + i, lat - (20 - i) * 0.004, lon, 9.0, name) for i in range(20)]
    return approach + [fix(mmsi, stop_at + m, lat, lon, 0.3, name) for m in range(minutes)]


def goes_dark(mmsi: str, lat: float, lon: float, dark_from: int, dark_to: int,
              name: str | None = None) -> list[ShipFix]:
    """A ship sailing, silent for a while, then reappearing further on."""
    before = [fix(mmsi, dark_from - 20 + i, lat - (20 - i) * 0.004, lon, 9.0, name) for i in range(20)]
    after = [fix(mmsi, dark_to + i, lat + 0.09 + i * 0.004, lon, 9.0, name) for i in range(20)]
    return before + after


def witnesses(count: int = 6, lat: float = 55.00, lon: float = 13.00,
              minutes: int = 200) -> list[ShipFix]:
    """Traffic heard nearby throughout - the proof that the receiver was awake."""
    out = []
    for i in range(count):
        out += [fix(f"w{i}", m, lat + i * 0.004, lon + 0.01, 7.0) for m in range(-30, minutes)]
    return out


def test_lone_ship_next_to_a_silence_is_found():
    fixes = (arrives_and_stops("111", 55.00, 13.00, minutes=150, name="WIDOCZNY")
             + goes_dark("222", 55.01, 13.00, 10, 130, name="ZGASZONY")
             + witnesses())
    found = find_dark_sts(fixes)
    assert len(found) == 1
    assert found[0].visible_mmsi == "111"
    assert found[0].dark_mmsi == "222"
    assert found[0].distance_km < 5
    assert found[0].overlap_min > 60


def test_silence_far_away_is_not_paired():
    fixes = (arrives_and_stops("111", 55.00, 13.00, minutes=150)
             + goes_dark("222", 55.80, 13.00, 10, 130)      # ok. 89 km dalej
             + witnesses() + witnesses(lat=55.80))
    assert find_dark_sts(fixes) == []


def test_silence_at_another_time_is_not_paired():
    fixes = (arrives_and_stops("111", 55.00, 13.00, minutes=60)
             + goes_dark("222", 55.01, 13.00, 200, 320)
             + witnesses(minutes=400))
    assert find_dark_sts(fixes) == []


def test_ship_with_a_visible_partner_belongs_to_D5_not_here():
    # Oba statki nadaja, wiec to zwykle spotkanie - ma je znalezc D5, a nie ten detektor.
    fixes = (arrives_and_stops("111", 55.00, 13.00, minutes=150)
             + arrives_and_stops("333", 55.0027, 13.00, minutes=150)
             + goes_dark("222", 55.01, 13.00, 10, 130)
             + witnesses())
    assert [d.visible_mmsi for d in find_dark_sts(fixes)] == []


def test_a_ship_is_never_paired_with_its_own_silence():
    loiters = stationary_periods(arrives_and_stops("111", 55.00, 13.00, minutes=150) + witnesses())
    fixes = goes_dark("111", 55.01, 13.00, 10, 130) + witnesses()
    gaps = suspicious(find_gaps(fixes))
    assert pair_up([p for p in loiters if p.mmsi == "111"], gaps) == []


def test_brief_overlap_is_not_enough():
    fixes = (arrives_and_stops("111", 55.00, 13.00, minutes=150)
             + goes_dark("222", 55.01, 13.00, 140, 260)     # nachodzi tylko 10 min
             + witnesses(minutes=300))
    assert find_dark_sts(fixes, rules=DarkStsRules(min_overlap=timedelta(minutes=20))) == []


def test_loiter_inside_an_anchorage_is_excluded():
    crowd = []
    for i in range(14):
        crowd += [fix(f"a{i}", m, 55.00 + i * 0.0004, 13.00, 0.1) for m in range(150)]
    fixes = crowd + goes_dark("222", 55.01, 13.00, 10, 130) + witnesses()
    assert find_dark_sts(fixes) == []


def test_ship_that_never_sailed_in_is_excluded():
    # Kuter przy kei stoi tam zawsze; nie przyplynal, wiec nie przyplynal sie z nikim spotkac.
    moored = [fix("111", m, 55.00, 13.00, 0.0) for m in range(150)]
    fixes = moored + goes_dark("222", 55.01, 13.00, 10, 130) + witnesses()
    assert find_dark_sts(fixes) == []


def test_unexplained_silence_only_counts_when_someone_was_listening():
    # Bez swiadkow luka jest zwykla dziura w zasiegu, wiec nie ma czego z czym laczyc.
    fixes = (arrives_and_stops("111", 55.00, 13.00, minutes=150)
             + goes_dark("222", 55.01, 13.00, 10, 130))
    assert find_dark_sts(fixes) == []


def test_empty_input_is_safe():
    assert find_dark_sts([]) == []
    assert pair_up([], []) == []


def test_dark_ship_that_could_not_have_reached_the_loiterer_is_rejected():
    # Zgaszony statek pojawia sie 120 km dalej po 100 min: caly ten czas zszedl na plyniecie,
    # wiec nie bylo kiedy stanac przy kimkolwiek. Bliskosc miejsca zanikniecia nic tu nie zmienia.
    far_away = [fix("222", 110 + i, 56.10 + i * 0.004, 13.00, 9.0, "DALEKI") for i in range(20)]
    fixes = (arrives_and_stops("111", 55.00, 13.00, minutes=150)
             + [fix("222", -10 + i, 54.96 + i * 0.004, 13.00, 9.0, "DALEKI") for i in range(20)]
             + far_away + witnesses())
    assert find_dark_sts(fixes) == []


def test_spare_time_is_what_the_transfer_would_have_had():
    fixes = (arrives_and_stops("111", 55.00, 13.00, minutes=150, name="WIDOCZNY")
             + goes_dark("222", 55.01, 13.00, 10, 130, name="ZGASZONY")
             + witnesses())
    d = find_dark_sts(fixes)[0]
    assert d.detour_km >= d.distance_km
    assert d.spare_min >= 30
    assert d.spare_min < d.gap_min


def test_dark_ship_arriving_after_the_loiter_ended_is_not_a_meeting():
    """Znalezione w audycie: okno brano z calej ciszy, wiec wystarczylo, ze luka ja obejmuje.

    Liczby dobrane tak, zeby trafic dokladnie w te regule, a nie w zapas czasu: droga tam i z
    powrotem (40 km przy 12 w. = 108 min) miesci sie w 400-minutowej ciszy z duzym zapasem, ale
    zgaszony statek dotrze na miejsce dopiero w 54. minucie - a widoczny stoi tylko do 45.
    """
    km20 = 20 / 111.0
    stoi = ([fix("111", -20 + i, 55.00 - (20 - i) * 0.004, 13.00, 9.0, "WIDOCZNY") for i in range(20)]
            + [fix("111", m, 55.00, 13.00, 0.3, "WIDOCZNY") for m in range(45)])
    ciemny = ([fix("222", -10 + i, 55.00 - km20 - (10 - i) * 0.004, 13.00, 9.0, "ZGASZONY") for i in range(10)]
              + [fix("222", 400 + i, 55.00 + km20 + i * 0.004, 13.00, 9.0, "ZGASZONY") for i in range(10)])
    # Swiadkowie musza byc w kratce ZANIKNIECIA, nie tylko przy stojacym statku - inaczej D4 uzna
    # cisze za zwykla dziure w zasiegu i para nie powstanie z zupelnie innego powodu.
    slychac = witnesses(minutes=430) + witnesses(lat=55.00 - km20, minutes=430)
    wszystko = stoi + ciemny + slychac
    assert suspicious(find_gaps(wszystko)), "luka ma byc wykryta - inaczej test nie bada tego, co mial"
    assert [d for d in find_dark_sts(wszystko) if d.visible_mmsi == "111"] == []


def test_a_visible_meeting_in_the_morning_does_not_hide_a_dark_one_at_night():
    # Znalezione w audycie: jedno spotkanie D5 skreslalo numer ze WSZYSTKICH postojow w dobie.
    rano = (arrives_and_stops("111", 55.00, 13.00, stop_at=0, minutes=90, name="WIDOCZNY")
            + arrives_and_stops("333", 55.0027, 13.00, stop_at=0, minutes=90, name="PARTNER"))
    wieczorem = (arrives_and_stops("111", 55.00, 13.00, stop_at=400, minutes=120, name="WIDOCZNY")
                 + goes_dark("222", 55.01, 13.00, 410, 520, name="ZGASZONY"))
    found = find_dark_sts(rano + wieczorem + witnesses(minutes=600))
    assert [(d.visible_mmsi, d.dark_mmsi) for d in found] == [("111", "222")]
