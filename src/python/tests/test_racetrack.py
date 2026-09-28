from datetime import datetime, timedelta, timezone
from math import cos, radians, sin
from random import Random
from statistics import median
from time import perf_counter

from wachta_detectors.geo import haversine_km
from wachta_detectors.racetrack import (
    LoiterRules,
    TracePoint,
    _stable_segments,
    angle_diff,
    axis_deg,
    bearing_deg,
    classify,
    find_loiters,
)

T0 = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
KM_PER_DEG = 111.0


def at(minutes: float, lat: float, lon: float, alt: float | None = 25000.0) -> TracePoint:
    return TracePoint(t=T0 + timedelta(minutes=minutes), lat=lat, lon=lon, alt_ft=alt)


def racetrack_track(legs: int = 6, leg_km: float = 60.0, alt: float = 25000.0,
                    lat0: float = 57.0, lon0: float = 21.0, per_leg_min: float = 12.0,
                    steps: int = 12) -> list[TracePoint]:
    """A north-south racetrack: straight legs with a turn at each end, one altitude."""
    points, minute = [], 0.0
    lat = lat0
    for leg in range(legs):
        direction = 1 if leg % 2 == 0 else -1
        for step in range(steps):
            frac = step / steps
            points.append(at(minute + per_leg_min * frac, lat + direction * frac * leg_km / KM_PER_DEG, lon0, alt))
        lat += direction * leg_km / KM_PER_DEG
        minute += per_leg_min
    points.append(at(minute, lat, lon0, alt))
    return points


def orbit_track(turns: float = 3.0, radius_km: float = 20.0, minutes: float = 60.0,
                lat0: float = 57.0, lon0: float = 21.0, steps: int = 90) -> list[TracePoint]:
    """A circle flown several times over in one direction - a holding pattern, not a racetrack."""
    points = []
    for i in range(steps + 1):
        angle = radians(360.0 * turns * i / steps)
        points.append(at(minutes * i / steps,
                         lat0 + radius_km * cos(angle) / KM_PER_DEG,
                         lon0 + radius_km * sin(angle) / (KM_PER_DEG * cos(radians(lat0)))))
    return points


def transit_track(km: float = 900.0, minutes: float = 80.0, steps: int = 60) -> list[TracePoint]:
    """A straight flight from A to B: the ordinary case that must never be flagged."""
    return [at(minutes * i / steps, 50.0 + km * i / steps / KM_PER_DEG, 10.0) for i in range(steps + 1)]


def right_hand_racetrack(laps: int = 3, leg_km: float = 70.0, turn_radius_km: float = 12.0,
                         lat0: float = 57.0, lon0: float = 21.0) -> list[TracePoint]:
    """The shape actually flown: straight legs joined by 180 degree turns, always to the right.

    Every lap adds a full 360 degrees of rotation, exactly like a circle does, so net rotation cannot
    be what separates the two shapes - only the straight legs can.
    """
    lon_km = KM_PER_DEG * cos(radians(lat0))
    points, minute = [], 0.0
    y = 0.0
    for lap in range(laps):
        for direction, x_turn in ((1, 0.0), (-1, 2 * turn_radius_km)):
            for step in range(14):          # noga prosto
                minute += 1.4
                points.append(at(minute, lat0 + (y + direction * leg_km * step / 14) / KM_PER_DEG,
                                 lon0 + x_turn / lon_km))
            y += direction * leg_km
            for step in range(9):           # zakret 180 stopni w prawo
                angle = radians(180.0 * step / 9)
                minute += 0.9
                cx = x_turn + (turn_radius_km if direction > 0 else -turn_radius_km)
                points.append(at(minute,
                                 lat0 + (y + direction * turn_radius_km * sin(angle)) / KM_PER_DEG,
                                 lon0 + (cx - direction * turn_radius_km * cos(angle)) / lon_km))
    return points


def test_bearing_north_and_east():
    assert bearing_deg(50.0, 20.0, 51.0, 20.0) == 0.0
    assert round(bearing_deg(50.0, 20.0, 50.0, 21.0)) == 90


