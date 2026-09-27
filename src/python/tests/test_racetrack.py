from datetime import datetime, timedelta, timezone
from math import cos, radians, sin

from wachta_detectors.racetrack import (
    LoiterRules,
    TracePoint,
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
