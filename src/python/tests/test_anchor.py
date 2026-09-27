from datetime import datetime, timedelta, timezone

import pytest

from wachta_detectors.anchor import AnchorRules, ShipFix, bearing_deg, course_spread_deg, find_anchor_drag
from wachta_detectors.infrastructure import Line

T0 = datetime(2026, 9, 26, 20, 0, tzinfo=timezone.utc)
# A cable running north-south at 25E, roughly across the Gulf of Finland.
CABLE = Line("Kabel testowy", "power", ((59.6, 25.0), (60.2, 25.0)))
FAR_AWAY = (59.9, 22.0)  # ~170 km west of the cable


def track(*, n=8, minutes=5, lat=59.9, lon=24.99, sog=3.0, courses=None, mmsi="123456789", name="TESTOWY"):
    """A ship sitting near the cable; `courses` decides whether it holds a heading or wanders."""
    fixes = []
    for i in range(n):
        cog = courses[i % len(courses)] if courses else 90.0
        fixes.append(ShipFix(mmsi=mmsi, ts=T0 + timedelta(minutes=minutes * i), lat=lat, lon=lon,
                             sog=sog, cog=cog, name=name))
    return fixes


WANDERING = [10.0, 70.0, 350.0, 120.0, 40.0, 300.0, 80.0, 20.0]


def test_slow_wandering_ship_over_a_cable_is_a_candidate():
    [alert] = find_anchor_drag(track(courses=WANDERING), [CABLE])
    assert alert.line_name == "Kabel testowy"
    assert alert.duration == timedelta(minutes=35)
    assert alert.min_distance_km < 2.0
    assert alert.mean_sog == 3.0
    assert alert.course_spread_deg > 20
    assert alert.evidence["note"].startswith("Candidate")


def test_ship_holding_its_course_is_not_flagged():
    assert find_anchor_drag(track(courses=[90.0, 92.0, 88.0, 91.0]), [CABLE]) == []


def test_transit_speed_is_not_flagged():
    assert find_anchor_drag(track(sog=12.0, courses=WANDERING), [CABLE]) == []


def test_a_ship_at_a_standstill_is_not_dragging():
    assert find_anchor_drag(track(sog=0.2, courses=WANDERING), [CABLE]) == []


def test_same_behaviour_far_from_any_cable_is_not_flagged():
    assert find_anchor_drag(track(lat=FAR_AWAY[0], lon=FAR_AWAY[1], courses=WANDERING), [CABLE]) == []


def test_too_short_an_episode_is_not_flagged():
    # Five fixes two minutes apart: enough points, but only eight minutes.
    assert find_anchor_drag(track(n=5, minutes=2, courses=WANDERING), [CABLE]) == []


def test_too_few_fixes_even_over_a_long_window():
    assert find_anchor_drag(track(n=4, minutes=20, courses=WANDERING), [CABLE]) == []


def test_episode_is_cut_when_the_ship_speeds_up_and_resumes():
    slow_before = track(n=8, courses=WANDERING)
    fast_gap = [ShipFix("123456789", T0 + timedelta(minutes=40), 59.9, 24.99, 14.0, 90.0)]
    slow_after = [ShipFix("123456789", T0 + timedelta(minutes=45 + 5 * i), 59.9, 24.99, 3.0,
                          WANDERING[i % len(WANDERING)]) for i in range(8)]

    alerts = find_anchor_drag(slow_before + fast_gap + slow_after, [CABLE])
    assert len(alerts) == 2
    assert alerts[0].ended_at < fast_gap[0].ts < alerts[1].started_at


def test_missing_speed_breaks_the_episode_rather_than_being_guessed():
    fixes = track(n=8, courses=WANDERING)
    without_speed = [f if i != 4 else ShipFix(f.mmsi, f.ts, f.lat, f.lon, None, f.cog) for i, f in enumerate(fixes)]
    # Two runs of four fixes each, so neither reaches min_fixes.
    assert find_anchor_drag(without_speed, [CABLE]) == []


def test_rules_are_configurable():
    quiet = track(courses=[90.0, 95.0, 85.0, 92.0])
    assert find_anchor_drag(quiet, [CABLE]) == []
    assert find_anchor_drag(quiet, [CABLE], AnchorRules(min_course_spread_deg=1.0))


def test_score_rises_with_closeness_and_erratic_course():
    close = find_anchor_drag(track(lon=25.0, courses=WANDERING), [CABLE])[0]
    further = find_anchor_drag(track(lon=24.975, courses=WANDERING), [CABLE])[0]
    assert close.score > further.score
    assert 0.0 < further.score <= 1.0


def test_no_cables_means_no_alerts():
    assert find_anchor_drag(track(courses=WANDERING), []) == []


def test_empty_track_is_handled():
    assert find_anchor_drag([], [CABLE]) == []


class TestCourseSpread:
    def test_steady_course_is_near_zero(self):
        assert course_spread_deg([90.0, 91.0, 89.0, 90.0]) < 2

    def test_wrapping_around_north_is_not_treated_as_a_turn(self):
        # 359 and 1 degrees are two degrees apart, not 358.
        assert course_spread_deg([359.0, 1.0, 0.0, 358.0]) < 5

    def test_scattered_courses_score_high(self):
        assert course_spread_deg([0.0, 90.0, 180.0, 270.0]) > 60

    def test_single_or_empty_input(self):
        assert course_spread_deg([]) == 0.0
        assert course_spread_deg([42.0]) == 0.0


def test_bearing_helper():
    assert bearing_deg(0.0, 0.0, 1.0, 0.0) == pytest.approx(0.0, abs=0.1)
    assert bearing_deg(0.0, 0.0, 0.0, 1.0) == pytest.approx(90.0, abs=0.1)