def test_angle_diff_wraps_the_short_way():
    assert angle_diff(350.0, 10.0) == 20.0
    assert angle_diff(10.0, 350.0) == -20.0


def test_axis_treats_opposite_headings_as_one_line():
    # Nogi toru polnoc-poludnie: 0 i 180 stopni to ta sama os, srednia katow dalaby bezsens.
    assert axis_deg([0.0, 180.0, 2.0, 178.0]) is not None
    assert round(axis_deg([0.0, 180.0, 2.0, 178.0])) % 180 == 0


def test_racetrack_is_recognised():
    found = find_loiters(racetrack_track())
    assert len(found) == 1
    assert found[0].kind == "tor wyscigowy"
    assert found[0].reversals >= 3
    assert found[0].axis_deg is not None


def test_orbit_is_not_called_a_racetrack():
    found = find_loiters(orbit_track())
    assert [f.kind for f in found] == ["krazenie"]
    assert found[0].axis_deg is None
    assert abs(found[0].turn_deg) >= 720


def test_straight_transit_is_not_a_pattern():
    assert find_loiters(transit_track()) == []


def test_single_u_turn_is_not_enough():
    # Dwie nogi, jeden zawrot - tyle robi kazdy samolot zawracajacy do bazy.
    assert find_loiters(racetrack_track(legs=2, per_leg_min=25.0)) == []


def test_pattern_that_drifts_across_the_map_is_rejected():
    # Ten sam ksztalt, ale kazda noga przesunieta na wschod: to przeszukiwanie terenu, nie dyzur.
    points, minute, lat, lon = [], 0.0, 57.0, 21.0
    for leg in range(6):
        direction = 1 if leg % 2 == 0 else -1
        for step in range(12):
            frac = step / 12
            points.append(at(minute + 12 * frac, lat + direction * frac * 60 / KM_PER_DEG, lon))
            lon += 0.6
        lat += direction * 60 / KM_PER_DEG
        minute += 12.0
    assert all(f.radius_km <= LoiterRules().max_radius_km for f in find_loiters(points))


def test_climb_through_the_pattern_breaks_it():
    points = racetrack_track()
    climbing = [TracePoint(p.t, p.lat, p.lon, 20000.0 + i * 120) for i, p in enumerate(points)]
    assert find_loiters(climbing) == []


def test_low_circuit_over_an_airfield_is_not_a_station():
    assert find_loiters(racetrack_track(alt=3000.0)) == []


def test_short_pattern_is_below_the_duration_rule():
    assert find_loiters(racetrack_track(legs=4, per_leg_min=4.0)) == []
    assert find_loiters(racetrack_track(legs=4, per_leg_min=4.0),
                        ) == []


def test_relaxed_rules_accept_a_short_pattern():
    rules = LoiterRules(min_duration=timedelta(minutes=10), min_points=10)
    found = find_loiters(racetrack_track(legs=4, per_leg_min=4.0), rules)
    assert [f.kind for f in found] == ["tor wyscigowy"]


def test_missing_altitude_does_not_block_the_shape():
    points = [TracePoint(p.t, p.lat, p.lon, None) for p in racetrack_track()]
    found = find_loiters(points)
    assert [f.kind for f in found] == ["tor wyscigowy"]
    assert found[0].alt_ft is None


def test_points_out_of_order_are_sorted_first():
    points = racetrack_track()
    assert find_loiters(list(reversed(points))) == find_loiters(points)


def test_empty_and_tiny_tracks_are_safe():
    assert find_loiters([]) == []
    assert find_loiters([at(0, 57.0, 21.0), at(5, 57.1, 21.0)]) == []
    assert classify([]) is None


def test_reported_centre_sits_inside_the_pattern():
    found = find_loiters(racetrack_track())[0]
    assert 56.9 < found.centre_lat < 58.6
    assert abs(found.centre_lon - 21.0) < 0.2
    assert found.radius_km > 0


def test_right_hand_racetrack_is_not_mistaken_for_an_orbit():
    found = find_loiters(right_hand_racetrack())
    assert [f.kind for f in found] == ["tor wyscigowy"]
    assert abs(found[0].turn_deg) >= 720      # obraca sie tyle co okrag...
    assert found[0].longest_leg_km >= 25      # ...ale ma proste nogi, ktorych okrag nie ma


def test_a_perfectly_even_circle_is_still_an_orbit():
    """Znalezione w audycie: brak dominujacej osi konczyl analize przed sprawdzeniem krazenia.

    Rownomierny rozklad kierunkow to wlasnie pelna orbita, wiec najczystszy okrag byl jedynym
    ksztaltem, ktorego detektor nie widzial. Os jest potrzebna do toru, nie do krazenia.
    """
    found = find_loiters(orbit_track(turns=4.0, radius_km=18.0, minutes=75, steps=144))
    assert [f.kind for f in found] == ["krazenie"]
    assert found[0].axis_deg is None


# --- Straznik optymalizacji _stable_segments -------------------------------------------------
#
# Stara wersja liczyla srodek, promien i statystyki wysokosci od nowa dla kazdego kandydata na
# koniec odcinka, czyli kwadratowo. Nowa liczy je przyrostowo. Ponizsza implementacja odwzorowuje
# ta stara, naiwna - jest wzorcem, z ktorym musi zgadzac sie co do bitu, bo optymalizacja, ktora
# zmienia wynik detektora, jest regresja, a nie optymalizacja.


def naive_fits_box(points: list[TracePoint], rules: LoiterRules) -> bool:
    lat = sum(p.lat for p in points) / len(points)
    lon = sum(p.lon for p in points) / len(points)
    if max(haversine_km(lat, lon, p.lat, p.lon) for p in points) > rules.max_radius_km:
        return False
    alts = [p.alt_ft for p in points if p.alt_ft is not None]
    if not alts:
        return True
    return max(alts) - min(alts) <= rules.max_alt_spread_ft and median(alts) >= rules.min_alt_ft


def naive_stable_segments(points: list[TracePoint], rules: LoiterRules) -> list[list[TracePoint]]:
    segments: list[list[TracePoint]] = []
    start = 0
    while start < len(points):
        end = start
        for j in range(start + rules.min_points, len(points) + 1):
            if not naive_fits_box(points[start:j], rules):
                break
            end = j
        if end > start:
            segments.append(points[start:end])
            start = end
        else:
            start += 1
    return segments


def naive_find_loiters(points: list[TracePoint], rules: LoiterRules = LoiterRules()) -> list:
    ordered = sorted(points, key=lambda p: p.t)
    found = [classify(segment, rules) for segment in naive_stable_segments(ordered, rules)]
    return [loiter for loiter in found if loiter is not None]


def gap_track() -> list[TracePoint]:
    """A station, a long transit away, then a second station: two patterns with a break between."""
    points = racetrack_track(legs=4, leg_km=55.0, lat0=57.0, lon0=21.0)
    minute = points[-1].t.minute + 60 * points[-1].t.hour
    for step in range(40):                    # przelot 900 km na wschod, poza pudelko
        points.append(at(minute + step * 2.0, 58.0, 21.0 + step * 0.4))
    minute += 80.0
    for p in racetrack_track(legs=4, leg_km=55.0, lat0=52.0, lon0=37.0):
        points.append(at(minute + (p.t - T0).total_seconds() / 60.0, p.lat, p.lon, p.alt_ft))
    return points


def widening_orbit() -> list[TracePoint]:
    """A circle whose radius grows straight through the 90 km limit.

    The radius is the one statistic that cannot be accumulated, so it is bracketed and only measured
    in full when the limit falls between the brackets. This track keeps landing in that band, so it
    is the case where the new code has to fall back and must still answer exactly as the old one.
    """
    points = []
    for i in range(300):
        radius = 40.0 + 0.25 * i           # 40 km na starcie, 115 km na koncu - prog 90 km w srodku
        angle = radians(360.0 * 10 * i / 300)
        points.append(at(i * 0.75,
                         57.0 + radius * cos(angle) / KM_PER_DEG,
                         21.0 + radius * sin(angle) / (KM_PER_DEG * cos(radians(57.0)))))
    return points


def long_racetrack(points_count: int = 900, leg_km: float = 60.0) -> list[TracePoint]:
    """The size adsb.lol actually returns: hundreds to a few thousand points on one station."""
    steps_per_leg = 40
    track = []
    for i in range(points_count):
        leg, frac = divmod(i, steps_per_leg)
        frac /= steps_per_leg
        direction = 1 if leg % 2 == 0 else -1
        base = 57.0 if direction > 0 else 57.0 + leg_km / KM_PER_DEG
        track.append(at(240.0 * i / points_count, base + direction * frac * leg_km / KM_PER_DEG,
                        21.0, 25000.0))
    return track


CASES = {
    "transit": transit_track(),
    "racetrack": racetrack_track(),
    "orbit": orbit_track(),
    "even circle": orbit_track(turns=4.0, radius_km=18.0, minutes=75, steps=144),
    "right hand racetrack": right_hand_racetrack(),
    "single u turn": racetrack_track(legs=2, per_leg_min=25.0),
    "no altitude": [TracePoint(p.t, p.lat, p.lon, None) for p in racetrack_track()],
    "climbing": [TracePoint(p.t, p.lat, p.lon, 20000.0 + i * 120)
                 for i, p in enumerate(racetrack_track())],
    "low circuit": racetrack_track(alt=3000.0),
    "gap": gap_track(),
    "widening orbit": widening_orbit(),
    "long racetrack": long_racetrack(),
}


def test_incremental_box_segments_exactly_like_the_naive_scan():
    rules = LoiterRules()
    for name, track in CASES.items():
        ordered = sorted(track, key=lambda p: p.t)
        fast = [[(p.t, p.lat, p.lon) for p in s] for s in _stable_segments(ordered, rules)]
        slow = [[(p.t, p.lat, p.lon) for p in s] for s in naive_stable_segments(ordered, rules)]
        assert fast == slow, f"inny podzial na odcinki: {name}"


def test_incremental_box_gives_identical_loiters():
    for name, track in CASES.items():
        assert find_loiters(track) == naive_find_loiters(track), f"inny wynik detektora: {name}"


def test_incremental_box_matches_under_relaxed_rules():
    # Inne progi przesuwaja granice pudelka, wiec widelki promienia trafiaja w inne miejsca.
    rules = LoiterRules(min_duration=timedelta(minutes=10), min_points=10, max_radius_km=25.0)
    for name, track in CASES.items():
        assert find_loiters(track, rules) == naive_find_loiters(track, rules), f"inny wynik: {name}"


def test_long_track_is_not_quadratic():
    """3000 points took over three seconds before the box statistics were made incremental."""
    track = long_racetrack(3000)
    started = perf_counter()
    found = find_loiters(track)
    elapsed = perf_counter() - started
    assert [f.kind for f in found] == ["tor wyscigowy"]
    assert elapsed < 2.0, f"find_loiters na 3000 punktach zajelo {elapsed:.2f} s"


def test_incremental_box_matches_the_naive_scan_on_random_tracks():
    """Random walks with a fixed seed: the curated shapes cannot cover every way brackets can meet."""
    rng = Random(7)
    for trial in range(80):
        lat, lon = rng.uniform(40.0, 65.0), rng.uniform(-5.0, 40.0)
        alt = rng.choice([None, rng.uniform(5000.0, 38000.0)])
        track, minute = [], 0.0
        for _ in range(rng.randint(0, 160)):
            minute += rng.uniform(0.2, 3.0)
            lat += rng.gauss(0.0, rng.choice([0.002, 0.02, 0.2]))
            lon += rng.gauss(0.0, rng.choice([0.002, 0.02, 0.2]))
            track.append(at(minute, lat, lon,
                            None if alt is None else alt + rng.gauss(0.0, rng.choice([5.0, 300.0, 3000.0]))))
        rules = rng.choice([
            LoiterRules(),
            LoiterRules(min_points=8, min_duration=timedelta(minutes=5)),
            # Ciasne pudelko trzyma promien tuz przy progu, wiec widelki rozjezdzaja sie czesto.
            LoiterRules(max_radius_km=15.0, min_points=10, min_duration=timedelta(minutes=5)),
        ])
        assert find_loiters(track, rules) == naive_find_loiters(track, rules), f"proba {trial}"
